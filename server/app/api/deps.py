"""FastAPI 依赖：当前登录用户、数据库会话等。"""

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import decode_access_token
from app.models import User

DbSession = Annotated[AsyncSession, Depends(get_db)]


def _extract_bearer(request: Request) -> str | None:
    header = request.headers.get("Authorization") or ""
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


async def get_current_user(request: Request, db: DbSession) -> User:
    """解析 Bearer token 并返回用户。

    任何鉴权失败都返回 401（前端据此清 token 并跳登录）；
    不要用 403，否则前端不会触发重新登录逻辑。
    """
    token = _extract_bearer(request)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供访问令牌",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_access_token(token)
    if not payload or not payload.get("sub"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="登录状态已失效，请重新登录",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = (await db.execute(select(User).where(User.id == payload["sub"]))).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在")

    # 改密码后旧 token 立即失效
    if int(payload.get("ver", 0)) != int(user.token_version):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="登录状态已失效，请重新登录"
        )

    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
