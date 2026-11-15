"""存储状态查询：磁盘容量、配额、上传限制。

前端在上传弹窗里展示「剩余空间 / 单文件上限」，避免把 100MB 之类的数字
再写死一份在页面上。
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.services import storage

router = APIRouter(prefix="/storage", tags=["system"])


@router.get("/status")
async def storage_status(user: CurrentUser, db: DbSession) -> dict:
    """当前磁盘、总配额、个人配额与上传限制。"""
    return await storage.storage_status(db, user.id)
