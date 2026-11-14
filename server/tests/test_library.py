# -*- coding: utf-8 -*-
"""引用导出格式的单元测试（纯函数，不联网）。"""
from __future__ import annotations

import pytest

from app.literature.dto import AuthorDTO, PaperDTO
from app.services.citation import format_citation, to_apa, to_bibtex, to_gbt7714, to_ris


def _paper(**overrides) -> PaperDTO:
    base = dict(
        id="crossref:10.1/x",
        source="crossref",
        source_id="10.1/x",
        title="Graph neural networks",
        doi="10.1/x",
        venue="Nature Reviews Methods Primers",
        year=2024,
        authors=[AuthorDTO(name="Gabriele Corso"), AuthorDTO(name="Hannes Stark")],
        url="https://doi.org/10.1/x",
    )
    base.update(overrides)
    return PaperDTO(**base)


def test_bibtex_contains_key_fields() -> None:
    text = to_bibtex(_paper())
    assert text.startswith("@article{corso2024graph,")
    assert "title = {Graph neural networks}" in text
    assert "author = {Gabriele Corso and Hannes Stark}" in text
    assert "doi = {10.1/x}" in text


def test_bibtex_without_year_and_authors() -> None:
    text = to_bibtex(_paper(year=None, authors=[], doi=""))
    assert "@article{unknownnd" in text
    assert "year" not in text


def test_ris_has_record_envelope() -> None:
    text = to_ris(_paper())
    assert text.startswith("TY  - JOUR")
    assert "TI  - Graph neural networks" in text
    assert text.rstrip().endswith("ER  -")


def test_apa_formats_authors_and_doi() -> None:
    text = to_apa(_paper())
    assert "Gabriele Corso, & Hannes Stark (2024)." in text
    assert "https://doi.org/10.1/x" in text


def test_gbt7714_marks_document_type() -> None:
    text = to_gbt7714(_paper())
    assert "Graph neural networks[J]." in text
    assert "DOI:10.1/x." in text


def test_unknown_format_raises() -> None:
    with pytest.raises(ValueError):
        format_citation(_paper(), "mla")


def test_alias_formats() -> None:
    assert format_citation(_paper(), "gb") == format_citation(_paper(), "gbt7714")
    assert format_citation(_paper(), "bib") == format_citation(_paper(), "bibtex")
