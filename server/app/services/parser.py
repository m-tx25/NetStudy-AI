"""文档解析：把各类文件抽成 LangChain Document（带页码元数据）。

为什么统一返回 LangChain Document：
  协作者的 `rag/build_db.py` 用 `PyPDFLoader` 产出 Document，再交给
  `RecursiveCharacterTextSplitter.split_documents()` —— 元数据（页码、来源）
  会沿着「加载 → 切片 → 入库」一路带下去。本模块对齐这一结构，
  后端就能直接复用他那套切分与向量化链路。

支持格式：
  - **Word**：.docx（LangChain UnstructuredWordDocumentLoader，回退 python-docx）
             .doc（OLE 复合文档，纯 Python 无稳定解析方案，尽力提取并提示转存）
  - **Markdown**：.md / .markdown（按标题切节，保留标题层级）
  - PDF：.pdf（PyPDFLoader，页数多时元数据自带 page_label）
  - 其他：.txt .csv .xlsx .xls .pptx .html .json

NFKC 归一化是必需的，不是可选优化：
  Chrome/Skia 导出的 PDF 文本层常把汉字写成 Unicode 兼容码位
  （'⼀' U+2F00 vs '一' U+4E00），看起来一样但码位不同，
  会导致关键词搜不到、embedding 与标准中文对不齐。见 rag/build_db.py 的说明。
"""

from __future__ import annotations

import csv
import io
import json
import re
import unicodedata
from pathlib import Path

from langchain_core.documents import Document

Pages = list[tuple[int | None, str]]


class ParseError(RuntimeError):
    """解析失败，消息会展示给用户，需可读。"""


def normalize_text(text: str) -> str:
    """Unicode NFKC 归一化，修复变体字（对齐 rag/build_db.py）。"""
    return unicodedata.normalize("NFKC", text)


def _clean(text: str) -> str:
    text = normalize_text(text or "")
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t\u00a0]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# --------------------------------------------------------------------------
# LangChain 加载器优先（与协作者实现一致）
# --------------------------------------------------------------------------
def _load_with_langchain(path: Path, loader_name: str) -> list[Document] | None:
    """尝试用指定的 LangChain 加载器读取；依赖缺失或失败时返回 None。"""
    try:
        from langchain_community.document_loaders import (
            PyPDFLoader,
            TextLoader,
            UnstructuredMarkdownLoader,
            UnstructuredWordDocumentLoader,
        )
    except ImportError:
        return None

    loaders = {
        "pdf": PyPDFLoader,
        "docx": UnstructuredWordDocumentLoader,
        "markdown": UnstructuredMarkdownLoader,
        "text": TextLoader,
    }
    loader_class = loaders.get(loader_name)
    if loader_class is None:
        return None

    try:
        if loader_name == "pdf":
            loader = loader_class(str(path), extraction_mode="plain")
        elif loader_name == "text":
            loader = loader_class(str(path), encoding="utf-8", autodetect_encoding=True)
        else:
            loader = loader_class(str(path))
        documents = loader.load()
    except Exception as exc:  # 缺 unstructured 依赖、文件损坏等
        # 不直接失败：调用方会用自研解析器回退
        import logging

        logging.getLogger(__name__).info(
            "LangChain %s 加载器不可用（%s），改用内置解析器", loader_name, exc
        )
        return None

    for document in documents:
        document.page_content = _clean(document.page_content)
    return [document for document in documents if (document.page_content or "").strip()]


# --------------------------------------------------------------------------
# 内置解析器（不依赖 unstructured，作为回退与补充）
# --------------------------------------------------------------------------
def _parse_pdf_builtin(path: Path) -> Pages:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise ParseError("缺少 PDF 解析依赖，请安装 pypdf") from exc

    reader = PdfReader(str(path))
    pages: Pages = []
    for index, page in enumerate(reader.pages, start=1):
        try:
            pages.append((index, _clean(page.extract_text() or "")))
        except Exception:
            pages.append((index, ""))
    return pages


def _parse_docx_builtin(path: Path) -> Pages:
    """python-docx 回退：段落 + 表格都要取，否则很多文档会丢关键信息。"""
    try:
        import docx
    except ImportError as exc:
        raise ParseError("缺少 Word 解析依赖，请安装 python-docx 或 unstructured") from exc

    document = docx.Document(str(path))
    parts: list[str] = []

    # 按文档顺序遍历段落与表格，尽量保留原始结构
    for paragraph in document.paragraphs:
        text = (paragraph.text or "").strip()
        if not text:
            continue
        style = (paragraph.style.name or "").lower() if paragraph.style else ""
        if style.startswith("heading"):
            level = "".join(ch for ch in style if ch.isdigit()) or "1"
            parts.append(f"{'#' * min(int(level), 6)} {text}")
        else:
            parts.append(text)

    for table in document.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if cells:
                parts.append(" | ".join(cells))

    return [(None, _clean("\n".join(parts)))]


def _parse_markdown_builtin(path: Path) -> Pages:
    """按 Markdown 标题切节：每节一个 Page，便于检索时定位到章节。"""
    raw = _read_text_file(path)
    lines = raw.splitlines()
    sections: Pages = []
    buffer: list[str] = []
    heading = ""

    def flush() -> None:
        body = "\n".join(buffer).strip()
        if body:
            sections.append((None, _clean(f"{heading}\n{body}" if heading else body)))

    for line in lines:
        if re.match(r"^\s{0,3}#{1,6}\s+\S", line):
            flush()
            buffer = []
            heading = line.strip()
            continue
        buffer.append(line)
    flush()

    if not sections:
        return [(None, _clean(raw))]
    return sections


