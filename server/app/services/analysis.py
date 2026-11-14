"""单篇论文智能分析（M4）。

流程：按分析维度检索原文片段 → 组装带编号的证据 → 让模型只依据证据作答 →
把 [n] 映射回页码/片段 → 结果落库缓存。

关键约束：
  - 检索范围限定在当前文档（document_ids），不会串到别的论文；
  - 检索优先限定章节（方法/实验/结论…），查不到再退回全文；
  - 模型没给引用时如实标记，不伪造引用。
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import replace
from typing import AsyncGenerator

from sqlalchemy import select

from app.models import Analysis, Document, DocumentMetadata, KnowledgeBase, now_utc
from app.rag import prompts_analysis
from app.services import access, keyring, llm, vectorstore
from app.services.sectionizer import section_labels
from app.utils.ids import new_id

logger = logging.getLogger(__name__)

_CITATION = re.compile(r"\[(\d{1,2})\]")
_MAX_EVIDENCE = 8


def kinds() -> list[dict]:
    return [
        {"kind": key, "label": spec["label"]}
        for key, spec in prompts_analysis.ANALYSIS_SPECS.items()
    ]


def _section_label(section_type: str) -> str:
    return section_labels().get(section_type or "", section_type or "正文")


def build_evidence(chunks: list, limit: int = _MAX_EVIDENCE) -> tuple[str, list[dict]]:
    """把检索片段编号成 [1]…[n]，同时返回结构化引用（供前端渲染）。"""
    lines: list[str] = []
    items: list[dict] = []
    for index, chunk in enumerate(chunks[:limit], start=1):
        snippet = " ".join((chunk.content or "").split())[:700]
        if not snippet:
            continue
        section = getattr(chunk, "section", "")
        heading = (getattr(chunk, "section_heading", "") or "").strip()
        # 有原文标题就显示标题（"2.2.1 BM25"），否则退回类型名（研究方法/摘要）
        label = heading or _section_label(section)
        lines.append(f"[{index}]（第 {chunk.page or '?'} 页 · {label}）{snippet}")
        items.append(
            {
                "index": index,
                "chunkId": chunk.chunk_id,
                "page": chunk.page,
                "section": section,
                "sectionLabel": label,
                "sectionHeading": heading,
                "snippet": snippet,
            }
        )
    return "\n".join(lines), items


def citations_from_text(text: str, evidence: list[dict]) -> list[dict]:
    """解析正文里的 [n]，按首次出现顺序返回对应证据。"""
    ordered: list[int] = []
    for match in _CITATION.finditer(text or ""):
        index = int(match.group(1))
        if 1 <= index <= len(evidence) and index not in ordered:
            ordered.append(index)
    return [evidence[index - 1] for index in ordered]


async def _team_id_of(db, document: Document) -> str | None:
    base = (
        await db.execute(
            select(KnowledgeBase).where(KnowledgeBase.id == document.knowledge_base_id)
        )
    ).scalar_one_or_none()
    if base is not None and (base.owner_type or "user") == "team":
        return base.owner_id
    return None


async def _paper_title(db, document: Document) -> str:
    meta = (
        await db.execute(
            select(DocumentMetadata).where(DocumentMetadata.document_id == document.id)
        )
    ).scalar_one_or_none()
    return (meta.title if meta and meta.title else document.name) or document.name


async def _resolve_model(db, user, team_id: str | None, model_id: str | None):
    """与问答引擎同一套规则：显式选择优先，否则按归属补密钥。"""
    team_ids = await access.member_team_ids(db, user.id)
    explicit = await keyring.resolve_model_config(
        db, model_id, user_id=user.id, team_ids=team_ids
    )
    selected = explicit or llm.resolve_model(model_id)
    resolved = await keyring.resolve_chat_key(db, team_id=team_id, user_id=user.id)
    if (
        not (explicit is not None and explicit.is_configured)
        and resolved.source in ("team", "user")
        and resolved.usable
    ):
        selected = replace(
            selected,
            api_key=resolved.secret,
            model=resolved.model or selected.model,
            base_url=resolved.base_url or selected.base_url,
            label=f"{selected.label}"
            + ("（团队密钥）" if resolved.source == "team" else "（个人密钥）"),
        )
    return selected


async def _retrieve(
    db, user, document: Document, query: str, sections: list[str] | None, top_k: int = 8
):
    team_id = await _team_id_of(db, document)
    team_ids = await access.member_team_ids(db, user.id)
    embedding = await keyring.resolve_embedding_key(
        db, team_id=team_id, user_id=None if team_id else user.id
    )

    def run(section_filter: list[str] | None):
        return vectorstore.search(
            db,
            query,
            owner_id=user.id,
            team_ids=team_ids,
            document_ids=[document.id],
            sections=section_filter,
            top_k=top_k,
            score_threshold=0.12,
            embedding_api_key=embedding.secret,
        )

    chunks = await asyncio.to_thread(run, sections or None)
    if not chunks and sections:
        # 章节识别不准时退回全文，避免「明明有内容却分析不了」
        chunks = await asyncio.to_thread(run, None)
    return chunks


async def _load_cached(db, document_id: str, kind: str, model_name: str):
    return (
        await db.execute(
            select(Analysis)
            .where(Analysis.document_id == document_id)
            .where(Analysis.kind == kind)
            .where(Analysis.model == model_name)
        )
    ).scalar_one_or_none()


async def _save(
    db, document_id: str, kind: str, model_name: str, content: str, citations: list[dict]
) -> Analysis:
    row = await _load_cached(db, document_id, kind, model_name)
    if row is None:
        row = Analysis(
            id=new_id("ana"),
            document_id=document_id,
            kind=kind,
            model=model_name,
            status="ready",
            content_md=content,
            citations_json=json.dumps(citations, ensure_ascii=False),
            created_at=now_utc(),
        )
        db.add(row)
    else:
        row.status = "ready"
        row.content_md = content
        row.citations_json = json.dumps(citations, ensure_ascii=False)
        row.updated_at = now_utc()
    await db.commit()
    return row


async def stream_analysis(
    db,
    user,
    document: Document,
    kind: str,
    *,
    model_id: str | None = None,
    force: bool = False,
) -> AsyncGenerator[dict, None]:
    spec = prompts_analysis.ANALYSIS_SPECS.get(kind)
    if spec is None:
        yield {"type": "error", "message": f"未知的分析类型：{kind}"}
        return

    team_id = await _team_id_of(db, document)
    model = await _resolve_model(db, user, team_id, model_id)
    if not model.is_configured:
        yield {
            "type": "error",
            "message": "未配置大模型：请在「账号设置 → API 密钥」配置，或在 server/.env 设置 LLM_API_KEY。",
        }
        return

    cached = await _load_cached(db, document.id, kind, model.model)
    if cached is not None and not force:
        try:
            citations = json.loads(cached.citations_json or "[]")
        except (TypeError, ValueError):
            citations = []
        yield {
            "type": "meta",
            "kind": kind,
            "model": model.model,
            "modelLabel": model.label,
            "cached": True,
            "evidence": [],
            "citations": citations,
        }
        yield {"type": "delta", "content": cached.content_md or ""}
        yield {
            "type": "done",
            "analysisId": cached.id,
            "citations": citations,
            "cached": True,
            "model": model.model,
            "modelLabel": model.label,
        }
        return

    title = await _paper_title(db, document)
    query = f"{spec['query']} {title}"
    chunks = await _retrieve(db, user, document, query, spec.get("sections"))
    if not chunks:
        yield {
            "type": "error",
            "message": "没有检索到可用的原文片段：可能是文档尚未解析完成，或解析出的文本过少。",
        }
        return

    evidence_text, evidence = build_evidence(chunks)
    yield {
        "type": "meta",
        "kind": kind,
        "model": model.model,
        "modelLabel": model.label,
        "cached": False,
        "evidence": evidence,
    }

    messages = prompts_analysis.build_analysis_messages(
        kind, title=title, evidence_text=evidence_text
    )
    collected: list[str] = []
    try:
        async for piece in llm.stream_chat(messages, model=model, temperature=0.1):
            collected.append(piece)
            yield {"type": "delta", "content": piece}
    except llm.LLMNotConfigured:
        yield {"type": "error", "message": "未配置大模型，无法生成分析。"}
        return
    except llm.LLMError as exc:
        yield {"type": "error", "message": str(exc)}
        return

    content = "".join(collected)
    citations = citations_from_text(content, evidence)
    warning = ""
    if not citations:
        warning = "本次生成未检测到 [n] 引用，请结合下方原文片段核对结论。"

    row = await _save(db, document.id, kind, model.model, content, citations)
    yield {
        "type": "done",
        "analysisId": row.id,
        "citations": citations,
        "citationWarning": warning,
        "model": model.model,
        "modelLabel": model.label,
    }


async def stream_ask(
    db,
    user,
    document: Document,
    question: str,
    *,
    section: str = "",
    model_id: str | None = None,
) -> AsyncGenerator[dict, None]:
    question = (question or "").strip()
    if not question:
        yield {"type": "error", "message": "问题不能为空"}
        return

    team_id = await _team_id_of(db, document)
    model = await _resolve_model(db, user, team_id, model_id)
    if not model.is_configured:
        yield {
            "type": "error",
            "message": "未配置大模型：请在「账号设置 → API 密钥」配置，或在 server/.env 设置 LLM_API_KEY。",
        }
        return

    sections = [section] if section else None
    chunks = await _retrieve(db, user, document, question, sections, top_k=6)
    if not chunks:
        yield {"type": "error", "message": "没有检索到与该问题相关的原文片段。"}
        return

    evidence_text, evidence = build_evidence(chunks, limit=6)
    yield {
        "type": "meta",
        "kind": "ask",
        "model": model.model,
        "modelLabel": model.label,
        "evidence": evidence,
    }

    title = await _paper_title(db, document)
    label = _section_label(section) if section else ""
    messages = prompts_analysis.build_ask_messages(
        question, title=title, evidence_text=evidence_text, section_label=label
    )
    collected: list[str] = []
    try:
        async for piece in llm.stream_chat(messages, model=model, temperature=0.1):
            collected.append(piece)
            yield {"type": "delta", "content": piece}
    except llm.LLMNotConfigured:
        yield {"type": "error", "message": "未配置大模型，无法回答。"}
        return
    except llm.LLMError as exc:
        yield {"type": "error", "message": str(exc)}
        return

    content = "".join(collected)
    citations = citations_from_text(content, evidence)
    yield {
        "type": "done",
        "citations": citations,
        "citationWarning": "" if citations else "未检测到引用编号，请自行核对原文。",
        "model": model.model,
        "modelLabel": model.label,
    }


async def load_analysis(db, document_id: str, kind: str) -> Analysis | None:
    rows = (
        await db.execute(
            select(Analysis)
            .where(Analysis.document_id == document_id)
            .where(Analysis.kind == kind)
            .order_by(Analysis.updated_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    return rows


async def list_analyses(db, document_id: str) -> list[Analysis]:
    rows = (
        await db.execute(
            select(Analysis)
            .where(Analysis.document_id == document_id)
            .order_by(Analysis.updated_at.desc())
        )
    ).scalars().all()
    return list(rows)
