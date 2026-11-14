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
    # 文件内容的 SHA-256（十六进制小写）。同一知识库内按它去重：
    # 重复上传同一份文件不会再产生第二份切片，否则检索时同一段内容会被召回两次、
    # 引用里出现两条一模一样的来源。
    content_hash: Mapped[str] = mapped_column(String(64), default="", index=True)
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


# ==========================================================================
# 学术文献（外部检索）
#
# papers 存「外部数据源发现的论文」元数据，是导入个人文献库之前的落点；
# 与 documents 的区别：documents 是**有实体文件、可解析可检索**的文档，
# papers 可能只有摘要和跳转链接（非开放获取论文不抓全文）。
# ==========================================================================
class Paper(Base):
    __tablename__ = "papers"
    __table_args__ = (
        UniqueConstraint("source", "source_id", name="uq_paper_source"),
        Index("ix_papers_title", "title"),
    )

    # 统一 id：`<source>:<source_id>`
    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    source: Mapped[str] = mapped_column(String(32), index=True)
    source_id: Mapped[str] = mapped_column(String(255), index=True)
    doi: Mapped[str] = mapped_column(String(128), default="", index=True)
    title: Mapped[str] = mapped_column(String(512), default="")
    abstract: Mapped[str] = mapped_column(Text, default="")
    # JSON：作者列表 / 研究领域列表
    authors_json: Mapped[str] = mapped_column(Text, default="[]")
    fields_json: Mapped[str] = mapped_column(Text, default="[]")
    venue: Mapped[str] = mapped_column(String(255), default="")
    year: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    cited_by: Mapped[int] = mapped_column(Integer, default=0)
    # 开放获取：只有 is_oa 且 pdf_url 可用的才允许下载全文
    is_oa: Mapped[bool] = mapped_column(Boolean, default=False)
    pdf_url: Mapped[str] = mapped_column(Text, default="")
    landing_url: Mapped[str] = mapped_column(Text, default="")
    type: Mapped[str] = mapped_column(String(32), default="article")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=now_utc, onupdate=now_utc
    )


class SearchLog(Base):
    """检索行为日志：用于统计与后续「热门检索/推荐」的数据基础。"""

    __tablename__ = "search_logs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    query_json: Mapped[str] = mapped_column(Text, default="")
    sources: Mapped[str] = mapped_column(String(255), default="")
    result_count: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc, index=True)


# ==========================================================================
# 个人文献库
#
# 关系：papers（元数据）—— library_items（用户收藏）—— documents（可选实体文件）
# 一个用户对同一篇论文只保留一条 library_item（唯一约束 user_id + paper_id）。
# ==========================================================================
class Collection(Base):
    """文献分类（可两级：parent_id 为空表示顶层）。"""

    __tablename__ = "collections"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(128))
    parent_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    sort: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)


class Tag(Base):
    __tablename__ = "tags"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_tag_user_name"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(64))
    color: Mapped[str] = mapped_column(String(16), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)


class LibraryItem(Base):
    """用户文献库条目：外部检索收藏的论文，或上传的 PDF。"""

    __tablename__ = "library_items"
    __table_args__ = (
        UniqueConstraint("user_id", "paper_id", name="uq_library_user_paper"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    paper_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("papers.id", ondelete="CASCADE"), index=True
    )
    # 有实体 PDF 并已进入解析管线时才有值
    document_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    collection_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    # unread / reading / read
    status: Mapped[str] = mapped_column(String(16), default="unread", index=True)
    # 阅读进度（0-100）
    progress: Mapped[int] = mapped_column(Integer, default=0)
    note: Mapped[str] = mapped_column(Text, default="")
    added_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc, index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=now_utc, onupdate=now_utc
    )
    last_read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class LibraryItemTag(Base):
    __tablename__ = "library_item_tags"

    library_item_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("library_items.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True
    )


class ReadingNote(Base):
    """阅读笔记（可带页码，便于回到原文）。"""

    __tablename__ = "reading_notes"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    library_item_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("library_items.id", ondelete="CASCADE"), index=True
    )
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    content: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)


