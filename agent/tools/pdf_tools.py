import urllib.request
import os
from typing import Any
from core.tools import BaseTool

class ArxivPdfReaderTool(BaseTool):
    name = "arxiv_pdf_reader"
    description = "用于根据 arXiv 论文 ID 下载并解析 PDF 全文"
    parameters = {
        "paper_id": "论文的 arXiv ID。必填",
        "read_full": "是否尽量多读，默认 false"
    }

    def __init__(self, papers_dir: str = None):
        self.papers_dir = papers_dir

    def execute(self, **kwargs) -> Any:
        try:
            import fitz
        except ImportError:
            return "缺少依赖 PyMuPDF"

        paper_id = kwargs.get("paper_id")
        if not paper_id:
            raise ValueError("缺少纸张ID")

        pdf_url = f"https://arxiv.org/pdf/{paper_id}.pdf"
        read_full = kwargs.get("read_full", False)

        try:
            import ssl
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

            req = urllib.request.Request(pdf_url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, context=ctx) as response:
                pdf_bytes = response.read()

            msg = ""
            if self.papers_dir:
                os.makedirs(self.papers_dir, exist_ok=True)
                pdf_path = os.path.join(self.papers_dir, f"{paper_id}.pdf")
                with open(pdf_path, "wb") as f:
                    f.write(pdf_bytes)
                msg += f"✅ 原文已下载并保存至 papers/ 目录\n"

            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            total_pages = len(doc)
            if total_pages == 0:
                return f"论文 {paper_id} 解析失败，PDF 为空。"

            text_blocks = []
            pages_to_read = list(range(min(5 if read_full else 2, total_pages)))
            if total_pages - 1 not in pages_to_read:
                pages_to_read.append(total_pages - 1)

            for p_num in pages_to_read:
                t = doc.load_page(p_num).get_text("text").strip()
                if t: text_blocks.append(f"--- 第 {p_num + 1} 页全文 ---\n{t}")

            return msg + f"成功提取部分正文：\n\n" + "\n\n".join(text_blocks)
        except Exception as e:
            return f"读取论文 PDF 时发生错误：{str(e)}。"


class ArxivDownloadPdfTool(BaseTool):
    """纯下载工具：只下载 PDF 到 papers/ 目录，不解析正文。轻量、快速、无依赖。"""
    name = "arxiv_download_pdf"
    description = "根据论文 ID (或直接给 url) 下载 PDF 原文到 papers/ 目录（只下载不解析，轻量快速）。每篇论文都应该调一次此工具保存 PDF。"
    parameters = {
        "paper_id": "论文的 arXiv ID（如 2308.11432），或以 http 开头的直接 PDF 下载链接。"
    }

    def __init__(self, papers_dir: str = None):
        self.papers_dir = papers_dir

    def execute(self, **kwargs) -> Any:
        paper_id = kwargs.get("paper_id")
        if not paper_id:
            return "❌ 缺少 paper_id 参数。请传入 arXiv ID（如 2308.11432）或 URL链接。"

        paper_id = paper_id.strip()
        
        # 判断是 arXiv ID 还是直接的 URL
        if paper_id.startswith("http://") or paper_id.startswith("https://"):
            pdf_url = paper_id
            # 生成一个简易的文件名
            import hashlib
            clean_id = "paper_" + hashlib.md5(pdf_url.encode('utf-8')).hexdigest()[:8]
        else:
            # 去版本后缀
            clean_id = paper_id.split("v")[0] if "v" in paper_id else paper_id
            pdf_url = f"https://arxiv.org/pdf/{clean_id}.pdf"

        try:
            import ssl
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
            req = urllib.request.Request(pdf_url, headers=headers)
            with urllib.request.urlopen(req, context=ctx) as response:
                pdf_bytes = response.read()

            save_msg = ""
            if self.papers_dir:
                os.makedirs(self.papers_dir, exist_ok=True)
                pdf_path = os.path.join(self.papers_dir, f"{clean_id}.pdf")
                with open(pdf_path, "wb") as f:
                    f.write(pdf_bytes)
                save_msg = f"，已保存至 papers/{clean_id}.pdf"

            return f"✅ PDF 下载成功（{len(pdf_bytes) / 1024:.0f} KB）{save_msg}"
        except urllib.error.HTTPError as e:
            return f"❌ 下载失败：HTTP {e.code}。该论文可能没有开放 PDF，或下载链接/arXiv ID 有误。"
        except Exception as e:
            return f"❌ 下载失败：{str(e)}"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  RAG upgrade：PDF 全量文本提取器
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def extract_full_text_from_pdf(pdf_path: str, session_id: str = "", paper_id: str = "") -> list[dict]:
    """
    从 PDF 文件中提取全量文本，返回段落块列表。
    使用滑动窗口分块策略：chunk_size=500 字符，overlap=100 字符，
    确保公式、算法描述等关键信息不会因硬切分而丢失。
    
    每个块是一个 dict：
    {
        "paper_id": 论文 ID,
        "page": 页码 (1-based),
        "chunk_idx": 块序号,
        "text": 段落文本
    }
    """
    try:
        import fitz
    except ImportError:
        return []

    try:
        doc = fitz.open(pdf_path)
    except Exception:
        return []

    CHUNK_SIZE = 500   # 每块最大字符数
    CHUNK_OVERLAP = 100  # 块之间重叠字符数

    blocks = []
    total_pages = len(doc)
    for page_num in range(total_pages):
        text = doc[page_num].get_text("text").strip()
        if not text:
            continue
        
        # 先按自然段落粗分，再对过长段落做滑动窗口切分
        paragraphs = [p.strip() for p in text.split("\n\n") if len(p.strip()) > 0]
        chunk_idx = 0
        for para in paragraphs:
            if len(para) <= CHUNK_SIZE:
                blocks.append({
                    "paper_id": paper_id,
                    "page": page_num + 1,
                    "chunk_idx": chunk_idx,
                    "text": para,
                })
                chunk_idx += 1
            else:
                # 滑动窗口切分长段落
                start = 0
                while start < len(para):
                    end = min(start + CHUNK_SIZE, len(para))
                    chunk_text = para[start:end].strip()
                    if chunk_text:
                        blocks.append({
                            "paper_id": paper_id,
                            "page": page_num + 1,
                            "chunk_idx": chunk_idx,
                            "text": chunk_text,
                        })
                        chunk_idx += 1
                    if end >= len(para):
                        break
                    start = end - CHUNK_OVERLAP
    doc.close()
    return blocks


def extract_all_session_pdfs(session_id: str, papers_dir: str) -> list[dict]:
    """
    提取某 Session 中所有 PDF 的全量文本，返回统一的段落块列表。
    """
    import glob
    all_blocks = []
    pattern = os.path.join(papers_dir, "*.pdf")
    for pdf_path in glob.glob(pattern):
        paper_id = os.path.splitext(os.path.basename(pdf_path))[0]
        blocks = extract_full_text_from_pdf(pdf_path, session_id, paper_id)
        all_blocks.extend(blocks)
    return all_blocks

