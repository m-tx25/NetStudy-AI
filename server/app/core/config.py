"""应用配置：全部通过环境变量注入，集中在此处读取。

约定：业务代码一律 `from app.core.config import settings`，不要散落 os.environ。
"""

from dataclasses import dataclass
from functools import lru_cache
import logging

from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---------------- 基础 ----------------
    APP_NAME: str = "chuangzhibei-server"
    DEBUG: bool = True
    API_PREFIX: str = "/api"
    PORT: int = 3000
    HOST: str = "0.0.0.0"

    # 允许跨域的前端源；开发期默认放开 vite 的 5173
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    # ---------------- 关系型数据库（MySQL）----------------
    # 业务数据：用户、知识库、文档元信息、会话、消息、引用。
    # 向量不在此库中，见下方 Chroma 配置。
    #
    # 格式：mysql+aiomysql://用户:密码@主机:端口/库名?charset=utf8mb4
    # 建库：CREATE DATABASE chuangzhibei DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
    MYSQL_HOST: str = "127.0.0.1"
    MYSQL_PORT: int = 3306
    MYSQL_USER: str = "root"
    MYSQL_PASSWORD: str = ""
    MYSQL_DATABASE: str = "chuangzhibei"

    # 直接指定完整 DSN 时优先使用它（留空则用上面的 MYSQL_* 拼装）
    DATABASE_URL: str = ""
    # 池化参数
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_ECHO: bool = False

    # 仅用于自动化测试/无 MySQL 环境的回退（正常开发不要开启）
    ALLOW_SQLITE_FALLBACK: bool = False
    SQLITE_FALLBACK_URL: str = "sqlite+aiosqlite:///./data/app.db"

    # ---------------- 鉴权 ----------------
    # 生产环境务必用 `openssl rand -hex 32` 生成并写进 .env
    SECRET_KEY: str = "dev-only-secret-change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 天

    @property
    def using_default_secret(self) -> bool:
        """是否仍在使用仓库内置的开发用 SECRET_KEY。

        这不是「能不能跑」的问题，而是**安全**问题：
          - 内置值在仓库里公开，任何人都能伪造 JWT（绕过登录）；
          - API 密钥的加密密钥也由它派生，等于所有人用同一把钥匙。
        启动时会据此告警，提示尽快替换。
        """
        return self.SECRET_KEY.strip() in (
            "",
            "dev-only-secret-change-me-in-production",
        )

    # ---------------- 上传 ----------------
    # 与前端 client/src/config/index.js 的 UPLOAD_LIMITS.maxSizeMB 保持一致
    MAX_UPLOAD_SIZE_MB: int = 50
    UPLOAD_DIR: str = "./data/uploads"

    # ---------------- 向量化：智谱 embedding-3 ----------------
    # 与协作者 rag/ 模块同一方案。申请：https://open.bigmodel.cn/
    # 注意变量名是 ZHIPUAI_API_KEY（LangChain 的 ZhipuAIEmbeddings 读这个）。
    # Key 形如 xxxxxxxx.xxxxxxxx，不是 sk- 开头。
    ZHIPUAI_API_KEY: str = ""
    ZHIPUAI_EMBEDDING_MODEL: str = "embedding-3"
    # embedding-3 支持 256/512/1024/2048，rag 模块实测用 2048
    ZHIPUAI_EMBEDDING_DIM: int = 2048

    # ---------------- 向量库：ChromaDB ----------------
    # 两种运行形态，由 CHROMA_HOST 是否为空决定：
    #   1) 嵌入式（默认，本地开发）：数据落在 CHROMA_PERSIST_DIR
    #   2) 客户端/服务端（Docker 部署）：设置 CHROMA_HOST / CHROMA_PORT，
    #      后端通过 HTTP 连接独立的 Chroma 容器，数据由该容器持久化。
    CHROMA_HOST: str = ""
    CHROMA_PORT: int = 8000
    # 嵌入式模式的落盘目录（CHROMA_HOST 非空时忽略）
    CHROMA_PERSIST_DIR: str = "./data/chroma_db"
    # 实际集合名会追加向量空间后缀（zhipu2048 / default），
    # 因为不同 embedding 模型的向量不可混用
    CHROMA_COLLECTION: str = "knowledge_chunks"
    # 混合检索：0.5×向量相似度 + 0.5×词面命中，术语/公式类文档更稳
    HYBRID_SEARCH: bool = True

    # ---------------- 大模型（OpenAI 兼容，用于生成）----------------
    # 注意：DeepSeek 没有 /embeddings 接口，只能用于生成，不能用于向量化。
    LLM_BASE_URL: str = "https://api.deepseek.com/v1"
    LLM_API_KEY: str = ""
    LLM_MODEL: str = "deepseek-chat"
    LLM_TIMEOUT: int = 120
    LLM_TEMPERATURE: float = 0.3

    # 可选模型列表（JSON 数组），供前端「模型选择」使用。
    # 每项：{"id","label","baseUrl","apiKey","model","temperature"?,"kind"?:"api"|"local"}
    # 留空则只提供上面的默认模型。apiKey 不会下发给前端，只告知该模型是否可用。
    # 任何 OpenAI 兼容服务都可（DeepSeek / 通义 / 智谱 / Moonshot / vLLM / Ollama / One-API）。
    LLM_MODELS: str = ""
    # 默认选中的模型 id（留空则用默认模型）
    LLM_DEFAULT_MODEL_ID: str = ""

    # 检索无依据时是否允许模型用自身知识回答：
    #   true（默认）—— 回退为通用回答，并在正文前明确标注「非知识库依据」+ 引导补充文档，
    #                  避免用户误以为答案出自文档。
    #   false       —— 维持严格 RAG：无依据只提示未检索到，不生成。
    RAG_FALLBACK_TO_MODEL: bool = True
    # 无依据回退时的温度。**留空（None）表示沿用所选模型自己的温度** ——
    # 因为「所选模型的配置应生效」是用户的明确预期，不应被回退逻辑悄悄覆盖。
    # 需要让回退回答更活泼时，再显式设成 0.6 之类的值。
    RAG_FALLBACK_TEMPERATURE: float | None = None
    # 「检索结果算不算知识库依据」的门槛。
    # 为什么需要它：弱向量模型下向量分无法区分有关/无关（实测无关问题 0.83、
    # 有关问题 0.67，区间完全重叠），而词面命中是干净信号（有关 ≥9、无关 ≤2）。
    # 因此以词面命中为主判据，向量分只作为强模型下的补充。
    RAG_MIN_LEXICAL_SCORE: int = 3
    # 向量分达到该值也视为命中（强向量模型下的纯语义命中场景）
    RAG_STRONG_SCORE: float = 0.85

    # ---------------- RAG 参数 ----------------
    # 与 rag/build_db.py 的 500/50 对齐
    CHUNK_SIZE: int = 500
    CHUNK_OVERLAP: int = 50
    TOP_K: int = 5
    SCORE_THRESHOLD: float = 0.2
    # 注入 prompt 的历史轮数（一问一答算一轮）
    MEMORY_TURNS: int = 6
    # 演示/验证用：让文档解析前先等待若干秒，便于观察前端「解析中 → 已就绪」。
    # 默认 0，不产生任何影响；生产环境不要设置。
    PIPELINE_ARTIFICIAL_DELAY_SECONDS: float = 0

    # ---------------- Celery / Redis ----------------
    REDIS_URL: str = "redis://127.0.0.1:6379/0"
    CELERY_BROKER_URL: str = ""
    CELERY_RESULT_BACKEND: str = ""
    # True 时任务在当前进程内同步执行（无需 Redis，便于本地开发与自测）
    CELERY_TASK_ALWAYS_EAGER: bool = False
    # eager 模式下是否改为「后台异步执行」：
    #   false（默认）—— 上传请求内同步等待解析完成，响应里直接是 ready。
    #                   省事，但看不到「解析中」，与生产（Redis + worker）行为不一致。
    #   true          —— 立即返回 processing，解析在后台协程里继续，前端需要轮询。
    #                   更贴近真实异步队列，且无需 Redis。
    CELERY_EAGER_ASYNC: bool = True

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.CORS_ORIGINS.split(",") if item.strip()]

    @property
    def broker_url(self) -> str:
        return self.CELERY_BROKER_URL or self.REDIS_URL

    @property
    def result_backend(self) -> str:
        return self.CELERY_RESULT_BACKEND or self.REDIS_URL

    @property
    def max_upload_bytes(self) -> int:
        return self.MAX_UPLOAD_SIZE_MB * 1024 * 1024

    @property
    def mysql_dsn(self) -> str:
        """拼装 MySQL 异步 DSN（DATABASE_URL 显式设置时优先）。"""
        if self.DATABASE_URL.strip():
            return self.DATABASE_URL.strip()
        from urllib.parse import quote_plus

        password = quote_plus(self.MYSQL_PASSWORD) if self.MYSQL_PASSWORD else ""
        credentials = f"{self.MYSQL_USER}:{password}@" if self.MYSQL_USER else ""
        return (
            f"mysql+aiomysql://{credentials}{self.MYSQL_HOST}:{self.MYSQL_PORT}"
            f"/{self.MYSQL_DATABASE}?charset=utf8mb4"
        )

    @property
    def is_mysql(self) -> bool:
        return self.mysql_dsn.startswith("mysql")

    # ------------------------------------------------------------------
    # 可选模型（供前端「模型选择」使用）
    # ------------------------------------------------------------------
    def available_models(self) -> list["ModelConfig"]:
        """解析 LLM_MODELS 配置。

        JSON 非法时**不抛异常**（否则整个服务起不来），而是退化为「只有默认模型」
        并记录告警 —— 配置写错不应导致服务不可用。
        """
        import json

        raw = (self.LLM_MODELS or "").strip()
        items: list[dict] = []

        if raw:
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    items = [item for item in parsed if isinstance(item, dict)]
                else:
                    logger.warning("LLM_MODELS 不是 JSON 数组，已忽略")
            except json.JSONDecodeError as exc:
                logger.warning("LLM_MODELS 解析失败（%s），退化为仅默认模型", exc)

        models: list[ModelConfig] = []
        for index, item in enumerate(items):
            model_name = str(item.get("model") or "").strip()
            if not model_name:
                logger.warning("LLM_MODELS[%s] 缺少 model 字段，已忽略", index)
                continue
            base_url = str(item.get("baseUrl") or item.get("base_url") or "").strip()
            is_local = bool(base_url) and any(
                host in base_url for host in ("127.0.0.1", "localhost", "0.0.0.0")
            )
            temperature = item.get("temperature")
            models.append(
                ModelConfig(
                    id=str(item.get("id") or model_name).strip(),
                    label=str(item.get("label") or model_name).strip(),
                    base_url=base_url,
                    api_key=str(item.get("apiKey") or item.get("api_key") or "").strip(),
                    model=model_name,
                    temperature=float(temperature) if temperature is not None else self.LLM_TEMPERATURE,
                    kind=str(item.get("kind") or ("local" if is_local else "api")),
                )
            )

        # 默认模型始终可选（id 固定为 "default"），保证前端至少有一个选项
        models.insert(
            0,
            ModelConfig(
                id="default",
                label=f"{self.LLM_MODEL}（默认）",
                base_url=self.LLM_BASE_URL,
                api_key=self.LLM_API_KEY,
                model=self.LLM_MODEL,
                temperature=self.LLM_TEMPERATURE,
                kind="local"
                if any(host in self.LLM_BASE_URL for host in ("127.0.0.1", "localhost"))
                else "api",
            ),
        )
        return models

    def resolve_model(self, model_id: str | None = None) -> "ModelConfig":
        """按 id 取模型；找不到时回退到默认模型（不抛错，保证问答始终可用）。"""
        models = self.available_models()
        wanted = (model_id or self.LLM_DEFAULT_MODEL_ID or "").strip()
        if wanted:
            for item in models:
                if item.id == wanted:
                    return item
        return models[0]

    def public_models(self) -> list[dict]:
        """下发给前端的模型清单 —— **绝不包含 apiKey**，只告知是否可用。"""
        return [
            {
                "id": item.id,
                "label": item.label,
                "model": item.model,
                "kind": item.kind,
                "configured": item.is_configured,
                "isDefault": item.id == "default",
            }
            for item in self.available_models()
        ]


@dataclass(frozen=True)
class ModelConfig:
    """一个可用于生成的模型。

    Embedding 与 LLM 是两件事：这里只描述「生成」用的模型。
    向量化模型见 ZHIPUAI_* 配置，二者互不影响。
    """

    id: str
    label: str
    base_url: str
    api_key: str
    model: str
    temperature: float = 0.3
    kind: str = "api"  # api | local

    @property
    def is_configured(self) -> bool:
        """本地部署通常不需要真实 key（Ollama 填任意非空值即可）。"""
        return bool(self.base_url and self.model and self.api_key)

    @property
    def is_local(self) -> bool:
        return self.kind == "local"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
