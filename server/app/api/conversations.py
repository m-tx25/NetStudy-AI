"""会话与消息路由：/api/conversations/*（5 个接口）。"""

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, DbSession
from app.api.serializers import conversation_out, message_out
from app.models import Conversation, ConversationKnowledgeBase, Message, now_utc
from app.schemas import (
    ConversationIn,
    ConversationOut,
    ConversationUpdateIn,
    MessageOut,
    OkOut,
)
from app.utils.ids import new_id

router = APIRouter(prefix="/conversations", tags=["conversations"])


async def _kb_ids_map(db: DbSession, conversation_ids: list[str]) -> dict[str, list[str]]:
    """一次查出多个会话的知识库范围，避免 N+1。"""
    if not conversation_ids:
        return {}
    rows = (
        await db.execute(
            select(
                ConversationKnowledgeBase.conversation_id,
                ConversationKnowledgeBase.knowledge_base_id,
            ).where(ConversationKnowledgeBase.conversation_id.in_(conversation_ids))
        )
    ).all()
    result: dict[str, list[str]] = {}
    for conversation_id, kb_id in rows:
        result.setdefault(conversation_id, []).append(kb_id)
    return result


async def _message_counts(db: DbSession, conversation_ids: list[str]) -> dict[str, int]:
    if not conversation_ids:
        return {}
    rows = (
        await db.execute(
            select(Message.conversation_id, func.count(Message.id))
            .where(Message.conversation_id.in_(conversation_ids))
            .group_by(Message.conversation_id)
        )
    ).all()
    return {conversation_id: count for conversation_id, count in rows}


async def _get_owned(db: DbSession, conversation_id: str, user_id: str) -> Conversation:
    conversation = (
        await db.execute(
            select(Conversation)
            .where(Conversation.id == conversation_id)
            .where(Conversation.owner_id == user_id)
        )
    ).scalar_one_or_none()
    if conversation is None:
        # 不区分「不存在」与「无权访问」，避免探测他人会话 ID
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")
    return conversation


@router.get("", response_model=list[ConversationOut])
async def list_conversations(user: CurrentUser, db: DbSession) -> list[ConversationOut]:
    conversations = (
        (
            await db.execute(
                select(Conversation)
                .where(Conversation.owner_id == user.id)
                .order_by(Conversation.updated_at.desc())
            )
        )
        .scalars()
        .all()
    )

    ids = [item.id for item in conversations]
    counts = await _message_counts(db, ids)
    kb_map = await _kb_ids_map(db, ids)

    return [
        ConversationOut(
            **conversation_out(
                item,
                message_count=counts.get(item.id, 0),
                knowledge_base_ids=kb_map.get(item.id, []),
            )
        )
        for item in conversations
    ]


@router.get("/{conversation_id}", response_model=ConversationOut)
async def get_conversation(
    conversation_id: str, user: CurrentUser, db: DbSession
) -> ConversationOut:
    """查询单个会话。显式声明以避免不存在时返回 405。"""
    conversation = await _get_owned(db, conversation_id, user.id)
    counts = await _message_counts(db, [conversation.id])
    kb_map = await _kb_ids_map(db, [conversation.id])
    return ConversationOut(
        **conversation_out(
            conversation,
            message_count=counts.get(conversation.id, 0),
            knowledge_base_ids=kb_map.get(conversation.id, []),
        )
    )


@router.post("", response_model=ConversationOut)
async def create_conversation(
    payload: ConversationIn, user: CurrentUser, db: DbSession
) -> ConversationOut:
    conversation = Conversation(
        id=new_id("conv"),
        owner_id=user.id,
        title=(payload.title or "新的对话").strip() or "新的对话",
    )
    db.add(conversation)

    for kb_id in payload.knowledge_base_ids:
        db.add(
            ConversationKnowledgeBase(
                conversation_id=conversation.id, knowledge_base_id=kb_id
            )
        )

    await db.flush()
    return ConversationOut(
        **conversation_out(
            conversation, message_count=0, knowledge_base_ids=list(payload.knowledge_base_ids)
        )
    )


@router.patch("/{conversation_id}", response_model=ConversationOut)
async def update_conversation(
    conversation_id: str, payload: ConversationUpdateIn, user: CurrentUser, db: DbSession
) -> ConversationOut:
    conversation = await _get_owned(db, conversation_id, user.id)

    if payload.title is not None:
        title = payload.title.strip()
        if not title:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="会话标题不能为空"
            )
        conversation.title = title[:255]

    if payload.knowledge_base_ids is not None:
        # 全量覆盖：先清空再写入，语义与前端「勾选哪些知识库」一致
        existing = (
            await db.execute(
                select(ConversationKnowledgeBase).where(
                    ConversationKnowledgeBase.conversation_id == conversation.id
                )
            )
        ).scalars().all()
        for link in existing:
            await db.delete(link)
        for kb_id in payload.knowledge_base_ids:
            db.add(
                ConversationKnowledgeBase(
                    conversation_id=conversation.id, knowledge_base_id=kb_id
                )
            )

    conversation.updated_at = now_utc()
    await db.flush()

    counts = await _message_counts(db, [conversation.id])
    kb_map = await _kb_ids_map(db, [conversation.id])
    return ConversationOut(
        **conversation_out(
            conversation,
            message_count=counts.get(conversation.id, 0),
            knowledge_base_ids=kb_map.get(conversation.id, []),
        )
    )


@router.delete("/{conversation_id}", response_model=OkOut)
async def delete_conversation(conversation_id: str, user: CurrentUser, db: DbSession) -> OkOut:
    conversation = await _get_owned(db, conversation_id, user.id)
    # messages / kb_links 由 relationship 的 cascade 一并删除
    await db.delete(conversation)
    return OkOut(ok=True)


@router.get("/{conversation_id}/messages", response_model=list[MessageOut])
async def list_messages(
    conversation_id: str, user: CurrentUser, db: DbSession
) -> list[MessageOut]:
    await _get_owned(db, conversation_id, user.id)

    messages = (
        (
            await db.execute(
                select(Message)
                .options(selectinload(Message.sources))
                .where(Message.conversation_id == conversation_id)
                .order_by(Message.created_at.asc())
            )
        )
        .scalars()
        .all()
    )
    return [MessageOut(**message_out(item)) for item in messages]
