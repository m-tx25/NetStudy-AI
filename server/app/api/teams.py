"""团队路由：/api/teams/*。

权限模型（沿用语微信群/QQ 群的直觉）：

    动作                     owner   admin   member
    -------------------------------------------------
    查看团队详情              ✓       ✓       ✓
    修改团队信息              ✓       ✓       ✗
    审批入队申请              ✓       ✓       ✗
    直接添加成员              ✓       ✓       ✗
    移除成员 / 改角色         ✓       ✓(仅普通成员)  ✗
    禁用团队知识库            ✓       ✓       ✗
    转让负责人 / 解散团队     ✓       ✗       ✗
    查看邀请码                ✓       ✓       ✗
    退出团队                  ✗(需先转让) ✓      ✓

设计约定：
  - 团队的**创建者即 owner**，且创建时会自动写入一条 role=owner 的成员记录，
    这样「是否成员」只需查 team_members 一张表；
  - 团队 → 知识库的关联复用 KnowledgeBase.owner_type/owner_id，
    不额外建关联表（见 models.py 的说明）。
"""

from __future__ import annotations

import logging
import secrets
import string

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import delete, func, or_, select

from app.api.deps import CurrentUser, DbSession
from app.models import (
    Document,
    KnowledgeBase,
    Team,
    TeamJoinRequest,
    TeamMember,
    User,
    now_utc,
)
from app.schemas import (
    OkOut,
    TeamCreateIn,
    TeamJoinHandleIn,
    TeamJoinIn,
    TeamJoinRequestOut,
    TeamMemberAddIn,
    TeamMemberOut,
    TeamMemberRoleIn,
    TeamOut,
    TeamTransferIn,
    TeamUpdateIn,
    UserBrief,
)
from app.utils.ids import new_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/teams", tags=["teams"])

ROLE_OWNER = "owner"
ROLE_ADMIN = "admin"
ROLE_MEMBER = "member"

_INVITE_ALPHABET = string.ascii_uppercase + string.digits


def _new_invite_code(length: int = 8) -> str:
    """生成易读的邀请码（去掉容易混淆的 0/O/1/I）。"""
    alphabet = _INVITE_ALPHABET.replace("O", "").replace("I", "").replace("0", "").replace("1", "")
    return "".join(secrets.choice(alphabet) for _ in range(length))


async def _unique_invite_code(db: DbSession) -> str:
    for _ in range(10):
        code = _new_invite_code()
        exists = (
            await db.execute(select(Team.id).where(Team.invite_code == code))
        ).scalar_one_or_none()
        if not exists:
            return code
    # 极小概率连续撞码：退回带时间戳的长码
    return f"{_new_invite_code(6)}{secrets.randbelow(1000):03d}"


async def _member_of(db: DbSession, team_id: str, user_id: str) -> TeamMember | None:
    row = await db.execute(
        select(TeamMember)
        .where(TeamMember.team_id == team_id)
        .where(TeamMember.user_id == user_id)
    )
    return row.scalar_one_or_none()


async def _require_member(db: DbSession, team_id: str, user: User) -> TeamMember:
    member = await _member_of(db, team_id, user.id)
    if member is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="你不是该团队成员")
    return member


async def _require_admin(db: DbSession, team_id: str, user: User) -> TeamMember:
    member = await _require_member(db, team_id, user)
    if member.role not in (ROLE_OWNER, ROLE_ADMIN):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="需要管理员或负责人权限")
    return member


async def _require_owner(db: DbSession, team_id: str, user: User) -> TeamMember:
    member = await _require_member(db, team_id, user)
    if member.role != ROLE_OWNER:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="仅团队负责人可执行该操作")
    return member


async def _user_brief(db: DbSession, user_id: str) -> UserBrief | None:
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None:
        return None
    return UserBrief(
        id=user.id, username=user.username, nickname=user.nickname or user.username,
        avatar=user.avatar or "",
    )


