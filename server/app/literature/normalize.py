"""归一化与去重工具。

跨源去重的判定顺序：
  1. DOI（最可靠，统一小写、去掉 https://doi.org/ 前缀）
  2. 标题归一化 + 年份（去掉标点/空白/大小写差异）

同一篇论文在多个源出现时保留「信息更全」的一条，并把缺失字段补齐。
"""

from __future__ import annotations

import re
import unicodedata

from app.literature.dto import PaperDTO

_DOI_PREFIX = re.compile(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", re.IGNORECASE)
_NON_WORD = re.compile(r"[^\w\u4e00-\u9fff]+", re.UNICODE)


def normalize_doi(raw: str | None) -> str:
    if not raw:
        return ""
    value = _DOI_PREFIX.sub("", raw.strip())
    return value.strip().lower()


def normalize_title(raw: str | None) -> str:
    """标题归一化：全角转半角、去标点、压缩空白、小写。"""
    if not raw:
        return ""
    text = unicodedata.normalize("NFKC", raw)
    text = _NON_WORD.sub(" ", text)
    return " ".join(text.lower().split())


def dedupe_key(paper: PaperDTO) -> str:
    doi = normalize_doi(paper.doi)
    if doi:
        return f"doi:{doi}"
    return f"title:{normalize_title(paper.title)}:{paper.year or ''}"


def _richness(paper: PaperDTO) -> int:
    """判断哪条记录更完整，用于去重时择优。"""
    score = 0
    score += 4 if paper.abstract else 0
    score += 2 if paper.authors else 0
    score += 2 if paper.open_access.pdf_url else 0
    score += 1 if paper.venue else 0
    score += 1 if paper.doi else 0
    score += min(paper.cited_by, 100) // 100
    return score


def merge_prefer_rich(primary: PaperDTO, other: PaperDTO) -> PaperDTO:
    """两条重复记录合并：主体取更完整的一条，缺失字段用另一条补。"""
    if _richness(other) > _richness(primary):
        primary, other = other, primary

    updates: dict = {}
    for field in ("doi", "abstract", "venue", "url"):
        if not getattr(primary, field) and getattr(other, field):
            updates[field] = getattr(other, field)
    if not primary.authors and other.authors:
        updates["authors"] = other.authors
    if not primary.open_access.pdf_url and other.open_access.pdf_url:
        updates["open_access"] = other.open_access
    if primary.cited_by < other.cited_by:
        updates["cited_by"] = other.cited_by
    return primary.model_copy(update=updates) if updates else primary


def dedupe(papers: list[PaperDTO]) -> list[PaperDTO]:
    """保序去重（先出现的顺序优先，但内容取更完整的一条）。"""
    seen: dict[str, int] = {}
    result: list[PaperDTO] = []
    for paper in papers:
        key = dedupe_key(paper)
        if key in seen:
            index = seen[key]
            result[index] = merge_prefer_rich(result[index], paper)
            continue
        seen[key] = len(result)
        result.append(paper)
    return result
