"""参考文献抽取：从 References 章节切出条目，并尽量识别 DOI / 年份。

只做「结构化参考列表」——识别不出来的条目保留原文，不强行解析成字段。
这样前端至少能展示引用列表，后续可与 Crossref 匹配补全。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.services.sectionizer import Section

_DOI = re.compile(r"\b(10\.\d{4,9}/[-._;()/:a-zA-Z0-9]+)")
_YEAR = re.compile(r"\b(19[5-9]\d|20[0-4]\d)\b")
_NUMBERED = re.compile(r"(?m)^\s*(?:\[\d{1,3}\]|\d{1,3}[\.\)])\s*")
# LaTeX/期刊常见格式：每行以「姓, 名首字母.」开头，且条目之间没有空行
_AUTHOR_START = re.compile(r"(?m)^(?=[A-Z][A-Za-z'\-]+,\s+[A-Z]\.)")


@dataclass
class Reference:
    raw_text: str
    doi: str = ""
    year: int | None = None
    title: str = ""


def _clean_doi(raw: str) -> str:
    return raw.rstrip(".,;:)]}\"'").strip().lower()


def _guess_title(raw: str) -> str:
    # 常见格式：作者. 标题. 期刊, 年. —— 取第二段
    parts = [part.strip() for part in raw.split(". ") if part.strip()]
    for part in parts[1:3]:
        if 12 <= len(part) <= 200:
            return part[:200]
    return raw[:120]


def _split_entries(text: str) -> list[str]:
    text = text.strip()
    if not text:
        return []
    numbered = _NUMBERED.split(text)
    entries = [part.strip() for part in numbered if part and len(part.strip()) >= 20]
    if len(entries) >= 2:
        return entries
    # 无编号：先按「姓, 名首字母.」开头的行切（期刊/LaTeX 常见），再退回空行
    by_author = _AUTHOR_START.split(text)
    entries = [part.strip() for part in by_author if len(part.strip()) >= 20]
    if len(entries) >= 2:
        return entries
    blocks = [block.strip() for block in re.split(r"\n\s*\n", text) if block.strip()]
    return [block for block in blocks if len(block) >= 20]


def extract(sections: list[Section], *, limit: int = 300) -> list[Reference]:
    ref_text = ""
    for section in sections:
        if section.section_type == "references":
            ref_text = section.text
            break
    if not ref_text:
        return []

    references: list[Reference] = []
    for entry in _split_entries(ref_text)[:limit]:
        raw = " ".join(entry.split())
        if len(raw) < 20:
            continue
        doi_match = _DOI.search(raw)
        year_match = _YEAR.search(raw)
        references.append(
            Reference(
                raw_text=raw[:600],
                doi=_clean_doi(doi_match.group(1)) if doi_match else "",
                year=int(year_match.group(1)) if year_match else None,
                title=_guess_title(raw),
            )
        )
    return references
