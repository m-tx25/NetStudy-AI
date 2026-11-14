"""引用格式导出（BibTeX / RIS / APA / GB/T 7714）。

只做「够用且可被文献管理软件识别」的实现：不追求期刊模板的全部细节，
但字段映射、作者分隔符、条目类型要正确，否则 Zotero / EndNote 导入会乱。
"""

from __future__ import annotations

import re

from app.literature.dto import PaperDTO

_BIB_TYPE = {
    "article": "article",
    "preprint": "misc",
    "review": "article",
    "book": "book",
    "conference": "inproceedings",
}


def _authors(paper: PaperDTO) -> list[str]:
    return [author.name.strip() for author in paper.authors if author.name.strip()]


def _first_lastname(paper: PaperDTO) -> str:
    names = _authors(paper)
    if not names:
        return "unknown"
    last = names[0].split()[-1]
    return re.sub(r"[^A-Za-z0-9]", "", last).lower() or "unknown"


def _first_title_word(paper: PaperDTO) -> str:
    words = re.findall(r"[A-Za-z0-9]+", paper.title or "")
    return (words[0].lower() if words else "untitled")[:20]


def _bib_key(paper: PaperDTO) -> str:
    return f"{_first_lastname(paper)}{paper.year or 'nd'}{_first_title_word(paper)}"


def _entry_type(paper: PaperDTO) -> str:
    return _BIB_TYPE.get((paper.type or "").lower(), "article")


def to_bibtex(paper: PaperDTO) -> str:
    fields = [
        ("title", paper.title),
        ("author", " and ".join(_authors(paper))),
        ("journal", paper.venue),
        ("year", str(paper.year) if paper.year else ""),
        ("doi", paper.doi),
        ("url", paper.url),
    ]
    body = ",\n".join(
        f"  {name} = {{{value}}}" for name, value in fields if value
    )
    return f"@{_entry_type(paper)}{{{_bib_key(paper)},\n{body}\n}}\n"


def to_ris(paper: PaperDTO) -> str:
    lines = ["TY  - JOUR"]
    if paper.title:
        lines.append(f"TI  - {paper.title}")
    lines.extend(f"AU  - {name}" for name in _authors(paper))
    if paper.venue:
        lines.append(f"JO  - {paper.venue}")
    if paper.year:
        lines.append(f"PY  - {paper.year}")
    if paper.doi:
        lines.append(f"DO  - {paper.doi}")
    if paper.url:
        lines.append(f"UR  - {paper.url}")
    lines.append("ER  - ")
    return "\n".join(lines) + "\n"


def to_apa(paper: PaperDTO) -> str:
    names = _authors(paper)
    if not names:
        author_text = "Unknown"
    elif len(names) == 1:
        author_text = names[0]
    else:
        author_text = ", ".join(names[:-1]) + ", & " + names[-1]
    year = f"({paper.year})" if paper.year else "(n.d.)"
    parts = [f"{author_text} {year}.", f"{paper.title}."]
    if paper.venue:
        parts.append(f"{paper.venue}.")
    if paper.doi:
        parts.append(f"https://doi.org/{paper.doi}")
    return " ".join(parts).strip() + "\n"


def to_gbt7714(paper: PaperDTO) -> str:
    names = _authors(paper)
    author_text = ", ".join(names[:3])
    if len(names) > 3:
        author_text += ", 等"
    parts = []
    if author_text:
        parts.append(f"{author_text}.")
    if paper.title:
        parts.append(f"{paper.title}[{'J' if paper.venue else 'EB/OL'}].")
    if paper.venue:
        parts.append(f"{paper.venue},")
    if paper.year:
        parts.append(f"{paper.year}.")
    if paper.doi:
        parts.append(f"DOI:{paper.doi}.")
    return " ".join(parts).strip() + "\n"


_FORMATTERS = {
    "bibtex": to_bibtex,
    "bib": to_bibtex,
    "ris": to_ris,
    "apa": to_apa,
    "gbt7714": to_gbt7714,
    "gb/t 7714": to_gbt7714,
    "gb": to_gbt7714,
}


def format_citation(paper: PaperDTO, fmt: str) -> str:
    key = (fmt or "").strip().lower()
    formatter = _FORMATTERS.get(key)
    if formatter is None:
        raise ValueError(f"不支持的引用格式：{fmt}（可选 bibtex/ris/apa/gbt7714）")
    return formatter(paper)
