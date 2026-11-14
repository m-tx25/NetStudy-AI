"""学术文献检索 API。

只负责「发现」：检索、详情、相关推荐。把论文导入个人文献库属于 M2，
见后续 `api/library.py`。
"""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import CurrentUser, DbSession
from app.literature import aggregator
from app.literature.dto import PaperDTO, SearchQuery, SearchResponse
from app.literature.registry import available_sources
from app.models import SearchLog
from app.utils.ids import new_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/literature", tags=["literature"])


@router.get("/sources")
async def list_sources(user: CurrentUser) -> dict:
    """可用数据源清单（前端筛选下拉用）。"""
    return {
        "sources": [
            {"name": source.name, "label": source.label} for source in available_sources()
        ]
    }


@router.get("/search", response_model=SearchResponse)
async def search_literature(
    user: CurrentUser,
    db: DbSession,
    q: str = "",
    author: str = "",
    doi: str = "",
    year_from: int | None = Query(default=None, alias="yearFrom"),
    year_to: int | None = Query(default=None, alias="yearTo"),
    venue: str = "",
    field: str = "",
    source: str = "",
    sort: str = "relevance",
    page: int = 1,
    page_size: int = Query(default=20, alias="pageSize"),
) -> SearchResponse:
    """聚合检索学术论文。

    参数至少给一个：关键词、作者、DOI。年份区间与期刊/领域是可选的过滤条件。
    """
    query = SearchQuery(
        q=q.strip(),
        author=author.strip(),
        doi=doi.strip(),
        year_from=year_from,
        year_to=year_to,
        venue=venue.strip(),
        field=field.strip(),
        source=source.strip(),
        sort=sort,
        page=page,
        page_size=page_size,
    )
    if query.is_empty:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请输入检索关键词、作者或 DOI",
        )

    started = time.perf_counter()
    try:
        response = await aggregator.search(query)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    latency = int((time.perf_counter() - started) * 1000)
    # 检索日志属于「有了更好」：写入失败不影响本次结果
    try:
        db.add(
            SearchLog(
                id=new_id("search"),
                user_id=user.id,
                query_json=query.model_dump_json(),
                sources=",".join(state.name for state in response.sources if state.ok),
                result_count=len(response.items),
                latency_ms=latency,
            )
        )
        await db.commit()
    except Exception:  # noqa: BLE001 - 日志失败不能影响检索
        await db.rollback()
        logger.warning("写入检索日志失败", exc_info=True)

    return response


@router.get("/paper", response_model=PaperDTO)
async def get_paper(
    user: CurrentUser,
    source: str = Query(..., description="数据源名，如 crossref / arxiv / openalex"),
    id: str = Query(..., description="数据源内部 id"),
) -> PaperDTO:
    """按「数据源 + 内部 id」取单篇详情。"""
    try:
        paper = await aggregator.get_paper(source, id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if paper is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到该论文")
    return paper


@router.get("/doi", response_model=PaperDTO)
async def get_paper_by_doi(user: CurrentUser, doi: str = Query(...)) -> PaperDTO:
    """按 DOI 精确取单篇（多源并发，取信息最全的一条）。"""
    paper = await aggregator.get_by_doi(doi)
    if paper is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="该 DOI 未检索到论文")
    return paper


@router.get("/related", response_model=list[PaperDTO])
async def get_related(
    user: CurrentUser,
    source: str = Query(...),
    id: str = Query(...),
    limit: int = Query(default=10, ge=1, le=25),
) -> list[PaperDTO]:
    """相关论文推荐（数据源不支持时返回空列表）。"""
    try:
        return await aggregator.related(source, id, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
