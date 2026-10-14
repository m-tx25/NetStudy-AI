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


# --------------------------------------------------------------------------
# 用户自带模型（BYOM）
# --------------------------------------------------------------------------
class UserModelIn(CamelModel):
    """用户在前端填写的模型配置。

    典型用法：
      · 本地 Ollama：baseUrl=http://127.0.0.1:11434/v1, model=qwen2.5:7b,
                     apiKey 填任意非空值（Ollama 不校验，但后端要求非空才认为已配置）
      · 云端 API  ：baseUrl=https://api.deepseek.com/v1, apiKey=sk-xxx,
                     model=deepseek-chat
    """

    label: str
    base_url: str
    api_key: str
    model: str
    is_local: bool = False
    temperature: float | None = None

    @field_validator("label")
    @classmethod
    def _label_ok(cls, value: str) -> str:
        value = (value or "").strip()
        if not value:
            raise ValueError("请填写模型名称（用于在列表里显示）")
        return value[:64]

    @field_validator("base_url")
    @classmethod
    def _base_url_ok(cls, value: str) -> str:
        value = (value or "").strip()
        if not value:
            raise ValueError("请填写接口地址（本地模型形如 http://127.0.0.1:11434/v1）")
        if not value.startswith(("http://", "https://")):
            raise ValueError("接口地址需以 http:// 或 https:// 开头")
        return value[:255]

    @field_validator("model")
    @classmethod
    def _model_ok(cls, value: str) -> str:
        value = (value or "").strip()
        if not value:
            raise ValueError("请填写模型名（如 qwen2.5:7b 或 deepseek-chat）")
        return value[:128]

    @field_validator("temperature")
    @classmethod
    def _temperature_ok(cls, value: float | None) -> float | None:
        if value is None:
            return None
        if value < 0 or value > 2:
            raise ValueError("temperature 需在 0~2 之间")
        return value

    @field_validator("api_key")
    @classmethod
    def _api_key_ok(cls, value: str) -> str:
        """校验密钥可放进 HTTP 请求头。

        为什么必须校验：HTTP 头只能承载 ASCII（latin-1）。
        若密钥里混入中文，httpx 构造请求头时会抛 UnicodeEncodeError，
        表现为接口 500 —— 用户完全看不懂，也猜不到是密钥格式问题。

        实测最常见的两种情况：
          1. 把**上一次的报错信息**整段粘了进来（如「连接测试未通过：...」）；
          2. 从网页复制时带上了中文说明或全角引号。
        这里都识别出来，并直接说清是什么问题。
        """
        raw = (value or "").strip()
        if not raw:
            return raw

        # 情况一：明显是报错文案或说明文字，而不是密钥。
        # 只有在「同时含非 ASCII 字符」且「出现报错措辞」时才这样判定，
        # 纯 ASCII 的字符串不会被误伤（真实密钥都是 ASCII）。
        noise_markers = ("连接测试", "未通过", "失败", "错误", "请检查", "无效", "非法")
        has_non_ascii = any(ord(ch) > 127 for ch in raw)
        if has_non_ascii and any(marker in raw for marker in noise_markers):
            raise ValueError(
                "这看起来不是 API Key，而是把提示文字/报错信息粘贴进来了。"
                "请只填写服务商给你的一串密钥（DeepSeek 形如 sk-xxxxxxxx）。"
            )

        # 情况二：含非 ASCII 字符
        try:
            raw.encode("ascii")
        except UnicodeEncodeError as exc:
            bad = raw[exc.start : exc.end]
            raise ValueError(
                f"API Key 里出现了中文字符（{bad!r}），而密钥只能是英文字母和数字。"
                "请检查是否从网页复制时把中文说明或全角符号一起带进来了。"
            ) from exc

        if any(ch.isspace() for ch in raw):
            raise ValueError("API Key 中间不能有空格或换行，请检查是否复制了多余字符")

        # 情况三：形状不像密钥（给出提示但不强制拒绝，兼容自定义网关）
        if len(raw) < 16:
            raise ValueError(
                f"API Key 太短（当前 {len(raw)} 个字符），看起来不完整。"
                "DeepSeek 的密钥形如 sk- 开头、约 35 个字符。"
            )
        return raw


class UserModelUpdateIn(CamelModel):
    """更新用户模型。**apiKey 留空表示不修改**（界面不回显密钥，避免误清空）。"""

    label: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    model: str | None = None
    is_local: bool | None = None
    temperature: float | None = None


class UserModelOut(CamelModel):
    """对外的模型信息 —— **绝不含密钥**，只告知是否已配置。"""

    id: str
    label: str
    model: str
    kind: str = "api"
    configured: bool = False
    is_default: bool = False
    builtin: bool = False
    editable: bool = False
    base_url: str | None = None
    has_api_key: bool = False
    is_local: bool = False
    temperature: float | None = None


class ModelListOut(CamelModel):
    models: list[UserModelOut] = Field(default_factory=list)
    default_id: str = ""
    fallback_to_model: bool = True
    presets: list[dict[str, Any]] = Field(default_factory=list)