async def _team_stats(db: DbSession, team_id: str) -> tuple[int, int, int]:
    """返回 (成员数, 知识库数, 待审批数)。"""
    members = (
        await db.execute(
            select(func.count(TeamMember.id)).where(TeamMember.team_id == team_id)
        )
    ).scalar_one()
    kbs = (
        await db.execute(
            select(func.count(KnowledgeBase.id))
            .where(KnowledgeBase.owner_type == "team")
            .where(KnowledgeBase.owner_id == team_id)
        )
    ).scalar_one()
    pending = (
        await db.execute(
            select(func.count(TeamJoinRequest.id))
            .where(TeamJoinRequest.team_id == team_id)
            .where(TeamJoinRequest.status == "pending")
        )
    ).scalar_one()
    return int(members or 0), int(kbs or 0), int(pending or 0)


async def _team_out(
    db: DbSession, team: Team, viewer: User, my_role: str | None = None
) -> TeamOut:
    member_count, kb_count, pending = await _team_stats(db, team.id)
    # 只有管理者能看到邀请码（避免邀请码被任意成员外泄）
    can_manage = my_role in (ROLE_OWNER, ROLE_ADMIN)
    my_request = None
    if my_role is None:
        row = (
            await db.execute(
                select(TeamJoinRequest.status)
                .where(TeamJoinRequest.team_id == team.id)
                .where(TeamJoinRequest.user_id == viewer.id)
                .where(TeamJoinRequest.status == "pending")
            )
        ).scalar_one_or_none()
        my_request = row
    return TeamOut(
        id=team.id,
        name=team.name,
        description=team.description or "",
        visibility=team.visibility,
        join_policy=team.join_policy,
        invite_code=team.invite_code if can_manage else None,
        owner_id=team.owner_id,
        owner=await _user_brief(db, team.owner_id),
        created_at=team.created_at.isoformat() if team.created_at else None,
        updated_at=team.updated_at.isoformat() if team.updated_at else None,
        my_role=my_role,
        member_count=member_count,
        knowledge_base_count=kb_count,
        my_request_status=my_request,
        pending_request_count=pending if can_manage else 0,
    )


# ==========================================================================
# 团队 CRUD
# ==========================================================================
@router.post("", response_model=TeamOut)
async def create_team(payload: TeamCreateIn, user: CurrentUser, db: DbSession) -> TeamOut:
    team = Team(
        id=new_id("team"),
        name=payload.name,
        description=payload.description or "",
        visibility=payload.visibility,
        join_policy=payload.join_policy,
        invite_code=await _unique_invite_code(db),
        owner_id=user.id,
    )
    db.add(team)
    # 创建者自动成为 owner 成员
    db.add(
        TeamMember(
            id=new_id("tm"),
            team_id=team.id,
            user_id=user.id,
            role=ROLE_OWNER,
        )
    )
    await db.flush()
    logger.info("团队已创建 id=%s name=%s owner=%s", team.id, team.name, user.id)
    return await _team_out(db, team, user, ROLE_OWNER)


@router.get("", response_model=list[TeamOut])
async def list_my_teams(user: CurrentUser, db: DbSession) -> list[TeamOut]:
    """我加入的团队。"""
    rows = (
        await db.execute(
            select(Team, TeamMember.role)
            .join(TeamMember, TeamMember.team_id == Team.id)
            .where(TeamMember.user_id == user.id)
            .order_by(Team.updated_at.desc())
        )
    ).all()
    return [await _team_out(db, team, user, role) for team, role in rows]


@router.get("/search", response_model=list[TeamOut])
async def search_teams(
    user: CurrentUser,
    db: DbSession,
    q: str = Query("", description="团队名关键字，留空则列出可加入的公开团队"),
    limit: int = Query(20, ge=1, le=50),
) -> list[TeamOut]:
    """搜索可加入的团队（只返回公开团队）。

    已在团队里的、以及已提交待审批申请的都照常返回，
    由前端根据 myRole / myRequestStatus 展示不同按钮。
    """
    statement = select(Team).where(Team.visibility == "public")
    keyword = (q or "").strip()
    if keyword:
        statement = statement.where(
            or_(Team.name.like(f"%{keyword}%"), Team.description.like(f"%{keyword}%"))
        )
    statement = statement.order_by(Team.updated_at.desc()).limit(limit)
    teams = list((await db.execute(statement)).scalars().all())

    result: list[TeamOut] = []
    for team in teams:
        member = await _member_of(db, team.id, user.id)
        result.append(await _team_out(db, team, user, member.role if member else None))
    return result


