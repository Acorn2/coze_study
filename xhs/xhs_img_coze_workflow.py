import re
from urllib.parse import urlsplit, urlunsplit, quote
from typing import Dict, Any, TypedDict
import asyncio


class Args(TypedDict):
    params: Dict[str, Any]


class Output(TypedDict):
    pngUrl: str
    jpgUrl: str


def _derive_basename_from_path(path: str) -> str:
    """
    从 URL 路径最后一段中提取基名：
    - 优先取 '!' 之前的部分作为基名
    - 若不存在 '!'，使用整段文件名
    """
    last = path.rsplit('/', 1)[-1]
    if '!' in last:
        return last.split('!', 1)[0]
    return last


def _normalize_fmt(fmt: str) -> str:
    fmt = fmt.lower().strip()
    if fmt == 'jpeg':
        # 强制标准化为 'jpg'
        return 'jpg'
    if fmt not in ('jpg', 'png'):
        raise ValueError("fmt 仅支持 'jpg' 或 'png'")
    return fmt


def _set_format_in_query(query: str, fmt: str) -> str:
    """
    在原有查询串中，确保存在 imageMogr2，并将/追加到 format/{fmt}。
    不使用 urlencode，避免把 'imageMogr2/...' 结构转义为 key=value。
    """
    parts = [p for p in query.split('&') if p] if query else []

    # 找 imageMogr2 段（它不是 key=value，而是单一段 'imageMogr2/...'）
    idx = next((i for i, p in enumerate(parts) if p.startswith('imageMogr2')), None)
    if idx is None:
        parts.append(f'imageMogr2/format/{fmt}')
    else:
        seg = parts[idx]
        if '/format/' in seg:
            seg = re.sub(r'/format/[^/&?]*', f'/format/{fmt}', seg, count=1)
        else:
            seg = seg.rstrip('/') + f'/format/{fmt}'
        parts[idx] = seg

    return '&'.join(parts)


def _set_attname_in_query(query: str, filename: str) -> str:
    """
    在查询串中设置/替换 attname=，并对文件名进行 URL 编码。
    """
    parts = [p for p in query.split('&') if p] if query else []
    encoded = 'attname=' + quote(filename, safe='')

    replaced = False
    for i, p in enumerate(parts):
        if p.startswith('attname='):
            parts[i] = encoded
            replaced = True
            break
    if not replaced:
        parts.append(encoded)
    return '&'.join(parts)


def convert_url(url: str, fmt: str, filename: str | None = None) -> str:
    """
    基于原始 URL，返回指定格式（png/jpg）且下载名与后缀一致的可访问 URL。
    - 不修改路径中的样式段（如 '!nd_dft_wlteh_jpg_3'），避免 403。
    - 在查询串中追加/替换 'imageMogr2/format/{fmt}'。
    - 设置 'attname=<期望文件名.后缀>'，确保保存名与实际格式一致。
    """
    fmt = _normalize_fmt(fmt)
    sp = urlsplit(url)

    # 生成合适的文件名
    base = _derive_basename_from_path(sp.path)
    expect_name = f"{base}.{fmt}" if not filename else filename

    # 处理查询串：设置/替换 format，再设置/替换 attname
    q1 = _set_format_in_query(sp.query, fmt)
    q2 = _set_attname_in_query(q1, expect_name)

    return urlunsplit((sp.scheme, sp.netloc, sp.path, q2, sp.fragment))


def to_png(url: str, filename: str | None = None) -> str:
    return convert_url(url, 'png', filename)


def to_jpg(url: str, filename: str | None = None) -> str:
    return convert_url(url, 'jpg', filename)


async def main(args: Args) -> Output:
    """
    Coze 工作流主函数：处理小红书图片URL转换
    
    预期输入参数：
    - url: 原始图片URL
    - custom_filename: 可选的自定义文件名
    """
    params = args['params']
    
    # 获取输入参数
    original_url = params.get('url', '')
    custom_filename = params.get('custom_filename', None)
    
    if not original_url:
        raise ValueError("必须提供 url 参数")
    
    # 构建输出对象
    ret: Output = {
        "pngUrl": to_png(original_url, custom_filename),  # PNG格式URL
        "jpgUrl": to_jpg(original_url, custom_filename),  # JPG格式URL
    }
    
    return ret


if __name__ == "__main__":
    # 测试示例 - 使用 async main 作为入口
    async def test_main():
        test_url = "https://sns-webpic-qc.xhscdn.com/202508081203/37ef76c1b643207bc131f3c54d95b607/notes_pre_post/1040g3k031kssdadd30005oujaj4ptcu7pvcpuh0!nd_dft_wlteh_jpg_3"
        
        # 正确构造 Args 类型的参数
        args: Args = {
            'params': {
                'url': test_url,
                'custom_filename': None
            }
        }
        
        result = await main(args)
        
        print("=== Coze 工作流输出结果 ===")
        print(f"PNG URL: {result['pngUrl']}")
        print(f"JPG URL: {result['jpgUrl']}")
    
    # 运行异步测试
    asyncio.run(test_main()) 