# -*- coding: utf-8 -*-
"""文献检索层单元测试（不联网、不连库）。

覆盖：DOI/标题归一化、跨源去重择优、查询参数裁剪、聚合层降级与源状态。
外部适配器（OpenAlex/Crossref/arXiv）由 respx 之类做集成测试，这里只测
「不依赖网络也一定会错」的纯逻辑，保证 CI 快速回归。
"""
from __future__ import annotations

import asyncio

from app.literature import aggregator
from app.literature.base import PaperSource
from app.literature.dto import AuthorDTO, PaperDTO, SearchQuery
from app.literature.normalize import dedupe, normalize_doi, normalize_title


def _paper(**overrides) -> PaperDTO:
    base = {
        "id": "x:1",
        "source": "x",
        "source_id": "1",
        "title": "T",
        "year": 2020,
    }
    base.update(overrides)
    return PaperDTO(**base)


def test_normalize_doi_strips_prefix_and_lowercases() -> None:
    assert normalize_doi("https://doi.org/10.1038/NATURE12373") == "10.1038/nature12373"
    assert normalize_doi("doi: 10.1/ABC") == "10.1/abc"
    assert normalize_doi(None) == ""


def test_normalize_title_removes_punctuation_and_spaces() -> None:
    assert normalize_title("A  Study: of  Transformers!") == "a study of transformers"


def test_dedupe_merges_same_doi_and_keeps_richer_record() -> None:
    thin = _paper(id="a:1", source="a", source_id="1", doi="10.1/x", title="Same")
    rich = _paper(
        id="b:2",
        source="b",
        source_id="2",
        doi="10.1/X",
        title="Same",
        abstract="long abstract",
        authors=[AuthorDTO(name="Ada")],
        cited_by=10,
    )
    merged = dedupe([thin, rich])
    assert len(merged) == 1
    assert merged[0].abstract == "long abstract"
    assert merged[0].cited_by == 10
    assert merged[0].authors[0].name == "Ada"


def test_dedupe_falls_back_to_title_and_year() -> None:
    first = _paper(id="a:1", source="a", source_id="1", title="Deep Learning", year=2015)
    second = _paper(id="b:2", source="b", source_id="2", title="deep  learning!", year=2015)
    assert len(dedupe([first, second])) == 1


def test_dto_serializes_camel_case() -> None:
    payload = _paper(doi="10.1/x", open_access={"is_oa": True}).model_dump(by_alias=True)
    assert payload["sourceId"] == "1"
    assert payload["openAccess"] is True or payload["openAccess"]["isOa"] is True


def test_query_normalized_clamps_pagination() -> None:
    query = SearchQuery(q="x", page=0, page_size=999).normalized()
    assert query.page == 1
    assert query.page_size == 50


class _FakeSource(PaperSource):
    def __init__(self, name: str, items: list[PaperDTO]) -> None:
        self.name = name
        self.label = name
        self.items = items
        self.calls = 0

    async def search(self, query: SearchQuery, *, limit: int) -> list[PaperDTO]:
        self.calls += 1
        return self.items


class _BrokenSource(PaperSource):
    name = "broken"
    label = "Broken"

    async def search(self, query: SearchQuery, *, limit: int) -> list[PaperDTO]:
        raise RuntimeError("boom")


def test_aggregator_merges_sources_and_reports_status(monkeypatch) -> None:
    first = _FakeSource("fake_a", [_paper(id="fake_a:1", source="fake_a", source_id="1", doi="10.1/dup", title="A")])
    second = _FakeSource("fake_b", [_paper(id="fake_b:1", source="fake_b", source_id="1", doi="10.1/DUP", title="A")])
    monkeypatch.setattr(aggregator, "available_sources", lambda: [first, second])
    monkeypatch.setattr(
        aggregator, "get_source", lambda name: {"fake_a": first, "fake_b": second}.get(name)
    )
    response = asyncio.run(aggregator.search(SearchQuery(q="unique-aggregator-query")))
    assert len(response.items) == 1
    assert {state.name for state in response.sources} == {"fake_a", "fake_b"}
    assert all(state.ok for state in response.sources)


def test_aggregator_degrades_when_one_source_fails(monkeypatch) -> None:
    good = _FakeSource("fake_good", [_paper(id="fake_good:1", source="fake_good", source_id="1", title="OK")])
    bad = _BrokenSource()
    monkeypatch.setattr(aggregator, "available_sources", lambda: [good, bad])
    monkeypatch.setattr(
        aggregator, "get_source", lambda name: {"fake_good": good, "broken": bad}.get(name)
    )
    response = asyncio.run(aggregator.search(SearchQuery(q="unique-degrade-query")))
    assert len(response.items) == 1
    states = {state.name: state for state in response.sources}
    assert states["fake_good"].ok is True
    assert states["broken"].ok is False
    assert states["broken"].error
