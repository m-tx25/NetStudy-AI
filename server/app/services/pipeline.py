"""文档处理流水线：解析 → 切片 → 向量化入库（ChromaDB）→ 回填统计（MySQL）。

数据落点分工：
    MySQL      —— 文档元信息、状态、切片数
    ChromaDB   —— 切片正文 + 向量 + 溯源元数据
两者通过 document_id 关联；删除文档时必须同时清理两边，否则会检索到已删内容。

向量化由 ChromaDB 在 upsert 时调用 embedding 函数完成（智谱 embedding-3），
本模块只负责把文本与元数据准备好。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from sqlalchemy import select

from app.core.config import settings
from app.core.database import SessionLocal
from app.models import Document, KnowledgeBase, now_utc
from app.services import chunking, keyring, parser, vectorstore

logger = logging.getLogger(__name__)


async def _process(document_id: str, reindex: bool) -> dict[str, Any]:
    async with SessionLocal() as db:
        document = (
            await db.execute(select(Document).where(Document.id == document_id))
        ).scalar_one_or_none()
        if document is None:
            return {"ok": False, "documentId": document_id, "error": "文档不存在"}

        base = (
            await db.execute(
                select(KnowledgeBase).where(KnowledgeBase.id == document.knowledge_base_id)
            )
        ).scalar_one_or_none()
        if base is None:
            return {"ok": False, "documentId": document_id, "error": "所属知识库不存在"}

        # 向量归属：owner_id 恒为「上传者用户 id」，团队库额外带 team_id。
        # 不能直接用 base.owner_id —— 团队库的 owner_id 是团队 id，
        # 与用户 id 不是一个命名空间，放进 Chroma 元数据会导致检索过滤错位。
        uploader_id = document.uploaded_by or base.owner_id
        team_id = base.owner_id if (base.owner_type or "user") == "team" else None
        knowledge_base_name = base.name

        # 向量化用谁的 Key：团队库用团队 Key → 个人库用本人 Key → 服务端 Key
        resolved = await keyring.resolve_embedding_key(
            db, team_id=team_id, user_id=None if team_id else uploader_id
        )
        embedding_key = resolved.secret

        # 重新处理前先清掉旧向量，避免重复累积。
        # 同步阻塞（Chroma），丢线程池避免冻住事件循环。
        removed = await asyncio.to_thread(vectorstore.delete_document, document.id)
        if removed:
            logger.info("重新索引前清理旧向量 %s 条（doc=%s）", removed, document.id)

        document.status = "processing"
        document.error = ""
        await db.commit()

        try:
            # 人为延迟：仅用于演示与验证异步解析状态（默认 0，不产生任何影响）。
            # 设 PIPELINE_ARTIFICIAL_DELAY_SECONDS=12 可以观察到前端「解析中 → 已就绪」
            # 的轮询过程；生产环境不要设置。
            if settings.PIPELINE_ARTIFICIAL_DELAY_SECONDS > 0:
                logger.info(
                    "按配置延迟 %.1fs 后开始解析（演示用）",
                    settings.PIPELINE_ARTIFICIAL_DELAY_SECONDS,
                )
                await asyncio.sleep(settings.PIPELINE_ARTIFICIAL_DELAY_SECONDS)

            # 1) 解析为 LangChain Document（Word / Markdown / PDF 等）
            documents = parser.parse_document(document.stored_path)
            if not documents:
                raise parser.ParseError("未能解析出任何文本")

            # 2) 切片，元数据（页码等）自动继承
            chunks = chunking.split_documents(documents)
            if not chunks:
                raise parser.ParseError("切片结果为空，请检查文档内容")

            # 3) 写入 ChromaDB（embedding 在此步由向量模型完成）
            payload: list[tuple[int, str, int | None]] = []
            for ordinal, chunk in enumerate(chunks):
                metadata = chunk.metadata or {}
                page = metadata.get("page_label") or metadata.get("page")
                payload.append(
                    (
                        ordinal,
                        chunk.page_content or "",
                        int(page) if isinstance(page, (int, float)) and page else None,
                    )
                )

            # 注意：add_chunks 内部是**同步阻塞**的（智谱 HTTP 请求 + ChromaDB 写入），
            # 必须丢到线程池执行。否则会把事件循环冻住，导致整个服务（含登录接口）
            # 在文档处理期间完全无响应。
            stored = await asyncio.to_thread(
                vectorstore.add_chunks,
                owner_id=uploader_id,
                knowledge_base_id=base.id,
                knowledge_base_name=knowledge_base_name,
                document_id=document.id,
                document_name=document.name,
                chunks=payload,
                team_id=team_id,
                embedding_api_key=embedding_key,
            )

            # 4) 回填统计
            document.chunks = stored
            document.status = "ready"
            document.error = ""
            document.updated_at = now_utc()
            base.updated_at = now_utc()
            await db.commit()

            logger.info(
                "文档处理完成 id=%s 切片=%s 向量模式=%s",
                document.id,
                stored,
                vectorstore.embeddings.current_mode(),
            )
            return {
                "ok": True,
                "documentId": document.id,
                "chunks": stored,
                "embeddingMode": vectorstore.embeddings.current_mode(),
                "reindex": reindex,
            }

        except Exception as exc:
            message = str(exc)[:500]
            await db.rollback()
            # rollback 会丢弃未提交的改动，需重新取一次文档再写失败状态
            document = (
                await db.execute(select(Document).where(Document.id == document_id))
            ).scalar_one_or_none()
            if document is not None:
                document.status = "failed"
                document.error = message
                document.updated_at = now_utc()
                await db.commit()
            # 失败时清掉可能已写入一半的向量，保证「非 ready 的文档不参与检索」
            await asyncio.to_thread(vectorstore.delete_document, document_id)
            logger.warning("文档处理失败 id=%s: %s", document_id, message)
            return {"ok": False, "documentId": document_id, "error": message}


def process_document_sync(document_id: str, *, reindex: bool = False) -> dict[str, Any]:
    """Celery 任务入口（同步）。"""
    from app.tasks import run_async

    return run_async(_process(document_id, reindex))


async def process_document_async(document_id: str, *, reindex: bool = False) -> dict[str, Any]:
    """异步入口：供 eager-async 模式在事件循环里直接调度。

    内部自行处理异常并写入文档状态，因此调用方无需 try/except。
    """
    try:
        return await _process(document_id, reindex)
    except Exception as exc:  # _process 内部已处理大部分异常，这里兜底
        logger.exception("后台解析任务异常 id=%s", document_id)
        try:
            await _mark_failed(document_id, str(exc))
        except Exception:
            logger.exception("写入失败状态时又出错 id=%s", document_id)
        return {"ok": False, "documentId": document_id, "error": str(exc)}


async def _mark_failed(document_id: str, error: str) -> None:
    async with SessionLocal() as db:
        document = (
            await db.execute(select(Document).where(Document.id == document_id))
        ).scalar_one_or_none()
        if document is not None:
            document.status = "failed"
            document.error = error[:500]
            document.updated_at = now_utc()
            await db.commit()
    await asyncio.to_thread(vectorstore.delete_document, document_id)


def mark_failed_sync(document_id: str, error: str) -> None:
    from app.tasks import run_async

    run_async(_mark_failed(document_id, error))
