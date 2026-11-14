"""OpenAlex 适配器。

文档：https://docs.openalex.org/
特点：覆盖广、免费、支持年份/引用数/相关论文过滤；摘要以倒排索引返回，
需要还原成正常文本。生产环境建议配置 `LITERATURE_MAILTO` 进入 polite pool。
"""

from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.literature.base import PaperSource, SourceError
from app.literature.dto import AuthorDTO, OaInfo, PaperDTO, SearchQuery
from app.literature.http import get_json

BASE = "https://api.openalex.org"


def _abstract_from_inverted(index: dict[str, list[int]] | None) -> str:
    """OpenAlex 的 abstract_inverted_index → 正常摘要。"""
    if not index:
        return ""
    positions: list[tuple[int, str]] = []
    for word, slots in index.items():
        for slot in slots or []:
            positions.append((int(slot), word))
    positions.sort(key=lambda item: item[0])
    return " ".join(word for _, word in positions)


def _venue(work: dict[str, Any]) -> str:
    primary = work.get("primary_location") or {}
    source = primary.get("source") or {}
    return source.get("display_name") or ""


def _oa(work: dict[str, Any]) -> OaInfo:
    oa = work.get("open_access") or {}
    primary = work.get("primary_location") or {}
    best = work.get("best_oa_location") or {}
    pdf_url = best.get("pdf_url") or primary.get("pdf_url") or ""
    landing = oa.get("oa_url") or primary.get("landing_page_url") or ""
    return OaInfo(is_oa=bool(oa.get("is_oa")), pdf_url=pdf_url or "", landing_url=landing or "")


def _to_paper(work: dict[str, Any]) -> PaperDTO:
    work_id = str(work.get("id") or "").rsplit("/", 1)[-1]
    authors: list[AuthorDTO] = []
    for authorship in work.get("authorships") or []:
        author = authorship.get("author") or {}
        institutions = authorship.get("institutions") or []
        authors.append(
            AuthorDTO(
                name=author.get("display_name") or "",
                affiliation=(institutions[0].get("display_name") if institutions else "") or "",
                orcid=(author.get("orcid") or "").rsplit("/", 1)[-1],
            )
        )
    fields = [
        (topic.get("display_name") or "")
        for topic in (work.get("topics") or [])[:5]
        if topic.get("display_name")
    ]
    doi = (work.get("doi") or "").replace("https://doi.org/", "")
    return PaperDTO(
        id=f"openalex:{work_id}",
        source="openalex",
        source_id=work_id,
        doi=doi,
        title=(work.get("title") or work.get("display_name") or "").strip(),
        abstract=_abstract_from_inverted(work.get("abstract_inverted_index")),
        authors=authors,
        venue=_venue(work),
        year=work.get("publication_year"),
        cited_by=int(work.get("cited_by_count") or 0),
        fields=fields,
        open_access=_oa(work),
        url=work.get("id") or "",
        type=(work.get("type") or "article"),
    )


class OpenAlexSource(PaperSource):
    name = "openalex"
    label = "OpenAlex"

    def _params(self, query: SearchQuery, limit: int) -> dict[str, Any]:
        params: dict[str, Any] = {
            "per-page": min(limit, 50),
            "page": query.page,
        }
        if settings.LITERATURE_MAILTO:
            params["mailto"] = settings.LITERATURE_MAILTO
        if settings.OPENALEX_API_KEY:
            params["api_key"] = settings.OPENALEX_API_KEY

        filters: list[str] = []
        if query.year_from:
            filters.append(f"from_publication_date:{query.year_from}-01-01")
        if query.year_to:
            filters.append(f"to_publication_date:{query.year_to}-12-31")
        if query.author:
            filters.append(f"raw_author_name.search:{query.author}")
        if query.venue:
            filters.append(f"primary_location.source.display_name.search:{query.venue}")
        if filters:
            params["filter"] = ",".join(filters)

        if query.sort == "cited":
            params["sort"] = "cited_by_count:desc"
        elif query.sort == "year":
            params["sort"] = "publication_date:desc"
        else:
            params["sort"] = "relevance_score:desc"

        if query.doi:
            # DOI 查询走 filter，比全文搜索精确
            params.pop("sort", None)
            params["filter"] = ",".join(filters + [f"doi:{query.doi.lower()}"])
        elif query.q:
            params["search"] = query.q
        return params

    async def search(self, query: SearchQuery, *, limit: int) -> list[PaperDTO]:
        data = await get_json(f"{BASE}/works", self._params(query, limit), label="OpenAlex")
        results = data.get("results") or []
        return [_to_paper(item) for item in results]

    async def get(self, source_id: str) -> PaperDTO | None:
        try:
            data = await get_json(f"{BASE}/works/{source_id}", label="OpenAlex")
        except SourceError:
            return None
        return _to_paper(data)

    async def get_by_doi(self, doi: str) -> PaperDTO | None:
        try:
            data = await get_json(
                f"{BASE}/works/https://doi.org/{doi}", label="OpenAlex"
            )
        except SourceError:
            return None
        return _to_paper(data)

    async def related(self, source_id: str, *, limit: int = 10) -> list[PaperDTO]:
        params: dict[str, Any] = {
            "filter": f"related_to:{source_id}",
            "per-page": min(limit, 25),
        }
        if settings.LITERATURE_MAILTO:
            params["mailto"] = settings.LITERATURE_MAILTO
        data = await get_json(f"{BASE}/works", params, label="OpenAlex")
        return [_to_paper(item) for item in (data.get("results") or [])]
