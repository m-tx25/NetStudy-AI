"""鉴权路由：/api/auth/*（7 个接口）。

与前端 client/src/api/auth.js 一一对应。
"""

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.api.serializers import user_out
from app.core.security import (
    create_access_token,
    hash_password,
    validate_email,
    validate_password,
    validate_username,
    verify_password,
)
from app.models import User
from app.schemas import (
    ChangePasswordIn,
    ForgotPasswordIn,
    LoginIn,
    OkOut,
    RegisterIn,
    TokenOut,
    UpdateProfileIn,
    UserOut,
)
from app.utils.ids import new_id

router = APIRouter(prefix="/auth", tags=["auth"])


async def _find_by_username(db: DbSession, username: str) -> User | None:
    return (await db.execute(select(User).where(User.username == username))).scalar_one_or_none()


@router.post("/login", response_model=TokenOut)
async def login(payload: LoginIn, db: DbSession) -> TokenOut:
    username = payload.username.strip()
    user = await _find_by_username(db, username)
    # 账号不存在与密码错误返回同一文案，避免用户名枚举
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码不正确"
        )

    user.last_login_at = datetime.now(timezone.utc)
    await db.flush()

    return TokenOut(
        token=create_access_token(user.id, user.token_version), user=UserOut(**user_out(user))
    )


@router.post("/register", response_model=TokenOut)
async def register(payload: RegisterIn, db: DbSession) -> TokenOut:
    username = payload.username.strip()

    if message := validate_username(username):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)
    if (message := validate_password(payload.password)):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)
    if payload.email and (message := validate_email(payload.email.strip())):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)
    if await _find_by_username(db, username):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该用户名已被注册")

    now = datetime.now(timezone.utc)
    user = User(
        id=new_id("user"),
        username=username,
        nickname=username,
        email=(payload.email or "").strip(),
        password_hash=hash_password(payload.password),
        role="user",
        created_at=now,
        last_login_at=now,
    )
    db.add(user)
    await db.flush()

    return TokenOut(
        token=create_access_token(user.id, user.token_version), user=UserOut(**user_out(user))
    )


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser) -> UserOut:
    return UserOut(**user_out(user))


@router.post("/logout", response_model=OkOut)
async def logout(user: CurrentUser) -> OkOut:
    """无状态 JWT：服务端不维护会话，退出即由前端丢弃 token。

    保留该接口是为了让前端调用链完整，也便于日后加入黑名单机制。
    """
    return OkOut(ok=True)


@router.patch("/profile", response_model=UserOut)
async def update_profile(payload: UpdateProfileIn, user: CurrentUser, db: DbSession) -> UserOut:
    if payload.username is not None:
        username = payload.username.strip()
        if (message := validate_username(username)):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)
        if username != user.username:
            existing = await _find_by_username(db, username)
            if existing is not None and existing.id != user.id:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该用户名已被占用")
            user.username = username

    if payload.email is not None:
        email = payload.email.strip()
        if email and (message := validate_email(email)):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)
        user.email = email

    if payload.nickname is not None:
        nickname = payload.nickname.strip()
        if len(nickname) > 32:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="昵称不能超过 32 个字符"
            )
        user.nickname = nickname

    if payload.avatar is not None:
        user.avatar = payload.avatar

    await db.flush()
    return UserOut(**user_out(user))


@router.put("/password", response_model=OkOut)
async def change_password(
    payload: ChangePasswordIn, user: CurrentUser, db: DbSession
) -> OkOut:
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="当前密码不正确")
    if (message := validate_password(payload.new_password)):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)
    if payload.new_password == payload.current_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="新密码不能与当前密码相同"
        )

    user.password_hash = hash_password(payload.new_password)
    # 递增版本号，使此前签发的所有 token 立即失效
    user.token_version = int(user.token_version or 1) + 1
    await db.flush()

    return OkOut(ok=True)


@router.post("/forgot-password", response_model=OkOut)
async def forgot_password(payload: ForgotPasswordIn) -> OkOut:
    """发送重置邮件。

    无论账号是否存在都返回成功，避免暴露注册状态（与前端提示一致）。
    接入真实邮件服务时在此处投递，并写入一次性重置令牌。
    """
    return OkOut(ok=True)