def _parse_pptx(path: Path) -> Pages:
    try:
        from pptx import Presentation
    except ImportError as exc:
        raise ParseError("缺少 PPT 解析依赖，请安装 python-pptx") from exc

    presentation = Presentation(str(path))
    pages: Pages = []
    for index, slide in enumerate(presentation.slides, start=1):
        texts: list[str] = []
        for shape in slide.shapes:
            if shape.has_text_frame and shape.text_frame.text.strip():
                texts.append(shape.text_frame.text)
        pages.append((index, _clean("\n".join(texts))))
    return pages


def _parse_xlsx(path: Path) -> Pages:
    try:
        import openpyxl
    except ImportError as exc:
        raise ParseError("缺少 Excel 解析依赖，请安装 openpyxl") from exc

    workbook = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
    pages: Pages = []
    for index, sheet in enumerate(workbook.worksheets, start=1):
        rows: list[str] = []
        for row in sheet.iter_rows(values_only=True):
            cells = [str(cell) for cell in row if cell is not None and str(cell).strip()]
            if cells:
                rows.append(" | ".join(cells))
        pages.append((index, _clean(f"[工作表 {sheet.title}]\n" + "\n".join(rows))))
    workbook.close()
    return pages


def _read_text_file(path: Path) -> str:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ParseError("文本编码无法识别")


def _parse_text(path: Path) -> Pages:
    return [(None, _clean(_read_text_file(path)))]


def _parse_csv(path: Path) -> Pages:
    text = _read_text_file(path)
    reader = csv.reader(io.StringIO(text))
    rows = [" | ".join(cell.strip() for cell in row if cell.strip()) for row in reader]
    return [(None, _clean("\n".join(row for row in rows if row)))]


def _parse_json(path: Path) -> Pages:
    data = json.loads(_read_text_file(path))
    return [(None, _clean(json.dumps(data, ensure_ascii=False, indent=2)))]


def _parse_html(path: Path) -> Pages:
    raw = _read_text_file(path)
    raw = re.sub(r"(?is)<(script|style).*?</\1>", " ", raw)
    text = re.sub(r"(?s)<[^>]+>", " ", raw)
    text = re.sub(r"&nbsp;?", " ", text)
    text = re.sub(r"&(amp|lt|gt|quot|#39);", " ", text)
    return [(None, _clean(text))]


def _parse_doc(path: Path) -> Pages:
    """旧版 .doc 是 OLE 复合文档，纯 Python 无稳定解析方案，尽力提取并提示。"""
    raw = path.read_bytes()
    candidates: list[str] = []
    for encoding in ("utf-16-le", "gb18030"):
        try:
            decoded = raw.decode(encoding, errors="ignore")
            candidates.extend(
                re.findall(r"[\u4e00-\u9fa5A-Za-z0-9，。；：、（）\s]{20,}", decoded)
            )
        except Exception:
            pass

    text = _clean("\n".join(candidates))
    if len(text) < 20:
        raise ParseError("旧版 .doc 解析效果很差，请在 Word 中另存为 .docx 后重新上传")
    return [(None, text)]


def _pages_to_documents(pages: Pages, path: Path, loader: str) -> list[Document]:
    documents: list[Document] = []
    for page_no, text in pages:
        if not (text or "").strip():
            continue
        metadata: dict[str, object] = {"source": str(path), "loader": loader}
        if page_no is not None:
            metadata["page"] = page_no - 1  # 与 LangChain 一致，0 基
            metadata["page_label"] = page_no  # 人类可读，1 基
        documents.append(Document(page_content=text, metadata=metadata))
    return documents


# 内置解析器分发表
_BUILTIN = {
    ".pdf": _parse_pdf_builtin,
    ".docx": _parse_docx_builtin,
    ".doc": _parse_doc,
    ".md": _parse_markdown_builtin,
    ".markdown": _parse_markdown_builtin,
    ".txt": _parse_text,
    ".csv": _parse_csv,
    ".json": _parse_json,
    ".html": _parse_html,
    ".htm": _parse_html,
    ".pptx": _parse_pptx,
    ".xlsx": _parse_xlsx,
    ".xls": _parse_xlsx,
}

# LangChain 加载器优先表（与协作者 rag 模块同源）
_LANGCHAIN_FIRST = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".md": "markdown",
    ".markdown": "markdown",
}

SUPPORTED_SUFFIXES = sorted(_BUILTIN)


def parse_document(path: str | Path) -> list[Document]:
    """解析文件，返回 LangChain Document 列表（带 page / page_label 元数据）。"""
    file_path = Path(path)
    if not file_path.exists():
        raise ParseError(f"文件不存在：{file_path}")

    suffix = file_path.suffix.lower()
    if suffix not in _BUILTIN:
        raise ParseError(
            f"不支持的文件类型 {suffix or '(无扩展名)'}，支持：{'、'.join(SUPPORTED_SUFFIXES)}"
        )

    # 1) 优先 LangChain 加载器（与协作者实现保持一致的行为）
    loader_name = _LANGCHAIN_FIRST.get(suffix)
    if loader_name:
        documents = _load_with_langchain(file_path, loader_name)
        if documents:
            return documents

    # 2) 回退到内置解析器
    pages = _BUILTIN[suffix](file_path)
    if not any(text.strip() for _, text in pages):
        raise ParseError("未能从文件中提取到任何文本（可能是扫描件或纯图片，需先 OCR）")

    documents = _pages_to_documents(pages, file_path, loader="builtin")
    if not documents:
        raise ParseError("解析后没有产生任何可用文本")
    return documents


def text_length(documents: list[Document]) -> int:
    return sum(len(document.page_content or "") for document in documents)
