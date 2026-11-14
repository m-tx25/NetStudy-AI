"""Crossref 适配器。

文档：https://api.crossref.org/
特点：DOI 权威、元数据规范；摘要常为 JATS XML，需要剥标签；
没有「相关论文」接口，`related()` 返回空。
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote

from app.core.config import settings
from app.literature.base import PaperSource, SourceError
from app.literature.dto import AuthorDTO, OaInfo, PaperDTO, SearchQuery
from app.literature.http import get_json

BASE = "https://api.crossref.org"
_TAG = re.compile(r"<[^>]+>")


def _clean_text(raw: str | None) -> str:
    if not raw:
        return ""
    text = _TAG.sub(" ", raw)
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    return " ".join(text.split())


def _year(item: dict[str, Any]) -> int | None:
    for key in ("published-print", "published-online", "issued", "created"):
        parts = (item.get(key) or {}).get("date-parts") or []
        if parts and parts[0] and parts[0][0]:
            return int(parts[0][0])
    return None


def _to_paper(item: dict[str, Any]) -> PaperDTO:
    doi = (item.get("DOI") or "").lower()
    authors = [
        AuthorDTO(
            name=" ".join(part for part in (a.get("given"), a.get("family")) if part).strip(),
            affiliation=(a.get("affiliation") or [{}])[0].get("name", "") if a.get("affiliation") else "",
            orcid=(a.get("ORCID") or "").rsplit("/", 1)[-1],
        )
        for a in (item.get("author") or [])
    ]
    pdf_url = ""
    for link in item.get("link") or []:
        if (link.get("content-type") or "").lower() == "application/pdf":
            pdf_url = link.get("URL") or ""
            break
    return PaperDTO(
        id=f"crossref:{doi}",
        source="crossref",
        source_id=doi,
        doi=doi,
        title=_clean_text((item.get("title") or [""])[0]),
        abstract=_clean_text(item.get("abstract")),
        authors=authors,
        venue=_clean_text((item.get("container-title") or [""])[0]),
        year=_year(item),
        cited_by=int(item.get("is-referenced-by-count") or 0),
        fields=[s for s in (item.get("subject") or [])][:5],
        open_access=OaInfo(is_oa=bool(pdf_url), pdf_url=pdf_url, landing_url=item.get("URL") or ""),
        url=item.get("URL") or (f"https://doi.org/{doi}" if doi else ""),
        type=item.get("type") or "article",
    )


class CrossrefSource(PaperSource):
    name = "crossref"
    label = "Crossref"

    def _params(self, query: SearchQuery, limit: int) -> dict[str, Any]:
        params: dict[str, Any] = {
            "rows": min(limit, 50),
            "offset": (query.page - 1) * query.page_size,
            "select": (
                "DOI,title,abstract,author,container-title,issued,published-print,"
                "published-online,is-referenced-by-count,URL,type,link,subject"
            ),
        }
        if settings.LITERATURE_MAILTO:
            params["mailto"] = settings.LITERATURE_MAILTO
        if query.q:
            params["query.bibliographic"] = query.q
        if query.author:
            params["query.author"] = query.author
        if query.venue:
            params["query.container-title"] = query.venue

        filters: list[str] = []
        if query.year_from:
            filters.append(f"from-pub-date:{query.year_from}-01-01")
        if query.year_to:
            filters.append(f"until-pub-date:{query.year_to}-12-31")
        if filters:
            params["filter"] = ",".join(filters)

        if query.sort == "cited":
            params["sort"] = "is-referenced-by-count"
            params["order"] = "desc"
        elif query.sort == "year":
            params["sort"] = "published"
            params["order"] = "desc"
        else:
            params["sort"] = "relevance"
        return params

    async def search(self, query: SearchQuery, *, limit: int) -> list[PaperDTO]:
        if query.doi:
            paper = await self.get_by_doi(query.doi)
            return [paper] if paper else []
        data = await get_json(f"{BASE}/works", self._params(query, limit), label="Crossref")
        return [_to_paper(item) for item in ((data.get("message") or {}).get("items") or [])]

    async def get(self, source_id: str) -> PaperDTO | None:
        return await self.get_by_doi(source_id)

    async def get_by_doi(self, doi: str) -> PaperDTO | None:
        try:
            data = await get_json(
                f"{BASE}/works/{quote(doi, safe='')}", label="Crossref"
            )
        except SourceError:
            return None
        message = data.get("message") or {}
        return _to_paper(message) if message else None
