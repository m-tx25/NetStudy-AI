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
import json
import logging
from typing import Any

from sqlalchemy import select

from app.core.config import settings
from app.core.database import SessionLocal
from app.models import (
    Analysis,
    Document,
    DocumentMetadata,
    DocumentQuality,
    KnowledgeBase,
    Paper,
    PaperAsset,
    PaperReference,
    PaperSection,
    now_utc,
)
from app.services import (
    assets as assets_service,
    chunking,
    diagnostics,
    keyring,
    paper_meta,
    parser,
    quality,
    references as references_service,
    sectionizer,
    vectorstore,
)
from app.utils.ids import new_id

logger = logging.getLogger(__name__)


async def _persist_structure(
    db,
    document: Document,
    sections: list[sectionizer.Section],
    refs: list[references_service.Reference],
    asset_items: list[assets_service.Asset],
    report: quality.QualityReport,
    meta: paper_meta.PaperMeta,
) -> None:
    """把结构解析结果落库（重跑时先清旧数据）。"""
    for model in (PaperSection, PaperReference, PaperAsset):
        await db.execute(model.__table__.delete().where(model.document_id == document.id))
    # 重新解析后旧的分析结果基于旧文本，必须失效，否则用户会看到过期结论
    await db.execute(
        Analysis.__table__.delete().where(Analysis.document_id == document.id)
    )
    await db.execute(
        DocumentQuality.__table__.delete().where(DocumentQuality.document_id == document.id)
    )
    await db.execute(
        DocumentMetadata.__table__.delete().where(DocumentMetadata.document_id == document.id)
    )

    db.add(
        DocumentMetadata(
            document_id=document.id,
            title=(meta.title or "")[:512],
            authors_json=json.dumps(meta.authors, ensure_ascii=False),
            doi=meta.doi or "",
            year=meta.year,
            abstract=meta.abstract or "",
            venue=meta.venue or "",
            created_at=now_utc(),
        )
    )

    for section in sections:
        db.add(
            PaperSection(
                id=new_id("sec"),
                document_id=document.id,
                section_type=section.section_type,
                heading=(section.heading or "")[:255],
                ordinal=section.ordinal,
                page_start=section.page_start,
                page_end=section.page_end,
                text=section.text,
            )
        )
    for index, reference in enumerate(refs):
        db.add(
            PaperReference(
                id=new_id("ref"),
                document_id=document.id,
                ordinal=index,
                raw_text=reference.raw_text,
                doi=reference.doi,
                year=reference.year,
                title=(reference.title or "")[:512],
            )
        )
    for asset in asset_items:
        db.add(
            PaperAsset(
                id=new_id("asset"),
                document_id=document.id,
                kind=asset.kind,
                page=asset.page,
                caption=(asset.caption or "")[:1000],
                content_json=asset.content_json,
                storage_path=asset.storage_path,
            )
        )
    db.add(
        DocumentQuality(
            document_id=document.id,
            char_count=report.char_count,
            page_count=report.page_count,
            section_count=report.section_count,
            reference_count=report.reference_count,
            table_count=report.table_count,
            figure_count=report.figure_count,
            garbage_ratio=report.garbage_ratio,
            warnings_json=json.dumps(report.warnings, ensure_ascii=False),
            created_at=now_utc(),
        )
    )

    # 上传时文献库条目用的是文件名；解析结果才是权威元数据，直接回填/覆盖。
    # 覆盖而不是「只在空时填」：修复解析器升级后旧记录仍是坏标题/坏摘要的问题。
    paper = (
        await db.execute(
            select(Paper).where(Paper.source == "upload", Paper.source_id == document.id)
        )
    ).scalar_one_or_none()
    if paper is not None:
        if meta.title:
            paper.title = meta.title[:512]
        if meta.authors:
            paper.authors_json = json.dumps(
                [{"name": name, "affiliation": "", "orcid": ""} for name in meta.authors],
                ensure_ascii=False,
            )
        if meta.doi:
            paper.doi = meta.doi
        if meta.year:
            paper.year = meta.year
        if meta.abstract:
            paper.abstract = meta.abstract

    await db.commit()


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

            # 2) 结构解析：章节 / 元数据 / 参考文献 / 表格图表 / 质量校验
            sections = sectionizer.build_sections(documents)
            meta = paper_meta.extract(documents, sections)
            refs = references_service.extract(sections)
            asset_items = assets_service.extract_tables(
                document.stored_path
            ) + assets_service.extract_figure_captions(documents)
            report = quality.evaluate(documents, sections, refs, asset_items)
            await _persist_structure(db, document, sections, refs, asset_items, report, meta)

            # 3) 按章节切片（每块带 section/page_start/page_end，供分析与引用定位）
            chunks = chunking.split_sections(sections)
            if not chunks:
                raise parser.ParseError("切片结果为空，请检查文档内容")

            # 4) 写入 ChromaDB（embedding 在此步由向量模型完成）
            payload: list[tuple] = []
            for ordinal, chunk in enumerate(chunks):
                metadata = chunk.metadata or {}
                page = metadata.get("page_label") or metadata.get("page")
                # 章节标题由 parser 识别并放进元数据（PDF 的「3 Method」这类标题），
                # 引用时展示「第 N 章」，比只有页码更好定位。
                section = str(metadata.get("section") or "")
                payload.append(
                    (
                        ordinal,
                        chunk.page_content or "",
                        int(page) if isinstance(page, (int, float)) and page else None,
                        {
                            "section": metadata.get("section", "other"),
                            "section_heading": metadata.get("section_heading", ""),
                            "page_start": int(metadata.get("page_start") or 0),
                            "page_end": int(metadata.get("page_end") or 0),
                        },
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

            # 5) 回填统计
            document.chunks = stored
            document.status = "ready"
            document.error = ""
            document.updated_at = now_utc()
            base.updated_at = now_utc()
            await db.commit()

            logger.info(
                "文档处理完成 id=%s 切片=%s 章节=%s 引用=%s 表格=%s 图注=%s 向量模式=%s",
                document.id,
                stored,
                report.section_count,
                report.reference_count,
                report.table_count,
                report.figure_count,
                vectorstore.embeddings.current_mode(),
            )
            return {
                "ok": True,
                "documentId": document.id,
                "chunks": stored,
                "sections": report.section_count,
                "references": report.reference_count,
                "embeddingMode": vectorstore.embeddings.current_mode(),
                "reindex": reindex,
            }

        except Exception as exc:
            # 对用户展示可读的原因（带处理建议）；原始异常仍完整记日志
            message = diagnostics.humanize_document_error(exc)
            logger.exception("文档处理失败 id=%s（原始异常）", document_id)
            await db.rollback()
            # rollback 会丢弃未提交的改动，需重新取一次文档再写失败状态
            document = (
                await db.execute(select(Document).where(Document.id == document_id))
            ).scalar_one_or_none()
            if document is not None:
                document.status = "failed"
                document.error = message[:2000]
                document.updated_at = now_utc()
                await db.commit()
            # 失败时清掉可能已写入一半的向量，保证「非 ready 的文档不参与检索」
            await asyncio.to_thread(vectorstore.delete_document, document_id)
            logger.warning("文档处理失败 id=%s: %s", document_id, str(exc)[:300])
            return {"ok": False, "documentId": document_id, "error": message[:500]}


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
        message = diagnostics.humanize_document_error(exc)
        try:
            await _mark_failed(document_id, message)
        except Exception:
            logger.exception("写入失败状态时又出错 id=%s", document_id)
        return {"ok": False, "documentId": document_id, "error": message[:500]}


async def _mark_failed(document_id: str, error: str) -> None:
    async with SessionLocal() as db:
        document = (
            await db.execute(select(Document).where(Document.id == document_id))
        ).scalar_one_or_none()
        if document is not None:
            document.status = "failed"
            document.error = error[:2000]
            document.updated_at = now_utc()
            await db.commit()
    await asyncio.to_thread(vectorstore.delete_document, document_id)


def mark_failed_sync(document_id: str, error: str) -> None:
    from app.tasks import run_async

    run_async(_mark_failed(document_id, error))
