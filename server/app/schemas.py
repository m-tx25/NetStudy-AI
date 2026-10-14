"""Pydantic 模型（对外契约）。

关键约定：字段名必须与前端 client/src/api/mock.js 完全一致，
即 camelCase（documentCount / knowledgeBaseIds / uploadedAt …）。
数据库层是 snake_case，转换集中在这里，业务代码不感知。

入参一律用 alias 接收 camelCase，并开启 populate_by_name 以兼容 snake_case 调用。
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


def to_camel(snake: str) -> str:
    head, *rest = snake.split("_")
    return head + "".join(word.capitalize() for word in rest)


class CamelModel(BaseModel):
    """统一开启 camelCase 别名与序列化。"""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


# --------------------------------------------------------------------------
# 鉴权
# --------------------------------------------------------------------------
class LoginIn(CamelModel):
    username: str
    password: str


class RegisterIn(CamelModel):
    username: str
    email: str = ""
    password: str


class UpdateProfileIn(CamelModel):
    """只传需要修改的字段。"""

    username: str | None = None
    nickname: str | None = None
    email: str | None = None
    avatar: str | None = None


class ChangePasswordIn(CamelModel):
    current_password: str
    new_password: str


class ForgotPasswordIn(CamelModel):
    username: str = ""
    email: str = ""


class UserOut(CamelModel):
    id: str
    username: str
    nickname: str = ""
    email: str = ""
    avatar: str = ""
    role: str = "user"
    created_at: str | None = None
    last_login_at: str | None = None


class TokenOut(CamelModel):
    token: str
    user: UserOut


class OkOut(CamelModel):
    ok: bool = True


# --------------------------------------------------------------------------
# 知识库与文档
# --------------------------------------------------------------------------
class KnowledgeBaseIn(CamelModel):
    name: str
    description: str = ""
    embedding_model: str | None = None
    # 传团队 id 则创建团队知识库（需为该团队成员），留空创建个人库
    team_id: str | None = None

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, value: str) -> str:
        value = (value or "").strip()
        if not value:
            raise ValueError("知识库名称不能为空")
        if len(value) > 128:
            raise ValueError("知识库名称不能超过 128 个字符")
        return value


class KnowledgeBaseUpdateIn(CamelModel):
    name: str | None = None
    description: str | None = None
    embedding_model: str | None = None


class KnowledgeBaseOut(CamelModel):
    id: str
    # user=个人库 / team=团队库，前端据此分组与显示团队标签
    owner_type: str = "user"
    owner_id: str = ""
    name: str
    description: str = ""
    document_count: int = 0
    chunk_count: int = 0
    embedding_model: str = ""
    created_at: str | None = None
    updated_at: str | None = None


class DocumentOut(CamelModel):
    id: str
    knowledge_base_id: str
    name: str
    size: int = 0
    chunks: int = 0
    status: str = "processing"
    enabled: bool = True
    uploaded_at: str | None = None
    # 前端未使用，便于排查解析失败原因
    error: str = ""


class DocumentUpdateIn(CamelModel):
    name: str | None = None
    enabled: bool | None = None


# --------------------------------------------------------------------------
# 会话与消息
# --------------------------------------------------------------------------
class ConversationIn(CamelModel):
    title: str | None = None
    knowledge_base_ids: list[str] = Field(default_factory=list)


class ConversationUpdateIn(CamelModel):
    title: str | None = None
    knowledge_base_ids: list[str] | None = None


class ConversationOut(CamelModel):
    id: str
    title: str
    created_at: str | None = None
    updated_at: str | None = None
    message_count: int = 0
    knowledge_base_ids: list[str] = Field(default_factory=list)


class SourceOut(CamelModel):
    id: str
    document_id: str = ""
    document_name: str = ""
    knowledge_base_id: str = ""
    knowledge_base_name: str = ""
    score: float = 0.0
    page: int | None = None
    snippet: str = ""


class MessageOut(CamelModel):
    id: str
    role: Literal["user", "assistant", "system"]
    content: str = ""
    sources: list[SourceOut] = Field(default_factory=list)
    created_at: str | None = None
    status: str = "done"
    # knowledge_base / model / none —— 前端据此标注「非知识库依据」
    source: str = "knowledge_base"


class StreamChatIn(CamelModel):
    conversation_id: str | None = None
    content: str
    knowledge_base_ids: list[str] = Field(default_factory=list)
    top_k: int | None = None
    score_threshold: float | None = None
    # 生成模型 id（见 GET /api/chat/models）；留空则用服务端默认模型。
    # 与向量化模型无关 —— 检索始终用 ZHIPUAI_* 配置的 embedding 模型。
    model_id: str | None = None

    @field_validator("content")
    @classmethod
    def _content_not_blank(cls, value: str) -> str:
        value = (value or "").strip()
        if not value:
            raise ValueError("问题内容不能为空")
        return value


class HealthOut(CamelModel):
    ok: bool = True
    service: str
    time: str
    llm_configured: bool = False
    embedding_mode: str = "hash-fallback"
    queue: dict[str, Any] = Field(default_factory=dict)


# ==========================================================================
# 团队
# ==========================================================================
class UserBrief(CamelModel):
    """成员展示用的精简用户信息（不含邮箱等敏感字段）。"""

    id: str
    username: str
    nickname: str = ""
    avatar: str = ""


class TeamCreateIn(CamelModel):
    name: str
    description: str = ""
    visibility: Literal["public", "private"] = "public"
    join_policy: Literal["open", "approval", "closed"] = "approval"

    @field_validator("name")
    @classmethod
    def _name_required(cls, value: str) -> str:
        value = (value or "").strip()
        if not value:
            raise ValueError("团队名称不能为空")
        if len(value) > 64:
            raise ValueError("团队名称不能超过 64 个字符")
        return value


class TeamUpdateIn(CamelModel):
    name: str | None = None
    description: str | None = None
    visibility: Literal["public", "private"] | None = None
    join_policy: Literal["open", "approval", "closed"] | None = None


class TeamOut(CamelModel):
    id: str
    name: str
    description: str = ""
    visibility: str = "public"
    join_policy: str = "approval"
    # 仅 owner / admin 会拿到邀请码，普通成员为 None
    invite_code: str | None = None
    owner_id: str
    owner: UserBrief | None = None
    created_at: str | None = None
    updated_at: str | None = None
    # 当前登录者在该团队中的角色；非成员为 None
    my_role: str | None = None
    member_count: int = 0
    knowledge_base_count: int = 0
    # 当前登录者是否有待审批的申请
    my_request_status: str | None = None
    pending_request_count: int = 0


class TeamMemberOut(CamelModel):
    id: str
    user_id: str
    role: str
    joined_at: str | None = None
    user: UserBrief | None = None


class TeamMemberAddIn(CamelModel):
    """owner/admin 直接拉人（免审批）。"""

    username: str
    role: Literal["admin", "member"] = "member"


class TeamMemberRoleIn(CamelModel):
    role: Literal["admin", "member"]


class TeamTransferIn(CamelModel):
    """转让负责人：目标必须是该团队成员。"""

    user_id: str


class TeamJoinIn(CamelModel):
    """申请入队（搜索或邀请码）。"""

    message: str = ""
    invite_code: str | None = None


class TeamJoinRequestOut(CamelModel):
    id: str
    team_id: str
    team_name: str = ""
    user_id: str
    user: UserBrief | None = None
    message: str = ""
    source: str = "search"
    status: str = "pending"
    created_at: str | None = None
    handled_at: str | None = None


class TeamJoinHandleIn(CamelModel):
    approve: bool
    role: Literal["admin", "member"] = "member"


# ==========================================================================
# API 密钥
# ==========================================================================
class ApiKeyIn(CamelModel):
    provider: str
    secret: str
    label: str = ""
    model: str = ""
    base_url: str = ""
    enabled: bool = True

    @field_validator("secret")
    @classmethod
    def _secret_required(cls, value: str) -> str:
        value = (value or "").strip()
        if not value:
            raise ValueError("密钥不能为空")
        return value


class ApiKeyUpdateIn(CamelModel):
    """更新时 secret 留空表示「不改密钥，只改其它字段」。"""

    secret: str | None = None
    label: str | None = None
    model: str | None = None
    base_url: str | None = None
    enabled: bool | None = None


class ApiKeyOut(CamelModel):
    id: str
    provider: str
    provider_label: str = ""
    label: str = ""
    # 掩码，绝不下发明文
    masked: str = ""
    model: str = ""
    base_url: str = ""
    enabled: bool = True
    capabilities: list[str] = Field(default_factory=list)
    created_at: str | None = None
    updated_at: str | None = None
    # 是否为当前实际生效的密钥（同 provider 下只解析一条）
    is_active: bool = False


class ProviderOut(CamelModel):
    id: str
    label: str
    capabilities: list[str] = Field(default_factory=list)
    default_base_url: str = ""
    default_embedding_model: str = ""
    default_chat_model: str = ""
    key_hint: str = ""
    apply_url: str = ""


class ApiKeyScopesOut(CamelModel):
    """密钥总览：供应商清单 + 各作用域已配置情况。"""

    providers: list[ProviderOut] = Field(default_factory=list)
    user_keys: list[ApiKeyOut] = Field(default_factory=list)
    team_keys: list[ApiKeyOut] = Field(default_factory=list)
    effective: dict[str, Any] = Field(default_factory=dict)


class ModelOptionOut(CamelModel):
    id: str
    label: str
    model: str = ""
    configured: bool = False
    source: str = "server"
