"""文本切片。

参数与协作者的 `rag/build_db.py` 对齐：
    RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    分隔符中文优先（默认的英文标点对中文 PDF 切得很差）

入参与出参都是 LangChain Document —— 元数据（页码、来源、文件名）会沿着
「加载 → 切片 → 入库」一路保留，检索命中后才能溯源到具体页码。
"""

from __future__ import annotations

import logging

from langchain_core.documents import Document

from app.core.config import settings

logger = logging.getLogger(__name__)

# 中文标点必须排在前面，否则中文长句会被硬切
SEPARATORS = ["\n\n", "\n", "。", "！", "？", "；", ". ", " ", ""]

_splitter = None
_splitter_signature: tuple[int, int] | None = None


def _get_splitter(chunk_size: int, chunk_overlap: int):
    """按尺寸缓存 splitter，避免每次调用都重建。"""
    global _splitter, _splitter_signature

    signature = (chunk_size, chunk_overlap)
    if _splitter is not None and _splitter_signature == signature:
        return _splitter

    try:
        from langchain_text_splitters import RecursiveCharacterTextSplitter

        _splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            length_function=len,
            separators=SEPARATORS,
            keep_separator=True,
        )
    except ImportError:  # pragma: no cover
        logger.warning("未安装 langchain-text-splitters，切片将退化为整段返回")
        _splitter = None

    _splitter_signature = signature
    return _splitter


def split_documents(
    documents: list[Document],
    *,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
) -> list[Document]:
    """把 Document 列表切成更小的 Document 列表，元数据自动继承。"""
    size = chunk_size or settings.CHUNK_SIZE
    overlap = chunk_overlap if chunk_overlap is not None else settings.CHUNK_OVERLAP
    if overlap >= size:
        overlap = max(0, size // 8)

    splitter = _get_splitter(size, overlap)
    if splitter is None:
        return [doc for doc in documents if (doc.page_content or "").strip()]

    chunks = splitter.split_documents(documents)
    return [chunk for chunk in chunks if (chunk.page_content or "").strip()]


def describe() -> dict:
    return {
        "chunkSize": settings.CHUNK_SIZE,
        "chunkOverlap": settings.CHUNK_OVERLAP,
        "separators": SEPARATORS,
    }
