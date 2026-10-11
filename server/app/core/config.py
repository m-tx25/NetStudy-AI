"""应用配置：全部通过环境变量注入，集中在此处读取。

约定：业务代码一律 `from app.core.config import settings`，不要散落 os.environ。
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


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


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
