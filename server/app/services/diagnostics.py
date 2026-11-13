# -*- coding: utf-8 -*-
"""把文档处理的技术异常翻译成「用户能看懂、能照着做」的提示。

背景：处理失败时 `document.error` 直接存的是原始异常字符串，前端展示出来
形如 `Error in compaction: Failed to apply logs to the metadata segment`。
这对用户没有任何指导意义，还会让人误以为是「没配 API Key」——而实际上
embedding 请求可能已经 200 成功了。

本模块按错误特征归类，给出「这是什么问题 + 该做什么」，并把原始报错附在末尾
供排查（不丢信息，但不让用户直面它）。
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------- 特征词表
# 顺序即优先级：先判向量库，因为它最容易和「API 问题」混淆。
_CHROMA_MARKERS = (
    "compaction",
    "metadata segment",
    "failed to apply logs",
    "database is locked",
    "unable to open database file",
    "rustbindingsapi",
    "bindings",
    "hnsw",
    "chroma",
    "sqlite",
    "error in compaction",
)

# 鉴权类：Key 无效、过期、无权限
_AUTH_MARKERS = (
    "401",
    "403",
    "unauthorized",
    "authentication",
    "invalid api key",
    "invalid_api_key",
    "api key",
    "apikey",
    "token",
    "permission denied",
    "鉴权",
    "无效的",
)

# 额度/限流类
_QUOTA_MARKERS = (
    "429",
    "rate limit",
    "ratelimit",
    "quota",
    "insufficient",
    "余额",
    "1113",
    "1114",
    "limit exceeded",
    "too many requests",
)

# 网络类
_NETWORK_MARKERS = (
    "connect",
    "connection",
    "timeout",
    "timed out",
    "getaddrinfo",
    "ssl",
    "network",
    "unreachable",
    "proxy",
    "connectionerror",
    "readtimeout",
)

_CHROMA_HINT = (
    "向量库写入失败（ChromaDB 存储层异常）——**这不是 API Key 的问题**，"
    "向量化请求通常已经成功。\n"
    "建议依次尝试：\n"
    "1) 点该文档的「重新索引」重试（多数偶发失败一次就恢复）；\n"
    "2) 停掉后端，删除 server/data/chroma_db 目录后重启"
    "（会重建向量库，需把所有文档重新索引）；\n"
    "3) 若本机 chromadb 原生库不稳定，可在 server/.env 设置 "
    "CHROMA_DISABLED=true 临时绕过（问答将不再检索文档，仅用模型自身知识作答）。"
)

_AUTH_HINT = (
    "模型 API 鉴权失败：Key 无效、已过期或没有该模型的权限。\n"
    "请到「账号设置 → API 密钥」重新填写（团队知识库请在「团队 → 团队设置 → 团队 API 密钥」配置），"
    "或检查 server/.env 里的 ZHIPUAI_API_KEY / LLM_API_KEY。"
)

_QUOTA_HINT = (
    "模型 API 额度不足或触发限流。\n"
    "请到「账号设置 → API 密钥」换一个 Key，或稍后重试。"
)

_NETWORK_HINT = (
    "无法连接模型服务（网络或代理问题）。\n"
    "请检查服务器的出网能力 / 代理设置，确认能访问 open.bigmodel.cn 与所配置的 LLM 地址后重试。"
)


def humanize_document_error(exc: BaseException) -> str:
    """返回给用户看的失败原因（带处理建议）。

    原始异常会附在末尾，方便排查，但不作为主要信息。
    """
    raw = f"{type(exc).__name__}: {exc}".strip()
    low = raw.lower()

    # 1) 解析/切片类：parser 抛的已经是可读中文，直接透出
    try:
        from app.services import parser

        if isinstance(exc, parser.ParseError):
            return str(exc)
    except Exception:  # pragma: no cover
        pass

    # 2) 向量库自身抛的异常（中文前缀已明确）
    try:
        from app.services.vectorstore import VectorStoreUnavailable

        if isinstance(exc, VectorStoreUnavailable):
            return f"{exc}\n\n处理建议：检查向量库配置与数据目录权限；" \
                   "必要时停后端删除 server/data/chroma_db 后重启。"
    except Exception:  # pragma: no cover
        pass

    def _with_detail(hint: str) -> str:
        return f"{hint}\n\n原始错误：{raw[:300]}"

    if any(marker in low for marker in _CHROMA_MARKERS):
        logger.info("文档处理失败归类：向量库（%s）", low[:120])
        return _with_detail(_CHROMA_HINT)

    if any(marker in low for marker in _AUTH_MARKERS):
        logger.info("文档处理失败归类：鉴权（%s）", low[:120])
        return _with_detail(_AUTH_HINT)

    if any(marker in low for marker in _QUOTA_MARKERS):
        logger.info("文档处理失败归类：额度/限流（%s）", low[:120])
        return _with_detail(_QUOTA_HINT)

    if any(marker in low for marker in _NETWORK_MARKERS):
        logger.info("文档处理失败归类：网络（%s）", low[:120])
        return _with_detail(_NETWORK_HINT)

    return (
        "文档处理失败。请点「重新索引」重试；若持续失败，把下面的原始错误发给管理员。\n\n"
        f"原始错误：{raw[:300]}"
    )
