import re
import os
import json
import time
import asyncio
from datetime import datetime
from playwright.async_api import async_playwright

class XHSCommentScraper:
    """小红书评论爬取器"""
    
    def __init__(self, headless=True, timeout=30, debug=True):
        self.headless = headless
        self.timeout = timeout
        self.debug = debug
        self.user_agent = (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    
    def log(self, message, level="INFO"):
        """调试日志输出"""
        if self.debug:
            timestamp = datetime.now().strftime("%H:%M:%S")
            print(f"[{timestamp}] {level}: {message}")
    
    def extract_note_id(self, url: str) -> str | None:
        """从URL中提取笔记ID"""
        match = re.search(r"/item/([a-z0-9]+)", url)
        note_id = match.group(1) if match else None
        self.log(f"提取笔记ID: {note_id}")
        return note_id
    
    def parse_cookie_string(self, cookie_string: str):
        """解析cookie字符串格式，转换为Playwright可用的cookie对象数组"""
        if not cookie_string:
            self.log("Cookie字符串为空", "ERROR")
            return None
        
        self.log("开始解析Cookie字符串...")
        
        # 分割cookie字符串
        cookie_pairs = [pair.strip() for pair in cookie_string.split(';') if pair.strip()]
        
        valid_cookies = []
        for pair in cookie_pairs:
            if '=' not in pair:
                continue
                
            name, value = pair.split('=', 1)
            name = name.strip()
            value = value.strip()
            
            # 创建cookie对象
            cookie = {
                "name": name,
                "value": value,
                "domain": ".xiaohongshu.com",
                "path": "/",
                "httpOnly": False,
                "secure": True,
                "sameSite": "Lax"
            }
            
            # 设置特殊属性 - 根据小红书的实际cookie特性
            if name in ['web_session', 'a1', 'websectiga']:
                cookie["httpOnly"] = True
            
            # 设置过期时间（24小时后）
            import time
            expires_timestamp = int(time.time()) + (24 * 60 * 60)
            cookie["expires"] = expires_timestamp
            
            valid_cookies.append(cookie)
            
            # 记录重要cookie信息
            if name in ['a1', 'web_session', 'webId', 'xsecappid', 'websectiga', 'sec_poison_id']:
                value_preview = value[:20] + "..." if len(value) > 20 else value
                self.log(f"  解析到重要cookie: {name} = {value_preview}")
        
        self.log(f"成功解析 {len(valid_cookies)} 个cookies")
        return valid_cookies

    def load_cookies_from_string(self, cookie_string: str):
        """从cookie字符串加载cookies"""
        try:
            return self.parse_cookie_string(cookie_string)
        except Exception as e:
            self.log(f"解析cookie字符串失败: {e}", "ERROR")
            return None

    def load_cookies(self, cookie_path: str | None = None, cookie_string: str = None):
        """加载cookies - 支持文件路径或直接的cookie字符串"""
        
        # 优先使用cookie字符串
        if cookie_string:
            self.log("使用提供的Cookie字符串")
            return self.load_cookies_from_string(cookie_string)
        
        # 如果没有cookie字符串，使用原有的文件加载逻辑
        if not cookie_path:
            self.log("未提供cookies文件路径或cookie字符串")
            return None
            
        if not os.path.exists(cookie_path):
            self.log(f"Cookies文件不存在: {cookie_path}")
            return None
            
        try:
            with open(cookie_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # 支持多种cookies格式
            cookies = None
            if isinstance(data, list):
                # 直接是cookie数组
                cookies = data
            elif isinstance(data, dict):
                if "cookies" in data:
                    # {cookies: [...]} 格式
                    cookies = data["cookies"]
                elif "value" in data or "name" in data:
                    # 单个cookie对象，转换为数组
                    cookies = [data]
                else:
                    # 可能是其他格式，尝试找到cookies字段
                    for key, value in data.items():
                        if isinstance(value, list) and len(value) > 0 and "name" in value[0]:
                            cookies = value
                            break
            
            if not cookies:
                self.log("cookies格式不正确或为空", "ERROR")
                return None
            
            # 验证cookies格式
            valid_cookies = []
            for cookie in cookies:
                if isinstance(cookie, dict) and "name" in cookie and "value" in cookie:
                    # 确保必要的字段存在
                    if "domain" not in cookie:
                        cookie["domain"] = ".xiaohongshu.com"
                    if "path" not in cookie:
                        cookie["path"] = "/"
                    
                    # 🔧 添加过期时间（设置为24小时后过期）
                    if "expires" not in cookie and "maxAge" not in cookie:
                        import time
                        expires_timestamp = int(time.time()) + (24 * 60 * 60)  # 24小时
                        cookie["expires"] = expires_timestamp
                    
                    valid_cookies.append(cookie)
            
            self.log(f"成功加载 {len(valid_cookies)} 个有效cookies")
            
            # 显示重要cookies信息
            important_names = ['web_session', 'a1', 'webId', 'xsecappid']
            for cookie in valid_cookies:
                if cookie['name'] in important_names:
                    value_preview = cookie['value'][:20] + "..." if len(cookie['value']) > 20 else cookie['value']
                    self.log(f"  - {cookie['name']}: {value_preview}")
            
            return valid_cookies
            
        except Exception as e:
            self.log(f"加载cookies失败: {e}", "ERROR")
            return None
    
    async def check_login_status(self, page):
        """检查登录状态"""
        self.log("检查登录状态...")
        
        try:
            # 等待页面加载
            await page.wait_for_timeout(2000)
            
            # 检查是否有登录相关的元素
            login_indicators = [
                "text=登录", "text=注册", "text=立即登录",
                "[data-testid*='login']", "[class*='login']"
            ]
            
            has_login_button = False
            for indicator in login_indicators:
                try:
                    element = await page.query_selector(indicator)
                    if element and await element.is_visible():
                        has_login_button = True
                        break
                except:
                    continue
            
            # 检查当前URL
            current_url = page.url
            is_login_page = any(keyword in current_url.lower() for keyword in ['login', 'signin', 'register'])
            
            # 检查页面内容
            page_text = await page.evaluate("document.body.textContent")
            has_login_text = any(keyword in page_text for keyword in ['请登录', '登录', '注册'])
            
            if has_login_button or is_login_page or has_login_text:
                self.log("❌ 检测到未登录状态", "WARNING")
                self.log(f"   当前URL: {current_url}")
                self.log(f"   登录按钮: {has_login_button}")
                self.log(f"   登录页面: {is_login_page}")
                return False
            else:
                self.log("✅ 已登录状态")
                return True
                
        except Exception as e:
            self.log(f"检查登录状态时出错: {e}", "ERROR")
            return False
    
    async def analyze_page_structure(self, page):
        """分析页面结构，帮助调试"""
        self.log("开始分析页面结构...")
        
        # 获取页面基本信息
        title = await page.title()
        url = page.url
        self.log(f"页面标题: {title}")
        self.log(f"当前URL: {url}")
        
        # 检查页面是否完全加载
        ready_state = await page.evaluate("document.readyState")
        self.log(f"页面加载状态: {ready_state}")
        
        # 分析页面中包含"评论"相关的元素
        analysis_js = """
        (() => {
            const info = {
                totalElements: document.querySelectorAll('*').length,
                commentKeywords: [],
                possibleCommentContainers: [],
                textContent: document.body.textContent.length,
                hasLoginButton: false,
                hasCommentSection: false,
                pageContent: document.body.textContent.substring(0, 500)
            };
            
            // 查找包含评论关键词的元素
            const keywords = ['评论', 'comment', '回复', 'reply', '点赞', 'like'];
            keywords.forEach(keyword => {
                const elements = Array.from(document.querySelectorAll('*')).filter(el => {
                    return el.textContent && el.textContent.toLowerCase().includes(keyword.toLowerCase());
                });
                if (elements.length > 0) {
                    info.commentKeywords.push({
                        keyword: keyword,
                        count: elements.length,
                        samples: elements.slice(0, 3).map(el => ({
                            tagName: el.tagName,
                            className: el.className,
                            textContent: el.textContent.substring(0, 100)
                        }))
                    });
                }
            });
            
            // 查找可能的评论容器
            const containerSelectors = [
                '[class*="comment"]', '[id*="comment"]',
                '[class*="Comment"]', '[id*="Comment"]',
                'section', 'div[class*="list"]',
                '[data-testid*="comment"]',
                '[class*="interaction"]', '[class*="note-detail"]'
            ];
            
            containerSelectors.forEach(selector => {
                try {
                    const elements = document.querySelectorAll(selector);
                    if (elements.length > 0) {
                        info.possibleCommentContainers.push({
                            selector: selector,
                            count: elements.length,
                            samples: Array.from(elements).slice(0, 2).map(el => ({
                                tagName: el.tagName,
                                className: el.className,
                                id: el.id,
                                textLength: el.textContent ? el.textContent.length : 0
                            }))
                        });
                    }
                } catch (e) {}
            });
            
            // 检查是否有登录相关元素
            const loginKeywords = ['登录', 'login', '登陆', 'sign in', '请登录'];
            loginKeywords.forEach(keyword => {
                const loginElements = Array.from(document.querySelectorAll('*')).filter(el => {
                    return el.textContent && el.textContent.toLowerCase().includes(keyword.toLowerCase());
                });
                if (loginElements.length > 0) {
                    info.hasLoginButton = true;
                }
            });
            
            // 检查是否有评论区域
            const commentSections = document.querySelectorAll('[class*="comment"], [id*="comment"]');
            info.hasCommentSection = commentSections.length > 0;
            
            return info;
        })();
        """
        
        try:
            analysis = await page.evaluate(analysis_js)
            
            self.log(f"页面总元素数: {analysis['totalElements']}")
            self.log(f"页面文本长度: {analysis['textContent']}")
            self.log(f"是否检测到登录按钮: {analysis['hasLoginButton']}")
            self.log(f"是否检测到评论区域: {analysis['hasCommentSection']}")
            
            # 显示页面内容预览
            self.log(f"页面内容预览: {analysis.get('pageContent', '')[:200]}...")
            
            self.log("评论关键词分析:")
            for item in analysis['commentKeywords']:
                self.log(f"  - '{item['keyword']}': {item['count']} 个元素")
                for sample in item['samples']:
                    self.log(f"    * {sample['tagName']}.{sample['className']}: {sample['textContent'][:50]}...")
            
            self.log("可能的评论容器:")
            for container in analysis['possibleCommentContainers']:
                self.log(f"  - {container['selector']}: {container['count']} 个元素")
                for sample in container['samples']:
                    self.log(f"    * {sample['tagName']}.{sample['className']} (文本长度: {sample['textLength']})")
            
            return analysis
            
        except Exception as e:
            self.log(f"页面结构分析失败: {e}", "ERROR")
            return None
    
    async def scroll_and_load_comments(self, page, max_rounds=30, sleep_sec=2.0):
        """滚动页面并加载更多评论"""
        self.log("开始滚动加载评论...")
        last_height = 0
        stable_rounds = 0
        
        for round_num in range(max_rounds):
            self.log(f"第 {round_num + 1}/{max_rounds} 轮滚动")
            
            # 获取当前页面高度
            curr_height = await page.evaluate("document.body.scrollHeight")
            self.log(f"当前页面高度: {curr_height}")
            
            # 滚动到页面底部
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(int(sleep_sec * 1000))
            
            # 尝试点击各种"加载更多"按钮
            load_more_texts = [
                "展开更多评论", "查看全部评论", "加载更多", "更多评论", 
                "展开", "更多", "查看更多", "点击查看全部评论", "显示更多评论"
            ]
            
            clicked_button = False
            for text in load_more_texts:
                try:
                    # 查找并点击按钮
                    buttons = await page.query_selector_all(f"text={text}")
                    for button in buttons:
                        if await button.is_visible():
                            await button.click(timeout=2000)
                            self.log(f"点击了'{text}'按钮")
                            await page.wait_for_timeout(1000)
                            clicked_button = True
                            break
                    if clicked_button:
                        break
                except Exception as e:
                    self.log(f"点击'{text}'按钮失败: {e}", "DEBUG")
                    continue
            
            # 检查页面高度变化
            new_height = await page.evaluate("document.body.scrollHeight")
            self.log(f"滚动后页面高度: {new_height}")
            
            if new_height == curr_height == last_height:
                stable_rounds += 1
                self.log(f"页面高度无变化 (连续 {stable_rounds} 轮)")
                if stable_rounds >= 3:  # 连续3轮无变化就停止
                    self.log("页面高度无变化，停止滚动")
                    break
            else:
                stable_rounds = 0
                last_height = new_height
        
        self.log("滚动加载完成")
    
    async def extract_comments(self, page):
        """提取评论数据"""
        self.log("开始提取评论数据...")
        
        # 增强的JavaScript代码用于提取评论
        js_code = """
        (() => {
            const debugInfo = {
                searchResults: [],
                finalComments: [],
                errors: []
            };
            
            // 尝试多种评论选择器
            const selectors = [
                '[class*="comment"]',
                '[class*="Comment"]', 
                '[data-testid*="comment"]',
                '.comment-item',
                '.comment-list .comment',
                '[class*="note-comment"]',
                '[class*="NoteComment"]',
                '[class*="feed-comment"]',
                '[class*="user-comment"]',
                '[class*="interaction"]'
            ];
            
            let commentElements = [];
            
            // 尝试每个选择器并记录结果
            for (const selector of selectors) {
                try {
                    const elements = document.querySelectorAll(selector);
                    debugInfo.searchResults.push({
                        selector: selector,
                        found: elements.length,
                        samples: Array.from(elements).slice(0, 2).map(el => ({
                            tagName: el.tagName,
                            className: el.className,
                            textLength: el.textContent ? el.textContent.length : 0,
                            textPreview: el.textContent ? el.textContent.substring(0, 50) : ''
                        }))
                    });
                    
                    if (elements.length > 0) {
                        commentElements = Array.from(elements);
                        break;
                    }
                } catch (e) {
                    debugInfo.errors.push(`选择器 ${selector} 出错: ${e.message}`);
                }
            }
            
            // 如果没找到特定选择器，尝试通过文本特征查找
            if (commentElements.length === 0) {
                console.log('使用文本特征查找评论...');
                const allElements = document.querySelectorAll('div, section, article, span, p');
                const candidateElements = Array.from(allElements).filter(el => {
                    const text = el.textContent || '';
                    const className = el.className || '';
                    
                    // 更宽泛的匹配条件
                    return (
                        text.length > 5 && text.length < 2000 && // 合理的评论长度范围
                        (className.toLowerCase().includes('comment') ||
                         text.includes('回复') || text.includes('点赞') ||
                         text.includes('❤️') || text.includes('👍') ||
                         text.includes('分钟前') || text.includes('小时前') ||
                         text.includes('天前') || text.includes('刚刚'))
                    );
                });
                
                commentElements = candidateElements;
                debugInfo.searchResults.push({
                    selector: 'text-feature-based',
                    found: candidateElements.length,
                    samples: candidateElements.slice(0, 5).map(el => ({
                        tagName: el.tagName,
                        className: el.className,
                        textLength: el.textContent ? el.textContent.length : 0,
                        textPreview: el.textContent ? el.textContent.substring(0, 50) : ''
                    }))
                });
            }
            
            // 提取评论信息
            const comments = [];
            commentElements.forEach((element, index) => {
                try {
                    const textContent = element.textContent?.trim() || '';
                    
                    // 过滤条件更加宽松
                    if (textContent.length < 2 || 
                        textContent.includes('展开更多') ||
                        textContent.includes('查看全部') ||
                        textContent === '评论' ||
                        textContent === '点赞' ||
                        textContent === '回复' ||
                        textContent.includes('登录') ||
                        textContent.includes('注册')) {
                        return;
                    }
                    
                    // 尝试提取用户名
                    let username = '';
                    const userSelectors = '[class*="user"], [class*="name"], [class*="author"], [class*="nick"]';
                    const userElements = element.querySelectorAll(userSelectors);
                    if (userElements.length > 0) {
                        username = userElements[0].textContent?.trim() || '';
                    }
                    
                    // 尝试提取时间
                    let timestamp = '';
                    const timeSelectors = '[class*="time"], time, [datetime], [class*="date"]';
                    const timeElements = element.querySelectorAll(timeSelectors);
                    if (timeElements.length > 0) {
                        timestamp = timeElements[0].textContent?.trim() || 
                                   timeElements[0].getAttribute('datetime') || '';
                    }
                    
                    // 尝试提取点赞数
                    let likeCount = 0;
                    const likeSelectors = '[class*="like"], [class*="heart"], [class*="thumb"]';
                    const likeElements = element.querySelectorAll(likeSelectors);
                    for (const likeEl of likeElements) {
                        const likeText = likeEl.textContent?.trim() || '';
                        const match = likeText.match(/\d+/);
                        if (match) {
                            likeCount = parseInt(match[0]);
                            break;
                        }
                    }
                    
                    const comment = {
                        id: `comment_${index}_${Date.now()}`,
                        content: textContent,
                        username: username,
                        timestamp: timestamp,
                        like_count: likeCount,
                        element_class: element.className || '',
                        element_tag: element.tagName,
                        element_id: element.id || '',
                        extracted_at: new Date().toISOString()
                    };
                    
                    comments.push(comment);
                    
                } catch (error) {
                    debugInfo.errors.push(`提取评论 ${index} 时出错: ${error.message}`);
                }
            });
            
            // 去重（基于内容）
            const uniqueComments = [];
            const seenContent = new Set();
            
            for (const comment of comments) {
                const contentKey = comment.content.substring(0, 30); // 使用前30个字符作为去重依据
                if (!seenContent.has(contentKey) && comment.content.length > 3) {
                    seenContent.add(contentKey);
                    uniqueComments.push(comment);
                }
            }
            
            debugInfo.finalComments = uniqueComments;
            
            return {
                comments: uniqueComments,
                debug: debugInfo
            };
        })();
        """
        
        try:
            result = await page.evaluate(js_code)
            comments = result['comments']
            debug_info = result['debug']
            
            # 输出详细的调试信息
            self.log(f"选择器搜索结果:")
            for search in debug_info['searchResults']:
                self.log(f"  - {search['selector']}: 找到 {search['found']} 个元素")
                for sample in search['samples']:
                    self.log(f"    * {sample['tagName']}.{sample['className']}: '{sample['textPreview']}'...")
            
            if debug_info['errors']:
                self.log("提取过程中的错误:")
                for error in debug_info['errors']:
                    self.log(f"  - {error}", "ERROR")
            
            self.log(f"成功提取到 {len(comments)} 条评论")
            
            # 显示前几条评论的详细信息
            if comments:
                self.log("前3条评论详情:")
                for i, comment in enumerate(comments[:3], 1):
                    self.log(f"  评论 {i}:")
                    self.log(f"    用户: {comment.get('username', '未知')}")
                    self.log(f"    内容: {comment['content'][:100]}...")
                    self.log(f"    元素类型: {comment.get('element_tag', 'unknown')}")
                    self.log(f"    CSS类: {comment.get('element_class', 'none')}")
            
            return comments
            
        except Exception as e:
            self.log(f"提取评论时出错: {e}", "ERROR")
            return []
    
    async def take_screenshot(self, page, filename):
        """截图保存用于调试"""
        try:
            screenshot_path = f"/Users/ankanghao/AiProjects/coze_study/xhs/{filename}"
            await page.screenshot(path=screenshot_path, full_page=True)
            self.log(f"截图已保存: {screenshot_path}")
        except Exception as e:
            self.log(f"截图失败: {e}", "ERROR")
    
    async def scrape_comments(self, url: str, cookies_path: str = None, cookie_string: str = None, max_scrolls: int = 30):
        """爬取指定URL的评论 - 支持cookie文件或直接的cookie字符串"""
        try:
            async with async_playwright() as playwright:
                self.log("正在启动浏览器...")
                browser = await playwright.chromium.launch(
                    headless=self.headless,
                    args=['--no-sandbox', '--disable-blink-features=AutomationControlled']
                )
                
                context = await browser.new_context(
                    user_agent=self.user_agent,
                    viewport={'width': 1280, 'height': 900},
                    locale='zh-CN'
                )
                
                # 加载cookies - 优先使用cookie字符串
                cookies = self.load_cookies(cookies_path, cookie_string)
                if cookies:
                    try:
                        await context.add_cookies(cookies)
                        self.log("✅ 已成功导入cookies")
                    except Exception as e:
                        self.log(f"❌ 导入cookies失败: {e}", "ERROR")
                        self.log("   继续尝试无cookies访问...")
                
                page = await context.new_page()
                page.set_default_timeout(self.timeout * 1000)
                
                self.log(f"正在访问页面: {url}")
                await page.goto(url, wait_until="domcontentloaded")
                
                # 等待页面加载
                self.log("等待页面加载...")
                await page.wait_for_timeout(3000)
                
                # 检查登录状态
                is_logged_in = await self.check_login_status(page)
                if not is_logged_in:
                    self.log("❌ 未检测到登录状态，可能需要有效的cookies", "WARNING")
                
                # 分析页面结构
                await self.analyze_page_structure(page)
                
                # 截图保存当前状态
                await self.take_screenshot(page, "page_initial.png")
                
                # 滚动加载更多评论
                await self.scroll_and_load_comments(page, max_rounds=max_scrolls)
                
                # 截图保存滚动后状态
                await self.take_screenshot(page, "page_after_scroll.png")
                
                # 提取评论数据
                comments = await self.extract_comments(page)
                
                await context.close()
                await browser.close()
                
                return comments
                
        except Exception as e:
            self.log(f"爬取过程中出错: {e}", "ERROR")
            return []
    
    def save_comments(self, comments, output_file, url):
        """保存评论数据到文件"""
        note_id = self.extract_note_id(url)
        
        result_data = {
            "note_id": note_id,
            "url": url,
            "scraped_at": datetime.now().isoformat(),
            "comment_count": len(comments),
            "comments": comments,
            "scraper_version": "v2.1_with_cookies"
        }
        
        # 确保输出目录存在
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        
        # 保存为JSON格式
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(result_data, f, ensure_ascii=False, indent=2)
        
        self.log(f"成功保存 {len(comments)} 条评论到: {output_file}")
        
        # 同时保存一个纯文本版本方便查看
        txt_file = output_file.replace('.json', '.txt')
        with open(txt_file, "w", encoding="utf-8") as f:
            f.write(f"小红书笔记评论 - {note_id}\n")
            f.write(f"URL: {url}\n")
            f.write(f"爬取时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"评论总数: {len(comments)}\n")
            f.write("=" * 50 + "\n\n")
            
            for i, comment in enumerate(comments, 1):
                f.write(f"{i}. {comment.get('username', '匿名用户')}\n")
                f.write(f"   时间: {comment.get('timestamp', '未知')}\n")
                f.write(f"   内容: {comment['content']}\n")
                f.write(f"   点赞: {comment.get('like_count', 0)}\n")
                f.write(f"   元素信息: {comment.get('element_tag', 'unknown')}.{comment.get('element_class', 'none')}\n")
                f.write("-" * 30 + "\n")
        
        self.log(f"同时保存文本版本到: {txt_file}")

import json
import asyncio
from playwright.async_api import async_playwright

class XHSCookieExtractor:
    """小红书Cookie提取工具"""
    
    def __init__(self):
        self.user_agent = (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    
    async def extract_cookies_manual(self, output_file="xhs_cookies.json"):
        """手动登录并提取cookies"""
        print("🍪 小红书Cookie提取工具")
        print("=" * 50)
        print("请按照以下步骤操作：")
        print("1. 浏览器将自动打开小红书网站")
        print("2. 请手动登录你的小红书账号")
        print("3. 登录成功后，在终端按回车键继续")
        print("4. 工具将自动提取并保存cookies")
        print("=" * 50)
        
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=False)  # 非无头模式
            context = await browser.new_context(
                user_agent=self.user_agent,
                viewport={'width': 1280, 'height': 900}
            )
            page = await context.new_page()
            
            # 访问小红书登录页面
            print("正在打开小红书网站...")
            await page.goto("https://www.xiaohongshu.com")
            
            # 等待用户手动登录
            input("请在浏览器中完成登录，然后按回车键继续...")
            
            # 检查是否已登录
            try:
                # 等待页面加载完成
                await page.wait_for_timeout(2000)
                
                # 检查当前URL和页面内容
                current_url = page.url
                print(f"当前页面URL: {current_url}")
                
                # 提取所有cookies
                cookies = await context.cookies()
                
                if cookies:
                    # 过滤重要的cookies
                    important_cookies = []
                    important_names = ['web_session', 'a1', 'webId', 'xsecappid', 'websectiga', 'sec_poison_id']
                    
                    for cookie in cookies:
                        if any(name in cookie['name'] for name in important_names) or cookie['name'] in important_names:
                            important_cookies.append(cookie)
                    
                    # 保存完整cookies
                    full_output = output_file
                    with open(full_output, 'w', encoding='utf-8') as f:
                        json.dump(cookies, f, indent=2, ensure_ascii=False)
                    
                    # 保存重要cookies
                    important_output = output_file.replace('.json', '_important.json')
                    with open(important_output, 'w', encoding='utf-8') as f:
                        json.dump(important_cookies, f, indent=2, ensure_ascii=False)
                    
                    print(f"✅ 成功提取到 {len(cookies)} 个cookies")
                    print(f"✅ 完整cookies保存到: {full_output}")
                    print(f"✅ 重要cookies保存到: {important_output}")
                    
                    # 显示重要cookies信息
                    print("\n🔑 重要cookies信息:")
                    for cookie in important_cookies:
                        print(f"  - {cookie['name']}: {cookie['value'][:20]}...")
                    
                    return cookies
                else:
                    print("❌ 未能获取到cookies，请确保已正确登录")
                    return None
                    
            except Exception as e:
                print(f"❌ 提取cookies时出错: {e}")
                return None
            finally:
                await browser.close()
    
    def validate_cookies(self, cookie_file):
        """验证cookies文件格式"""
        try:
            with open(cookie_file, 'r', encoding='utf-8') as f:
                cookies = json.load(f)
            
            if not isinstance(cookies, list):
                print("❌ Cookies格式错误：应该是数组格式")
                return False
            
            required_fields = ['name', 'value', 'domain']
            for cookie in cookies:
                if not all(field in cookie for field in required_fields):
                    print(f"❌ Cookie缺少必要字段: {cookie}")
                    return False
            
            print(f"✅ Cookies文件格式正确，包含 {len(cookies)} 个cookies")
            return True
            
        except Exception as e:
            print(f"❌ 验证cookies文件失败: {e}")
            return False

async def check_cookies_validity(self, page):
    """检查cookies是否仍然有效"""
    try:
        # 访问需要登录的页面
        await page.goto("https://www.xiaohongshu.com/user/profile/xxx")
        await page.wait_for_timeout(2000)
        
        # 检查是否被重定向到登录页面
        current_url = page.url
        if "login" in current_url.lower() or "signin" in current_url.lower():
            self.log("❌ Cookies已失效，需要重新获取", "WARNING")
            return False
        
        return True
    except:
        return False

async def refresh_cookies_if_needed(self, cookies_path):
    """如果cookies失效，提示重新获取"""
    if not await self.check_cookies_validity(page):
        self.log("🔄 正在尝试重新获取cookies...")
        # 可以调用cookie提取器
        extractor = XHSCookieExtractor()
        new_cookies = await extractor.extract_cookies_manual(cookies_path)
        return new_cookies
    return None

def main():
    """主函数"""
    
    # 🔧 直接在代码中设置Cookie字符串
    COOKIE_STRING = "abRequestId=8c75f667-887e-5974-8c0b-dcfbdd56e64e; webBuild=4.75.3; a1=198943cb50309nhtxwbse0vn7xeg7lgsb4r5wuxkj30000117446; webId=0b39a34b2d77ce7b2aec1f5cb8a1cb9c; gid=yjYj4qSSd8DdyjYj4qSD247C8q8jIx9CEDMdFTV8hIWCd2q8kW1kME888yyW44K8WqDJW804; beaker.session.id=fc9ca6dbec13b48a83bc62ded38519b1250ff462gAJ9cQEoWA4AAAByYS11c2VyLWlkLWFya3ECWBgAAAA2M2JkNzIxZDNkMGQzYzAwMDFmMjkyZjVxA1UIX2V4cGlyZXNxBGNkYXRldGltZQpkYXRldGltZQpxBVUKB+kICw06KwoX/4VScQZYCwAAAGFyay1saWFzLWlkcQdYGAAAADYzYmQ3MzIwMTNmZTVmMDAwMTY1YWZhOXEIWBEAAAByYS1hdXRoLXRva2VuLWFya3EJWEEAAABlYTQxNTViYzUxNjc0MWRiYjY1MzY4Yzk4YjdlMWQ0OS05NzI3YzZlYTBlOTI0NjA4ODhkNjI2ZTQ0MWFiMjMwMXEKVQNfaWRxC1ggAAAAYjU4M2MzOTE4M2ZkNGUwZjk5MTlkNmM4NzVmZWVhMTRxDFgOAAAAX2FjY2Vzc2VkX3RpbWVxDUdB2iYpZOqZqlgOAAAAX2NyZWF0aW9uX3RpbWVxDkdB2iYpZH1wpHUu; xsecappid=xhs-pc-web; loadts=1754838082923; websectiga=59d3ef1e60c4aa37a7df3c23467bd46d7f1da0b1918cf335ee7f2e9e52ac04cf; sec_poison_id=635f1686-381c-4957-bbf3-1b928c77396f"
    
    # 配置参数
    config = {
        "url": "https://www.xiaohongshu.com/discovery/item/68982712000000002500d698?source=webshare&xhsshare=pc_web&xsec_token=ABQ8B9Q9MRNQCx1O5MA3-xNhA3h96U30ZFxvX5eWKkGtQ=&xsec_source=pc_share",
        "output_file": "/Users/ankanghao/AiProjects/coze_study/xhs/code/comments_data_with_cookies.json",
        "cookie_string": COOKIE_STRING,  # 🔧 使用cookie字符串而不是文件路径
        "headless": False,     # 非无头模式，方便观察
        "max_scrolls": 20,     # 减少滚动次数用于调试
        "debug": True          # 启用调试模式
    }
    
    print("=" * 60)
    print("🔥 小红书评论爬取工具 (Cookie字符串版)")
    print("=" * 60)
    print(f"目标URL: {config['url']}")
    print(f"输出文件: {config['output_file']}")
    print(f"Cookie来源: 直接字符串")
    print(f"调试模式: {config['debug']}")
    print(f"无头模式: {config['headless']}")
    print("=" * 60)
    
    # 创建爬取器实例
    scraper = XHSCommentScraper(
        headless=config["headless"], 
        debug=config["debug"]
    )
    
    try:
        # 执行爬取 - 传入cookie字符串
        comments = asyncio.run(scraper.scrape_comments(
            url=config["url"],
            cookie_string=config["cookie_string"],  # 🔧 使用cookie字符串
            max_scrolls=config["max_scrolls"]
        ))
        
        if comments:
            # 保存结果
            scraper.save_comments(comments, config["output_file"], config["url"])
            
            # 打印统计信息
            print("\n📊 爬取统计:")
            print(f"   总评论数: {len(comments)}")
            
            # 显示前5条评论预览
            print("\n📝 评论预览 (前5条):")
            for i, comment in enumerate(comments[:5], 1):
                content = comment['content'][:50] + "..." if len(comment['content']) > 50 else comment['content']
                print(f"   {i}. {comment.get('username', '匿名')}: {content}")
        else:
            print("❌ 未能爬取到任何评论")
            print("\n🔍 调试建议:")
            print("1. 检查cookies字符串是否有效和完整")
            print("2. 重新获取最新的cookies")
            print("3. 检查生成的截图文件了解页面状态")
            print("4. 确认笔记URL是否正确且可访问")
    
    except Exception as e:
        print(f"❌ 程序执行失败: {e}")

if __name__ == "__main__":
    main() 