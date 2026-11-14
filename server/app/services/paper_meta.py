"""论文元数据抽取：标题、作者、DOI、年份、摘要。

都是启发式规则——学术 PDF 的版式千差万别，没有版面分析（字体/坐标）时
不可能 100% 准确。目标是「大部分论文能抽出可用值，抽不出就留空」，
而不是猜一个错误值。后续可用 Crossref 按 DOI 补全（见 enrich_with_crossref）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from langchain_core.documents import Document

from app.services.sectionizer import Section

_DOI = re.compile(r"\b(10\.\d{4,9}/[-._;()/:a-zA-Z0-9]+)")
_YEAR = re.compile(r"\b(19[5-9]\d|20[0-4]\d)\b")
_YEAR_HINT = re.compile(r"(?:©|\(c\)|published|accepted|received|copyright)\D{0,40}(19[5-9]\d|20[0-4]\d)", re.I)
_SKIP_TITLE = re.compile(
    r"(doi|arxiv|https?://|www\.|@|proceedings|journal|transactions|conference|"
    r"issn|volume|vol\.|issue|received|accepted|published|copyright|©|preprint)",
    re.I,
)
_AUTHOR_SPLIT = re.compile(r",|，|;|；|\band\b|、")
_AFFILIATION = re.compile(
    r"(universit|institut|department|college|laborator|school of|academy|"
    r"hospital|corporation|inc\.|ltd|company|research center)",
    re.I,
)


@dataclass
class PaperMeta:
    title: str = ""
    authors: list[str] = field(default_factory=list)
    doi: str = ""
    year: int | None = None
    abstract: str = ""
    venue: str = ""


def _clean_doi(raw: str) -> str:
    return raw.rstrip(".,;:)]}\"'").strip().lower()


def _first_pages_text(documents: list[Document], limit: int = 3) -> str:
    return "\n".join((document.page_content or "") for document in documents[:limit])


_AUTHOR_LINE = re.compile(
    r"^(?:"
    r"[A-Z][\w.'-]*(?:\s+[A-Z][\w.'-]*){0,3}"
    r"|[\u4e00-\u9fff]{2,4}"
    r")"
    r"(?:\s*[,，]\s*(?:[A-Z][\w.'-]*(?:\s+[A-Z][\w.'-]*){0,3}|[\u4e00-\u9fff]{2,4}))+$"
)


def _looks_like_authors(line: str) -> bool:
    """判断一行是否像作者列表（用于标题分行的截断）。

    两类：带逗号的「A, B, C」名单；以及标题后紧跟的 2-3 个首字母大写的姓名
    （如 "John Smith"）。后者是标题与前缀名的常见分界信号。
    """
    text = line.strip()
    if _AUTHOR_LINE.match(text):
        return True
    if any(char in text for char in "()@"):
        return False
    if re.search(r"\d", text):
        return False
    words = text.replace("，", ",").split()
    if 2 <= len(words) <= 3:
        return all(
            word[:1].isupper() or "\u4e00" <= word[0] <= "\u9fff" for word in words
        )
    return False


def _title_block(first_page: str) -> tuple[str, int]:
    """返回（标题, 标题最后一行的下一行下标）。

    标题可能跨 2-3 行；同时把结束位置带出来，供作者抽取从正确位置开始，
    否则会把标题单词误当作者（实测标题跨行时会出现）。
    """
    lines = [line.strip() for line in first_page.splitlines() if line.strip()]
    block: list[str] = []
    end = 0
    for index, line in enumerate(lines[:20]):
        if not 4 <= len(line) <= 250:
            if block:
                break
            continue
        if _SKIP_TITLE.search(line) or "@" in line:
            if block:
                break
            continue
        if _AFFILIATION.search(line) or re.search(r"\b(19|20)\d{2}\b", line):
            if block:
                break
            continue
        if _looks_like_authors(line):
            if block:
                break
            continue
        letters = sum(1 for char in line if char.isalpha())
        if letters < max(3, len(line) // 5):
            if block:
                break
            continue
        block.append(line)
        end = index + 1
        if len(" ".join(block)) >= 160 or len(block) >= 3:
            break
    if not block:
        return "", 0
    return " ".join(block)[:300], end


def _guess_authors(first_page: str, start: int = 0) -> list[str]:
    lines = [line.strip() for line in first_page.splitlines() if line.strip()]
    authors: list[str] = []
    for line in lines[start : start + 8]:
        lowered = line.lower()
        if lowered.startswith(("abstract", "摘要", "keywords", "关键词")):
            break
        # 先剥掉括号里的机构信息，避免 "USA)" 被当成作者
        line = re.sub(r"\([^)]*\)", " ", line)
        if len(line) > 300 or "@" in line or "http" in lowered:
            continue
        for token in _AUTHOR_SPLIT.split(line):
            name = token.strip(" 0123456789*†‡§¶")
            if not 3 <= len(name) <= 60:
                continue
            if not any(char.isalpha() for char in name):
                continue
            if name.lower() in {"and", "et al", "university", "department"}:
                continue
            if _AFFILIATION.search(name):
                continue
            # 姓名里出现数字/年份基本是版权行或页眉
            if re.search(r"\d", name):
                continue
            if name not in authors:
                authors.append(name)
        if len(authors) >= 10:
            break
    return authors[:12]


def _guess_year(text: str) -> int | None:
    hinted = _YEAR_HINT.search(text)
    if hinted:
        return int(hinted.group(1))
    years = [int(match.group(1)) for match in _YEAR.finditer(text)]
    if not years:
        return None
    # 版权/发表年份通常出现多次；取出现最多的，平票取较小值
    counts: dict[int, int] = {}
    for year in years:
        counts[year] = counts.get(year, 0) + 1
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]


def _abstract_from_sections(sections: list[Section]) -> str:
    for section in sections:
        if section.section_type == "abstract":
            text = section.text
            # 去掉标题本身
            if text.lower().startswith(("abstract", "摘要")):
                text = text.split("\n", 1)[1] if "\n" in text else text
            # 摘要是一个整体：把 PDF 断行压成单空格，避免「一个词一行」
            return " ".join(text.split())[:6000]
    return ""


def extract(documents: list[Document], sections: list[Section]) -> PaperMeta:
    head_text = _first_pages_text(documents)
    first_page = (documents[0].page_content or "") if documents else ""

    doi_match = _DOI.search(head_text) or _DOI.search(first_page)
    doi = _clean_doi(doi_match.group(1)) if doi_match else ""

    title, title_end = _title_block(first_page)
    authors = _guess_authors(first_page, title_end) if title else []
    abstract = _abstract_from_sections(sections)

    return PaperMeta(
        title=title,
        authors=authors,
        doi=doi,
        year=_guess_year(head_text),
        abstract=abstract,
    )


async def enrich_with_crossref(meta: PaperMeta, *, timeout: float = 4.0) -> PaperMeta:
    """有 DOI 时用 Crossref 补全标题/作者/年份（失败就原样返回）。

    网络不通不报错：元数据抽取是「尽力而为」，不能因为外部服务不可用
    让整篇文档解析失败。
    """
    if not meta.doi or meta.title:
        return meta
    import httpx

    from app.core.config import settings

    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.get(
                f"https://api.crossref.org/works/{meta.doi}",
                headers={"User-Agent": "NetStudy-AI/0.1"},
            )
            if response.status_code >= 400:
                return meta
            message = (response.json() or {}).get("message") or {}
    except Exception:  # noqa: BLE001 - 外部补全失败不影响主流程
        return meta

    title = (message.get("title") or [""])[0]
    if title and not meta.title:
        meta.title = title[:300]
    if not meta.authors:
        meta.authors = [
            " ".join(part for part in (item.get("given"), item.get("family")) if part).strip()
            for item in (message.get("author") or [])[:12]
        ]
    if not meta.year:
        parts = ((message.get("issued") or {}).get("date-parts") or [[]])[0]
        if parts and parts[0]:
            meta.year = int(parts[0])
    return meta
