# -*- coding: utf-8 -*-
"""M3 结构解析的单元测试（不联网、不连库）。

覆盖：章节识别（中英/编号）、元数据抽取、参考文献切分、
章节感知切片的元数据透传。
"""
from __future__ import annotations

from langchain_core.documents import Document

from app.services import chunking, paper_meta, references, sectionizer
from app.services.assets import _is_meaningful_table

EN_PAPER = """Graph Neural Networks for Molecules
Alice Zhang, Bob Li
Department of Computer Science, Example University
© 2021 Example Press
Abstract
We study graph neural networks for molecular property prediction.
1 Introduction
Graphs are everywhere in chemistry.
2 Method
We use message passing with edge features.
3 Experiments
We evaluate on QM9 and ZINC.
4 Conclusion
GNNs work well.
References
[1] A. Author. Learning on graphs. Nature, 2021. doi:10.1038/abc123.
[2] B. Author. Graph nets. ICML, 2020.
"""

CN_PAPER = """基于图神经网络的分子性质预测
张三, 李四
某大学计算机学院
摘要
本文研究图神经网络在分子性质预测中的应用。
一、引言
图结构广泛存在于化学领域。
2 方法
我们使用消息传递机制。
3 实验
在 QM9 数据集上验证。
4 结论
方法有效。
参考文献
[1] 张三. 图神经网络综述. 计算机学报, 2021.
"""


def _docs(text: str) -> list[Document]:
    return [Document(page_content=text, metadata={"page_label": 1})]


def test_sectionizer_english_headings() -> None:
    sections = sectionizer.build_sections(_docs(EN_PAPER))
    types = [section.section_type for section in sections]
    for expected in ("abstract", "introduction", "method", "experiment", "conclusion", "references"):
        assert expected in types
    assert types[0] == "front"
    assert sections[0].text.startswith("Graph Neural Networks")


def test_sectionizer_chinese_headings() -> None:
    types = [section.section_type for section in sectionizer.build_sections(_docs(CN_PAPER))]
    for expected in ("abstract", "introduction", "method", "experiment", "conclusion", "references"):
        assert expected in types


def test_sectionizer_falls_back_to_single_section() -> None:
    sections = sectionizer.build_sections(_docs("这是一段没有章节标题的普通文本。" * 5))
    assert len(sections) == 1
    assert sections[0].section_type == "other"


def test_metadata_title_authors_doi_year() -> None:
    documents = _docs(EN_PAPER)
    sections = sectionizer.build_sections(documents)
    meta = paper_meta.extract(documents, sections)
    assert meta.title == "Graph Neural Networks for Molecules"
    assert "Alice Zhang" in meta.authors and "Bob Li" in meta.authors
    assert all("University" not in author for author in meta.authors)
    assert meta.doi == "10.1038/abc123"
    assert meta.year == 2021
    assert "molecular property" in meta.abstract


def test_metadata_without_abstract_section() -> None:
    documents = _docs("A Short Paper Title\nJohn Smith\n")
    meta = paper_meta.extract(documents, [])
    assert meta.title == "A Short Paper Title"
    assert meta.abstract == ""


def test_references_are_split_and_enriched() -> None:
    sections = sectionizer.build_sections(_docs(EN_PAPER))
    refs = references.extract(sections)
    assert len(refs) == 2
    assert refs[0].doi == "10.1038/abc123"
    assert refs[0].year == 2021
    assert "Learning on graphs" in refs[0].raw_text


def test_references_empty_when_no_section() -> None:
    assert references.extract(sectionizer.build_sections(_docs("no refs here " * 20))) == []


def test_split_sections_carries_metadata() -> None:
    sections = sectionizer.build_sections(_docs(EN_PAPER))
    chunks = chunking.split_sections(sections, chunk_size=120, chunk_overlap=10)
    assert chunks
    for chunk in chunks:
        assert "section" in chunk.metadata
        assert "page_start" in chunk.metadata
        assert chunk.page_content.strip()


def test_fake_table_from_two_column_text_is_rejected() -> None:
    """双栏正文常被 pdfplumber 误判成「左列空、右列一句话」的表格。"""
    rows = [
        ["", "ponents jointly, enabling better alignment between the retrieved information"],
        ["generated output. RAG (Lewis et al. 2020) further extended this paradigm", ""],
        ["retrieval (Karpukhin et al., 2020) to fetch relevant", ""],
    ]
    assert _is_meaningful_table(rows) is False


def test_real_table_is_kept() -> None:
    rows = [
        ["Model", "Accuracy", "F1"],
        ["BM25", "0.81", "0.79"],
        ["DPR", "0.87", "0.85"],
    ]
    assert _is_meaningful_table(rows) is True
