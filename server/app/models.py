"""ORM 模型（关系型数据库：MySQL）。

存储**业务数据**；向量由 ChromaDB 管理（见 app/services/vectorstore.py），
两者通过 knowledge_base_id / document_id 关联。

MySQL 相关注意点：
  - 字符集统一 utf8mb4（建库时指定），才能正确存储中文与 emoji；
  - 所有被索引的字符串列长度都控制在 255 以内 —— utf8mb4 下索引键上限 3072 字节，
    255×4 = 1020 字节，远低于上限，不会出现 "Specified key was too long"；
  - 长文本一律用 Text，不加索引。

命名约定：数据库用 snake_case；对外的 camelCase 由 serializers 层转换。
ID 一律使用带前缀的字符串（如 kb_xxx / doc_xxx），与前端 mock 数据形态一致。
"""

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso(value: datetime | None) -> str | None:
    """统一输出 ISO8601 字符串，前端直接 new Date(...) 解析。"""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    nickname: Mapped[str] = mapped_column(String(64), default="")
    email: Mapped[str] = mapped_column(String(255), default="")
    avatar: Mapped[str] = mapped_column(Text, default="")
    role: Mapped[str] = mapped_column(String(32), default="user")
    password_hash: Mapped[str] = mapped_column(String(255))
    # 改密码后此前签发的 token 全部失效：token 里的版本号与此不符即拒绝
    token_version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class KnowledgeBase(Base):
    __tablename__ = "knowledge_bases"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    # 归属类型：user（个人库，owner_id=用户）/ team（团队库，owner_id=团队）
    # 这两种库共用一张表，权限与检索隔离都靠 owner_type + owner_id 判断。
    owner_type: Mapped[str] = mapped_column(String(16), default="user", index=True)
    owner_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str] = mapped_column(Text, default="")
    # 记录建库时使用的向量模型，便于日后判断是否需要重建向量
    embedding_model: Mapped[str] = mapped_column(String(128), default="embedding-3")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=now_utc, onupdate=now_utc
    )

    documents: Mapped[list["Document"]] = relationship(
        back_populates="knowledge_base", cascade="all, delete-orphan"
    )


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    knowledge_base_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("knowledge_bases.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(512))
    # 上传者用户 id。团队知识库的文档由多位成员上传，
    # 记录上传者才能在重新索引时写入正确的向量归属（见 vectorstore.add_chunks 的 owner_id）。
    uploaded_by: Mapped[str] = mapped_column(String(64), default="", index=True)
    # 原始文件在磁盘上的相对路径
    stored_path: Mapped[str] = mapped_column(Text, default="")
    size: Mapped[int] = mapped_column(Integer, default=0)
    # 切片数量：由 ChromaDB 统计回填（向量不在 MySQL 中）
    chunks: Mapped[int] = mapped_column(Integer, default=0)
    # pending / processing / ready / failed
    status: Mapped[str] = mapped_column(String(32), default="processing", index=True)
    error: Mapped[str] = mapped_column(Text, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=now_utc, onupdate=now_utc
    )

    knowledge_base: Mapped[KnowledgeBase] = relationship(back_populates="documents")


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(255), default="新的对话")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=now_utc, onupdate=now_utc, index=True
    )

    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )
    kb_links: Mapped[list["ConversationKnowledgeBase"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )


class ConversationKnowledgeBase(Base):
    """会话选中的知识库范围（多对多）。"""

    __tablename__ = "conversation_knowledge_bases"
    __table_args__ = (
        UniqueConstraint("conversation_id", "knowledge_base_id", name="uq_conv_kb"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    knowledge_base_id: Mapped[str] = mapped_column(String(64), index=True)

    conversation: Mapped[Conversation] = relationship(back_populates="kb_links")


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(16))  # user / assistant
    content: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="done")  # streaming / done / error
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc, index=True)
    # 答案来源：knowledge_base（有检索依据）/ model（模型自身知识）/ none（未生成）
    # 前端据此在气泡上标注「非知识库依据」，与 rag/prompts.py 的 FALLBACK_BANNER 对应
    source: Mapped[str] = mapped_column(String(32), default="knowledge_base", index=True)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")
    sources: Mapped[list["MessageSource"]] = relationship(
        back_populates="message", cascade="all, delete-orphan"
    )