# ==========================================================================
# 论文结构化解析（M3）
#
# 解析产物与 documents 分开存：documents 是「文件级」状态，下面这些是
# 「内容级」结构。删除文档时由服务层显式清理（SQLite 默认不启用外键级联）。
# ==========================================================================
class PaperSection(Base):
    __tablename__ = "paper_sections"
    __table_args__ = (Index("ix_paper_sections_doc_ordinal", "document_id", "ordinal"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    document_id: Mapped[str] = mapped_column(String(64), index=True)
    # abstract / introduction / method / ... / references / other
    section_type: Mapped[str] = mapped_column(String(32), index=True)
    heading: Mapped[str] = mapped_column(String(255), default="")
    ordinal: Mapped[int] = mapped_column(Integer, default=0)
    page_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    text: Mapped[str] = mapped_column(Text, default="")


class PaperReference(Base):
    __tablename__ = "paper_references"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    document_id: Mapped[str] = mapped_column(String(64), index=True)
    ordinal: Mapped[int] = mapped_column(Integer, default=0)
    raw_text: Mapped[str] = mapped_column(Text, default="")
    doi: Mapped[str] = mapped_column(String(128), default="")
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    title: Mapped[str] = mapped_column(String(512), default="")


class PaperAsset(Base):
    """表格/图表。table 存结构化行（JSON），figure 目前存图注。"""

    __tablename__ = "paper_assets"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    document_id: Mapped[str] = mapped_column(String(64), index=True)
    kind: Mapped[str] = mapped_column(String(16), default="table", index=True)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    caption: Mapped[str] = mapped_column(Text, default="")
    content_json: Mapped[str] = mapped_column(Text, default="")
    storage_path: Mapped[str] = mapped_column(Text, default="")


class DocumentQuality(Base):
    __tablename__ = "document_quality"

    document_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    char_count: Mapped[int] = mapped_column(Integer, default=0)
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    section_count: Mapped[int] = mapped_column(Integer, default=0)
    reference_count: Mapped[int] = mapped_column(Integer, default=0)
    table_count: Mapped[int] = mapped_column(Integer, default=0)
    figure_count: Mapped[int] = mapped_column(Integer, default=0)
    garbage_ratio: Mapped[float] = mapped_column(Float, default=0.0)
    warnings_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)


class DocumentMetadata(Base):
    """解析出的论文元数据（每篇文档一份）。

    与 papers 表的区别：papers 是「检索到的论文元数据」，本表是「从 PDF 正文
    抽取出来的元数据」，知识库里的文档也能有，不依赖是否收藏进文献库。
    """

    __tablename__ = "document_metadata"

    document_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(512), default="")
    authors_json: Mapped[str] = mapped_column(Text, default="[]")
    doi: Mapped[str] = mapped_column(String(128), default="")
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    abstract: Mapped[str] = mapped_column(Text, default="")
    venue: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)


class Analysis(Base):
    """单篇论文的结构化分析结果（按 kind + model 缓存）。"""

    __tablename__ = "analyses"
    __table_args__ = (
        UniqueConstraint("document_id", "kind", "model", name="uq_analysis_doc_kind_model"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    document_id: Mapped[str] = mapped_column(String(64), index=True)
    # summary / background / question / method / pipeline / innovation /
    # results / limitations / glossary
    kind: Mapped[str] = mapped_column(String(32), index=True)
    model: Mapped[str] = mapped_column(String(128), default="")
    status: Mapped[str] = mapped_column(String(16), default="ready")
    content_md: Mapped[str] = mapped_column(Text, default="")
    citations_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=now_utc, onupdate=now_utc
    )


class PaperProfile(Base):
    """一篇论文的「结构化卡片」：多篇对比的原料。

    为什么单独建表缓存：抽取要求整篇论文（取样后约 6~8k token），
    一次调用成本不低；同一篇论文反复参与对比时不应重复付费。
    命中策略：document_id 唯一，`force=True` 时重新抽取并覆盖。
    """

    __tablename__ = "paper_profiles"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    document_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("documents.id", ondelete="CASCADE"), unique=True, index=True
    )
    knowledge_base_id: Mapped[str] = mapped_column(String(64), default="", index=True)

    title: Mapped[str] = mapped_column(String(512), default="")
    authors: Mapped[str] = mapped_column(String(512), default="")
    year: Mapped[int] = mapped_column(Integer, default=0)
    venue: Mapped[str] = mapped_column(String(255), default="")

    research_problem: Mapped[str] = mapped_column(Text, default="")
    method_family: Mapped[str] = mapped_column(String(255), default="")
    key_technique: Mapped[str] = mapped_column(Text, default="")
    dataset: Mapped[str] = mapped_column(Text, default="")
    main_results: Mapped[str] = mapped_column(Text, default="")

    # 以下为 JSON 文本（MySQL 里不依赖 JSON 类型，兼容性更好）
    metrics_json: Mapped[str] = mapped_column(Text, default="[]")
    innovations_json: Mapped[str] = mapped_column(Text, default="[]")
    limitations_json: Mapped[str] = mapped_column(Text, default="[]")
    future_work_json: Mapped[str] = mapped_column(Text, default="[]")
    citations_json: Mapped[str] = mapped_column(Text, default="{}")

    # ready / failed
    status: Mapped[str] = mapped_column(String(32), default="ready", index=True)
    error: Mapped[str] = mapped_column(Text, default="")
    extractor_version: Mapped[str] = mapped_column(String(16), default="v1")
    page_count: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=now_utc, onupdate=now_utc
    )


