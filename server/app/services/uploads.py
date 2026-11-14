"""文件落盘与文档记录创建。

为什么单独抽出来：文档页上传（documents）和文献库上传（library）需要完全
一致的校验、大小限制、内容去重与异步解析派发。复制一份必然出现两套规则，
所以这里做成唯一入口，两边都调它。
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import Document, KnowledgeBase, now_utc
from app.tasks import dispatch_process_document
from app.utils.ids import new_id

logger = logging.getLogger(__name__)

# 与 services/parser.py 的 _BUILTIN 分发键保持一致；.doc 留给解析器给出
# 「请另存为 .docx」的具体提示。
ALLOWED_EXTENSIONS = {
    ".pdf", ".docx", ".doc", ".md", ".markdown", ".txt",
    ".csv", ".json", ".html", ".htm", ".pptx", ".xlsx", ".xls",
}

CHUNK_SIZE = 1024 * 1024  # 1MB


def uploads_dir() -> Path:
    directory = Path(settings.UPLOAD_DIR)
    if not directory.is_absolute():
        directory = Path.cwd() / directory
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _validate_filename(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"不支持的文件类型「{suffix or '无扩展名'}」。"
                f"支持：{', '.join(sorted(ALLOWED_EXTENSIONS))}"
            ),
        )
    return suffix


async def _save_to_disk(file: UploadFile, suffix: str, document_id: str) -> tuple[Path, int, str]:
    """流式落盘，边写边算 SHA-256，避免大文件二次 IO。"""
    target = uploads_dir() / f"{document_id}{suffix}"
    written = 0
    limit = settings.max_upload_bytes
    hasher = hashlib.sha256()
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
                hasher.update(chunk)
                sink.write(chunk)
    except HTTPException:
        raise
    except OSError as exc:
        target.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"保存文件失败：{exc}",
        ) from exc
    finally:
        await file.close()

    if written == 0:
        target.unlink(missing_ok=True)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="上传的文件为空")
    return target, written, hasher.hexdigest()


async def store_upload(
    db: AsyncSession,
    *,
    user_id: str,
    base: KnowledgeBase,
    file: UploadFile,
) -> tuple[Document, bool]:
    """保存上传并建 Document 记录。

    返回 `(document, duplicated)`：
      - duplicated=True 表示同一知识库已有相同内容的文件，返回的是**已有记录**，
        新文件已丢弃，不会重复解析/向量化。
    """
    filename = (file.filename or "").strip()
    if not filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="未获取到文件名")
    suffix = _validate_filename(filename)

    document_id = new_id("doc")
    target, written, content_hash = await _save_to_disk(file, suffix, document_id)

    existing = (
        await db.execute(
            select(Document)
            .where(Document.knowledge_base_id == base.id)
            .where(Document.content_hash == content_hash)
            .where(Document.status != "failed")
            .order_by(Document.uploaded_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if existing is not None:
        target.unlink(missing_ok=True)
        logger.info(
            "上传去重命中：kb=%s hash=%s 复用文档 %s（新上传的文件已丢弃）",
            base.id, content_hash[:12], existing.id,
        )
        return existing, True

    document = Document(
        id=document_id,
        knowledge_base_id=base.id,
        name=filename[:512],
        uploaded_by=user_id,
        stored_path=str(target),
        content_hash=content_hash,
        size=written,
        chunks=0,
        status="processing",
        enabled=True,
        uploaded_at=now_utc(),
    )
    db.add(document)
    await db.flush()

    # 局部导入：knowledge_bases 属于 api 层，模块顶部导入会形成循环依赖
    from app.api.knowledge_bases import refresh_counts

    await refresh_counts(db, base.id)
    # 先提交，确保 worker/异步任务一定能查到这条记录
    await db.commit()

    result = dispatch_process_document(document.id)
    if result.get("mode") == "eager":
        await db.refresh(document)
    elif not result.get("queued"):
        document.status = "failed"
        document.error = (
            "任务队列不可用，文档未开始解析："
            f"{result.get('error', '未知原因')}。请启动 Redis 或设置 CELERY_TASK_ALWAYS_EAGER=true"
        )
        await db.commit()

    return document, False
