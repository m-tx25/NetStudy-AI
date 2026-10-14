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


class UserModelConfig(Base):
    """用户自带的生成模型（BYOM）。

    用途：让用户在前端自己填写模型 —— 既可以是本地部署（Ollama / vLLM / LM Studio），
    也可以是任意 OpenAI 兼容的云端 API，密钥由用户提供。

    安全约定：
      - `api_key` 存的是**密文**（见 app/core/crypto.py），绝不存明文；
      - 该字段**永远不会**出现在任何 API 响应里，前端只知道「是否已配置」；
      - 与环境变量里的内置模型分开管理：内置模型全用户共享、用户不可改。
    """

    __tablename__ = "user_model_configs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    label: Mapped[str] = mapped_column(String(64))
    base_url: Mapped[str] = mapped_column(String(255))
    # 加密后的密钥；空串表示未配置（例如本地服务不需要密钥）
    api_key: Mapped[str] = mapped_column(Text, default="")
    model_name: Mapped[str] = mapped_column(String(128))
    # True 表示本地部署（界面会显示「本地」标签，并给出连通性提示）
    is_local: Mapped[bool] = mapped_column(Boolean, default=False)
    temperature: Mapped[float] = mapped_column(Float, default=0.3)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=now_utc, onupdate=now_utc
    )