@router.get("/join-requests/mine", response_model=list[TeamJoinRequestOut])
async def my_join_requests(user: CurrentUser, db: DbSession) -> list[TeamJoinRequestOut]:
    """我提交的入队申请（含历史记录）。"""
    rows = (
        await db.execute(
            select(TeamJoinRequest, Team.name)
            .join(Team, Team.id == TeamJoinRequest.team_id)
            .where(TeamJoinRequest.user_id == user.id)
            .order_by(TeamJoinRequest.created_at.desc())
        )
    ).all()
    return [
        TeamJoinRequestOut(
            id=req.id,
            team_id=req.team_id,
            team_name=name,
            user_id=req.user_id,
            message=req.message or "",
            source=req.source,
            status=req.status,
            created_at=req.created_at.isoformat() if req.created_at else None,
            handled_at=req.handled_at.isoformat() if req.handled_at else None,
        )
        for req, name in rows
    ]


@router.get("/invite/{invite_code}", response_model=TeamOut)
async def preview_by_invite(invite_code: str, user: CurrentUser, db: DbSession) -> TeamOut:
    """用邀请码查看团队信息（加入前的预览）。"""
    team = (
        await db.execute(select(Team).where(Team.invite_code == invite_code.strip().upper()))
    ).scalar_one_or_none()
    if team is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="邀请码无效")
    member = await _member_of(db, team.id, user.id)
    return await _team_out(db, team, user, member.role if member else None)


@router.get("/{team_id}", response_model=TeamOut)
async def get_team(team_id: str, user: CurrentUser, db: DbSession) -> TeamOut:
    team = (await db.execute(select(Team).where(Team.id == team_id))).scalar_one_or_none()
    if team is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="团队不存在")
    member = await _member_of(db, team.id, user.id)
    # 私有团队：非成员不可见（除非已提交申请，用于查看审批进度）
    if team.visibility == "private" and member is None:
        pending = (
            await db.execute(
                select(TeamJoinRequest.id)
                .where(TeamJoinRequest.team_id == team.id)
                .where(TeamJoinRequest.user_id == user.id)
                .where(TeamJoinRequest.status == "pending")
            )
        ).scalar_one_or_none()
        if not pending:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="团队不存在或不可见")
    return await _team_out(db, team, user, member.role if member else None)


@router.patch("/{team_id}", response_model=TeamOut)
async def update_team(
    team_id: str, payload: TeamUpdateIn, user: CurrentUser, db: DbSession
) -> TeamOut:
    member = await _require_admin(db, team_id, user)
    team = (await db.execute(select(Team).where(Team.id == team_id))).scalar_one()
    if payload.name is not None:
        name = payload.name.strip()
        if not name:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="团队名称不能为空")
        team.name = name[:64]
    if payload.description is not None:
        team.description = payload.description
    if payload.visibility is not None:
        team.visibility = payload.visibility
    if payload.join_policy is not None:
        team.join_policy = payload.join_policy
    team.updated_at = now_utc()
    await db.flush()
    return await _team_out(db, team, user, member.role)


@router.delete("/{team_id}", response_model=OkOut)
async def delete_team(team_id: str, user: CurrentUser, db: DbSession) -> OkOut:
    """解散团队（仅 owner）。会连带删除团队知识库、文档与向量。"""
    await _require_owner(db, team_id, user)
    team = (await db.execute(select(Team).where(Team.id == team_id))).scalar_one()

    # 团队知识库下的文档一并清理（向量由调用方或后续清理任务处理）
    kb_ids = [
        row
        for row in (
            await db.execute(
                select(KnowledgeBase.id)
                .where(KnowledgeBase.owner_type == "team")
                .where(KnowledgeBase.owner_id == team_id)
            )
        ).scalars().all()
    ]
    if kb_ids:
        await db.execute(delete(Document).where(Document.knowledge_base_id.in_(kb_ids)))
        await db.execute(delete(KnowledgeBase).where(KnowledgeBase.id.in_(kb_ids)))

    await db.delete(team)
    await db.flush()
    logger.info("团队已解散 id=%s by=%s 连带知识库=%s", team_id, user.id, len(kb_ids))
    return OkOut(ok=True)


