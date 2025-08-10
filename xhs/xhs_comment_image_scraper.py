import re
import os
import json
import time
import argparse
import asyncio
from urllib.parse import urlparse
from playwright.async_api import async_playwright

def extract_note_id(url: str) -> str | None:
    m = re.search(r"/item/([a-z0-9]+)", url)
    return m.group(1) if m else None

def load_cookies(cookie_path: str | None):
    if not cookie_path:
        return None
    try:
        with open(cookie_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        # 兼容常见导出格式：直接数组或 {cookies: []}
        if isinstance(data, dict) and "cookies" in data:
            return data["cookies"]
        return data if isinstance(data, list) else None
    except Exception as e:
        print(f"加载cookies失败: {e}")
        return None

async def scroll_and_expand(page, max_rounds: int = 20, sleep_sec: float = 1.0):
    last_height = 0
    stable_rounds = 0
    for i in range(max_rounds):
        curr_height = await page.evaluate("document.body.scrollHeight")
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(int(sleep_sec * 1000))

        # 尝试点击"展开更多评论/查看全部/更多"等按钮
        for txt in ["展开更多评论", "查看全部", "更多", "展开", "更多评论"]:
            try:
                btn = page.get_by_text(txt, exact=False).first
                if await btn.is_visible():
                    await btn.click(timeout=1000)
                    await page.wait_for_timeout(500)
            except:
                pass

        new_height = await page.evaluate("document.body.scrollHeight")
        if new_height == curr_height == last_height:
            stable_rounds += 1
            if stable_rounds >= 2:
                break
        else:
            stable_rounds = 0
            last_height = new_height

async def extract_comment_images(page):
    # 优先从疑似"评论区"容器提取
    js = r"""
(() => {
  const urls = new Set();

  const pickUrl = (u) => {
    if (!u) return;
    try {
      const clean = u.split('?')[0];
      if (/(xiaohongshu\.com|xhscdn\.com|sns-img|redcdn)/i.test(clean)) {
        urls.add(clean);
      }
    } catch (e) {}
  };

  const fromImg = (root) => {
    const imgs = root.querySelectorAll('img');
    imgs.forEach(img => {
      const c1 = img.currentSrc || img.src || img.getAttribute('data-src') || "";
      if (c1) pickUrl(c1);
      const srcset = img.srcset || img.getAttribute('srcset');
      if (srcset) {
        const first = srcset.split(',')[0].trim().split(' ')[0];
        pickUrl(first);
      }
    });
  };

  const fromBg = (root) => {
    const all = root.querySelectorAll('*');
    all.forEach(el => {
      const bg = getComputedStyle(el).backgroundImage;
      if (bg && bg.startsWith('url(')) {
        const m = bg.match(/url\(["']?(.*?)["']?\)/);
        if (m && m[1]) pickUrl(m[1]);
      }
    });
  };

  const candidates = [];
  const nodes = Array.from(document.querySelectorAll('section,div,main,article,aside'));
  nodes.forEach(n => {
    const label = (
      (n.getAttribute('aria-label')||'') + ' ' +
      (n.id||'') + ' ' +
      (n.className||'')
    ).toLowerCase();
    const text = (n.textContent||'').slice(0, 200).toLowerCase();
    if (
      label.includes('comment') || label.includes('评论') ||
      text.includes('评论') || text.includes('comment')
    ) {
      candidates.push(n);
    }
  });

  // 如果找不到特定容器，退化为全局扫描
  const scopes = candidates.length ? candidates : [document];

  scopes.forEach(root => { fromImg(root); fromBg(root); });

  return Array.from(urls);
})();
"""
    try:
        urls = await page.evaluate(js)
        return list(dict.fromkeys(urls))  # 去重保序
    except Exception as e:
        print(f"提取图片URL时出错: {e}")
        return []

async def scrape(url: str, cookies_path: str | None = None, headless: bool = True,
                 timeout: int = 25, max_scrolls: int = 20):
    try:
        async with async_playwright() as p:
            print("正在启动浏览器...")
            browser = await p.chromium.launch(headless=headless)
            context_args = dict(
                user_agent=("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/124.0.0.0 Safari/537.36"),
                viewport={'width': 1280, 'height': 900},
                locale='zh-CN',
            )
            context = await browser.new_context(**context_args)

            # 导入登录态（可选）
            cookies = load_cookies(cookies_path)
            if cookies:
                try:
                    await context.add_cookies(cookies)
                    print("已导入cookies")
                except Exception as e:
                    print(f"导入cookies失败: {e}")

            page = await context.new_page()
            page.set_default_timeout(timeout * 1000)

            print("正在访问页面...")
            await page.goto(url, wait_until="load")
            # 等待首屏主要内容
            try:
                await page.wait_for_timeout(1500)
            except:
                pass

            print("正在滚动加载评论...")
            # 滚动加载评论，并尽可能展开更多
            await scroll_and_expand(page, max_rounds=max_scrolls, sleep_sec=1.0)

            print("正在提取图片...")
            # 抽取评论区图片
            imgs = await extract_comment_images(page)

            await context.close()
            await browser.close()
            return imgs
    except Exception as e:
        print(f"抓取过程中出错: {e}")
        return []

def main():
    # 硬编码配置参数
    DEFAULT_TOKEN = "e10adc3949ba59abbe56e057f20f883e"
    
    # 默认配置
    config = {
        "url": "https://www.xiaohongshu.com/discovery/item/68982712000000002500d698?source=webshare&xhsshare=pc_web&xsec_token=ABQ8B9Q9MRNQCx1O5MA3-xNhA3h96U30ZFxvX5eWKkGtQ=&xsec_source=pc_share",
        "out": "xhs/comment_images.json",  # 默认输出文件
        "cookies": None,  # 可手动指定cookies文件路径
        "headless": True,  # 无头模式
        "timeout": 25,  # 超时时间
        "max_scrolls": 20,  # 滚动次数
        "token": DEFAULT_TOKEN
    }
    
    print("=" * 50)
    print("小红书笔记评论区图片抓取工具")
    print("=" * 50)
    print(f"目标URL: {config['url']}")
    print(f"使用Token: {config['token']}")
    print(f"输出文件: {config['out']}")
    print("=" * 50)
    
    try:
        # 执行抓取
        imgs = asyncio.run(scrape(
            url=config["url"],
            cookies_path=config["cookies"],
            headless=config["headless"],
            timeout=config["timeout"],
            max_scrolls=config["max_scrolls"]
        ))
        
        # 保存结果
        if config["out"]:
            # 确保输出目录存在
            output_path = os.path.abspath(config["out"])
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            if config["out"].lower().endswith(".json"):
                # 保存为JSON格式，包含token信息
                result_data = {
                    "token": config["token"],
                    "url": config["url"],
                    "timestamp": time.time(),
                    "image_count": len(imgs),
                    "images": imgs
                }
                with open(output_path, "w", encoding="utf-8") as f:
                    json.dump(result_data, f, ensure_ascii=False, indent=2)
            else:
                # 保存为文本格式
                with open(output_path, "w", encoding="utf-8") as f:
                    f.write(f"# Token: {config['token']}\n")
                    f.write(f"# URL: {config['url']}\n")
                    f.write(f"# Image Count: {len(imgs)}\n\n")
                    f.write("\n".join(imgs))
            
            print(f"✅ 成功保存 {len(imgs)} 条图片URL -> {output_path}")
        else:
            # 直接打印结果
            result = {
                "token": config["token"],
                "url": config["url"],
                "image_count": len(imgs),
                "images": imgs
            }
            print(json.dumps(result, ensure_ascii=False, indent=2))
        
        return imgs
        
    except Exception as e:
        print(f"❌ 程序执行失败: {e}")
        return []

if __name__ == "__main__":
    main()
