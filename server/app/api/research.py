# -*- coding: utf-8 -*-
"""学术研究辅助 API：/api/research/briefs。

权限与对比一致：只有创建者可见；创建时逐篇校验论文归属。
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.models import Document, KnowledgeBase, ResearchBrief
from app.schemas import OkOut, ResearchBriefCreateIn, ResearchBriefOut
from app.services import access, research
from app.tasks import dispatch_research

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/research", tags=["research"])

MAX_PAPERS = 8


def _loads(text: str, default):
    try:
        return json.loads(text) if text else default
    except (TypeError, ValueError):
        return default


def _as_dict(text: str) -> dict:
    """JSON 列里可能存着 ``[]``（模型默认值），但契约要求对象 —— 统一兜底成 {}。"""
    value = _loads(text, {})
    return value if isinstance(value, dict) else {}


def brief_out(brief: ResearchBrief) -> dict:
    return {
        "id": brief.id,
        "goal": brief.goal,
        "status": brief.status,
        "stage": brief.stage,
        "progress": int(brief.progress or 0),
        "error": brief.error or "",
        "documentIds": _loads(brief.document_ids_json, []),
        "directions": _loads(brief.directions_json, []),
        "questions": _loads(brief.questions_json, []),
        "roadmap": _as_dict(brief.roadmap_json),
        "novelty": _as_dict(brief.novelty_json),
        "relatedWork": _as_dict(brief.related_work_json),
        "relatedDocs": _loads(brief.related_docs_json, []),
        "createdAt": brief.created_at.isoformat() if brief.created_at else None,
        "updatedAt": brief.updated_at.isoformat() if brief.updated_at else None,
    }


async def _owned(db: DbSession, brief_id: str, user_id: str) -> ResearchBrief:
    brief = (
        await db.execute(select(ResearchBrief).where(ResearchBrief.id == brief_id))
    ).scalar_one_or_none()
    if brief is None or brief.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="研究任务不存在")
    return brief


@router.post("/briefs", response_model=ResearchBriefOut)
async def create_brief(
    payload: ResearchBriefCreateIn, user: CurrentUser, db: DbSession
) -> ResearchBriefOut:
    document_ids = list(dict.fromkeys(payload.document_ids or []))
    if not document_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="至少选择一篇论文"
        )
    if len(document_ids) > MAX_PAPERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"一次最多 {MAX_PAPERS} 篇（再多模型会顾此失彼）",
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
            await db.execute(
                select(KnowledgeBase).where(KnowledgeBase.id.in_(base_ids))
            )
        ).scalars().all()
        if bases and (bases[0].owner_type or access.OWNER_USER) == access.OWNER_TEAM:
            team_id = bases[0].owner_id

    brief = await research.create_brief(
        db,
        user_id=user.id,
        document_ids=[d.id for d in rows],
        goal=payload.goal or "",
        team_id=team_id,
    )
    dispatch_research(brief.id)
    return ResearchBriefOut(**brief_out(brief))


@router.get("/briefs", response_model=list[ResearchBriefOut])
async def list_briefs(user: CurrentUser, db: DbSession) -> list[ResearchBriefOut]:
    rows = list(
        (
            await db.execute(
                select(ResearchBrief)
                .where(ResearchBrief.user_id == user.id)
                .order_by(ResearchBrief.created_at.desc())
                .limit(50)
            )
        ).scalars()
    )
    return [ResearchBriefOut(**brief_out(row)) for row in rows]


@router.get("/briefs/{brief_id}", response_model=ResearchBriefOut)
async def get_brief(
    brief_id: str, user: CurrentUser, db: DbSession
) -> ResearchBriefOut:
    brief = await _owned(db, brief_id, user.id)
    return ResearchBriefOut(**brief_out(brief))


@router.post("/briefs/{brief_id}/rerun", response_model=ResearchBriefOut)
async def rerun_brief(
    brief_id: str, user: CurrentUser, db: DbSession
) -> ResearchBriefOut:
    brief = await _owned(db, brief_id, user.id)
    brief.status = "pending"
    brief.stage = "cards"
    brief.progress = 0
    brief.error = ""
    await db.commit()
    await db.refresh(brief)
    dispatch_research(brief.id)
    return ResearchBriefOut(**brief_out(brief))


@router.delete("/briefs/{brief_id}", response_model=OkOut)
async def delete_brief(
    brief_id: str, user: CurrentUser, db: DbSession
) -> OkOut:
    brief = await _owned(db, brief_id, user.id)
    await db.delete(brief)
    await db.commit()
    return OkOut(ok=True)


@router.get("/briefs/{brief_id}/report.md")
async def download_report(
    brief_id: str, user: CurrentUser, db: DbSession
) -> Response:
    brief = await _owned(db, brief_id, user.id)
    if not brief.report_md:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="报告尚未生成（任务可能还在进行或已失败）",
        )
    return Response(
        content=brief.report_md.encode("utf-8"),
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="research-{brief.id}.md"'
        },
    )