@router.post("/{team_id}/invite-code", response_model=TeamOut)
async def regenerate_invite_code(
    team_id: str, user: CurrentUser, db: DbSession
) -> TeamOut:
    """重置邀请码（旧码立即失效）。"""
    member = await _require_admin(db, team_id, user)
    team = (await db.execute(select(Team).where(Team.id == team_id))).scalar_one()
    team.invite_code = await _unique_invite_code(db)
    team.updated_at = now_utc()
    await db.flush()
    return await _team_out(db, team, user, member.role)


# ==========================================================================
# 成员
# ==========================================================================
@router.get("/{team_id}/members", response_model=list[TeamMemberOut])
async def list_members(team_id: str, user: CurrentUser, db: DbSession) -> list[TeamMemberOut]:
    await _require_member(db, team_id, user)
    rows = (
        await db.execute(
            select(TeamMember, User)
            .join(User, User.id == TeamMember.user_id)
            .where(TeamMember.team_id == team_id)
            .order_by(
                # owner 在前，其次 admin，最后按加入时间
                TeamMember.role.asc(),
                TeamMember.joined_at.asc(),
            )
        )
    ).all()
    order = {ROLE_OWNER: 0, ROLE_ADMIN: 1, ROLE_MEMBER: 2}
    members = [
        TeamMemberOut(
            id=tm.id,
            user_id=tm.user_id,
            role=tm.role,
            joined_at=tm.joined_at.isoformat() if tm.joined_at else None,
            user=UserBrief(
                id=u.id, username=u.username, nickname=u.nickname or u.username,
                avatar=u.avatar or "",
            ),
        )
        for tm, u in rows
    ]
    members.sort(key=lambda m: order.get(m.role, 9))
    return members


@router.post("/{team_id}/members", response_model=TeamMemberOut)
async def add_member(
    team_id: str, payload: TeamMemberAddIn, user: CurrentUser, db: DbSession
) -> TeamMemberOut:
    """owner/admin 直接拉人入队（免审批）。"""
    await _require_admin(db, team_id, user)

    target = (
        await db.execute(select(User).where(User.username == payload.username.strip()))
    ).scalar_one_or_none()
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="用户不存在")

    existing = await _member_of(db, team_id, target.id)
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="该用户已在团队中")

    member = TeamMember(
        id=new_id("tm"), team_id=team_id, user_id=target.id, role=payload.role
    )
    db.add(member)
    # 直接拉人时，撤销其待审批申请，避免审核列表里残留
    await db.execute(
        delete(TeamJoinRequest)
        .where(TeamJoinRequest.team_id == team_id)
        .where(TeamJoinRequest.user_id == target.id)
        .where(TeamJoinRequest.status == "pending")
    )
    await db.flush()
    logger.info("团队成员已添加 team=%s user=%s role=%s", team_id, target.id, payload.role)
    return TeamMemberOut(
        id=member.id,
        user_id=member.user_id,
        role=member.role,
        joined_at=member.joined_at.isoformat() if member.joined_at else None,
        user=UserBrief(
            id=target.id, username=target.username,
            nickname=target.nickname or target.username, avatar=target.avatar or "",
        ),
    )


@router.patch("/{team_id}/members/{member_user_id}", response_model=TeamMemberOut)
async def set_member_role(
    team_id: str,
    member_user_id: str,
    payload: TeamMemberRoleIn,
    user: CurrentUser,
    db: DbSession,
) -> TeamMemberOut:
    """设置成员角色（owner/admin 可设 admin 或降级为 member）。

    owner 角色不能通过本接口设置 —— 转让负责人请用 /transfer。
    """
    actor = await _require_admin(db, team_id, user)
    target = await _member_of(db, team_id, member_user_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="成员不存在")
    if target.role == ROLE_OWNER:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="不能修改负责人的角色，请使用转让功能"
        )
    # 管理员只能管理普通成员，不能互相降级（避免内斗）
    if actor.role == ROLE_ADMIN and target.role == ROLE_ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="管理员之间不能互相修改角色")
    if member_user_id == user.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="不能修改自己的角色")

    target.role = payload.role
    await db.flush()
    target_user = (
        await db.execute(select(User).where(User.id == member_user_id))
    ).scalar_one_or_none()
    return TeamMemberOut(
        id=target.id,
        user_id=target.user_id,
        role=target.role,
        joined_at=target.joined_at.isoformat() if target.joined_at else None,
        user=UserBrief(
            id=target_user.id,
            username=target_user.username,
            nickname=target_user.nickname or target_user.username,
            avatar=target_user.avatar or "",
        )
        if target_user
        else None,
    )


