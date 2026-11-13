# -*- coding: utf-8 -*-
"""纯单元测试（不连数据库、不发网络请求），供 CI 快速回归。

只覆盖「纯函数」这一层：
    - 文档失败原因分类器
    - 密钥加解密与掩码
    - id 生成
    - 默认 SECRET_KEY 的识别

依赖数据库 / Chroma 的验收脚本仍在 tests/verify_*.py，
需要在服务启动后手动运行（README 第五章有命令）。
"""
from __future__ import annotations

import pytest

from app.core.config import settings
from app.core.secrets import decrypt_secret, encrypt_secret, mask_secret
from app.services.diagnostics import humanize_document_error
from app.utils.ids import new_id


# --------------------------------------------------------------- 错误分类器
@pytest.mark.parametrize(
    'raw, expected_keyword',
    [
        # 向量库：最常见的误判来源，提示里必须写明「不是 API Key 的问题」
        ('Error executing plan: Error sending backfill request to compactor: '
         'Failed to apply logs to the metadata segment', 'API Key'),
        ('Error in compaction: Failed to apply logs to the metadata segment', 'API Key'),
        ('error returned from database: (code: 14) unable to open database file', 'ChromaDB'),
        # 鉴权
        ('Error code: 401 - invalid api key provided', '鉴权失败'),
        # 额度 / 限流
        ('Error code: 429 rate limit exceeded', '额度不足'),
        # 网络
        ('HTTPSConnectionPool: connection timeout after 30s', '无法连接模型服务'),
        # 兜底
        ('某个没见过的内部错误', '文档处理失败'),
    ],
)
def test_humanize_classifies(raw: str, expected_keyword: str) -> None:
    out = humanize_document_error(Exception(raw))
    assert expected_keyword in out


def test_humanize_keeps_original_error() -> None:
    """提示里要保留原始错误，方便排查，但不能把它当作主要信息。"""
    raw = 'Error in compaction: Failed to apply logs to the metadata segment'
    out = humanize_document_error(Exception(raw))
    assert '原始错误' in out
    assert 'compaction' in out.lower()


# --------------------------------------------------------------- 密钥处理
def test_encrypt_decrypt_roundtrip() -> None:
    plain = 'sk-test-0123456789abcdef'
    cipher = encrypt_secret(plain)
    assert cipher and cipher != plain, '密文不能等于明文'
    assert decrypt_secret(cipher) == plain


def test_encrypt_is_not_deterministic() -> None:
    """Fernet 带随机 IV，同一明文两次加密结果应不同（避免密文比对）。"""
    plain = 'sk-test-0123456789abcdef'
    assert encrypt_secret(plain) != encrypt_secret(plain)


def test_mask_keeps_head_and_tail() -> None:
    """格式是 `sk-tes…cdef`：保留首尾，中间用省略号（与前端展示一致）。"""
    masked = mask_secret('sk-test-0123456789abcdef', keep_head=6, keep_tail=4)
    assert masked == 'sk-tes…cdef'
    assert '0123456789' not in masked, '中间段必须被去掉'


def test_mask_short_secret_is_fully_hidden() -> None:
    """短密钥保留首尾就等于整串暴露，必须全星号。"""
    masked = mask_secret('abc', keep_head=6, keep_tail=4)
    assert masked == '***'
    assert 'abc' not in masked


# --------------------------------------------------------------- id 生成
def test_new_id_has_prefix_and_is_unique() -> None:
    a, b = new_id('kb'), new_id('kb')
    assert a.startswith('kb_') and b.startswith('kb_')
    assert a != b
    assert len(a) > 3


# --------------------------------------------------------------- 配置校验
def test_default_secret_detected() -> None:
    """CI / 本地默认配置下应识别为「未更换默认密钥」。"""
    assert settings.using_default_secret is True


def test_upsert_batch_is_reasonably_small() -> None:
    """批次调小是为了降低 chromadb compactor 被打断的概率（见 config 注释）。"""
    assert 1 <= settings.CHROMA_UPSERT_BATCH <= 32
