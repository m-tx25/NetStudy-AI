"""存储管理：容量配额、磁盘监控、孤儿文件清理。

设计前提（2 核 4GB / 50GB 磁盘的演示服务器）：
  - 原文件、解析文本、向量数据分开存放：原文件在 UPLOAD_DIR，解析文本在
    MySQL 的 paper_sections，向量在 ChromaDB；这里只管**原文件**的容量。
  - 总配额 40GB、单用户 5GB、至少保留 5GB 空闲：既防止把磁盘写满导致
    MySQL/Chroma 写失败，也给系统日志和备份留余量。
  - 清理只删「数据库没有引用、且超过一定时间」的孤儿文件；**有引用的原始
    PDF 永不自动删除**（需求 9），删除文献必须由用户显式操作。
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import time
from pathlib import Path

from fastapi import HTTPException, status
from sqlalchemy import func, select

from app.core.config import settings
from app.models import Document

logger = logging.getLogger(__name__)

_GB = 1024**3
_MB = 1024**2


def human_bytes(value: int | float) -> str:
    size = float(value or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.1f}{unit}" if unit != "B" else f"{int(size)}B"
        size /= 1024
    return f"{size:.1f}TB"


def uploads_dir() -> Path:
    directory = Path(settings.UPLOAD_DIR)
    if not directory.is_absolute():
        directory = Path.cwd() / directory
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _dir_size(directory: Path) -> int:
    total = 0
    try:
        for item in directory.iterdir():
            if item.is_file():
                try:
                    total += item.stat().st_size
                except OSError:
                    continue
    except OSError as exc:
        logger.warning("统计上传目录失败：%s", exc)
    return total


def disk_snapshot() -> dict:
    usage = shutil.disk_usage(str(uploads_dir()))
    return {
        "totalBytes": usage.total,
        "usedBytes": usage.used,
        "freeBytes": usage.free,
        "totalGb": round(usage.total / _GB, 2),
        "usedGb": round(usage.used / _GB, 2),
        "freeGb": round(usage.free / _GB, 2),
    }


async def user_usage_bytes(db, user_id: str) -> int:
    total = (
        await db.execute(
            select(func.coalesce(func.sum(Document.size), 0)).where(
                Document.uploaded_by == user_id
            )
        )
    ).scalar_one()
    return int(total or 0)


async def storage_status(db, user_id: str) -> dict:
    directory = uploads_dir()
    disk = disk_snapshot()
    used_bytes = _dir_size(directory)
    files = 0
    try:
        files = sum(1 for item in directory.iterdir() if item.is_file())
    except OSError:
        files = 0
    return {
        "disk": disk,
        "quota": {
            "totalQuotaGb": settings.STORAGE_TOTAL_QUOTA_GB,
            "usedBytes": used_bytes,
            "usedGb": round(used_bytes / _GB, 2),
            "userUsedBytes": await user_usage_bytes(db, user_id),
            "userQuotaGb": settings.STORAGE_PER_USER_QUOTA_GB,
            "minFreeGb": settings.STORAGE_MIN_FREE_GB,
        },
        "limits": {
            "maxUploadMb": settings.MAX_UPLOAD_SIZE_MB,
            "chunkSizeKb": settings.UPLOAD_CHUNK_SIZE_KB,
            "maxConcurrentParseTasks": settings.MAX_CONCURRENT_PARSE_TASKS,
        },
        "uploads": {"fileCount": files},
    }


async def ensure_upload_capacity(
    db, *, user_id: str, incoming_bytes: int, already_on_disk: bool = False
) -> None:
    """上传前/落盘后校验容量。失败抛 413（用户配额）或 507（磁盘/总配额）。

    `already_on_disk=True` 表示文件已经写入上传目录：
      - 磁盘空闲、总目录大小都**已经包含**这份文件，不能再加一遍；
      - 用户配额来自 documents 表，此时还没建记录，仍需加上 incoming。
    """
    incoming = max(0, int(incoming_bytes or 0))
    disk = disk_snapshot()
    reserve = int(settings.STORAGE_MIN_FREE_GB * _GB)
    free_after = disk["freeBytes"] if already_on_disk else disk["freeBytes"] - incoming
    if free_after < reserve:
        raise HTTPException(
            status_code=status.HTTP_507_INSUFFICIENT_STORAGE,
            detail=(
                f"服务器磁盘空间不足：剩余 {human_bytes(disk['freeBytes'])}，"
                f"需保留 {settings.STORAGE_MIN_FREE_GB}GB。请稍后重试或联系管理员清理。"
            ),
        )

    used_total = _dir_size(uploads_dir())
    projected_total = used_total if already_on_disk else used_total + incoming
    if projected_total > int(settings.STORAGE_TOTAL_QUOTA_GB * _GB):
        raise HTTPException(
            status_code=status.HTTP_507_INSUFFICIENT_STORAGE,
            detail=(
                f"存储总配额不足：已用 {human_bytes(projected_total)} / "
                f"{settings.STORAGE_TOTAL_QUOTA_GB}GB。"
            ),
        )

    used_user = await user_usage_bytes(db, user_id)
    if used_user + incoming > int(settings.STORAGE_PER_USER_QUOTA_GB * _GB):
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                f"个人存储配额不足：已用 {human_bytes(used_user)} / "
                f"{settings.STORAGE_PER_USER_QUOTA_GB}GB，"
                "请删除部分文献后重试。"
            ),
        )


async def cleanup_orphan_files(
    db, *, older_than_hours: int = 24, dry_run: bool = True
) -> dict:
    """清理上传目录里的孤儿文件（数据库无引用）。

    安全约束：有 `documents.stored_path` 引用的文件一律跳过，绝不自动删除
    原始 PDF；只清理由失败上传/测试残留产生的无引用文件。
    """
    rows = (
        await db.execute(
            select(Document.stored_path).where(Document.stored_path != "")
        )
    ).scalars().all()
    referenced = {
        str(Path(path).resolve()) for path in rows if path
    }

    cutoff = time.time() - older_than_hours * 3600
    removed: list[dict] = []
    kept = 0
    directory = uploads_dir()
    for item in directory.iterdir():
        if not item.is_file():
            continue
        resolved = str(item.resolve())
        if resolved in referenced:
            kept += 1
            continue
        try:
            stat = item.stat()
        except OSError:
            continue
        if stat.st_mtime > cutoff:
            continue
        removed.append({"name": item.name, "bytes": stat.st_size})
        if not dry_run:
            item.unlink(missing_ok=True)

    total_bytes = sum(entry["bytes"] for entry in removed)
    return {
        "dryRun": dry_run,
        "referencedFiles": len(referenced),
        "keptFiles": kept,
        "orphanFiles": len(removed),
        "reclaimedBytes": total_bytes,
        "reclaimed": human_bytes(total_bytes),
        "items": removed[:50],
    }


async def cleanup_orphans_async(*, older_than_hours: int = 24, dry_run: bool = True) -> dict:
    """脚本入口：自己开一个数据库会话。"""
    from app.core.database import SessionLocal

    async with SessionLocal() as db:
        return await cleanup_orphan_files(
            db, older_than_hours=older_than_hours, dry_run=dry_run
        )
