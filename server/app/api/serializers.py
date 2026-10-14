"""序列化辅助：把 ORM 对象转成前端契约要求的 camelCase 字典。

集中在此处，避免各路由重复拼装字段（也便于日后统一调整）。
"""

from __future__ import annotations

from app.models import Conversation, Document, KnowledgeBase, Message, User, iso


def user_out(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "nickname": user.nickname or user.username,
        "email": user.email or "",
        "avatar": user.avatar or "",
        "role": user.role or "user",
        "createdAt": iso(user.created_at),
        "lastLoginAt": iso(user.last_login_at),
    }


def knowledge_base_out(
    base: KnowledgeBase, document_count: int = 0, chunk_count: int = 0
) -> dict:
    return {
        "id": base.id,
        # 归属：user=个人库 / team=团队库；前端据此分组展示「我的」与「团队」
        "ownerType": getattr(base, "owner_type", None) or "user",
        "ownerId": base.owner_id,
        "name": base.name,
        "description": base.description or "",
        "documentCount": int(document_count or 0),
        "chunkCount": int(chunk_count or 0),
        "embeddingModel": base.embedding_model or "",
        "createdAt": iso(base.created_at),
        "updatedAt": iso(base.updated_at),
    }


def document_out(document: Document) -> dict:
    return {
        "id": document.id,
        "knowledgeBaseId": document.knowledge_base_id,
        "name": document.name,
        "size": int(document.size or 0),
        "chunks": int(document.chunks or 0),
        "status": document.status,
        "enabled": bool(document.enabled),
        "uploadedAt": iso(document.uploaded_at),
        "error": document.error or "",
    }


def source_out(source) -> dict:
    return {
        "id": source.chunk_id or source.id,
        "documentId": source.document_id,
        "documentName": source.document_name,
        "knowledgeBaseId": source.knowledge_base_id,
        "knowledgeBaseName": source.knowledge_base_name,
        "score": float(source.score or 0.0),
        "page": source.page,
        "snippet": source.snippet or "",
    }


def message_out(message: Message) -> dict:
    return {
        "id": message.id,
        "role": message.role,
        "content": message.content or "",
        "sources": [source_out(item) for item in sorted(message.sources, key=lambda s: s.ordinal)],
        "createdAt": iso(message.created_at),
        "status": message.status,
        # knowledge_base / model / none —— 前端据此标注「非知识库依据」
        "source": getattr(message, "source", "knowledge_base") or "knowledge_base",
    }


def conversation_out(
    conversation: Conversation,
    *,
    message_count: int = 0,
    knowledge_base_ids: list[str] | None = None,
) -> dict:
    return {
        "id": conversation.id,
        "title": conversation.title or "新的对话",
        "createdAt": iso(conversation.created_at),
        "updatedAt": iso(conversation.updated_at),
        "messageCount": int(message_count or 0),
        "knowledgeBaseIds": list(knowledge_base_ids or []),
    }
