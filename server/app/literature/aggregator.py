"""聚合层：并行请求多个数据源，合并、去重、排序、分页。

关键行为：
  - 单个源失败/超时不影响其它源（返回部分结果 + 源状态）；
  - 同 DOI / 同标题+年份 的记录只保留一条（字段互补）；
  - 结果按「轮询交错」排序，避免某个源（如 Crossref 一次返回 20 条）
    把其它源的结果全挤到后面；
  - 整次检索结果带 TTL 缓存。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from typing import Any

from app.core.config import settings
from app.literature.base import PaperSource, SourceError
from app.literature.cache import get_cache
from app.literature.dto import PaperDTO, SearchQuery, SearchResponse, SourceState
from app.literature.normalize import dedupe, normalize_doi
from app.literature.ratelimit import limiter_for
from app.literature.registry import available_sources, get_source

logger = logging.getLogger(__name__)


def _cache_key(prefix: str, payload: Any) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return f"{prefix}:{hashlib.sha1(raw.encode('utf-8')).hexdigest()}"


def _interleave(groups: list[list[PaperDTO]]) -> list[PaperDTO]:
    merged: list[PaperDTO] = []
    index = 0
    while True:
        added = False
        for group in groups:
            if index < len(group):
                merged.append(group[index])
                added = True
        if not added:
            break
        index += 1
    return merged


async def _run_source(
    source: PaperSource, query: SearchQuery, limit: int
) -> tuple[SourceState, list[PaperDTO]]:
    started = time.perf_counter()
    try:
        await limiter_for(source.name).acquire()
        items = await asyncio.wait_for(
            source.search(query, limit=limit),
            timeout=settings.LITERATURE_PER_SOURCE_TIMEOUT,
        )
        latency = int((time.perf_counter() - started) * 1000)
        state = SourceState(
            name=source.name, label=source.label, ok=True, count=len(items), latency_ms=latency
        )
        return state, items
    except asyncio.TimeoutError:
        return (
            SourceState(
                name=source.name,
                label=source.label,
                ok=False,
                latency_ms=int((time.perf_counter() - started) * 1000),
                error="请求超时",
            ),
            [],
        )
    except SourceError as exc:
        return (
            SourceState(name=source.name, label=source.label, ok=False, error=str(exc)),
            [],
        )
    except Exception as exc:  # 适配器 bug 不应拖垮整次检索
        logger.exception("数据源 %s 检索异常", source.name)
        return (
            SourceState(name=source.name, label=source.label, ok=False, error=f"内部错误：{exc}"),
            [],
        )


async def search(query: SearchQuery, *, sources: list[str] | None = None) -> SearchResponse:
    """执行一次聚合检索。"""
    q = query.normalized()
    names = [q.source] if q.source else [item.name for item in available_sources()]
    picked: list[PaperSource] = []
    for name in names:
        source = get_source(name)
        if source is not None:
            picked.append(source)
    if not picked:
        raise ValueError(f"未知的数据源：{q.source}")

    key = _cache_key(
        "lit:search",
        {
            "q": q.model_dump(exclude={"page"}),
            "sources": [item.name for item in picked],
        },
    )
    cache = get_cache()
    cached = await cache.get(key)
    if cached is not None:
        response = SearchResponse(**cached)
        response.cached = True
        return response

    results = await asyncio.gather(
        *[_run_source(source, q, q.page_size) for source in picked]
    )
    states = [state for state, _ in results]
    groups = [items for _, items in results]

    merged = dedupe(_interleave(groups))
    if q.sort == "cited":
        merged.sort(key=lambda item: item.cited_by, reverse=True)
    elif q.sort == "year":
        merged.sort(key=lambda item: item.year or 0, reverse=True)

    total = (
        q.page * q.page_size + 1
        if len(merged) >= q.page_size
        else (q.page - 1) * q.page_size + len(merged)
    )
    response = SearchResponse(
        items=merged, total=total, page=q.page, page_size=q.page_size, sources=states
    )
    await cache.set(key, response.model_dump(), ttl=settings.LITERATURE_CACHE_TTL)
    return response


async def get_paper(source_name: str, source_id: str) -> PaperDTO | None:
    source = get_source(source_name)
    if source is None:
        raise ValueError(f"未知的数据源：{source_name}")
    cache = get_cache()
    key = _cache_key("lit:paper", {"source": source.name, "id": source_id})
    cached = await cache.get(key)
    if cached is not None:
        return PaperDTO(**cached)
    paper = await source.get(source_id)
    if paper is not None:
        await cache.set(key, paper.model_dump(), ttl=24 * 3600)
    return paper


async def get_by_doi(doi: str) -> PaperDTO | None:
    """按 DOI 精确取一篇：多源并发，取信息最全的一条。"""
    normalized = normalize_doi(doi)
    if not normalized:
        return None
    cache = get_cache()
    key = _cache_key("lit:doi", {"doi": normalized})
    cached = await cache.get(key)
    if cached is not None:
        return PaperDTO(**cached)

    async def _fetch(source: PaperSource) -> PaperDTO | None:
        try:
            await limiter_for(source.name).acquire()
            return await asyncio.wait_for(
                source.get_by_doi(normalized),
                timeout=settings.LITERATURE_PER_SOURCE_TIMEOUT,
            )
        except Exception:
            return None

    found = [paper for paper in await asyncio.gather(*[_fetch(s) for s in available_sources()]) if paper]
    if not found:
        return None
    best = max(found, key=lambda item: (bool(item.abstract), len(item.authors), bool(item.venue)))
    await cache.set(key, best.model_dump(), ttl=24 * 3600)
    return best


async def related(source_name: str, source_id: str, *, limit: int = 10) -> list[PaperDTO]:
    source = get_source(source_name)
    if source is None:
        raise ValueError(f"未知的数据源：{source_name}")
    key = _cache_key("lit:related", {"source": source_name, "id": source_id, "limit": limit})
    cache = get_cache()
    cached = await cache.get(key)
    if cached is not None:
        return [PaperDTO(**item) for item in cached]
    try:
        await limiter_for(source.name).acquire()
        items = await asyncio.wait_for(
            source.related(source_id, limit=limit),
            timeout=settings.LITERATURE_PER_SOURCE_TIMEOUT,
        )
    except (SourceError, asyncio.TimeoutError):
        items = []
    items = dedupe(items)[:limit]
    await cache.set(key, [item.model_dump() for item in items], ttl=3600)
    return items
