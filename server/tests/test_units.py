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
def test_default_secret_detection(monkeypatch) -> None:
    """验证「是否仍用默认密钥」的判定逻辑。

    这里直接改配置值来判断，**不依赖运行环境**：
    CI 会注入自定义 SECRET_KEY，若断言「当前一定是默认值」就会误报。
    """
    from app.core.config import DEFAULT_SECRET_KEY

    monkeypatch.setattr(settings, 'SECRET_KEY', DEFAULT_SECRET_KEY)
    assert settings.using_default_secret is True

    monkeypatch.setattr(settings, 'SECRET_KEY', 'a' * 64)
    assert settings.using_default_secret is False


def test_upsert_batch_is_reasonably_small() -> None:
    """批次调小是为了降低 chromadb compactor 被打断的概率（见 config 注释）。"""
    assert 1 <= settings.CHROMA_UPSERT_BATCH <= 32


# ------------------------------------------------- 向量库连接自愈（回归保护）
def test_connection_error_detection() -> None:
    """区分「连不上」与「集合不存在」——这个判定错了会导致计数恒 0。"""
    from app.services import vectorstore

    assert vectorstore._looks_like_connection_error(
        RuntimeError('All connection attempts failed')
    )
    assert vectorstore._looks_like_connection_error(
        RuntimeError('Server disconnected without sending a response')
    )
    assert not vectorstore._looks_like_connection_error(
        RuntimeError('Collection knowledge_chunks_x does not exist')
    )


def test_call_with_reset_recovers_once(monkeypatch) -> None:
    """连接断了要丢弃客户端重连一次，而不是一直返回空结果。"""
    from app.services import vectorstore

    class Broken:
        def get_collection(self, name):
            raise RuntimeError('connection closed by peer')

    class Good:
        def get_collection(self, name):
            return f'ok:{name}'

    seq = [Broken(), Good()]
    monkeypatch.setattr(
        vectorstore, 'get_client', lambda: seq.pop(0) if len(seq) > 1 else seq[0]
    )

    assert vectorstore._call_with_reset(lambda c: c.get_collection('x')) == 'ok:x'


def test_call_with_reset_does_not_retry_business_errors(monkeypatch) -> None:
    """业务错误（如集合不存在）不该触发重连，否则会掩盖真实原因。"""
    from app.services import vectorstore

    class Nope:
        def get_collection(self, name):
            raise ValueError('collection does not exist')

    monkeypatch.setattr(vectorstore, 'get_client', lambda: Nope())

    with pytest.raises(ValueError):
        vectorstore._call_with_reset(lambda c: c.get_collection('x'))


def test_existing_collections_propagates_connection_error(monkeypatch) -> None:
    """连接类错误必须往外抛，不能被当成「没有集合」吞掉。

    这正是线上表现「health 里 collections 为空、检索 0 条」的根因：
    原实现 `except Exception: continue` 把连接失败也跳过了。
    """
    from app.services import vectorstore

    class Broken:
        def get_collection(self, name):
            raise RuntimeError('connection reset by peer')

    monkeypatch.setattr(vectorstore, 'get_client', lambda: Broken())

    with pytest.raises(RuntimeError):
        vectorstore._existing_collections()


# ------------------------------------------------- 回答正文里的「无依据」标注
def test_strip_leading_banner_removes_marker() -> None:
    """历史消息里的标注要剥掉，否则模型下一轮会跟着复读（实测出现两次）。"""
    from app.rag import prompts

    body = 'CAPWAP 是一种无线接入点控制协议。'
    assert prompts.strip_leading_banner(prompts.FALLBACK_BANNER + body) == body
    # 剥两层也算对：连续复读后正文开头可能叠了多条标注
    assert prompts.strip_leading_banner(prompts.FALLBACK_BANNER * 2 + body) == body


def test_strip_leading_banner_keeps_normal_quotes() -> None:
    """正文中间的普通引用块不能被误删。"""
    from app.rag import prompts

    text = '> 这是引用原文\n\n' + '结论如下。'
    assert prompts.strip_leading_banner(text) == text


def test_weak_banner_mentions_thresholds() -> None:
    """「召回了但不够相关」的文案要和「完全没召回」区分开。"""
    from app.rag import prompts

    weak = prompts.FALLBACK_BANNER_WEAK.format(
        retrieved=5, top_score=0.76, lex=3, strong=0.85
    )
    assert '检索到 5 条' in weak
    assert '0.76' in weak
    assert '相关度都不足' in weak
    assert '未检索到' not in weak


# --------------------------------------------------- 启动预热（不能拖垮服务）
def test_warmup_swallows_errors(monkeypatch) -> None:
    """预热失败（没配 Key / 向量库不可用）绝不能影响启动。"""
    import asyncio

    from app import main as app_main
    from app.services import vectorstore

    def boom(*args, **kwargs):
        raise RuntimeError('向量库不可用')

    monkeypatch.setattr(vectorstore, 'search', boom)

    # 不应抛异常
    asyncio.run(app_main._warmup_connections())


def test_warmup_uses_real_search_path() -> None:
    """预热必须走 search()，而不是只 embed 一次。

    实测：只预热 embed_query 时，首个真实请求仍会再冷 8 秒
    （检索路径要打开集合、做混合检索）。
    """
    import inspect

    from app import main as app_main

    source = inspect.getsource(app_main._warmup_connections)
    assert 'vectorstore.search' in source
