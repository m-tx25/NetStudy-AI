"""API 密钥的加密存储。

用户在「个人设置 / 团队设置」里填写的第三方 API Key 都要落库，**绝不能明文**。
这里用对称加密（Fernet / AES-128-CBC + HMAC）做一层可逆加密：

    密钥 = SHA256(SECRET_KEY 的原始字节) 的 urlsafe base64

为什么可逆而不是哈希：调用第三方接口时必须还原出**原文**，哈希做不到。
安全性依赖 `SECRET_KEY`：
  - 生产环境必须换成随机长字符串（`openssl rand -hex 32`）；
  - SECRET_KEY 一旦更换，此前存的所有密钥都无法解密 —— 这是预期行为，
    此时接口会提示用户重新填写，而不是抛 500（见 keyring 的容错处理）。
"""

from __future__ import annotations

import base64
import hashlib
import logging

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings

logger = logging.getLogger(__name__)


def _fernet() -> Fernet:
    digest = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(plain: str) -> str:
    """明文 → 密文（存入数据库）。"""
    if not plain:
        return ""
    return _fernet().encrypt(plain.encode("utf-8")).decode("ascii")


def decrypt_secret(cipher: str) -> str:
    """密文 → 明文。

    解密失败（SECRET_KEY 换过、数据被改坏）时返回空字符串并记日志，
    让上层走「未配置」分支，而不是把异常抛给用户。
    """
    if not cipher:
        return ""
    try:
        return _fernet().decrypt(cipher.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, TypeError) as exc:
        logger.warning("API Key 解密失败（SECRET_KEY 可能已更换）：%s", exc)
        return ""


def mask_secret(plain: str, keep_head: int = 6, keep_tail: int = 4) -> str:
    """给前端展示用的掩码，如 sk-abc…f123。"""
    if not plain:
        return ""
    if len(plain) <= keep_head + keep_tail:
        return "*" * len(plain)
    return f"{plain[:keep_head]}…{plain[-keep_tail:]}"
