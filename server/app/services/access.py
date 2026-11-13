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

# 能对「团队」本身做管理动作的角色。
# 注意：普通成员可以读写团队知识库（上传、检索），但**不能删除或改名整个库**，
# 否则任何成员一次误操作就能把全团队的资料清空。
TEAM_MANAGER_ROLES = ("owner", "admin")


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


async def can_manage_kb(
    db: AsyncSession, base: KnowledgeBase, user_id: str
) -> bool:
    """能否对该知识库做「管理动作」（改名、删除整库）。

    与 merely 可访问不同：
      个人库 → 本人可以
      团队库 → 只有 owner / admin 可以，普通成员不行
    """
    if (base.owner_type or OWNER_USER) == OWNER_TEAM:
        role = await team_role(db, base.owner_id, user_id)
        return role in TEAM_MANAGER_ROLES
    return base.owner_id == user_id


async def can_manage_document(
    db: AsyncSession, kb: KnowledgeBase, document, user_id: str
) -> bool:
    """能否管理某个文档（改名、启停、删除）。

    规则：
      个人库        → 本人可以
      团队库 · 管理员 → 可以管理该团队下的任意文档
      团队库 · 成员   → 只能管理**自己上传的**文档
                        （否则任何成员都能逐条删光大家的资料，
                         那与「直接删整库」没有实质区别）
    """
    if (kb.owner_type or OWNER_USER) != OWNER_TEAM:
        return kb.owner_id == user_id
    if await can_manage_kb(db, kb, user_id):
        return True
    uploaded_by = getattr(document, "uploaded_by", "") or ""
    # 历史文档的 uploaded_by 可能为空（补列时回填成 ''），此时只认管理员，
    # 避免「谁都能认领」的歧义。
    return bool(uploaded_by) and uploaded_by == user_id


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
