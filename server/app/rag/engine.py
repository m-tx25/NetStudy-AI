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

import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from dataclasses import replace
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import (
    Conversation,
    ConversationKnowledgeBase,
    Document,
    KnowledgeBase,
    Message,
    MessageSource,
    User,
    now_utc,
)
from app.rag import prompts
from app.services import access, keyring, llm, vectorstore
from app.utils.ids import new_id

logger = logging.getLogger(__name__)


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

    # 倒序取出后反转回正序；跳过生成失败或内容为空的回答。
    # assistant 内容要先剥掉「无依据」标注：那段标注是服务端加的，
    # 留在记忆里会让模型下一轮跟着复读（实测同一条回答出现两次标注）。
    ordered = list(reversed(rows))
    return [
        (
            message.role,
            prompts.strip_leading_banner(message.content)
            if message.role == "assistant"
            else message.content,
        )
        for message in ordered
        if message.content.strip()
    ]


async def _conversation_kb_ids(db: AsyncSession, conversation_id: str) -> list[str]:
    rows = (
        await db.execute(
            select(ConversationKnowledgeBase.knowledge_base_id).where(
                ConversationKnowledgeBase.conversation_id == conversation_id
            )
        )
    ).scalars().all()
    return list(rows)


def _pick_evidence(chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
    """从检索结果中挑出真正算「知识库依据」的片段。

    判据见 RetrievedChunk.is_evidence：词面命中达阈值，或向量分很高。
    返回空列表表示「知识库里确实没有这个问题的依据」，此时应切换到模型自身知识作答。
    """
    if not chunks:
        return []
    return [
        chunk
        for chunk in chunks
        if chunk.is_evidence(settings.RAG_MIN_LEXICAL_SCORE, settings.RAG_STRONG_SCORE)
    ]


def _extractive_answer(question: str, evidence: list[RetrievedChunk]) -> str:
    """未配置大模型时的抽取式回答：直接摘录检索到的片段。

    为什么需要它：评委/首次运行者通常没有 API Key。若直接报错，
    整个问答演示就断了。这里退化为「把命中的原文整理出来」——
    虽然不如模型生成自然，但**内容真实来自文档**，配合引用溯源仍是有意义的演示。

    明确标注，避免用户误以为这是模型生成的答案。
    """
    banner = (
        "> ⚠️ **当前离线演示模式**：未配置大模型 API Key，以下内容为"
        "**直接从知识库摘录的原文片段**（未经模型组织语言）。\n"
        "> 配置 `LLM_API_KEY`（或在前端「API 密钥」页填写）后即可获得流畅的生成式回答。\n\n"
    )
    if not evidence:
        return banner + "未检索到可摘录的内容。"

    lines = [banner]
    for index, chunk in enumerate(evidence[:3], 1):
        snippet = (chunk.content or "").strip()
        if len(snippet) > 320:
            cut = snippet[:320]
            for mark in ("。", "！", "？", "\n", "；"):
                pos = cut.rfind(mark)
                if pos > 80:
                    cut = cut[: pos + 1]
                    break
            snippet = cut + "…"
        source = chunk.document_name or "未知文档"
        if getattr(chunk, "page", None):
            source += f" 第 {chunk.page} 页"
        lines.append(f"**{index}. 摘自《{source}》**\n\n{snippet}\n")
    return "\n".join(lines)


def _chunk_text_for_stream(text: str, size: int = 12):
    """把整段文本切块 yield，模拟流式输出（前端打字机效果依赖增量）。"""
    for start in range(0, len(text), size):
        yield text[start : start + size]


async def stream_answer(
    db: AsyncSession,
    *,
    user: User,
    conversation_id: str | None,
    question: str,
    knowledge_base_ids: list[str] | None = None,
    document_ids: list[str] | None = None,
    top_k: int | None = None,
    score_threshold: float | None = None,
    model_id: str | None = None,
) -> AsyncGenerator[dict[str, Any], None]:
    """执行一次完整问答，边生成边产出事件。

    作答模式由检索结果决定：
      - 命中资料         → 「知识库依据」模式：强约束只依据资料回答并标注引用；
      - 未命中且允许回退  → 「模型自身知识」模式：服务端先下发醒目标注（说明非文档依据、
                            引导上传文档），再让模型正常作答；
      - 未命中且禁止回退  → 只返回可操作提示，不调用模型。

    model_id 用于选择生成模型（见 settings.available_models()）；
    向量化模型与此无关，始终由 ZHIPUAI_* 配置决定。
    """
    kb_ids = list(knowledge_base_ids or [])
    doc_ids = list(dict.fromkeys(document_ids or []))

    # 论文级范围：校验这些文档确实可访问（跨用户/跨团队一律按不存在处理），
    # 同时拿到名称，用于「哪几篇有依据 / 哪几篇没有」的覆盖清单。
    paper_names: dict[str, str] = {}
    if doc_ids:
        rows = (
            await db.execute(
                select(Document.id, Document.name)
                .join(KnowledgeBase, Document.knowledge_base_id == KnowledgeBase.id)
                .where(Document.id.in_(doc_ids))
                .where(
                    access.accessible_condition(
                        user.id, await access.member_team_ids(db, user.id)
                    )
                )
            )
        ).all()
        paper_names = {row[0]: row[1] for row in rows}
        # 过滤掉越权/已删的 id；一篇都不剩则按「没选论文」处理，退回知识库范围
        doc_ids = [item for item in doc_ids if item in paper_names]
        if doc_ids and not kb_ids:
            kb_ids = list(
                (
                    await db.execute(
                        select(Document.knowledge_base_id).where(
                            Document.id.in_(doc_ids)
                        )
                    )
                ).scalars()
            )

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
    # 团队知识库的切片带 team_id，提问者是团队成员就要能召回 ——
    # 因此把「我所在的团队」一并作为检索范围（个人库仍按 owner_id 隔离）。
    team_ids = await access.member_team_ids(db, user.id)

    # 检索用谁的向量 Key：本次范围里若有团队库，优先用团队 Key（费用归团队）；
    # 否则用提问者自己的 Key。向量模型固定，不同 Key 产生的向量等价，故不影响召回。
    embed_team_id: str | None = None
    if kb_ids:
        rows = (
            await db.execute(
                select(KnowledgeBase.owner_type, KnowledgeBase.owner_id)
                .where(KnowledgeBase.id.in_(kb_ids))
                .where(KnowledgeBase.owner_type == "team")
                .where(KnowledgeBase.owner_id.in_(team_ids or [""]))
            )
        ).all()
        if rows:
            embed_team_id = rows[0][1]
    resolved_embed = await keyring.resolve_embedding_key(
        db, team_id=embed_team_id, user_id=None if embed_team_id else user.id
    )

    # search() 内部要调 embedding HTTP 接口 + 查 Chroma，是同步阻塞的；
    # 放在事件循环里会冻住整个服务（含其它接口），必须丢线程池。
    #
    # 向量库不可用（Chroma 初始化失败、集合打不开等）时**不能让整个问答 500**：
    # 统一按「本次没有检索到依据」处理，继续走下面的回退逻辑
    # （用模型自身知识作答并在正文标注「非知识库依据」），
    # 否则用户只会看到一条原始的内部错误，连换个问法重试都做不到。
    try:
        chunks = await asyncio.to_thread(
            vectorstore.search,
            db,
            question,
            owner_id=user.id,
            knowledge_base_ids=kb_ids,
            document_ids=doc_ids,
            top_k=(
                top_k
                or (max(6, 2 * len(doc_ids)) if doc_ids else settings.TOP_K)
            ),
            score_threshold=(
                score_threshold if score_threshold is not None else settings.SCORE_THRESHOLD
            ),
            team_ids=team_ids,
            embedding_api_key=resolved_embed.secret,
        )
    except vectorstore.VectorStoreUnavailable as exc:
        logger.warning("向量检索不可用，按「无知识库依据」处理：%s", exc)
        chunks = []

    # ---------- 5. 选择生成模型与作答模式 ----------
    # 前端显式选了模型（user:<keyId> / server:<id>）就以选择为准；
    # 解析不出（id 非法 / 密钥已停用 / 不属于本人）再退回服务端默认模型。
    explicit_model = await keyring.resolve_model_config(
        db, model_id, user_id=user.id, team_ids=team_ids
    )
    selected_model = explicit_model or llm.resolve_model(model_id)

    # 生成用谁的密钥：团队库优先团队 Key，**团队没配时用提问者自己的 Key 兜底**，
    # 个人库/无库用本人 Key，最后才回落到服务端 .env（旧版团队库会把个人 Key 直接跳过，
    # 于是一选团队库就报「未配置大模型」）。
    # 但用户明确选了一个「带密钥」的模型时，尊重该选择，不再按归属覆盖。
    resolved_chat = await keyring.resolve_chat_key(
        db, team_id=embed_team_id, user_id=user.id
    )
    if (
        not (explicit_model is not None and explicit_model.is_configured)
        and resolved_chat.source in ("team", "user")
        and resolved_chat.usable
    ):
        selected_model = replace(
            selected_model,
            api_key=resolved_chat.secret,
            model=resolved_chat.model or selected_model.model,
            base_url=resolved_chat.base_url or selected_model.base_url,
            label=f"{selected_model.label}"
            + ("（团队密钥）" if resolved_chat.source == "team" else "（个人密钥）"),
        )

    # 检索到了片段 ≠ 有依据。弱向量模型下无关问题也会返回高分片段
    # （实测"量子纠缠"拿到 0.83），若只看 chunks 是否为空，回退将永远不触发。
    # 因此这里用证据门槛判断：词面命中达阈值，或向量分很高。
    evidence = _pick_evidence(chunks)
    grounded = bool(evidence)
    # 无依据且允许回退 → 改用模型自身知识作答；否则维持严格 RAG
    use_fallback = (not grounded) and settings.RAG_FALLBACK_TO_MODEL
    answer_source = "knowledge_base" if grounded else ("model" if use_fallback else "none")

    # 没有依据时，不把弱相关片段当"参考资料"塞给模型 —— 否则它会照着无关内容硬答
    context_chunks = evidence if grounded else []

    # 引用来源只展示**构成依据**的片段；没有依据时不展示弱相关片段，
    # 否则前端会显示"引用了 X 文档"却给出模型自行生成的回答，自相矛盾。
    sources = [
        {
            "id": chunk.chunk_id,
            "documentId": chunk.document_id,
            "documentName": chunk.document_name,
            "knowledgeBaseId": chunk.knowledge_base_id,
            "knowledgeBaseName": chunk.knowledge_base_name,
            "score": chunk.score,
            "page": chunk.page,
            # 章节标题（如「3 Method」），解析时识别；识别不到为空串
            "section": chunk.section,
            "snippet": chunk.snippet(),
        }
        for chunk in context_chunks
    ]

    # 逐篇统计「这篇论文有没有被召回的依据」。
    # 多篇论文问答里最误导的情况是：用户选了 3 篇，模型只依据 1 篇作答却不说。
    # 这里把覆盖情况随 meta 下发，前端可明确提示「X、Y 两篇未找到相关依据」。
    coverage: list[dict[str, Any]] = []
    missing_documents: list[str] = []
    if doc_ids:
        counts: dict[str, int] = {}
        for chunk in context_chunks:
            counts[chunk.document_id] = counts.get(chunk.document_id, 0) + 1
        for doc_id in doc_ids:
            hits = counts.get(doc_id, 0)
            name = paper_names.get(doc_id, doc_id)
            coverage.append({"documentId": doc_id, "documentName": name, "hits": hits})
            if hits == 0:
                missing_documents.append(name)

    yield {
        "type": "meta",
        "conversationId": conversation.id,
        "model": selected_model.model if selected_model.is_configured else "no-llm",
        "modelLabel": selected_model.label,
        # 前端据此即时显示「本次回答没有知识库依据」
        "grounded": grounded,
        "answerSource": answer_source,
        "fallback": use_fallback,
        "retrieved": len(chunks),
        # 构成依据的片段数；为 0 才是真正的「知识库里没有」
        "evidence": len(evidence),
        # 论文级范围与覆盖情况（未选论文时为空）
        "documentIds": doc_ids,
        "coverage": coverage,
        "missingDocuments": missing_documents,
    }

    # 先推引用来源，再推正文 —— 与前端 mock 的顺序一致，
    # 这样用户能在答案生成前就看到「依据了哪些文档」。
    yield {"type": "sources", "sources": sources}

    # ---------- 6. 生成 ----------
    assistant_message = Message(
        id=new_id("msg"),
        conversation_id=conversation.id,
        role="assistant",
        content="",
        status="streaming",
        source=answer_source,
    )
    db.add(assistant_message)
    await db.flush()

    collected: list[str] = []
    usage: dict[str, int] = {}
    failed = False
    # 未配置大模型时是否走了「抽取式兜底」
    extractive = False

    if grounded or use_fallback:
        # 有依据 → 严格 RAG（只喂构成依据的片段）；无依据但允许回退 → 用模型自身知识
        messages = prompts.build_messages(
            question,
            context_chunks,
            history,
            grounded=grounded,
            document_names=[paper_names.get(item, item) for item in doc_ids] if doc_ids else None,
        )
        if not grounded:
            # 标注由服务端直接下发，不依赖模型自觉 —— 保证用户一定看得到。
            # 两种情况文案不同：
            #   chunks 为空 → 真的没召回到（多半没索引 / 没上传 / 未参与检索）
            #   chunks 非空 → 召回了但被相关性门槛过滤（换问法更有效）
            if chunks:
                banner = prompts.FALLBACK_BANNER_WEAK.format(
                    retrieved=len(chunks),
                    top_score=max(chunk.score for chunk in chunks),
                    lex=settings.RAG_MIN_LEXICAL_SCORE,
                    strong=settings.RAG_STRONG_SCORE,
                )
            else:
                banner = prompts.FALLBACK_BANNER
            collected.append(banner)
            yield {"type": "delta", "content": banner}

        try:
            async for piece in llm.stream_chat(
                messages,
                model=selected_model,
                temperature=(
                    None if grounded else settings.RAG_FALLBACK_TEMPERATURE
                ),
            ):
                collected.append(piece)
                yield {"type": "delta", "content": piece}
        except llm.LLMNotConfigured:
            # 没配 LLM Key：不让演示断掉。
            # 有依据时用「抽取式回答」——直接把检索到的片段整理成答案，
            # 并明确标注这是摘录而非模型生成，既保证可演示，也不误导用户。
            if grounded:
                extractive = True
                text = _extractive_answer(question, evidence)
                for piece in _chunk_text_for_stream(text):
                    collected.append(piece)
                    yield {"type": "delta", "content": piece}
            else:
                failed = True
                yield {
                    "type": "error",
                    "message": (
                        "未配置大模型，且知识库中没有检索到可摘录的内容。"
                        "请在「账号设置 → API 密钥」或 server/.env 里配置 LLM_API_KEY 后再试。"
                    ),
                }
        except llm.LLMError as exc:
            # 模型「配了但调不通」（Key 无效、余额不足、网络失败、模型名写错）。
            # 同样不让演示断掉：有依据时降级为摘录，并说明原因；
            # 无依据则只能如实报错（没有可展示的内容）。
            if grounded:
                extractive = True
                note = (
                    "> ⚠️ **大模型调用失败**："
                    f"{str(exc)[:200]}\n"
                    "> 以下改为直接从知识库摘录原文。请检查 API Key / 模型名 / 网络后重试。\n\n"
                )
                text = note + _extractive_answer(question, evidence)
                for piece in _chunk_text_for_stream(text):
                    collected.append(piece)
                    yield {"type": "delta", "content": piece}
            else:
                failed = True
                yield {"type": "error", "message": str(exc)}
        except Exception as exc:  # 兜底，避免流中断后连接悬挂
            failed = True
            yield {"type": "error", "message": f"生成回答时出错：{exc}"}
    else:
        # 关闭回退时的严格模式：不调用大模型，只给出可操作的提示
        collected.append(prompts.NO_CONTEXT_ANSWER)
        yield {"type": "delta", "content": prompts.NO_CONTEXT_ANSWER}

    answer = "".join(collected)

    # ---------- 7. 持久化回答与引用 ----------
    assistant_message.content = answer
    assistant_message.status = "error" if failed else "done"
    assistant_message.source = answer_source
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
        # 回传来源，便于前端在气泡上保留「非知识库依据」标注
        "source": answer_source,
        "grounded": grounded,
        "model": selected_model.model,
        "modelLabel": selected_model.label,
        # true 表示未配置大模型，正文是知识库原文摘录（非模型生成）
        "extractive": extractive,
    }


def sse(event: dict[str, Any]) -> str:
    """把事件编码为 SSE 帧。

    同时带上 `event:` 名与 `data` 里的 type 字段，兼容前端的两种解析路径。
    """
    name = event.get("type", "message")
    return f"event: {name}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
