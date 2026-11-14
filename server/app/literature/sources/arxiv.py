"""arXiv 适配器（Atom XML）。

文档：https://info.arxiv.org/help/api/user-manual.html
特点：预印本、开放 PDF 直链；无 DOI（部分有）/无引用数；官方要求 3 秒一次。
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Any

from app.literature.base import PaperSource, SourceError
from app.literature.dto import AuthorDTO, OaInfo, PaperDTO, SearchQuery
from app.literature.http import get_text

BASE = "http://export.arxiv.org/api/query"
NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
}
_WS = re.compile(r"\s+")


def _text(node: ET.Element | None) -> str:
    return _WS.sub(" ", (node.text or "")).strip() if node is not None else ""


def _entry_to_paper(entry: ET.Element) -> PaperDTO:
    raw_id = _text(entry.find("atom:id", NS))
    match = re.search(r"abs/([^v]+)(?:v\d+)?$", raw_id)
    source_id = match.group(1) if match else raw_id.rsplit("/", 1)[-1]
    pdf_url = ""
    landing = raw_id
    for link in entry.findall("atom:link", NS):
        if link.get("title") == "pdf":
            pdf_url = link.get("href") or ""
        elif link.get("rel") == "alternate":
            landing = link.get("href") or landing
    doi_node = entry.find("arxiv:doi", NS)
    doi = _text(doi_node).lower()
    published = _text(entry.find("atom:published", NS))
    year = int(published[:4]) if published[:4].isdigit() else None
    categories = [c.get("term", "") for c in entry.findall("atom:category", NS)]
    authors = [
        AuthorDTO(name=_text(a.find("atom:name", NS)))
        for a in entry.findall("atom:author", NS)
    ]
    return PaperDTO(
        id=f"arxiv:{source_id}",
        source="arxiv",
        source_id=source_id,
        doi=doi,
        title=_text(entry.find("atom:title", NS)),
        abstract=_text(entry.find("atom:summary", NS)),
        authors=authors,
        venue="arXiv",
        year=year,
        cited_by=0,
        fields=[c for c in categories if c][:5],
        open_access=OaInfo(is_oa=True, pdf_url=pdf_url, landing_url=landing),
        url=landing,
        type="preprint",
    )


class ArxivSource(PaperSource):
    name = "arxiv"
    label = "arXiv"

    def _search_query(self, query: SearchQuery) -> str:
        clauses: list[str] = []
        if query.q:
            clauses.append(f'all:"{query.q}"')
        if query.author:
            clauses.append(f'au:"{query.author}"')
        if query.venue:
            clauses.append(f'abs:"{query.venue}"')
        return " AND ".join(clauses) or "all:*"

    async def search(self, query: SearchQuery, *, limit: int) -> list[PaperDTO]:
        if query.doi:
            return []  # arXiv 不支持 DOI 检索
        params: dict[str, Any] = {
            "search_query": self._search_query(query),
            "start": (query.page - 1) * query.page_size,
            "max_results": min(limit, 50),
            "sortBy": "submittedDate" if query.sort == "year" else "relevance",
            "sortOrder": "descending",
        }
        xml = await get_text(BASE, params, label="arXiv")
        try:
            root = ET.fromstring(xml)
        except ET.ParseError as exc:
            raise SourceError(f"arXiv 返回的 XML 无法解析：{exc}") from exc
        return [_entry_to_paper(entry) for entry in root.findall("atom:entry", NS)]

    async def get(self, source_id: str) -> PaperDTO | None:
        xml = await get_text(
            BASE, {"id_list": source_id, "max_results": 1}, label="arXiv"
        )
        root = ET.fromstring(xml)
        entries = root.findall("atom:entry", NS)
        return _entry_to_paper(entries[0]) if entries else None