@router.delete("/{team_id}/members/{member_user_id}", response_model=OkOut)
async def remove_member(
    team_id: str, member_user_id: str, user: CurrentUser, db: DbSession
) -> OkOut:
    """移除成员。owner 移除任意人；admin 只能移除普通成员；成员只能移除自己（退队）。"""
    actor = await _require_member(db, team_id, user)
    target = await _member_of(db, team_id, member_user_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="成员不存在")

    removing_self = member_user_id == user.id
    if not removing_self:
        if actor.role not in (ROLE_OWNER, ROLE_ADMIN):
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="没有权限移除成员")
        if target.role == ROLE_OWNER:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="不能移除团队负责人")
        if actor.role == ROLE_ADMIN and target.role == ROLE_ADMIN:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="管理员之间不能互相移除")
    else:
        # owner 退队前必须先转让，否则团队会没有负责人
        if actor.role == ROLE_OWNER:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="负责人不能直接退出，请先转让给其他成员",
            )

    await db.delete(target)
    await db.flush()
    logger.info("团队成员已移除 team=%s user=%s by=%s", team_id, member_user_id, user.id)
    return OkOut(ok=True)


@router.post("/{team_id}/transfer", response_model=TeamOut)
async def transfer_ownership(
    team_id: str, payload: TeamTransferIn, user: CurrentUser, db: DbSession
) -> TeamOut:
    """转让负责人：原 owner 降为 admin，目标成员升为 owner。"""
    await _require_owner(db, team_id, user)
    if payload.user_id == user.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="你已经是负责人")

    target = await _member_of(db, team_id, payload.user_id)
    if target is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="目标用户不是团队成员")

    actor_member = await _member_of(db, team_id, user.id)
    team = (await db.execute(select(Team).where(Team.id == team_id))).scalar_one()

    actor_member.role = ROLE_ADMIN  # 原负责人保留管理员权限，便于交接
    target.role = ROLE_OWNER
    team.owner_id = payload.user_id
    team.updated_at = now_utc()
    await db.flush()
    logger.info("团队负责人已转让 team=%s from=%s to=%s", team_id, user.id, payload.user_id)
    # 转让后当前用户是 admin，仍能看到邀请码
    return await _team_out(db, team, user, ROLE_ADMIN)


# ==========================================================================
# 入队：邀请码 / 搜索 / 审核
# ==========================================================================
async def _apply_join(
    db: DbSession, team: Team, user: User, message: str, source: str
) -> dict:
    """提交入队申请，或按 join_policy 直接加入。"""
    if await _member_of(db, team.id, user.id) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="你已经是该团队成员")

    if team.join_policy == "closed":
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="该团队已关闭加入")

    # open：直接入队
    if team.join_policy == "open":
        db.add(
            TeamMember(
                id=new_id("tm"), team_id=team.id, user_id=user.id, role=ROLE_MEMBER
            )
        )
        await db.flush()
        return {"ok": True, "status": "joined", "message": "已加入团队"}

    # approval：已有待审批申请则幂等返回
    existing = (
        await db.execute(
            select(TeamJoinRequest)
            .where(TeamJoinRequest.team_id == team.id)
            .where(TeamJoinRequest.user_id == user.id)
            .where(TeamJoinRequest.status == "pending")
        )
    ).scalar_one_or_none()
    if existing is not None:
        return {"ok": True, "status": "pending", "message": "申请已提交，等待管理员审批"}

    db.add(
        TeamJoinRequest(
            id=new_id("req"),
            team_id=team.id,
            user_id=user.id,
            message=(message or "")[:255],
            source=source,
            status="pending",
        )
    )
    await db.flush()
    return {"ok": True, "status": "pending", "message": "申请已提交，等待管理员审批"}


