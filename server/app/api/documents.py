"""文档路由：/api/documents/*（5 个接口）。

上传采用流式落盘 + 边写边校验大小，避免大文件先读进内存；
超限返回 413（前端对 413 有专门文案）。
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.api.knowledge_bases import refresh_counts
from app.api.serializers import document_out
from app.core.config import settings
from app.models import Document, KnowledgeBase, now_utc
from app.schemas import DocumentOut, DocumentUpdateIn, OkOut
from app.services import access, chunking, keyring, parser, vectorstore
from app.tasks import dispatch_process_document
from app.utils.ids import new_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])

CHUNK_SIZE = 1024 * 1024  # 1MB


def _uploads_dir() -> Path:
    directory = Path(settings.UPLOAD_DIR)
    if not directory.is_absolute():
        directory = Path.cwd() / directory
    directory.mkdir(parents=True, exist_ok=True)
    return directory


async def _get_owned_document(db: DbSession, document_id: str, user_id: str) -> Document:
    """取文档：个人库看归属，团队库看成员身份（规则见 services/access.py）。"""
    team_ids = await access.member_team_ids(db, user_id)
    document = (
        await db.execute(
            select(Document)
            .join(KnowledgeBase, Document.knowledge_base_id == KnowledgeBase.id)
            .where(Document.id == document_id)
            .where(access.accessible_condition(user_id, team_ids))
        )
    ).scalar_one_or_none()
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文档不存在")
    return document


def _remove_file(path: str) -> None:
    if not path:
        return
    try:
        file_path = Path(path)
        if not file_path.is_absolute():
            file_path = Path.cwd() / file_path
        file_path.unlink(missing_ok=True)
    except OSError as exc:  # 文件被占用等，不应影响接口成功
        logger.warning("删除文件失败 %s: %s", path, exc)


@router.get("", response_model=list[DocumentOut])
async def list_documents(
    user: CurrentUser,
    db: DbSession,
    knowledge_base_id: str | None = Query(default=None, alias="knowledgeBaseId"),
) -> list[DocumentOut]:
    team_ids = await access.member_team_ids(db, user.id)
    statement = (
        select(Document)
        .join(KnowledgeBase, Document.knowledge_base_id == KnowledgeBase.id)
        .where(access.accessible_condition(user.id, team_ids))
    )
    if knowledge_base_id:
        statement = statement.where(Document.knowledge_base_id == knowledge_base_id)

    documents = (
        (await db.execute(statement.order_by(Document.uploaded_at.desc()))).scalars().all()
    )
    return [DocumentOut(**document_out(item)) for item in documents]


@router.get("/{document_id}", response_model=DocumentOut)
async def get_document(document_id: str, user: CurrentUser, db: DbSession) -> DocumentOut:
    """查询单个文档。

    必须显式声明：否则 GET /documents/{id} 会落到 405（该路径只注册了
    PATCH/DELETE），而前端对 404 有专门文案、对 405 没有。
    """
    document = await _get_owned_document(db, document_id, user.id)
    return DocumentOut(**document_out(document))


@router.post("/upload", response_model=DocumentOut)
async def upload_document(
    user: CurrentUser,
    db: DbSession,
    file: UploadFile = File(...),
    knowledge_base_id: str = Form(..., alias="knowledgeBaseId"),
) -> DocumentOut:
    filename = (file.filename or "").strip()
    if not filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="未获取到文件名")

    # 上传目标知识库：个人库需本人拥有，团队库需本人是团队成员
    # （团队知识库对成员开放上传，这是团队协作的核心诉求）
    base = await access.get_accessible(db, knowledge_base_id, user.id)
    if base is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识库不存在")

    document_id = new_id("doc")
    suffix = Path(filename).suffix.lower()
    target = _uploads_dir() / f"{document_id}{suffix}"

    written = 0
    limit = settings.max_upload_bytes
    try:
        with target.open("wb") as sink:
            while True:
                chunk = await file.read(CHUNK_SIZE)
                if not chunk:
                    break
                written += len(chunk)
                if written > limit:
                    sink.close()
                    target.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"文件过大，已超出服务端限制（{settings.MAX_UPLOAD_SIZE_MB}MB）",
                    )
                sink.write(chunk)
    except HTTPException:
        raise
    except OSError as exc:
        target.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"保存文件失败：{exc}"
        ) from exc
    finally:
        await file.close()

    if written == 0:
        target.unlink(missing_ok=True)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="上传的文件为空")

    document = Document(
        id=document_id,
        knowledge_base_id=base.id,
        name=filename[:512],
        uploaded_by=user.id,
        stored_path=str(target),
        size=written,
        chunks=0,
        status="processing",
        enabled=True,
        uploaded_at=now_utc(),
    )
    db.add(document)
    await db.flush()
    await refresh_counts(db, base.id)
    # 先提交，确保 worker 一定能查到这条记录
    await db.commit()

    result = dispatch_process_document(document.id)
    if result.get("mode") == "eager":
        # 同步执行完毕，重新读取最终状态与切片数
        await db.refresh(document)
    elif not result.get("queued"):
        # 队列不可用：明确告知原因，而不是让文档永远停在 processing
        document.status = "failed"
        document.error = (
            "任务队列不可用，文档未开始解析："
            f"{result.get('error', '未知原因')}。请启动 Redis 或设置 CELERY_TASK_ALWAYS_EAGER=true"
        )
        await db.commit()

    return DocumentOut(**document_out(document))


@router.patch("/{document_id}", response_model=DocumentOut)
async def update_document(
    document_id: str, payload: DocumentUpdateIn, user: CurrentUser, db: DbSession
) -> DocumentOut:
    document = await _get_owned_document(db, document_id, user.id)

    if payload.name is not None:
        name = payload.name.strip()
        if not name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="文档名称不能为空"
            )
        document.name = name[:512]

    if payload.enabled is not None:
        document.enabled = payload.enabled
        if payload.enabled:
            # 重新启用：把向量写回（此前停用时已移除）
            await asyncio.to_thread(vectorstore.delete_document, document.id)
            if document.status == "ready" and document.stored_path:
                await _reindex_vectors(db, document)
        else:
            # 停用即从向量库移除，确保检索不会命中已停用文档
            await asyncio.to_thread(vectorstore.delete_document, document.id)

    document.updated_at = now_utc()
    await db.flush()
    return DocumentOut(**document_out(document))


async def _reindex_vectors(db: DbSession, document: Document) -> None:
    """把已解析文档重新写入向量库（不重新解析文件）。"""
    base = (
        await db.execute(
            select(KnowledgeBase).where(KnowledgeBase.id == document.knowledge_base_id)
        )
    ).scalar_one_or_none()
    if base is None:
        return

    try:
        documents = parser.parse_document(document.stored_path)
        chunks = chunking.split_documents(documents)
        payload = []
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
        # 向量化用谁的 Key：团队库用团队 Key → 个人库用上传者 Key → 服务端 Key
        _team_id = base.owner_id if (base.owner_type or "user") == "team" else None
        _resolved = await keyring.resolve_embedding_key(
            db,
            team_id=_team_id,
            user_id=None if _team_id else (document.uploaded_by or user.id),
        )
        # 向量归属：owner_id 用上传者，团队库额外带 team_id（见 pipeline.py 说明）
        stored = await asyncio.to_thread(
            vectorstore.add_chunks,
            owner_id=document.uploaded_by or base.owner_id,
            knowledge_base_id=base.id,
            knowledge_base_name=base.name,
            document_id=document.id,
            document_name=document.name,
            chunks=payload,
            team_id=_team_id,
            embedding_api_key=_resolved.secret,
        )
        document.chunks = stored
    except Exception as exc:
        logger.warning("重新启用文档时写回向量失败 id=%s: %s", document.id, exc)
        document.status = "failed"
        document.error = str(exc)[:500]


@router.delete("/{document_id}", response_model=OkOut)
async def delete_document(document_id: str, user: CurrentUser, db: DbSession) -> OkOut:
    document = await _get_owned_document(db, document_id, user.id)
    knowledge_base_id = document.knowledge_base_id
    stored_path = document.stored_path

    # 切片向量存放于 ChromaDB，需与关系库一并清理
    await db.delete(document)
    await db.flush()
    await refresh_counts(db, knowledge_base_id)
    await db.commit()

    # 同步阻塞（Chroma 删除），丢线程池避免冻住事件循环
    removed = await asyncio.to_thread(vectorstore.delete_document, document_id)
    if removed:
        logger.info("已清理文档 %s 的向量 %s 条", document_id, removed)

    _remove_file(stored_path)
    return OkOut(ok=True)


@router.post("/{document_id}/reindex", response_model=DocumentOut)
async def reindex_document(
    document_id: str, user: CurrentUser, db: DbSession
) -> DocumentOut:
    document = await _get_owned_document(db, document_id, user.id)

    if not document.stored_path or not Path(document.stored_path).exists():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="原始文件已不存在，无法重新解析，请删除后重新上传",
        )

    document.status = "processing"
    document.error = ""
    document.updated_at = now_utc()
    await db.flush()
    await db.commit()

    result = dispatch_process_document(document.id, reindex=True)
    if result.get("mode") == "eager":
        await db.refresh(document)
    elif not result.get("queued"):
        document.status = "failed"
        document.error = (
            f"任务队列不可用：{result.get('error', '未知原因')}。"
            "请启动 Redis 或设置 CELERY_TASK_ALWAYS_EAGER=true"
        )
        await db.commit()

    return DocumentOut(**document_out(document))
