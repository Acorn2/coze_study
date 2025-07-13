import requests
import PyPDF2
import io
from typing import Dict, Any, List

async def main(args: Args) -> Output:
    params = args.params
    downloaded_pdf_url = params.get('downloaded_pdf_url', '')
    
    def parse_pdf_content(pdf_url: str) -> Dict[str, Any]:
        try:
            # 下载PDF文件
            response = requests.get(pdf_url, timeout=30)
            response.raise_for_status()
            
            # 创建PDF文件对象
            pdf_file = io.BytesIO(response.content)
            pdf_reader = PyPDF2.PdfReader(pdf_file)
            
            # 提取基本信息
            num_pages = len(pdf_reader.pages)
            
            # 提取文本内容
            text_content = ""
            page_contents = []
            
            for page_num, page in enumerate(pdf_reader.pages):
                page_text = page.extract_text()
                page_contents.append({
                    "page_number": page_num + 1,
                    "content": page_text,
                    "word_count": len(page_text.split())
                })
                text_content += page_text + "\n"
            
            # 提取元数据
            metadata = {}
            if pdf_reader.metadata:
                metadata = {
                    "title": pdf_reader.metadata.get('/Title', ''),
                    "author": pdf_reader.metadata.get('/Author', ''),
                    "subject": pdf_reader.metadata.get('/Subject', ''),
                    "creator": pdf_reader.metadata.get('/Creator', ''),
                    "producer": pdf_reader.metadata.get('/Producer', ''),
                    "creation_date": str(pdf_reader.metadata.get('/CreationDate', '')),
                    "modification_date": str(pdf_reader.metadata.get('/ModDate', ''))
                }
            
            # 统计信息
            total_words = len(text_content.split())
            total_chars = len(text_content)
            
            return {
                "success": True,
                "content": text_content,
                "pages": page_contents,
                "metadata": metadata,
                "statistics": {
                    "total_pages": num_pages,
                    "total_words": total_words,
                    "total_characters": total_chars,
                    "average_words_per_page": total_words // num_pages if num_pages > 0 else 0
                },
                "error_message": ""
            }
            
        except requests.RequestException as e:
            return {
                "success": False,
                "content": "",
                "pages": [],
                "metadata": {},
                "statistics": {},
                "error_message": f"下载PDF文件失败: {str(e)}"
            }
        except Exception as e:
            return {
                "success": False,
                "content": "",
                "pages": [],
                "metadata": {},
                "statistics": {},
                "error_message": f"解析PDF文件失败: {str(e)}"
            }
    
    # 执行PDF解析
    parse_result = parse_pdf_content(downloaded_pdf_url)
    
    # 构建输出对象
    ret: Output = {
        "success": parse_result["success"],
        "full_content": parse_result["content"],
        "page_by_page": parse_result["pages"],
        "document_info": {
            "metadata": parse_result["metadata"],
            "statistics": parse_result["statistics"],
            "source_url": downloaded_pdf_url
        },
        "error_info": {
            "has_error": not parse_result["success"],
            "error_message": parse_result["error_message"]
        }
    }
    
    return ret