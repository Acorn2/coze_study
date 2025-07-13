import json
import re
from datetime import datetime
from typing import Dict, Any, List

async def main(args: Args) -> Output:
    params = args.params
    
    # 获取输入参数 - 现在只需要一个大字符串
    raw_content = params.get('raw_content', '')
    
    def clean_and_format_text(text: str) -> str:
        """清理和格式化混乱的PDF文本"""
        if not text:
            return ""
        
        # 移除多余的换行符和空格
        text = re.sub(r'\n+', ' ', text)
        text = re.sub(r'\s+', ' ', text)
        
        # 处理中文字符间的空格问题
        text = re.sub(r'(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])', '', text)
        
        # 处理英文单词被分割的问题
        text = re.sub(r'(?<=[a-zA-Z])\s+(?=[a-zA-Z])', '', text)
        
        # 处理数字和符号
        text = re.sub(r'(?<=\d)\s+(?=\d)', '', text)
        text = re.sub(r'(?<=[.,;:!?])\s+(?=[\u4e00-\u9fff])', ' ', text)
        
        # 处理特殊符号
        text = re.sub(r'\s*\(\s*', '(', text)
        text = re.sub(r'\s*\)\s*', ')', text)
        text = re.sub(r'\s*\[\s*', '[', text)
        text = re.sub(r'\s*\]\s*', ']', text)
        
        # 处理标点符号
        text = re.sub(r'\s*[。，；：！？]\s*', lambda m: m.group().strip() + ' ', text)
        
        return text.strip()
    
    def extract_key_sections(text: str) -> Dict[str, str]:
        """提取关键章节"""
        sections = {}
        
        # 查找标题模式
        title_patterns = [
            r'(摘要|Abstract)[\s\S]*?(?=关键词|Key\s*words|１|1\s*引言|Introduction)',
            r'(关键词|Key\s*words)[：:\s]*([^\n]*)',
            r'(引言|Introduction)[\s\S]*?(?=２|2\s*|方法|Method)',
            r'(结论|Conclusion|结束语)[\s\S]*?(?=参考文献|References|$)',
        ]
        
        for pattern in title_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                section_name = match.group(1)
                section_content = match.group(0) if len(match.groups()) == 1 else match.group(2)
                sections[section_name] = clean_and_format_text(section_content)
        
        return sections
    
    def generate_summary(text: str) -> str:
        """生成文档摘要"""
        # 寻找摘要部分
        abstract_match = re.search(r'摘要[\s\S]*?(?=关键词|Key)', text)
        if abstract_match:
            return clean_and_format_text(abstract_match.group(0))
        
        # 如果没有找到摘要，取前1000个字符
        cleaned_text = clean_and_format_text(text)
        return cleaned_text[:1000] + "..." if len(cleaned_text) > 1000 else cleaned_text
    
    def extract_key_points(text: str) -> List[str]:
        """提取关键点"""
        key_points = []
        
        # 查找关键词
        keywords_match = re.search(r'关键词[：:\s]*([^\n]*)', text)
        if keywords_match:
            keywords = keywords_match.group(1).split('；')
            key_points.extend([kw.strip() for kw in keywords if kw.strip()])
        
        # 查找编号列表
        numbered_items = re.findall(r'[１-９1-9]\s*[）)]\s*([^１-９1-9）)]*?)(?=[１-９1-9]\s*[）)]|$)', text)
        for item in numbered_items[:5]:  # 最多5个
            cleaned_item = clean_and_format_text(item)
            if len(cleaned_item) > 10 and len(cleaned_item) < 200:
                key_points.append(cleaned_item)
        
        return key_points[:10]  # 最多返回10个关键点
    
    def detect_document_type(text: str) -> str:
        """检测文档类型"""
        if re.search(r'摘要|Abstract|关键词|Key\s*words', text):
            return "学术论文"
        elif re.search(r'第[一二三四五六七八九十]章|Chapter', text):
            return "书籍/报告"
        elif re.search(r'条款|协议|合同', text):
            return "法律文档"
        else:
            return "普通文档"
    
    def create_structured_content(text: str) -> Dict[str, Any]:
        """创建结构化内容"""
        cleaned_text = clean_and_format_text(text)
        sections = extract_key_sections(cleaned_text)
        
        return {
            "original_length": len(text),
            "cleaned_length": len(cleaned_text),
            "document_type": detect_document_type(text),
            "sections": sections,
            "full_content": cleaned_text
        }
    
    # 处理原始内容
    if not raw_content:
        return {
            "formatted_content": {
                "full_text": "",
                "summary": "未提供内容",
                "key_points": []
            },
            "document_structure": {
                "document_type": "未知",
                "sections": {},
                "statistics": {"original_length": 0, "cleaned_length": 0}
            },
            "processing_report": {
                "processed_at": datetime.now().isoformat(),
                "processing_status": "failed",
                "error_message": "输入内容为空"
            },
            "export_formats": {
                "json": "{}",
                "markdown": "# 处理失败\n\n未提供有效内容",
                "plain_text": ""
            }
        }
    
    # 创建结构化内容
    structured_content = create_structured_content(raw_content)
    
    # 生成摘要和关键点
    summary = generate_summary(raw_content)
    key_points = extract_key_points(raw_content)
    
    # 生成统计信息
    stats = {
        "original_length": structured_content["original_length"],
        "cleaned_length": structured_content["cleaned_length"],
        "compression_ratio": round(structured_content["cleaned_length"] / structured_content["original_length"] * 100, 2) if structured_content["original_length"] > 0 else 0,
        "sections_found": len(structured_content["sections"]),
        "key_points_extracted": len(key_points)
    }
    
    # 构建最终输出
    ret: Output = {
        "formatted_content": {
            "full_text": structured_content["full_content"],
            "summary": summary,
            "key_points": key_points
        },
        "document_structure": {
            "document_type": structured_content["document_type"],
            "sections": structured_content["sections"],
            "statistics": stats
        },
        "processing_report": {
            "processed_at": datetime.now().isoformat(),
            "processing_status": "completed",
            "quality_score": min(100, max(0, int(stats["compression_ratio"] * 0.8 + len(key_points) * 5))),
            "recommendations": [
                "文本格式混乱，已进行清理" if stats["compression_ratio"] < 80 else "文本格式良好",
                f"提取到{len(key_points)}个关键点" if key_points else "未能提取关键点",
                f"识别为{structured_content['document_type']}"
            ]
        },
        "export_formats": {
            "json": json.dumps({
                "content": structured_content["full_content"],
                "summary": summary,
                "key_points": key_points,
                "document_type": structured_content["document_type"],
                "processed_at": datetime.now().isoformat()
            }, ensure_ascii=False, indent=2),
            "markdown": f"""# PDF解析结果

## 文档信息
- 文档类型: {structured_content['document_type']}
- 原始长度: {stats['original_length']} 字符
- 清理后长度: {stats['cleaned_length']} 字符
- 压缩率: {stats['compression_ratio']}%

## 内容摘要
{summary}

## 关键点
{chr(10).join([f"- {point}" for point in key_points])}

## 章节内容
{chr(10).join([f"### {title}{chr(10)}{content}{chr(10)}" for title, content in structured_content['sections'].items()])}

## 完整内容
{structured_content['full_content']}
""",
            "plain_text": structured_content["full_content"]
        }
    }
    
    return ret