@router.post("/{team_id}/join")
async def join_team(
    team_id: str, payload: TeamJoinIn, user: CurrentUser, db: DbSession
) -> dict:
    """申请加入（搜索入口）。"""
    team = (await db.execute(select(Team).where(Team.id == team_id))).scalar_one_or_none()
    if team is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="团队不存在")
    return await _apply_join(db, team, user, payload.message, "search")


@router.post("/join-by-code")
async def join_by_invite_code(
    payload: TeamJoinIn, user: CurrentUser, db: DbSession
) -> dict:
    """用邀请码加入（邀请码入口）。"""
    code = (payload.invite_code or "").strip().upper()
    if not code:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="请填写邀请码")
    team = (
        await db.execute(select(Team).where(Team.invite_code == code))
    ).scalar_one_or_none()
    if team is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="邀请码无效")
    return await _apply_join(db, team, user, payload.message, "invite_code")


@router.get("/{team_id}/join-requests", response_model=list[TeamJoinRequestOut])
async def list_join_requests(
    team_id: str, user: CurrentUser, db: DbSession, status_filter: str = Query("pending")
) -> list[TeamJoinRequestOut]:
    """待审批申请列表（owner/admin）。"""
    await _require_admin(db, team_id, user)
    statement = select(TeamJoinRequest).where(TeamJoinRequest.team_id == team_id)
    if status_filter and status_filter != "all":
        statement = statement.where(TeamJoinRequest.status == status_filter)
    statement = statement.order_by(TeamJoinRequest.created_at.desc())
    rows = list((await db.execute(statement)).scalars().all())

    team_name = (
        await db.execute(select(Team.name).where(Team.id == team_id))
    ).scalar_one_or_none()
    result = []
    for req in rows:
        result.append(
            TeamJoinRequestOut(
                id=req.id,
                team_id=req.team_id,
                team_name=team_name or "",
                user_id=req.user_id,
                user=await _user_brief(db, req.user_id),
                message=req.message or "",
                source=req.source,
                status=req.status,
                created_at=req.created_at.isoformat() if req.created_at else None,
                handled_at=req.handled_at.isoformat() if req.handled_at else None,
            )
        )
    return result


@router.post("/{team_id}/join-requests/{request_id}", response_model=OkOut)
async def handle_join_request(
    team_id: str,
    request_id: str,
    payload: TeamJoinHandleIn,
    user: CurrentUser,
    db: DbSession,
) -> OkOut:
    """审批入队申请（QQ 群式的同意/拒绝）。"""
    await _require_admin(db, team_id, user)
    req = (
        await db.execute(
            select(TeamJoinRequest)
            .where(TeamJoinRequest.id == request_id)
            .where(TeamJoinRequest.team_id == team_id)
        )
    ).scalar_one_or_none()
    if req is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="申请不存在")
    if req.status != "pending":
        raise HTTPException(status.HTTP_409_CONFLICT, detail="该申请已处理")

    req.status = "approved" if payload.approve else "rejected"
    req.handled_at = now_utc()
    req.handled_by = user.id

    if payload.approve:
        if await _member_of(db, team_id, req.user_id) is None:
            db.add(
                TeamMember(
                    id=new_id("tm"),
                    team_id=team_id,
                    user_id=req.user_id,
                    role=payload.role,
                )
            )
    await db.flush()
    logger.info(
        "入队申请已处理 team=%s req=%s approve=%s by=%s",
        team_id, request_id, payload.approve, user.id,
    )
    return OkOut(ok=True)


@router.delete("/{team_id}/join-requests/{request_id}", response_model=OkOut)
async def cancel_my_join_request(
    team_id: str, request_id: str, user: CurrentUser, db: DbSession
) -> OkOut:
    """撤回自己提交的申请。"""
    req = (
        await db.execute(
            select(TeamJoinRequest)
            .where(TeamJoinRequest.id == request_id)
            .where(TeamJoinRequest.team_id == team_id)
            .where(TeamJoinRequest.user_id == user.id)
        )
    ).scalar_one_or_none()
    if req is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="申请不存在")
    if req.status != "pending":
        raise HTTPException(status.HTTP_409_CONFLICT, detail="该申请已处理，无法撤回")
    req.status = "rejected"
    req.handled_at = now_utc()
    req.handled_by = user.id
    await db.flush()
    return OkOut(ok=True)
