"""API 密钥的静态加密。

背景：用户在前端自己填写的模型密钥必须落库（否则每次请求都要携带它）。
但**绝不能明文存** —— 数据库被拖库、备份泄露、或有人误查表都会直接暴露密钥。

方案：以 SECRET_KEY 为根派生一把对称密钥，用 Fernet（AES-128-CBC + HMAC）加密。
  - SECRET_KEY 已经在 .env 中，且是部署时必换的配置，不额外引入新密钥管理；
  - 密文带版本前缀 `v1:`，便于日后轮换算法；
  - 解密失败（换了 SECRET_KEY、密文损坏）时返回空串而不是抛错 ——
    模型会因此被判定为「未配置」，界面提示重填，而不是整个服务 500。

注意：这项能力用于「保护用户自己的密钥」，不是端到端加密。
拥有 SECRET_KEY 与数据库的人仍可解出明文 —— 这是服务端代办密钥的固有限制。
如果不想承担这个风险，可改用「不落库、随请求携带」的模式。
"""

from __future__ import annotations

import base64
import hashlib
import logging

logger = logging.getLogger(__name__)

_PREFIX = "v1:"


def _fernet():
    """按 SECRET_KEY 派生 Fernet 实例（惰性导入，缺库时降级）。"""
    try:
        from cryptography.fernet import Fernet
    except ImportError:  # pragma: no cover
        logger.warning("未安装 cryptography，模型密钥将无法加密存储")
        return None

    from app.core.config import settings

    digest = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt(plain: str) -> str:
    """加密密钥；空值原样返回空串。"""
    if not plain:
        return ""
    fernet = _fernet()
    if fernet is None:
        # 没有加密库时宁可拒绝存储，也不静默明文落库
        raise RuntimeError(
            "缺少 cryptography 依赖，无法安全保存 API 密钥。"
            "请执行 pip install -r requirements.txt 后重试。"
        )
    token = fernet.encrypt(plain.encode("utf-8")).decode("ascii")
    return f"{_PREFIX}{token}"


def decrypt(stored: str) -> str:
    """解密密钥；失败时返回空串（视为未配置），不抛错。"""
    if not stored:
        return ""
    if not stored.startswith(_PREFIX):
        # 兼容历史明文数据：原样返回，下次保存时会自动转为密文
        return stored

    fernet = _fernet()
    if fernet is None:
        return ""
    try:
        return fernet.decrypt(stored[len(_PREFIX) :].encode("ascii")).decode("utf-8")
    except Exception as exc:
        logger.warning("模型密钥解密失败（SECRET_KEY 是否变更过？）：%s", exc)
        return ""


def mask(value: str, keep: int = 4) -> str:
    """用于日志/诊断的掩码显示，绝不输出原文。"""
    if not value:
        return ""
    if len(value) <= keep * 2:
        return "***"
    return f"{value[:keep]}…{value[-keep:]}"
