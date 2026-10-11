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


class StreamChatIn(CamelModel):
    conversation_id: str | None = None
    content: str
    knowledge_base_ids: list[str] = Field(default_factory=list)
    top_k: int | None = None
    score_threshold: float | None = None

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