class MessageSource(Base):
    """助手回答引用的检索片段（元数据快照）。

    这里保存的是检索当时的片段文本与来源信息，**不存向量**。
    即便原文档后来被删除或重新索引，历史回答的引用仍可正常展示。
    """

    __tablename__ = "message_sources"
    __table_args__ = (Index("ix_message_sources_msg_ordinal", "message_id", "ordinal"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    message_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("messages.id", ondelete="CASCADE"), index=True
    )
    chunk_id: Mapped[str] = mapped_column(String(128), default="")
    document_id: Mapped[str] = mapped_column(String(64), default="")
    document_name: Mapped[str] = mapped_column(String(512), default="")
    knowledge_base_id: Mapped[str] = mapped_column(String(64), default="")
    knowledge_base_name: Mapped[str] = mapped_column(String(255), default="")
    score: Mapped[float] = mapped_column(Float, default=0.0)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    snippet: Mapped[str] = mapped_column(Text, default="")
    ordinal: Mapped[int] = mapped_column(Integer, default=0)

    message: Mapped[Message] = relationship(back_populates="sources")


# ==========================================================================
# 团队（类群组）
#
# 角色模型：
#   owner  负责人 —— 1 人，可转让；拥有全部权限
#   admin  管理员 —— 可审批入队、拉人、管理团队知识库、移除普通成员
#   member 成员   —— 可上传/检索团队知识库，可退队
#
# 入队方式：
#   1) 邀请码（team.invite_code）直接加入或提交申请，取决于 join_policy
#   2) 搜索团队后提交申请，owner/admin 审批（QQ 群式审核）
#   3) owner/admin 直接添加成员（免审批）
# ==========================================================================
class Team(Base):
    __tablename__ = "teams"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    # 公开团队可被搜索到；私有团队只能靠邀请码进入
    visibility: Mapped[str] = mapped_column(String(16), default="public", index=True)
    # 入队策略：open=邀请码直接进；approval=需 owner/admin 审核；closed=禁止申请
    join_policy: Mapped[str] = mapped_column(String(16), default="approval")
    invite_code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    owner_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=now_utc, onupdate=now_utc
    )

    members: Mapped[list["TeamMember"]] = relationship(
        back_populates="team", cascade="all, delete-orphan"
    )


class TeamMember(Base):
    __tablename__ = "team_members"
    __table_args__ = (UniqueConstraint("team_id", "user_id", name="uq_team_member"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    team_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("teams.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(16), default="member", index=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)

    team: Mapped[Team] = relationship(back_populates="members")


class TeamJoinRequest(Base):
    """入队申请（待 owner/admin 审批）。"""

    __tablename__ = "team_join_requests"
    __table_args__ = (
        UniqueConstraint("team_id", "user_id", "status", name="uq_join_request"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    team_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("teams.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # 申请人留言（可选，便于管理员判断）
    message: Mapped[str] = mapped_column(String(255), default="")
    # 来源：search（搜索申请）/ invite_code（邀请码申请）
    source: Mapped[str] = mapped_column(String(16), default="search")
    # pending / approved / rejected
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)
    handled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    handled_by: Mapped[str] = mapped_column(String(64), default="")


class ApiKey(Base):
    """第三方 API 密钥（加密存储）。

    scope_type / scope_id 决定归属：
      user + 用户 id  —— 个人密钥，只对自己的**个人知识库**生效
      team + 团队 id  —— 团队密钥，对**团队知识库**生效（费用由团队承担）

    解析优先级见 app/services/keyring.py：
      知识库归属方自己的 Key  →  服务端 .env 里的全局 Key（兜底）
    """

    __tablename__ = "api_keys"
    __table_args__ = (
        UniqueConstraint("scope_type", "scope_id", "provider", name="uq_api_key_scope"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    scope_type: Mapped[str] = mapped_column(String(16), index=True)  # user / team
    scope_id: Mapped[str] = mapped_column(String(64), index=True)
    # zhipu（向量化）/ deepseek 等（生成）
    provider: Mapped[str] = mapped_column(String(32), index=True)
    label: Mapped[str] = mapped_column(String(64), default="")
    # Fernet 密文，绝不明文落库；对前端只回掩码
    secret: Mapped[str] = mapped_column(Text, default="")
    # 生成类密钥可指定模型与 base_url（留空则用 provider 默认值）
    model: Mapped[str] = mapped_column(String(128), default="")
    base_url: Mapped[str] = mapped_column(String(255), default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=now_utc, onupdate=now_utc
    )
