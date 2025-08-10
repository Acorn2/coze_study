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
    
    def load_cookies(self, cookie_path: str | None):
        """加载cookies文件 - 支持多种格式"""
        if not cookie_path:
            self.log("未提供cookies文件路径")
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
    
    async def scrape_comments(self, url: str, cookies_path: str = None, max_scrolls: int = 30):
        """爬取指定URL的评论"""
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
                
                # 加载cookies
                cookies = self.load_cookies(cookies_path)
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

def main():
    """主函数"""
    # 配置参数
    config = {
        "url": "https://www.xiaohongshu.com/discovery/item/68982712000000002500d698?source=webshare&xhsshare=pc_web&xsec_token=ABQ8B9Q9MRNQCx1O5MA3-xNhA3h96U30ZFxvX5eWKkGtQ=&xsec_source=pc_share",
        "output_file": "/Users/ankanghao/AiProjects/coze_study/xhs/code/comments_data_with_cookies.json",
        "cookies_path": "/Users/ankanghao/AiProjects/coze_study/xhs/code/cookies_template.json",  # 设置cookies文件路径
        "headless": False,     # 非无头模式，方便观察
        "max_scrolls": 20,     # 减少滚动次数用于调试
        "debug": True          # 启用调试模式
    }
    
    print("=" * 60)
    print("🔥 小红书评论爬取工具 (Cookies版)")
    print("=" * 60)
    print(f"目标URL: {config['url']}")
    print(f"输出文件: {config['output_file']}")
    print(f"Cookies文件: {config['cookies_path']}")
    print(f"调试模式: {config['debug']}")
    print(f"无头模式: {config['headless']}")
    print("=" * 60)
    
    # 检查cookies文件是否存在
    if not os.path.exists(config['cookies_path']):
        print(f"❌ Cookies文件不存在: {config['cookies_path']}")
        print("\n📋 获取Cookies的步骤:")
        print("1. 运行 cookie_extractor.py 脚本")
        print("2. 或者手动从浏览器导出cookies")
        print("3. 将cookies保存为JSON格式")
        return
    
    # 创建爬取器实例
    scraper = XHSCommentScraper(
        headless=config["headless"], 
        debug=config["debug"]
    )
    
    try:
        # 执行爬取
        comments = asyncio.run(scraper.scrape_comments(
            url=config["url"],
            cookies_path=config["cookies_path"],
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
            print("1. 检查cookies是否有效和完整")
            print("2. 重新获取最新的cookies")
            print("3. 检查生成的截图文件了解页面状态")
            print("4. 确认笔记URL是否正确且可访问")
    
    except Exception as e:
        print(f"❌ 程序执行失败: {e}")

if __name__ == "__main__":
    main() 