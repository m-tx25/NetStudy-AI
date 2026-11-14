"""Semantic Scholar 适配器（可选数据源）。

文档：https://api.semanticscholar.org/api-docs/
特点：相关推荐与引用网络强；无 Key 时 1 次/秒，容易 429。
Key 从 `SEMANTIC_SCHOLAR_API_KEY` 读取（也可以让用户自带，后续接 keyring）。
"""

from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.literature.base import PaperSource, SourceError
from app.literature.dto import AuthorDTO, OaInfo, PaperDTO, SearchQuery
from app.literature.http import get_json

BASE = "https://api.semanticscholar.org/graph/v1"
FIELDS = (
    "title,abstract,authors,venue,year,citationCount,externalIds,"
    "openAccessPdf,url,fieldsOfStudy,publicationTypes"
)


def _headers() -> dict[str, str]:
    key = settings.SEMANTIC_SCHOLAR_API_KEY.strip()
    return {"x-api-key": key} if key else {}


def _to_paper(item: dict[str, Any]) -> PaperDTO:
    external = item.get("externalIds") or {}
    doi = (external.get("DOI") or "").lower()
    paper_id = item.get("paperId") or doi
    authors = [
        AuthorDTO(name=a.get("name") or "")
        for a in (item.get("authors") or [])
    ]
    oa = item.get("openAccessPdf") or {}
    return PaperDTO(
        id=f"semantic_scholar:{paper_id}",
        source="semantic_scholar",
        source_id=str(paper_id),
        doi=doi,
        title=(item.get("title") or "").strip(),
        abstract=(item.get("abstract") or "").strip(),
        authors=authors,
        venue=item.get("venue") or "",
        year=item.get("year"),
        cited_by=int(item.get("citationCount") or 0),
        fields=[f for f in (item.get("fieldsOfStudy") or []) if f][:5],
        open_access=OaInfo(
            is_oa=bool(oa.get("url")),
            pdf_url=oa.get("url") or "",
            landing_url=item.get("url") or "",
        ),
        url=item.get("url") or "",
        type=(item.get("publicationTypes") or ["article"])[0],
    )


class SemanticScholarSource(PaperSource):
    name = "semantic_scholar"
    label = "Semantic Scholar"

    async def search(self, query: SearchQuery, *, limit: int) -> list[PaperDTO]:
        if query.doi:
            paper = await self.get_by_doi(query.doi)
            return [paper] if paper else []
        text = " ".join(part for part in (query.q, query.author) if part).strip()
        if not text:
            return []
        params = {
            "query": text,
            "limit": min(limit, 50),
            "offset": (query.page - 1) * query.page_size,
            "fields": FIELDS,
        }
        data = await get_json(
            f"{BASE}/paper/search", params, headers=_headers(), label="Semantic Scholar"
        )
        return [_to_paper(item) for item in (data.get("data") or [])]

    async def get(self, source_id: str) -> PaperDTO | None:
        try:
            data = await get_json(
                f"{BASE}/paper/{source_id}",
                {"fields": FIELDS},
                headers=_headers(),
                label="Semantic Scholar",
            )
        except SourceError:
            return None
        return _to_paper(data)

    async def get_by_doi(self, doi: str) -> PaperDTO | None:
        return await self.get(f"DOI:{doi}")

    async def related(self, source_id: str, *, limit: int = 10) -> list[PaperDTO]:
        try:
            data = await get_json(
                f"https://api.semanticscholar.org/recommendations/v1/papers/forpaper/{source_id}",
                {"fields": FIELDS, "limit": min(limit, 25)},
                headers=_headers(),
                label="Semantic Scholar",
            )
        except SourceError:
            return []
        return [_to_paper(item) for item in (data.get("recommendedPapers") or [])]
