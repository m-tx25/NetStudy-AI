"""第三方 API 密钥的解析与作用域管理。

## 为什么要单独一层

密钥有多个来源，且**按知识库归属决定用谁的**：

| 场景 | 用谁的密钥 |
| --- | --- |
| 检索/索引**个人知识库** | 该用户自己的 Key（未配置则用服务端 Key） |
| 检索/索引**团队知识库** | 该团队的 Key（未配置则用服务端 Key） |
| 生成回答（问答） | 同一次问答所用知识库的归属方；无知识库时用提问者自己的 Key |

这样设计的好处：费用归属清晰（团队库花团队的钱），且**永远不会跨团队串用密钥**。

## Provider（供应商）

    zhipu     智谱：既能向量化（embedding-3）也能生成（glm 系列，OpenAI 兼容）
    deepseek  DeepSeek：**只能生成**，没有 /embeddings 接口
    openai    OpenAI 及任何兼容 /chat/completions 的服务
    custom    自填 base_url 的兼容服务（vLLM / Ollama / One-API …）

`capability` 描述该供应商能干什么，前端据此只在对应下拉框里列出可选项。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.secrets import decrypt_secret
from app.models import ApiKey

logger = logging.getLogger(__name__)

SCOPE_USER = "user"
SCOPE_TEAM = "team"

# 供应商清单：capability 决定它能用于「向量化」还是「生成」
PROVIDERS: dict[str, dict] = {
    "zhipu": {
        "label": "智谱 AI（GLM）",
        "capabilities": ["embedding", "chat"],
        "default_base_url": "https://open.bigmodel.cn/api/paas/v4",
        "default_embedding_model": "embedding-3",
        "default_chat_model": "glm-4-flash",
        "key_hint": "形如 xxxxxxxx.xxxxxxxx（带一个点），不是 sk- 开头",
        "apply_url": "https://open.bigmodel.cn/",
    },
    "deepseek": {
        "label": "DeepSeek",
        "capabilities": ["chat"],  # 没有 embedding 接口
        "default_base_url": "https://api.deepseek.com/v1",
        "default_chat_model": "deepseek-chat",
        "key_hint": "形如 sk-xxxxxxxx",
        "apply_url": "https://platform.deepseek.com/",
    },
    "openai": {
        "label": "OpenAI 兼容",
        "capabilities": ["chat", "embedding"],
        "default_base_url": "https://api.openai.com/v1",
        "default_embedding_model": "text-embedding-3-small",
        "default_chat_model": "gpt-4o-mini",
        "key_hint": "形如 sk-xxxxxxxx",
        "apply_url": "https://platform.openai.com/",
    },
    "custom": {
        "label": "自定义（Ollama / vLLM / One-API 等）",
        "capabilities": ["chat", "embedding"],
        "default_base_url": "",
        "default_chat_model": "",
        "default_embedding_model": "",
        "key_hint": "本地服务可填任意非空值",
        "apply_url": "",
    },
}


def provider_catalog() -> list[dict]:
    """下发给前端的供应商清单（不含任何密钥）。"""
    return [
        {"id": pid, **{k: v for k, v in meta.items()}}
        for pid, meta in PROVIDERS.items()
    ]


def provider_meta(provider: str) -> dict:
    return PROVIDERS.get(provider, PROVIDERS["custom"])


@dataclass
class ResolvedKey:
    """一次调用实际使用的密钥配置。"""

    provider: str
    secret: str
    source: str  # user / team / server / none
    base_url: str = ""
    model: str = ""
    scope_id: str = ""

    @property
    def usable(self) -> bool:
        return bool(self.secret)

    def describe(self) -> dict:
        """可安全下发的描述（绝不含明文密钥）。"""
        return {
            "provider": self.provider,
            "source": self.source,
            "configured": self.usable,
            "model": self.model or None,
            "baseUrl": self.base_url or None,
        }


# --------------------------------------------------------------------------
# 数据库查询
# --------------------------------------------------------------------------
async def list_keys(db: AsyncSession, scope_type: str, scope_id: str) -> list[ApiKey]:
    rows = await db.execute(
        select(ApiKey)
        .where(ApiKey.scope_type == scope_type)
        .where(ApiKey.scope_id == scope_id)
        .order_by(ApiKey.provider)
    )
    return list(rows.scalars().all())


async def get_key_row(
    db: AsyncSession, scope_type: str, scope_id: str, provider: str
) -> ApiKey | None:
    row = await db.execute(
        select(ApiKey)
        .where(ApiKey.scope_type == scope_type)
        .where(ApiKey.scope_id == scope_id)
        .where(ApiKey.provider == provider)
    )
    return row.scalar_one_or_none()


# --------------------------------------------------------------------------
# 解析
# --------------------------------------------------------------------------
def _server_key(provider: str, capability: str) -> ResolvedKey:
    """服务端 .env 兜底配置。"""
    if provider == "zhipu":
        return ResolvedKey(
            provider="zhipu",
            secret=settings.ZHIPUAI_API_KEY or "",
            source="server",
            base_url=PROVIDERS["zhipu"]["default_base_url"],
            model=settings.ZHIPUAI_EMBEDDING_MODEL
            if capability == "embedding"
            else settings.LLM_MODEL,
        )
    # 生成类：直接用 .env 的默认模型配置
    if capability == "chat":
        return ResolvedKey(
            provider=provider,
            secret=settings.LLM_API_KEY or "",
            source="server",
            base_url=settings.LLM_BASE_URL,
            model=settings.LLM_MODEL,
        )
    # 向量化但服务端只配了智谱
    return ResolvedKey(
        provider="zhipu",
        secret=settings.ZHIPUAI_API_KEY or "",
        source="server",
        base_url=PROVIDERS["zhipu"]["default_base_url"],
        model=settings.ZHIPUAI_EMBEDDING_MODEL,
    )


def _from_row(row: ApiKey, capability: str) -> ResolvedKey:
    """把数据库里的一行密钥转换成解析结果（解密失败则视为不可用）。"""
    meta = provider_meta(row.provider)
    model_field = (
        "default_embedding_model" if capability == "embedding" else "default_chat_model"
    )
    return ResolvedKey(
        provider=row.provider,
        secret=decrypt_secret(row.secret),
        source=row.scope_type,
        scope_id=row.scope_id,
        base_url=row.base_url or meta.get("default_base_url", ""),
        model=row.model or meta.get(model_field, ""),
    )


async def resolve_key(
    db: AsyncSession,
    provider: str,
    capability: str,
    *,
    team_id: str | None = None,
    user_id: str | None = None,
) -> ResolvedKey:
    """按作用域解析密钥：团队 Key → 用户 Key → 服务端 Key。

    团队优先于用户：查询团队知识库时不应花某个成员自己的钱。
    """
    if team_id:
        row = await get_key_row(db, SCOPE_TEAM, team_id, provider)
        if row and row.enabled:
            resolved = _from_row(row, capability)
            if resolved.usable:
                return resolved

    if user_id:
        row = await get_key_row(db, SCOPE_USER, user_id, provider)
        if row and row.enabled:
            resolved = _from_row(row, capability)
            if resolved.usable:
                return resolved

    return _server_key(provider, capability)


async def resolve_embedding_key(
    db: AsyncSession, *, team_id: str | None = None, user_id: str | None = None
) -> ResolvedKey:
    """向量化密钥。

    优先用**归属方自配**的可向量化供应商（zhipu / openai / custom），
    都没有时回落到服务端 .env 的智谱配置。
    """
    if team_id:
        for provider in ("zhipu", "openai", "custom"):
            row = await get_key_row(db, SCOPE_TEAM, team_id, provider)
            if row and row.enabled:
                resolved = _from_row(row, "embedding")
                if resolved.usable:
                    return resolved
    if user_id:
        for provider in ("zhipu", "openai", "custom"):
            row = await get_key_row(db, SCOPE_USER, user_id, provider)
            if row and row.enabled:
                resolved = _from_row(row, "embedding")
                if resolved.usable:
                    return resolved
    return _server_key("zhipu", "embedding")


async def resolve_chat_key(
    db: AsyncSession, *, team_id: str | None = None, user_id: str | None = None
) -> ResolvedKey:
    """生成密钥。优先归属方自配的生成类供应商，否则服务端默认。"""
    if team_id:
        for provider in ("deepseek", "zhipu", "openai", "custom"):
            row = await get_key_row(db, SCOPE_TEAM, team_id, provider)
            if row and row.enabled:
                resolved = _from_row(row, "chat")
                if resolved.usable:
                    return resolved
    if user_id:
        for provider in ("deepseek", "zhipu", "openai", "custom"):
            row = await get_key_row(db, SCOPE_USER, user_id, provider)
            if row and row.enabled:
                resolved = _from_row(row, "chat")
                if resolved.usable:
                    return resolved
    return _server_key("deepseek", "chat")


async def list_available_models(
    db: AsyncSession, *, team_id: str | None = None, user_id: str | None = None
) -> list[dict]:
    """合并「服务端配置的模型」与「用户/团队自配密钥」，供前端下拉选择。

    绝不下发任何密钥原文，只告知 id / label / 是否已配置。
    """
    models: list[dict] = []

    # 服务端在 .env 的 LLM_MODELS 里配置的模型
    for item in settings.public_models():
        models.append(
            {
                "id": f"server:{item['id']}",
                "label": item["label"],
                "model": item["model"],
                "configured": item["configured"],
                "source": "server",
            }
        )

    # 用户/团队自配的生成类密钥
    scopes: list[tuple[str, str]] = []
    if user_id:
        scopes.append((SCOPE_USER, user_id))
    if team_id:
        scopes.append((SCOPE_TEAM, team_id))

    for scope_type, scope_id in scopes:
        for row in await list_keys(db, scope_type, scope_id):
            meta = provider_meta(row.provider)
            if "chat" not in meta["capabilities"] or not row.enabled:
                continue
            models.append(
                {
                    "id": f"{scope_type}:{row.id}",
                    "label": f"{row.label or meta['label']}（{'团队' if scope_type == SCOPE_TEAM else '个人'}）",
                    "model": row.model or meta.get("default_chat_model", ""),
                    "configured": bool(decrypt_secret(row.secret)),
                    "source": scope_type,
                }
            )
    return models
