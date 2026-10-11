"""知识库路由：/api/knowledge-bases/*（5 个接口）。

注意 documentCount / chunkCount 是前端直接展示的冗余计数：
  - 文档数来自 MySQL；
  - 切片数来自 ChromaDB（向量不在关系库里）。
任何影响文档或向量的操作都必须调用 refresh_counts 重新统计。
"""

import logging

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbSession
from app.api.serializers import knowledge_base_out
from app.core.config import settings
from app.models import ConversationKnowledgeBase, Document, KnowledgeBase, now_utc
from app.schemas import KnowledgeBaseIn, KnowledgeBaseOut, KnowledgeBaseUpdateIn, OkOut
from app.services import vectorstore
from app.utils.ids import new_id

router = APIRouter(prefix="/knowledge-bases", tags=["knowledge-bases"])

logger = logging.getLogger(__name__)


async def refresh_counts(db: DbSession, knowledge_base_id: str) -> tuple[int, int]:
    """重新统计某知识库的文档数与切片数，并刷新 updated_at。

    文档数来自 MySQL；切片数来自 ChromaDB —— 向量不在关系库里。
    """
    document_count = (
        await db.execute(
            select(func.count(Document.id)).where(
                Document.knowledge_base_id == knowledge_base_id
            )
        )
    ).scalar_one()

    chunk_count = vectorstore.count_chunks(knowledge_base_id=knowledge_base_id)

    base = (
        await db.execute(select(KnowledgeBase).where(KnowledgeBase.id == knowledge_base_id))
    ).scalar_one_or_none()
    if base is not None:
        base.updated_at = now_utc()

    return int(document_count or 0), int(chunk_count or 0)


async def counts_for(
    db: DbSession, knowledge_base_ids: list[str]
) -> dict[str, tuple[int, int]]:
    """批量统计，避免列表接口 N+1。"""
    if not knowledge_base_ids:
        return {}

    document_rows = (
        await db.execute(
            select(Document.knowledge_base_id, func.count(Document.id))
            .where(Document.knowledge_base_id.in_(knowledge_base_ids))
            .group_by(Document.knowledge_base_id)
        )
    ).all()
    documents = {kb_id: count for kb_id, count in document_rows}
    chunks = vectorstore.count_by_knowledge_base(knowledge_base_ids)

    return {
        kb_id: (int(documents.get(kb_id, 0)), int(chunks.get(kb_id, 0)))
        for kb_id in knowledge_base_ids
    }


async def _get_owned(db: DbSession, knowledge_base_id: str, user_id: str) -> KnowledgeBase:
    base = (
        await db.execute(
            select(KnowledgeBase)
            .where(KnowledgeBase.id == knowledge_base_id)
            .where(KnowledgeBase.owner_id == user_id)
        )
    ).scalar_one_or_none()
    if base is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识库不存在")
    return base


@router.get("", response_model=list[KnowledgeBaseOut])
async def list_knowledge_bases(user: CurrentUser, db: DbSession) -> list[KnowledgeBaseOut]:
    bases = (
        (
            await db.execute(
                select(KnowledgeBase)
                .where(KnowledgeBase.owner_id == user.id)
                .order_by(KnowledgeBase.updated_at.desc())
            )
        )
        .scalars()
        .all()
    )
    counts = await counts_for(db, [base.id for base in bases])
    return [
        KnowledgeBaseOut(
            **knowledge_base_out(base, *counts.get(base.id, (0, 0)))
        )
        for base in bases
    ]


@router.post("", response_model=KnowledgeBaseOut)
async def create_knowledge_base(
    payload: KnowledgeBaseIn, user: CurrentUser, db: DbSession
) -> KnowledgeBaseOut:
    base = KnowledgeBase(
        id=new_id("kb"),
        owner_id=user.id,
        name=payload.name.strip(),
        description=(payload.description or "").strip(),
        embedding_model=payload.embedding_model or settings.ZHIPUAI_EMBEDDING_MODEL,
    )
    db.add(base)
    await db.flush()
    return KnowledgeBaseOut(**knowledge_base_out(base, 0, 0))


@router.get("/{knowledge_base_id}", response_model=KnowledgeBaseOut)
async def get_knowledge_base(
    knowledge_base_id: str, user: CurrentUser, db: DbSession
) -> KnowledgeBaseOut:
    """查询单个知识库。显式声明以避免不存在时返回 405。"""
    base = await _get_owned(db, knowledge_base_id, user.id)
    counts = await counts_for(db, [base.id])
    return KnowledgeBaseOut(**knowledge_base_out(base, *counts.get(base.id, (0, 0))))


@router.patch("/{knowledge_base_id}", response_model=KnowledgeBaseOut)
async def update_knowledge_base(
    knowledge_base_id: str,
    payload: KnowledgeBaseUpdateIn,
    user: CurrentUser,
    db: DbSession,
) -> KnowledgeBaseOut:
    base = await _get_owned(db, knowledge_base_id, user.id)

    if payload.name is not None:
        name = payload.name.strip()
        if not name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="知识库名称不能为空"
            )
        base.name = name[:128]

    if payload.description is not None:
        base.description = payload.description.strip()

    if payload.embedding_model is not None:
        base.embedding_model = payload.embedding_model

    await db.flush()
    counts = await counts_for(db, [base.id])
    return KnowledgeBaseOut(**knowledge_base_out(base, *counts.get(base.id, (0, 0))))


@router.delete("/{knowledge_base_id}", response_model=OkOut)
async def delete_knowledge_base(
    knowledge_base_id: str, user: CurrentUser, db: DbSession
) -> OkOut:
    base = await _get_owned(db, knowledge_base_id, user.id)

    # 文档与切片由 cascade 删除；会话里的引用需要显式摘除，
    # 否则该会话会一直指向一个已不存在的知识库。
    links = (
        await db.execute(
            select(ConversationKnowledgeBase).where(
                ConversationKnowledgeBase.knowledge_base_id == knowledge_base_id
            )
        )
    ).scalars().all()
    for link in links:
        await db.delete(link)

    await db.delete(base)
    await db.flush()

    # 向量单独存放于 ChromaDB，必须显式清理，否则会留下检索不到的孤儿数据
    removed = vectorstore.delete_knowledge_base(knowledge_base_id)
    if removed:
        logger.info("已清理知识库 %s 的向量 %s 条", knowledge_base_id, removed)

    return OkOut(ok=True)
