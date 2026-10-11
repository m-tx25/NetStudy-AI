"""RAG 核心引擎：检索 → 增强 → 生成，并管理多轮对话记忆。

对外只暴露一个异步生成器 `stream_answer`，产出前端约定的事件：
    {"type": "meta",    "conversationId": ..., "model": ...}
    {"type": "sources", "sources": [...]}
    {"type": "delta",   "content": "..."}
    {"type": "done",    "messageId": ..., "usage": {...}}
    {"type": "error",   "message": "..."}

记忆策略（多轮对话 Memory）：
  - 每次提问前取该会话最近 MEMORY_TURNS 轮问答注入 prompt；
  - 只带纯文本，不重复携带历史引用资料，避免上下文与费用失控；
  - 当前问题单独拼装「参考资料」，保证模型只依据本次检索结果作答。
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import (
    Conversation,
    ConversationKnowledgeBase,
    Message,
    MessageSource,
    User,
    now_utc,
)
from app.rag import prompts
from app.services import llm, vectorstore
from app.utils.ids import new_id


async def load_history(
    db: AsyncSession, conversation_id: str, turns: int | None = None
) -> list[tuple[str, str]]:
    """取最近 N 轮对话（一问一答算一轮），按时间正序返回。"""
    limit = (turns or settings.MEMORY_TURNS) * 2
    rows = (
        await db.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .where(Message.role.in_(("user", "assistant")))
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
    ).scalars().all()

    # 倒序取出后反转回正序；跳过生成失败或内容为空的回答
    ordered = list(reversed(rows))
    return [(message.role, message.content) for message in ordered if message.content.strip()]


async def _conversation_kb_ids(db: AsyncSession, conversation_id: str) -> list[str]:
    rows = (
        await db.execute(
            select(ConversationKnowledgeBase.knowledge_base_id).where(
                ConversationKnowledgeBase.conversation_id == conversation_id
            )
        )
    ).scalars().all()
    return list(rows)


async def stream_answer(
    db: AsyncSession,
    *,
    user: User,
    conversation_id: str | None,
    question: str,
    knowledge_base_ids: list[str] | None = None,
    top_k: int | None = None,
    score_threshold: float | None = None,
) -> AsyncGenerator[dict[str, Any], None]:
    """执行一次完整问答，边生成边产出事件。"""
    kb_ids = list(knowledge_base_ids or [])

    # ---------- 1. 会话：能复用则复用，否则新建 ----------
    conversation: Conversation | None = None
    if conversation_id:
        conversation = (
            await db.execute(
                select(Conversation)
                .where(Conversation.id == conversation_id)
                .where(Conversation.owner_id == user.id)
            )
        ).scalar_one_or_none()

    if conversation is None:
        conversation = Conversation(
            id=new_id("conv"), owner_id=user.id, title=prompts.title_from_question(question)
        )
        db.add(conversation)
        await db.flush()
        if kb_ids:
            for kb_id in kb_ids:
                db.add(
                    ConversationKnowledgeBase(
                        conversation_id=conversation.id, knowledge_base_id=kb_id
                    )
                )
    elif kb_ids:
        # 本次提问的知识库范围覆盖会话设置
        existing = set(await _conversation_kb_ids(db, conversation.id))
        for kb_id in kb_ids:
            if kb_id not in existing:
                db.add(
                    ConversationKnowledgeBase(
                        conversation_id=conversation.id, knowledge_base_id=kb_id
                    )
                )
    else:
        # 未显式传范围时，沿用会话已保存的范围
        kb_ids = await _conversation_kb_ids(db, conversation.id)

    # ---------- 2. 记忆：取历史轮次（必须在写入本轮提问之前） ----------
    history = await load_history(db, conversation.id)

    # ---------- 3. 落地用户提问 ----------
    user_message = Message(
        id=new_id("msg"), conversation_id=conversation.id, role="user", content=question
    )
    db.add(user_message)

    # ---------- 4. 检索（ChromaDB：向量 + 词面混合） ----------
    chunks = vectorstore.search(
        db,
        question,
        owner_id=user.id,
        knowledge_base_ids=kb_ids,
        top_k=top_k or settings.TOP_K,
        score_threshold=(
            score_threshold if score_threshold is not None else settings.SCORE_THRESHOLD
        ),
    )

    sources = [
        {
            "id": chunk.chunk_id,
            "documentId": chunk.document_id,
            "documentName": chunk.document_name,
            "knowledgeBaseId": chunk.knowledge_base_id,
            "knowledgeBaseName": chunk.knowledge_base_name,
            "score": chunk.score,
            "page": chunk.page,
            "snippet": chunk.snippet(),
        }
        for chunk in chunks
    ]

    yield {
        "type": "meta",
        "conversationId": conversation.id,
        "model": settings.LLM_MODEL if llm.is_configured() else "no-llm",
        "retrieved": len(chunks),
    }

    # 先推引用来源，再推正文 —— 与前端 mock 的顺序一致，
    # 这样用户能在答案生成前就看到「依据了哪些文档」。
    yield {"type": "sources", "sources": sources}

    # ---------- 5. 生成 ----------
    assistant_message = Message(
        id=new_id("msg"),
        conversation_id=conversation.id,
        role="assistant",
        content="",
        status="streaming",
    )
    db.add(assistant_message)
    await db.flush()

    collected: list[str] = []
    usage: dict[str, int] = {}
    failed = False

    if not chunks:
        # 没有检索到依据时不调用大模型，直接给出可操作的提示，避免编造
        text = prompts.NO_CONTEXT_ANSWER
        collected.append(text)
        yield {"type": "delta", "content": text}
    else:
        messages = prompts.build_messages(question, chunks, history)
        try:
            async for piece in llm.stream_chat(messages):
                collected.append(piece)
                yield {"type": "delta", "content": piece}
        except llm.LLMNotConfigured as exc:
            failed = True
            yield {"type": "error", "message": str(exc)}
        except llm.LLMError as exc:
            failed = True
            yield {"type": "error", "message": str(exc)}
        except Exception as exc:  # 兜底，避免流中断后连接悬挂
            failed = True
            yield {"type": "error", "message": f"生成回答时出错：{exc}"}

    answer = "".join(collected)

    # ---------- 6. 持久化回答与引用 ----------
    assistant_message.content = answer
    assistant_message.status = "error" if failed else "done"
    assistant_message.prompt_tokens = usage.get("promptTokens", 0)
    assistant_message.completion_tokens = usage.get("completionTokens", 0)

    for index, source in enumerate(sources):
        db.add(
            MessageSource(
                id=new_id("src"),
                message_id=assistant_message.id,
                chunk_id=source["id"],
                document_id=source["documentId"],
                document_name=source["documentName"],
                knowledge_base_id=source["knowledgeBaseId"],
                knowledge_base_name=source["knowledgeBaseName"],
                score=float(source["score"]),
                page=source["page"],
                snippet=source["snippet"],
                ordinal=index,
            )
        )

    # 会话标题：首轮提问后自动命名，与前端交互一致
    if not conversation.title or conversation.title == "新的对话":
        conversation.title = prompts.title_from_question(question)
    conversation.updated_at = now_utc()

    await db.commit()

    yield {
        "type": "done",
        "messageId": assistant_message.id,
        "conversationId": conversation.id,
        "usage": usage,
        "status": assistant_message.status,
    }


def sse(event: dict[str, Any]) -> str:
    """把事件编码为 SSE 帧。

    同时带上 `event:` 名与 `data` 里的 type 字段，兼容前端的两种解析路径。
    """
    name = event.get("type", "message")
    return f"event: {name}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
