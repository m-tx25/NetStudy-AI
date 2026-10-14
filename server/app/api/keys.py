"""API 密钥路由：个人密钥 /api/keys*、团队密钥 /api/teams/{id}/keys*。

安全约定：
  - 密钥**加密后**存库（见 app/core/secrets.py），接口只回掩码与元信息；
  - 更新时 `secret` 留空表示「不改密钥，只改其它字段」；
  - 团队密钥仅 owner/admin 可读写，普通成员看不到任何密钥信息。

解析优先级见 app/services/keyring.py：团队 Key → 用户 Key → 服务端 .env。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.core.secrets import decrypt_secret, encrypt_secret, mask_secret
from app.models import ApiKey, TeamMember
from app.schemas import (
    ApiKeyIn,
    ApiKeyOut,
    ApiKeyScopesOut,
    ApiKeyUpdateIn,
    ModelOptionOut,
    OkOut,
    ProviderOut,
)
from app.services import keyring
from app.utils.ids import new_id

logger = logging.getLogger(__name__)

# 个人密钥：/api/keys
router = APIRouter(prefix="/keys", tags=["keys"])
# 团队密钥：/api/teams/{team_id}/keys
team_router = APIRouter(prefix="/teams", tags=["keys"])

ROLE_OWNER = "owner"
ROLE_ADMIN = "admin"


def _to_out(row: ApiKey, active_id: str | None = None) -> ApiKeyOut:
    meta = keyring.provider_meta(row.provider)
    plain = decrypt_secret(row.secret)
    return ApiKeyOut(
        id=row.id,
        provider=row.provider,
        provider_label=meta.get("label", row.provider),
        label=row.label or "",
        masked=mask_secret(plain) if plain else "",
        model=row.model or "",
        base_url=row.base_url or "",
        enabled=bool(row.enabled),
        capabilities=meta.get("capabilities", []),
        created_at=row.created_at.isoformat() if row.created_at else None,
        updated_at=row.updated_at.isoformat() if row.updated_at else None,
        is_active=(active_id == row.id),
    )


def _provider_list() -> list[ProviderOut]:
    return [ProviderOut(id=item["id"], **{k: v for k, v in item.items() if k != "id"})
            for item in keyring.provider_catalog()]


async def _effective_summary(db: DbSession, scope_type: str, scope_id: str) -> dict:
    """该作用域下每个 provider 当前是否已配置（供前端展示「生效中」）。"""
    summary: dict[str, dict] = {}
    for provider in keyring.PROVIDERS:
        key = await keyring.resolve_key(db, provider, "chat",
                                       team_id=scope_id if scope_type == "team" else None,
                                       user_id=scope_id if scope_type == "user" else None)
        summary[provider] = key.describe()
    return summary


async def _active_id_for(
    db: DbSession, scope_type: str, scope_id: str
) -> str | None:
    """找出当前实际生效的那条密钥 id（团队优先，其次用户，最后服务端无 id）。"""
    for provider in ("deepseek", "zhipu", "openai", "custom"):
        key = await keyring.resolve_key(
            db,
            provider,
            "chat",
            team_id=scope_id if scope_type == "team" else None,
            user_id=scope_id if scope_type == "user" else None,
        )
        if key.usable and key.scope_id:
            return key.scope_id
    return None


# ==========================================================================
# 供应商清单 / 可用模型
# ==========================================================================
@router.get("/providers", response_model=list[ProviderOut])
async def list_providers() -> list[ProviderOut]:
    """可选供应商（含它能做向量化还是生成）。"""
    return _provider_list()


@router.get("/models", response_model=list[ModelOptionOut])
async def list_models(
    user: CurrentUser,
    db: DbSession,
    team_id: str | None = Query(None, description="指定团队时把团队密钥也算进可选项"),
) -> list[ModelOptionOut]:
    """可用于「生成」的模型清单：服务端配置的 + 用户/团队自配密钥。"""
    models = await keyring.list_available_models(db, team_id=team_id, user_id=user.id)
    return [ModelOptionOut(**item) for item in models]


@router.get("", response_model=ApiKeyScopesOut)
async def overview(user: CurrentUser, db: DbSession) -> ApiKeyScopesOut:
    """个人密钥总览（团队密钥请用 /api/teams/{id}/keys）。"""
    rows = await keyring.list_keys(db, keyring.SCOPE_USER, user.id)
    active_scope = await _active_id_for(db, "user", user.id)
    return ApiKeyScopesOut(
        providers=_provider_list(),
        user_keys=[_to_out(row) for row in rows],
        team_keys=[],
        effective={
            "activeSource": "server" if not active_scope else "user",
            "serverConfigured": {
                "zhipu": bool(keyring.settings.ZHIPUAI_API_KEY),
                "deepseek": bool(keyring.settings.LLM_API_KEY),
            },
        },
    )


# ==========================================================================
# 个人密钥 CRUD
# ==========================================================================
@router.post("", response_model=ApiKeyOut)
async def upsert_user_key(payload: ApiKeyIn, user: CurrentUser, db: DbSession) -> ApiKeyOut:
    """新增或覆盖个人密钥（同一 provider 只保留一条）。"""
    if payload.provider not in keyring.PROVIDERS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="不支持的供应商")

    row = await keyring.get_key_row(db, keyring.SCOPE_USER, user.id, payload.provider)
    if row is None:
        row = ApiKey(
            id=new_id("key"),
            scope_type=keyring.SCOPE_USER,
            scope_id=user.id,
            provider=payload.provider,
        )
        db.add(row)
    row.label = payload.label or keyring.provider_meta(payload.provider).get("label", "")
    row.secret = encrypt_secret(payload.secret)
    row.model = payload.model or ""
    row.base_url = payload.base_url or ""
    row.enabled = payload.enabled
    await db.flush()
    logger.info("个人密钥已保存 user=%s provider=%s", user.id, payload.provider)
    return _to_out(row)


@router.patch("/{key_id}", response_model=ApiKeyOut)
async def update_user_key(
    key_id: str, payload: ApiKeyUpdateIn, user: CurrentUser, db: DbSession
) -> ApiKeyOut:
    row = (
        await db.execute(
            select(ApiKey)
            .where(ApiKey.id == key_id)
            .where(ApiKey.scope_type == keyring.SCOPE_USER)
            .where(ApiKey.scope_id == user.id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="密钥不存在")

    if payload.secret is not None and payload.secret.strip():
        row.secret = encrypt_secret(payload.secret.strip())
    if payload.label is not None:
        row.label = payload.label
    if payload.model is not None:
        row.model = payload.model
    if payload.base_url is not None:
        row.base_url = payload.base_url
    if payload.enabled is not None:
        row.enabled = payload.enabled
    await db.flush()
    return _to_out(row)


@router.delete("/{key_id}", response_model=OkOut)
async def delete_user_key(key_id: str, user: CurrentUser, db: DbSession) -> OkOut:
    row = (
        await db.execute(
            select(ApiKey)
            .where(ApiKey.id == key_id)
            .where(ApiKey.scope_type == keyring.SCOPE_USER)
            .where(ApiKey.scope_id == user.id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="密钥不存在")
    await db.delete(row)
    await db.flush()
    return OkOut(ok=True)


# ==========================================================================
# 团队密钥 CRUD（owner/admin 才能访问）
# ==========================================================================
async def _require_team_admin(db: DbSession, team_id: str, user_id: str) -> TeamMember:
    member = (
        await db.execute(
            select(TeamMember)
            .where(TeamMember.team_id == team_id)
            .where(TeamMember.user_id == user_id)
        )
    ).scalar_one_or_none()
    if member is None or member.role not in (ROLE_OWNER, ROLE_ADMIN):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="需要团队管理员或负责人权限")
    return member


@team_router.get("/{team_id}/keys", response_model=ApiKeyScopesOut)
async def overview_team_keys(
    team_id: str, user: CurrentUser, db: DbSession
) -> ApiKeyScopesOut:
    await _require_team_admin(db, team_id, user.id)
    rows = await keyring.list_keys(db, keyring.SCOPE_TEAM, team_id)
    active_scope = await _active_id_for(db, "team", team_id)
    return ApiKeyScopesOut(
        providers=_provider_list(),
        user_keys=[],
        team_keys=[_to_out(row) for row in rows],
        effective={
            "activeSource": "team" if active_scope else "server",
            "serverConfigured": {
                "zhipu": bool(keyring.settings.ZHIPUAI_API_KEY),
                "deepseek": bool(keyring.settings.LLM_API_KEY),
            },
        },
    )


@team_router.post("/{team_id}/keys", response_model=ApiKeyOut)
async def upsert_team_key(
    team_id: str, payload: ApiKeyIn, user: CurrentUser, db: DbSession
) -> ApiKeyOut:
    await _require_team_admin(db, team_id, user.id)
    if payload.provider not in keyring.PROVIDERS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="不支持的供应商")

    row = await keyring.get_key_row(db, keyring.SCOPE_TEAM, team_id, payload.provider)
    if row is None:
        row = ApiKey(
            id=new_id("key"),
            scope_type=keyring.SCOPE_TEAM,
            scope_id=team_id,
            provider=payload.provider,
        )
        db.add(row)
    row.label = payload.label or keyring.provider_meta(payload.provider).get("label", "")
    row.secret = encrypt_secret(payload.secret)
    row.model = payload.model or ""
    row.base_url = payload.base_url or ""
    row.enabled = payload.enabled
    await db.flush()
    logger.info("团队密钥已保存 team=%s provider=%s by=%s", team_id, payload.provider, user.id)
    return _to_out(row)


@team_router.patch("/{team_id}/keys/{key_id}", response_model=ApiKeyOut)
async def update_team_key(
    team_id: str, key_id: str, payload: ApiKeyUpdateIn, user: CurrentUser, db: DbSession
) -> ApiKeyOut:
    await _require_team_admin(db, team_id, user.id)
    row = (
        await db.execute(
            select(ApiKey)
            .where(ApiKey.id == key_id)
            .where(ApiKey.scope_type == keyring.SCOPE_TEAM)
            .where(ApiKey.scope_id == team_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="密钥不存在")

    if payload.secret is not None and payload.secret.strip():
        row.secret = encrypt_secret(payload.secret.strip())
    if payload.label is not None:
        row.label = payload.label
    if payload.model is not None:
        row.model = payload.model
    if payload.base_url is not None:
        row.base_url = payload.base_url
    if payload.enabled is not None:
        row.enabled = payload.enabled
    await db.flush()
    return _to_out(row)


@team_router.delete("/{team_id}/keys/{key_id}", response_model=OkOut)
async def delete_team_key(
    team_id: str, key_id: str, user: CurrentUser, db: DbSession
) -> OkOut:
    await _require_team_admin(db, team_id, user.id)
    row = (
        await db.execute(
            select(ApiKey)
            .where(ApiKey.id == key_id)
            .where(ApiKey.scope_type == keyring.SCOPE_TEAM)
            .where(ApiKey.scope_id == team_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="密钥不存在")
    await db.delete(row)
    await db.flush()
    return OkOut(ok=True)