class Comparison(Base):
    """一次「多篇论文对比」任务及其结果。

    结果全部落库：矩阵/趋势/空白/结论都是 JSON，
    这样重新打开不再调用模型，报告也能离线导出。
    report_md 由结构化结果拼装，不是模型直接写的，保证两者一致。
    """

    __tablename__ = "comparisons"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    # 若参与对比的论文全部属于同一个团队库，记录 team id（费用归属与权限判断用）
    team_id: Mapped[str] = mapped_column(String(64), default="", index=True)

    topic: Mapped[str] = mapped_column(String(255), default="")
    document_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    knowledge_base_ids_json: Mapped[str] = mapped_column(Text, default="[]")

    # pending / running / ready / failed
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    # cards / dimensions / matrix / trends / gaps / verdict / done
    stage: Mapped[str] = mapped_column(String(32), default="cards")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str] = mapped_column(Text, default="")

    dimensions_json: Mapped[str] = mapped_column(Text, default="[]")
    matrix_json: Mapped[str] = mapped_column(Text, default="[]")
    trends_json: Mapped[str] = mapped_column(Text, default="{}")
    gaps_json: Mapped[str] = mapped_column(Text, default="[]")
    verdict: Mapped[str] = mapped_column(Text, default="")
    scenarios_json: Mapped[str] = mapped_column(Text, default="[]")
    report_md: Mapped[str] = mapped_column(Text, default="")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=now_utc, onupdate=now_utc
    )

class ResearchBrief(Base):
    """一份「研究辅助报告」：基于若干篇论文，给出方向/问题/思路/路线/计划。

    与 Comparison 的区别：
      - Comparison 回答「这些论文有什么不同」；
      - ResearchBrief 回答「我接下来能做什么」，因此它的产物必须区分
        「已有文献结论」与「AI 提出的假设/建议」，且不能承诺创新性。

    所有分节都以 JSON 存：每个条目自带 ``kind``（evidence / hypothesis / suggestion）
    与 ``evidence``（documentId + 页码），前端才能如实标注。
    """

    __tablename__ = "research_briefs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    team_id: Mapped[str] = mapped_column(String(64), default="", index=True)

    # 用户填的研究目标（可空：空则根据论文自动推断）
    goal: Mapped[str] = mapped_column(String(512), default="")
    document_ids_json: Mapped[str] = mapped_column(Text, default="[]")

    # pending / running / ready / failed
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    # cards / directions / questions / roadmap / novelty / related / done
    stage: Mapped[str] = mapped_column(String(32), default="cards")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str] = mapped_column(Text, default="")

    directions_json: Mapped[str] = mapped_column(Text, default="[]")
    questions_json: Mapped[str] = mapped_column(Text, default="[]")
    approaches_json: Mapped[str] = mapped_column(Text, default="[]")
    roadmap_json: Mapped[str] = mapped_column(Text, default="[]")
    novelty_json: Mapped[str] = mapped_column(Text, default="{}")
    related_work_json: Mapped[str] = mapped_column(Text, default="[]")
    related_docs_json: Mapped[str] = mapped_column(Text, default="[]")
    report_md: Mapped[str] = mapped_column(Text, default="")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=now_utc, onupdate=now_utc
    )

class Report(Base):
    """一份可导出的学术材料（模块八）。

    kind 取值：
      - ``reading``   单篇论文阅读报告
      - ``review``    多篇文献综述初稿
      - ``status``    研究现状整理（主题 / 方法 / 阶段）
      - ``comparison``多论文对比报告（内容取自已有 Comparison，不重新生成）

    内容统一存 Markdown（``content_md``），导出 DOCX / HTML / PDF 都由它转换，
    保证「预览看到的」与「导出的」是同一份内容。

    引用溯源：``sources_json`` 存本报告实际引用到的论文（documentId + 页码），
    导出时据此生成参考文献表，**不会凭空出现未选中的文献**。
    """

    __tablename__ = "reports"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    team_id: Mapped[str] = mapped_column(String(64), default="", index=True)

    kind: Mapped[str] = mapped_column(String(32), index=True)
    title: Mapped[str] = mapped_column(String(512), default="")
    document_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    # comparison kind 时记录来源对比 id
    comparison_id: Mapped[str] = mapped_column(String(64), default="")

    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    stage: Mapped[str] = mapped_column(String(32), default="cards")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str] = mapped_column(Text, default="")

    content_md: Mapped[str] = mapped_column(Text, default="")
    # 引用到的论文与页码，用于生成参考文献与溯源
    sources_json: Mapped[str] = mapped_column(Text, default="[]")
    refs_json: Mapped[str] = mapped_column(Text, default="{}")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=now_utc, onupdate=now_utc
    )
