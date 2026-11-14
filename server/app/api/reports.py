# -*- coding: utf-8 -*-
"""学术成果生成与导出 API：/api/reports。

导出格式：
  - md   ：原始 Markdown
  - docx ：python-docx 生成的真 DOCX
  - html ：打印视图（浏览器「另存为 PDF」即可得到 PDF）
"""
from __future__ import annotations

import io
import json
from urllib.parse import quote
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.models import Comparison, Document, KnowledgeBase, Report
from app.schemas import OkOut, ReportCreateIn, ReportOut
from app.services import access, reports
from app.tasks import dispatch_report

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/reports", tags=["reports"])

MAX_PAPERS = 8


def _loads(text: str, default):
    try:
        return json.loads(text) if text else default
    except (TypeError, ValueError):
        return default


def report_out(report: Report) -> dict:
    return {
        "id": report.id,
        "kind": report.kind,
        "title": report.title,
        "status": report.status,
        "stage": report.stage,
        "progress": int(report.progress or 0),
        "error": report.error or "",
        "documentIds": _loads(report.document_ids_json, []),
        "comparisonId": report.comparison_id or "",
        "contentMd": report.content_md or "",
        "sources": _loads(report.sources_json, []),
        "references": _loads(report.refs_json, {}),
        "createdAt": report.created_at.isoformat() if report.created_at else None,
        "updatedAt": report.updated_at.isoformat() if report.updated_at else None,
    }


async def _owned(db: DbSession, report_id: str, user_id: str) -> Report:
    report = (
        await db.execute(select(Report).where(Report.id == report_id))
    ).scalar_one_or_none()
    if report is None or report.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="报告不存在")
    return report


@router.post("", response_model=ReportOut)
async def create_report(
    payload: ReportCreateIn, user: CurrentUser, db: DbSession
) -> ReportOut:
    kind = (payload.kind or "").strip()
    if kind not in reports.KINDS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"报告类型必须是 {', '.join(reports.KINDS)} 之一",
        )

    # 对比报告：直接引用已有对比
    if kind == "comparison":
        if not payload.comparison_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="缺少 comparisonId"
            )
        comparison = (
            await db.execute(
                select(Comparison).where(Comparison.id == payload.comparison_id)
            )
        ).scalar_one_or_none()
        if comparison is None or comparison.user_id != user.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="对比记录不存在"
            )
        report = await reports.create_report(
            db,
            user_id=user.id,
            kind=kind,
            document_ids=_loads(comparison.document_ids_json, []),
            title=comparison.topic or "多论文对比报告",
            comparison_id=comparison.id,
            team_id=comparison.team_id or "",
        )
        dispatch_report(report.id)
        return ReportOut(**report_out(report))

    document_ids = list(dict.fromkeys(payload.document_ids or []))
    if not document_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="至少选择一篇论文"
        )
    if len(document_ids) > MAX_PAPERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"一次最多 {MAX_PAPERS} 篇",
        )
    if kind == "reading" and len(document_ids) != 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="阅读报告只能针对单篇论文",
        )

    team_ids = await access.member_team_ids(db, user.id)
    rows = list(
        (
            await db.execute(
                select(Document)
                .join(KnowledgeBase, Document.knowledge_base_id == KnowledgeBase.id)
                .where(Document.id.in_(document_ids))
                .where(access.accessible_condition(user.id, team_ids))
            )
        ).scalars()
    )
    if len(rows) != len(document_ids):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="部分论文不存在或你无权访问",
        )
    missing = [d.name for d in rows if not d.stored_path or not Path(d.stored_path).exists()]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"这些论文的原始文件已丢失：{', '.join(missing[:3])}",
        )

    team_id = ""
    base_ids = {d.knowledge_base_id for d in rows}
    if len(base_ids) == 1:
        bases = (
            await db.execute(select(KnowledgeBase).where(KnowledgeBase.id.in_(base_ids)))
        ).scalars().all()
        if bases and (bases[0].owner_type or access.OWNER_USER) == access.OWNER_TEAM:
            team_id = bases[0].owner_id

    report = await reports.create_report(
        db,
        user_id=user.id,
        kind=kind,
        document_ids=[d.id for d in rows],
        title=payload.title or "",
        team_id=team_id,
    )
    dispatch_report(report.id)
    return ReportOut(**report_out(report))


@router.get("", response_model=list[ReportOut])
async def list_reports(user: CurrentUser, db: DbSession) -> list[ReportOut]:
    rows = list(
        (
            await db.execute(
                select(Report)
                .where(Report.user_id == user.id)
                .order_by(Report.created_at.desc())
                .limit(50)
            )
        ).scalars()
    )
    return [ReportOut(**report_out(row)) for row in rows]


@router.get("/{report_id}", response_model=ReportOut)
async def get_report(report_id: str, user: CurrentUser, db: DbSession) -> ReportOut:
    report = await _owned(db, report_id, user.id)
    return ReportOut(**report_out(report))


@router.post("/{report_id}/rerun", response_model=ReportOut)
async def rerun_report(report_id: str, user: CurrentUser, db: DbSession) -> ReportOut:
    report = await _owned(db, report_id, user.id)
    report.status = "pending"
    report.stage = "cards"
    report.progress = 0
    report.error = ""
    await db.commit()
    await db.refresh(report)
    dispatch_report(report.id)
    return ReportOut(**report_out(report))


@router.delete("/{report_id}", response_model=OkOut)
async def delete_report(report_id: str, user: CurrentUser, db: DbSession) -> OkOut:
    report = await _owned(db, report_id, user.id)
    await db.delete(report)
    await db.commit()
    return OkOut(ok=True)


@router.get("/{report_id}/export")
async def export_report(
    report_id: str,
    user: CurrentUser,
    db: DbSession,
    format: str = Query("md", pattern="^(md|docx|html)$"),
) -> Response:
    """导出报告：md / docx / html（html 用于浏览器打印成 PDF）。"""
    report = await _owned(db, report_id, user.id)
    if not report.content_md:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="报告内容尚未生成（任务可能还在进行或已失败）",
        )

    title = report.title or "report"
    safe_title = "".join(ch for ch in title if ch not in '\\/:*?"<>|')[:60] or "report"

    if format == "md":
        return Response(
            content=report.content_md.encode("utf-8"),
            media_type="text/markdown; charset=utf-8",
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{quote(safe_title)}.md"
            },
        )

    if format == "html":
        html = reports.to_html(report.content_md, title)
        return Response(
            content=html.encode("utf-8"),
            media_type="text/html; charset=utf-8",
        )

    # DOCX
    try:
        document = reports.to_docx(report.content_md, title)
        buffer = io.BytesIO()
        document.save(buffer)
    except Exception as exc:
        logger.exception("DOCX 生成失败 %s", report_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"DOCX 生成失败：{exc}",
        ) from exc

    return Response(
        content=buffer.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(safe_title)}.docx"},
    )
