"""知识库访问控制（个人库 / 团队库统一判定）。

放在独立模块是为了让 knowledge_bases / documents / chat 三处**共用同一套规则**，
避免各写一份导致权限口径不一致。

规则：
    个人库（owner_type=user）：只有 owner_id 本人可访问
    团队库（owner_type=team）：owner_id 是团队 id，该团队成员（owner/admin/member）
                              都可访问 —— 团队知识库本就是「成员都能上传」的
"""

from __future__ import annotations

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import KnowledgeBase, TeamMember

OWNER_USER = "user"
OWNER_TEAM = "team"


async def member_team_ids(db: AsyncSession, user_id: str) -> list[str]:
    """用户所在的团队 id 列表。"""
    rows = await db.execute(
        select(TeamMember.team_id).where(TeamMember.user_id == user_id)
    )
    return list(rows.scalars().all())


async def is_team_member(db: AsyncSession, team_id: str, user_id: str) -> bool:
    row = await db.execute(
        select(TeamMember.id)
        .where(TeamMember.team_id == team_id)
        .where(TeamMember.user_id == user_id)
    )
    return row.scalar_one_or_none() is not None


async def team_role(db: AsyncSession, team_id: str, user_id: str) -> str | None:
    row = await db.execute(
        select(TeamMember.role)
        .where(TeamMember.team_id == team_id)
        .where(TeamMember.user_id == user_id)
    )
    return row.scalar_one_or_none()


def accessible_condition(user_id: str, team_ids: list[str]):
    """生成「可访问的知识库」SQL 条件。

    注意 owner_type 可能为 **NULL**：该列是后加的（见 database._ensure_columns），
    早期数据迁移时没有默认值，老行会是 NULL。
    语义上 NULL 等价于「个人库」，因此这里必须把 NULL 也算进去，
    否则老用户会看到「知识库数量为 0」，而数据其实都还在。
    """
    personal = and_(
        or_(
            KnowledgeBase.owner_type == OWNER_USER,
            KnowledgeBase.owner_type.is_(None),
        ),
        KnowledgeBase.owner_id == user_id,
    )
    if not team_ids:
        return personal
    return or_(
        personal,
        and_(
            KnowledgeBase.owner_type == OWNER_TEAM,
            KnowledgeBase.owner_id.in_(team_ids),
        ),
    )


async def get_accessible(
    db: AsyncSession, knowledge_base_id: str, user_id: str
) -> KnowledgeBase | None:
    """取知识库；无权访问时返回 None（调用方统一按 404 处理，不暴露存在性）。"""
    base = (
        await db.execute(
            select(KnowledgeBase).where(KnowledgeBase.id == knowledge_base_id)
        )
    ).scalar_one_or_none()
    if base is None:
        return None

    if (base.owner_type or OWNER_USER) == OWNER_TEAM:
        if await is_team_member(db, base.owner_id, user_id):
            return base
        return None

    return base if base.owner_id == user_id else None
