"""论文结构化解析结果 API（M3）。

前端「解析」页读取这里的数据：章节树、元数据、参考文献、表格/图注、质量报告。
真正的解析在文档上传/重建索引时由 pipeline 完成，这里只负责读取。
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.api.chat import SSE_HEADERS
from app.api.deps import CurrentUser, DbSession
from app.api.documents import _get_owned_document
from app.models import (
    Analysis,
    DocumentMetadata,
    DocumentQuality,
    Paper,
    PaperAsset,
    PaperReference,
    PaperSection,
)
from app.rag.engine import sse
from app.schemas_paper import (
    AnalysisKindOut,
    AnalysisOut,
    AnalysisStreamIn,
    AssetOut,
    CitationOut,
    MetadataOut,
    PaperAskIn,
    PaperStructureOut,
    QualityOut,
    ReferenceOut,
    SectionOut,
)
from app.services import analysis as analysis_service
from app.services.sectionizer import section_labels

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/papers", tags=["papers"])


@router.get("/{document_id}/structure", response_model=PaperStructureOut)
async def get_structure(
    document_id: str, user: CurrentUser, db: DbSession
) -> PaperStructureOut:
    """读取一篇文档的结构解析结果（章节/参考文献/表格/质量）。"""
    document = await _get_owned_document(db, document_id, user.id)

    section_rows = (
        await db.execute(
            select(PaperSection)
            .where(PaperSection.document_id == document.id)
            .order_by(PaperSection.ordinal)
        )
    ).scalars().all()
    reference_rows = (
        await db.execute(
            select(PaperReference)
            .where(PaperReference.document_id == document.id)
            .order_by(PaperReference.ordinal)
        )
    ).scalars().all()
    asset_rows = (
        await db.execute(
            select(PaperAsset).where(PaperAsset.document_id == document.id)
        )
    ).scalars().all()
    quality_row = (
        await db.execute(
            select(DocumentQuality).where(DocumentQuality.document_id == document.id)
        )
    ).scalar_one_or_none()

    meta_row = (
        await db.execute(
            select(DocumentMetadata).where(DocumentMetadata.document_id == document.id)
        )
    ).scalar_one_or_none()
    paper = (
        await db.execute(
            select(Paper).where(Paper.source == "upload", Paper.source_id == document.id)
        )
    ).scalar_one_or_none()

    labels = section_labels()
    metadata = MetadataOut()
    if meta_row is not None:
        try:
            authors = [str(name) for name in json.loads(meta_row.authors_json or "[]")]
        except (TypeError, ValueError):
            authors = []
        metadata = MetadataOut(
            title=meta_row.title or "",
            authors=authors,
            doi=meta_row.doi or "",
            year=meta_row.year,
            abstract=meta_row.abstract or "",
            venue=meta_row.venue or "",
        )
    elif paper is not None:
        try:
            authors = [
                item.get("name", "")
                for item in json.loads(paper.authors_json or "[]")
                if isinstance(item, dict) and item.get("name")
            ]
        except (TypeError, ValueError):
            authors = []
        metadata = MetadataOut(
            title=paper.title or "",
            authors=authors,
            doi=paper.doi or "",
            year=paper.year,
            abstract=paper.abstract or "",
            venue=paper.venue or "",
        )

    assets: list[AssetOut] = []
    for row in asset_rows:
        rows: list[list[str]] = []
        if row.kind == "table" and row.content_json:
            try:
                parsed = json.loads(row.content_json)
                if isinstance(parsed, list):
                    rows = [
                        [str(cell) for cell in line]
                        for line in parsed
                        if isinstance(line, list)
                    ]
            except (TypeError, ValueError):
                rows = []
        assets.append(
            AssetOut(
                id=row.id, kind=row.kind, page=row.page, caption=row.caption, rows=rows
            )
        )

    quality = QualityOut()
    if quality_row is not None:
        try:
            warnings = list(json.loads(quality_row.warnings_json or "[]"))
        except (TypeError, ValueError):
            warnings = []
        quality = QualityOut(
            char_count=quality_row.char_count,
            page_count=quality_row.page_count,
            section_count=quality_row.section_count,
            reference_count=quality_row.reference_count,
            table_count=quality_row.table_count,
            figure_count=quality_row.figure_count,
            garbage_ratio=quality_row.garbage_ratio,
            warnings=warnings,
        )

    return PaperStructureOut(
        document_id=document.id,
        name=document.name,
        status=document.status,
        metadata=metadata,
        sections=[
            SectionOut(
                id=row.id,
                type=row.section_type,
                # 类型徽标只在「能补充信息」时才下发：
                #   - other / front 的标题本身就是最好的说明，再给一个「小节/题名与作者」
                #     会和标题重复；
                #   - 标准章节（摘要、方法…）保留中文类型，与英文原标题互补。
                label=(
                    ""
                    if row.section_type in ("other", "front")
                    else labels.get(row.section_type, row.section_type)
                ),
                heading=row.heading,
                ordinal=row.ordinal,
                page_start=row.page_start,
                page_end=row.page_end,
                char_count=len(row.text or ""),
                text=row.text,
            )
            for row in section_rows
        ],
        references=[
            ReferenceOut(
                id=row.id,
                ordinal=row.ordinal,
                raw_text=row.raw_text,
                doi=row.doi,
                year=row.year,
                title=row.title,
            )
            for row in reference_rows
        ],
        assets=assets,
        quality=quality,
    )

# --------------------------------------------------------------------------
# 单篇分析（M4）
# --------------------------------------------------------------------------
def _analysis_out(row: Analysis) -> AnalysisOut:
    try:
        citations = [CitationOut(**item) for item in json.loads(row.citations_json or "[]")]
    except (TypeError, ValueError):
        citations = []
    return AnalysisOut(
        id=row.id,
        document_id=row.document_id,
        kind=row.kind,
        model=row.model,
        status=row.status,
        content_md=row.content_md or "",
        citations=citations,
        updated_at=row.updated_at,
    )


@router.get("/kinds", response_model=list[AnalysisKindOut])
async def list_analysis_kinds(user: CurrentUser) -> list[AnalysisKindOut]:
    """可用的分析维度（前端按这个渲染按钮）。"""
    return [AnalysisKindOut(**item) for item in analysis_service.kinds()]


@router.get("/{document_id}/analyses", response_model=list[AnalysisOut])
async def list_analyses(
    document_id: str, user: CurrentUser, db: DbSession
) -> list[AnalysisOut]:
    """已生成的分析结果（用于前端标记哪些已缓存）。"""
    await _get_owned_document(db, document_id, user.id)
    rows = await analysis_service.list_analyses(db, document_id)
    return [_analysis_out(row) for row in rows]


@router.get("/{document_id}/analysis/{kind}", response_model=AnalysisOut)
async def get_analysis(
    document_id: str, kind: str, user: CurrentUser, db: DbSession
) -> AnalysisOut:
    await _get_owned_document(db, document_id, user.id)
    row = await analysis_service.load_analysis(db, document_id, kind)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="尚未生成该分析")
    return _analysis_out(row)


@router.post("/{document_id}/analysis/{kind}/stream")
async def stream_analysis(
    document_id: str,
    kind: str,
    payload: AnalysisStreamIn,
    user: CurrentUser,
    db: DbSession,
) -> StreamingResponse:
    document = await _get_owned_document(db, document_id, user.id)

    async def source():
        async for event in analysis_service.stream_analysis(
            db, user, document, kind, model_id=payload.model_id, force=payload.force
        ):
            yield sse(event)

    return StreamingResponse(
        source(), media_type="text/event-stream; charset=utf-8", headers=SSE_HEADERS
    )


@router.post("/{document_id}/ask/stream")
async def ask_paper(
    document_id: str, payload: PaperAskIn, user: CurrentUser, db: DbSession
) -> StreamingResponse:
    """论文范围内的章节问答（不落库，按需检索原文作答）。"""
    document = await _get_owned_document(db, document_id, user.id)

    async def source():
        async for event in analysis_service.stream_ask(
            db,
            user,
            document,
            payload.content,
            section=payload.section,
            model_id=payload.model_id,
        ):
            yield sse(event)

    return StreamingResponse(
        source(), media_type="text/event-stream; charset=utf-8", headers=SSE_HEADERS
    )
