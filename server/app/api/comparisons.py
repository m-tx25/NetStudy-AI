# -*- coding: utf-8 -*-
"""多篇论文对比：/api/comparisons/* 与 /api/papers/*。

权限口径与文档接口一致：
  - 创建对比时逐篇校验「当前用户能否访问该文档」；
  - 查询/删除对比记录只能看到自己创建的（团队共享留到后续迭代）；
  - 论文卡片按 document_id 缓存，重复抽取需显式 refresh。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.models import Comparison, Document, KnowledgeBase, PaperProfile
from app.schemas import (
    ComparisonCreateIn,
    ComparisonOut,
    OkOut,
    PaperProfileOut,
)
from app.services import access, compare
from app.tasks import dispatch_comparison

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/comparisons", tags=["comparisons"])
paper_router = APIRouter(prefix="/papers", tags=["papers"])

MAX_PAPERS = 6


def _loads(text: str, default):
    try:
        return json.loads(text) if text else default
    except (TypeError, ValueError):
        return default


def comparison_out(comparison: Comparison) -> dict:
    return {
        "id": comparison.id,
        "topic": comparison.topic,
        "status": comparison.status,
        "stage": comparison.stage,
        "progress": int(comparison.progress or 0),
        "error": comparison.error or "",
        "documentIds": _loads(comparison.document_ids_json, []),
        "dimensions": _loads(comparison.dimensions_json, []),
        "matrix": _loads(comparison.matrix_json, []),
        "trends": _loads(comparison.trends_json, {}),
        "gaps": _loads(comparison.gaps_json, []),
        "verdict": comparison.verdict or "",
        "scenarios": _loads(comparison.scenarios_json, []),
        "createdAt": comparison.created_at.isoformat() if comparison.created_at else None,
        "updatedAt": comparison.updated_at.isoformat() if comparison.updated_at else None,
    }


def profile_out(profile: PaperProfile) -> dict:
    return {
        "documentId": profile.document_id,
        "status": profile.status,
        "title": profile.title,
        "authors": profile.authors,
        "year": int(profile.year or 0),
        "venue": profile.venue,
        "researchProblem": profile.research_problem,
        "methodFamily": profile.method_family,
        "keyTechnique": profile.key_technique,
        "dataset": profile.dataset,
        "mainResults": profile.main_results,
        "metrics": _loads(profile.metrics_json, []),
        "innovations": _loads(profile.innovations_json, []),
        "limitations": _loads(profile.limitations_json, []),
        "futureWork": _loads(profile.future_work_json, []),
        "citations": _loads(profile.citations_json, {}),
        "pageCount": int(profile.page_count or 0),
        "error": profile.error or "",
    }


async def _get_owned_comparison(
    db: DbSession, comparison_id: str, user_id: str
) -> Comparison:
    comparison = (
        await db.execute(select(Comparison).where(Comparison.id == comparison_id))
    ).scalar_one_or_none()
    # 不区分「不存在」与「别人的」，统一 404，避免暴露存在性
    if comparison is None or comparison.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="对比记录不存在")
    return comparison


@router.post("", response_model=ComparisonOut)
async def create_comparison(
    payload: ComparisonCreateIn, user: CurrentUser, db: DbSession
) -> ComparisonOut:
    """创建一次多篇论文对比。

    只做校验与建记录，真正的分析在后台跑；前端拿 id 轮询 `GET /comparisons/{id}`。
    """
    document_ids = list(dict.fromkeys(payload.document_ids or []))
    if len(document_ids) < 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="至少选择两篇论文"
        )
    if len(document_ids) > MAX_PAPERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"一次最多对比 {MAX_PAPERS} 篇（再多模型上下文与费用都不划算）",
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

    missing_files = [
        d.name for d in rows if not d.stored_path or not Path(d.stored_path).exists()
    ]
    if missing_files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"这些论文的原始文件已丢失，无法分析：{', '.join(missing_files[:3])}",
        )

    # 若全部论文同属一个团队库，费用与权限都按团队算
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

    comparison = await compare.create_comparison(
        db,
        user_id=user.id,
        document_ids=[d.id for d in rows],
        topic=payload.topic or "",
        team_id=team_id,
    )
    dispatch_comparison(comparison.id)
    return ComparisonOut(**comparison_out(comparison))


@router.get("", response_model=list[ComparisonOut])
async def list_comparisons(user: CurrentUser, db: DbSession) -> list[ComparisonOut]:
    rows = list(
        (
            await db.execute(
                select(Comparison)
                .where(Comparison.user_id == user.id)
                .order_by(Comparison.created_at.desc())
                .limit(50)
            )
        ).scalars()
    )
    return [ComparisonOut(**comparison_out(row)) for row in rows]


@router.get("/{comparison_id}", response_model=ComparisonOut)
async def get_comparison(
    comparison_id: str, user: CurrentUser, db: DbSession
) -> ComparisonOut:
    comparison = await _get_owned_comparison(db, comparison_id, user.id)
    return ComparisonOut(**comparison_out(comparison))


@router.post("/{comparison_id}/rerun", response_model=ComparisonOut)
async def rerun_comparison(
    comparison_id: str, user: CurrentUser, db: DbSession
) -> ComparisonOut:
    comparison = await _get_owned_comparison(db, comparison_id, user.id)
    comparison.status = "pending"
    comparison.stage = "cards"
    comparison.progress = 0
    comparison.error = ""
    await db.commit()
    await db.refresh(comparison)
    dispatch_comparison(comparison.id)
    return ComparisonOut(**comparison_out(comparison))


@router.delete("/{comparison_id}", response_model=OkOut)
async def delete_comparison(
    comparison_id: str, user: CurrentUser, db: DbSession
) -> OkOut:
    comparison = await _get_owned_comparison(db, comparison_id, user.id)
    await db.delete(comparison)
    await db.commit()
    return OkOut(ok=True)


@router.get("/{comparison_id}/report.md")
async def download_report(
    comparison_id: str, user: CurrentUser, db: DbSession
) -> Response:
    comparison = await _get_owned_comparison(db, comparison_id, user.id)
    if not comparison.report_md:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="报告尚未生成（对比可能还在进行或已失败）",
        )
    filename = f"comparison-{comparison.id}.md"
    return Response(
        content=comparison.report_md.encode("utf-8"),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# 论文卡片
# ---------------------------------------------------------------------------
@paper_router.get("/{document_id}", response_model=PaperProfileOut)
async def get_paper_profile(
    document_id: str, user: CurrentUser, db: DbSession
) -> PaperProfileOut:
    """查看某篇论文已抽取的卡片（不存在则 404，前端可提示「先加入一次对比」）。"""
    team_ids = await access.member_team_ids(db, user.id)
    document = (
        await db.execute(
            select(Document)
            .join(KnowledgeBase, Document.knowledge_base_id == KnowledgeBase.id)
            .where(Document.id == document_id)
            .where(access.accessible_condition(user.id, team_ids))
        )
    ).scalar_one_or_none()
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文档不存在")

    profile = (
        await db.execute(
            select(PaperProfile).where(PaperProfile.document_id == document_id)
        )
    ).scalar_one_or_none()
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="该论文尚未抽取过结构化卡片"
        )
    return PaperProfileOut(**profile_out(profile))


@paper_router.post("/{document_id}/refresh", response_model=PaperProfileOut)
async def refresh_paper_profile(
    document_id: str, user: CurrentUser, db: DbSession
) -> PaperProfileOut:
    """强制重新抽取卡片（模型升级或抽取质量不满意时用）。"""
    team_ids = await access.member_team_ids(db, user.id)
    document = (
        await db.execute(
            select(Document)
            .join(KnowledgeBase, Document.knowledge_base_id == KnowledgeBase.id)
            .where(Document.id == document_id)
            .where(access.accessible_condition(user.id, team_ids))
        )
    ).scalar_one_or_none()
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文档不存在")

    model = await compare.resolve_compare_model(db, user.id, "")
    profile = await compare.extract_card(db, document, model=model, force=True)
    if profile.status != "ready":
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"抽取失败：{profile.error or '未知原因'}",
        )
    return PaperProfileOut(**profile_out(profile))
