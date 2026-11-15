"""文件落盘与文档记录创建。

为什么单独抽出来：文档页上传（documents）和文献库上传（library）需要完全
一致的校验、大小限制、内容去重与异步解析派发。复制一份必然出现两套规则，
所以这里做成唯一入口，两边都调它。
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import zipfile
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import Document, KnowledgeBase, now_utc
from app.services import storage
from app.tasks import dispatch_process_document
from app.utils.ids import new_id

logger = logging.getLogger(__name__)

# 与 services/parser.py 的 _BUILTIN 分发键保持一致；.doc 留给解析器给出
# 「请另存为 .docx」的具体提示。
ALLOWED_EXTENSIONS = {
    ".pdf", ".docx", ".doc", ".md", ".markdown", ".txt",
    ".csv", ".json", ".html", ".htm", ".pptx", ".xlsx", ".xls",
}

# 需要校验 zip/OLE 头的格式
_ZIP_SUFFIXES = {".docx", ".pptx", ".xlsx"}
_TEXT_SUFFIXES = {".md", ".markdown", ".txt", ".csv", ".json", ".html", ".htm"}
_OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


def uploads_dir() -> Path:
    directory = Path(settings.UPLOAD_DIR)
    if not directory.is_absolute():
        directory = Path.cwd() / directory
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _read_head(path: Path, size: int = 16) -> bytes:
    with path.open("rb") as handle:
        return handle.read(size)


def _read_tail(path: Path, size: int = 4096) -> bytes:
    with path.open("rb") as handle:
        handle.seek(0, 2)
        length = handle.tell()
        handle.seek(max(0, length - size))
        return handle.read()


def _pdf_page_count(path: Path) -> int:
    from pypdf import PdfReader

    try:
        reader = PdfReader(str(path))
        if reader.is_encrypted:
            raise ValueError("PDF 已加密，暂不支持解析，请上传未加密版本")
        return len(reader.pages)
    except ValueError:
        raise
    except Exception as exc:  # noqa: BLE001 - pypdf 的损坏异常类型不统一
        raise ValueError(f"PDF 解析失败，文件可能已损坏：{exc}") from exc


async def _validate_content(target: Path, suffix: str) -> None:
    """校验文件格式与完整性（上传完成后调用，失败则删除临时文件）。

    只做「能快速判断、且确实能拦住坏文件」的检查：
      - PDF：%PDF- 头 + %%EOF 尾 + pypdf 能读出页面且未加密；
      - docx/pptx/xlsx：必须是合法 zip；
      - .doc：OLE 复合文档头；
      - 文本类：不能含 NUL 字节（防止把二进制改名上传）。
    """
    head = await asyncio.to_thread(_read_head, target, 16)

    if suffix == ".pdf":
        if not head.startswith(b"%PDF-"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="文件格式不正确：不是有效的 PDF（缺少 %PDF- 文件头）",
            )
        tail = await asyncio.to_thread(_read_tail, target)
        if b"%%EOF" not in tail:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="PDF 文件不完整（缺少 %%EOF 结束标记），可能上传被中断，请重新上传",
            )
        try:
            pages = await asyncio.to_thread(_pdf_page_count, target)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        if pages <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="PDF 中没有可用页面，文件可能已损坏",
            )
        return

    if suffix in _ZIP_SUFFIXES:
        valid = await asyncio.to_thread(zipfile.is_zipfile, target)
        if not valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"文件格式不正确：{suffix} 不是有效的 Office 压缩包，可能已损坏",
            )
        return

    if suffix == ".doc":
        if not head.startswith(_OLE_MAGIC):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="文件格式不正确：不是有效的 .doc 文件（建议另存为 .docx 后上传）",
            )
        return

    if suffix in _TEXT_SUFFIXES:
        sample = await asyncio.to_thread(_read_head, target, 4096)
        if b"\x00" in sample:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="文件内容不是文本（包含二进制字节），请检查文件类型",
            )


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
    """流式落盘，边写边算 SHA-256，避免大文件二次 IO。

    分块大小由 `UPLOAD_CHUNK_SIZE_KB` 控制（默认 1MB），内存占用与文件大小无关；
    超限时立即中止并删除半成品。
    """
    target = uploads_dir() / f"{document_id}{suffix}"
    written = 0
    limit = settings.max_upload_bytes
    chunk_size = max(64 * 1024, settings.UPLOAD_CHUNK_SIZE_KB * 1024)
    hasher = hashlib.sha256()
    try:
        with target.open("wb") as sink:
            while True:
                chunk = await file.read(chunk_size)
                if not chunk:
                    break
                written += len(chunk)
                if written > limit:
                    sink.close()
                    target.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=(
                            f"文件过大（{storage.human_bytes(written)}），"
                            f"单文件上限 {settings.MAX_UPLOAD_SIZE_MB}MB"
                        ),
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

    # 上传前先按声明大小做一次容量检查（避免白传 100MB 再被拒）
    declared = int(getattr(file, "size", None) or 0)
    if declared > settings.max_upload_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                f"文件过大（{storage.human_bytes(declared)}），"
                f"单文件上限 {settings.MAX_UPLOAD_SIZE_MB}MB"
            ),
        )
    await storage.ensure_upload_capacity(db, user_id=user_id, incoming_bytes=declared)

    document_id = new_id("doc")
    target, written, content_hash = await _save_to_disk(file, suffix, document_id)

    # 落盘后再校验格式/完整性，并按实际大小复查配额（Content-Length 可能缺失或不准）
    try:
        await _validate_content(target, suffix)
        await storage.ensure_upload_capacity(
            db, user_id=user_id, incoming_bytes=written, already_on_disk=True
        )
    except Exception:
        target.unlink(missing_ok=True)
        raise

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
