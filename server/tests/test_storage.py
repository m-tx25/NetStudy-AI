# -*- coding: utf-8 -*-
"""上传校验与存储配额的单元测试（不联网、不连库）。"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi import HTTPException

from app.services import storage, uploads


def _call_validate(path: Path, suffix: str):
    asyncio.run(uploads._validate_content(path, suffix))


def _make_pdf(path: Path, pages: int = 1) -> None:
    from pypdf import PdfWriter

    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=72, height=72)
    with path.open("wb") as handle:
        writer.write(handle)


def test_human_bytes() -> None:
    assert storage.human_bytes(0) == "0B"
    assert storage.human_bytes(1024) == "1.0KB"
    assert storage.human_bytes(5 * 1024**3) == "5.0GB"


def test_valid_pdf_passes(tmp_path: Path) -> None:
    target = tmp_path / "ok.pdf"
    _make_pdf(target, pages=2)
    _call_validate(target, ".pdf")  # 不抛异常即通过


def test_pdf_without_magic_is_rejected(tmp_path: Path) -> None:
    target = tmp_path / "bad.pdf"
    target.write_bytes(b"this is not a pdf")
    with pytest.raises(HTTPException) as info:
        _call_validate(target, ".pdf")
    assert info.value.status_code == 400
    assert "PDF" in info.value.detail


def test_pdf_without_eof_is_rejected(tmp_path: Path) -> None:
    target = tmp_path / "truncated.pdf"
    target.write_bytes(b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n")
    with pytest.raises(HTTPException) as info:
        _call_validate(target, ".pdf")
    assert "不完整" in info.value.detail


def test_docx_must_be_zip(tmp_path: Path) -> None:
    target = tmp_path / "bad.docx"
    target.write_bytes(b"not a zip file")
    with pytest.raises(HTTPException) as info:
        _call_validate(target, ".docx")
    assert info.value.status_code == 400


def test_binary_text_file_is_rejected(tmp_path: Path) -> None:
    target = tmp_path / "fake.md"
    target.write_bytes(b"hello\x00world")
    with pytest.raises(HTTPException) as info:
        _call_validate(target, ".md")
    assert "文本" in info.value.detail


def test_utf8_text_file_is_accepted(tmp_path: Path) -> None:
    target = tmp_path / "note.md"
    target.write_text("# 标题\n\n正文", encoding="utf-8")
    _call_validate(target, ".md")


def test_max_upload_default_is_100mb() -> None:
    from app.core.config import settings

    assert settings.MAX_UPLOAD_SIZE_MB >= 100
