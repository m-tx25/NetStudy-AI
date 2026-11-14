# -*- coding: utf-8 -*-
"""M4 单篇分析的纯函数测试（不联网、不连库）。"""
from __future__ import annotations

from types import SimpleNamespace

from app.services import analysis


def _chunk(index: int, *, page: int | None = 3, section: str = "method", content: str = "正文片段"):
    return SimpleNamespace(
        chunk_id=f"doc_x:{index:05d}",
        page=page,
        section=section,
        content=content,
    )


def test_kinds_cover_nine_dimensions() -> None:
    items = analysis.kinds()
    assert len(items) == 9
    labels = {item["kind"]: item["label"] for item in items}
    assert labels["summary"] == "论文速览"
    assert labels["limitations"] == "局限性"
    assert labels["glossary"] == "关键术语"


def test_build_evidence_numbers_and_labels() -> None:
    text, items = analysis.build_evidence(
        [_chunk(1, page=2, section="abstract", content="摘要内容"), _chunk(2, page=5, section="method")]
    )
    assert text.startswith("[1]（第 2 页 · 摘要）")
    assert "[2]（第 5 页 · 研究方法）" in text
    assert [item["index"] for item in items] == [1, 2]
    assert items[0]["chunkId"] == "doc_x:00001"


def test_build_evidence_truncates_long_snippet() -> None:
    _, items = analysis.build_evidence([_chunk(1, content="长" * 2000)])
    assert len(items[0]["snippet"]) == 700


def test_citations_follow_first_appearance_and_drop_unknown() -> None:
    evidence = [
        {"index": 1, "page": 1},
        {"index": 2, "page": 2},
        {"index": 3, "page": 3},
    ]
    text = "结论 A[2]，结论 B[1][2]，越界[9]。"
    result = analysis.citations_from_text(text, evidence)
    assert [item["index"] for item in result] == [2, 1]


def test_citations_empty_when_model_gives_none() -> None:
    assert analysis.citations_from_text("没有引用的回答", [{"index": 1}]) == []
