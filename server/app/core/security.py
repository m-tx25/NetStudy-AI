"""密码哈希与 JWT。

密码选择直接用 bcrypt 库而非 passlib：passlib 1.7.4 会去读 bcrypt.__about__.__version__，
该属性在 bcrypt 4.1+ 已被移除，会抛出版本读取异常。直接用 bcrypt 更稳。

bcrypt 的两个硬限制在这里都做了处理：
  1. 输入超过 72 字节会被静默截断 —— 先做 SHA-256 预哈希再交给 bcrypt；
  2. 不接受含 NUL 的输入 —— 预哈希后是纯 hex，不含 NUL。
"""

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
from jose import JWTError, jwt

from app.core.config import settings

_BCRYPT_ROUNDS = 12


def _prehash(password: str) -> bytes:
    """把任意长度的密码规约到 bcrypt 可安全处理的 72 字节以内。"""
    return hashlib.sha256(password.encode("utf-8")).hexdigest().encode("ascii")


def hash_password(password: str) -> str:
    salt = bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)
    return bcrypt.hashpw(_prehash(password), salt).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    if not password or not password_hash:
        return False
    try:
        return bcrypt.checkpw(_prehash(password), password_hash.encode("ascii"))
    except (ValueError, TypeError):
        # 哈希格式非法（例如历史脏数据）时按校验失败处理，不抛 500
        return False


def create_access_token(user_id: str, token_version: int = 1) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": user_id,
        "ver": token_version,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)).timestamp()),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any] | None:
    """解析 token；签名错误、过期、格式非法一律返回 None。"""
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        return None


# --------------------------------------------------------------------------
# 字段校验：与前端 client/src/api/mock.js 的规则保持一致，
# 否则会出现「前端允许提交、后端却 422」的错位。
# --------------------------------------------------------------------------
import re

USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_\u4e00-\u9fa5-]{2,32}$")
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")

MIN_PASSWORD_LENGTH = 6


def validate_username(username: str) -> str | None:
    if not USERNAME_PATTERN.match(username or ""):
        return "用户名需为 2~32 位的字母、数字、下划线、连字符或中文"
    return None


def validate_email(email: str) -> str | None:
    if not EMAIL_PATTERN.match(email or ""):
        return "邮箱格式不正确"
    return None


def validate_password(password: str) -> str | None:
    if len(password or "") < MIN_PASSWORD_LENGTH:
        return f"密码至少 {MIN_PASSWORD_LENGTH} 位"
    return None
