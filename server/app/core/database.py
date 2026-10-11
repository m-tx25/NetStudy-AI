"""数据库引擎与会话管理（SQLAlchemy 2.x 异步 + MySQL）。

关系型库存放**业务数据**：用户、知识库、文档元信息、会话、消息、引用。
**向量不在 MySQL 中** —— 它们由 ChromaDB 管理（见 app/services/vectorstore.py），
两者通过 `knowledge_base_id` / `document_id` 关联。

MySQL 连接串由 config 的 MYSQL_* 拼装，或直接用 DATABASE_URL 覆盖：

    mysql+aiomysql://root:密码@127.0.0.1:3306/chuangzhibei?charset=utf8mb4

驱动选 aiomysql 而非 asyncmy：前者是纯 Python，无需编译，
在较新的 Python（实测 3.14）上也能直接装上。
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """所有 ORM 模型的基类。"""


def _build_engine():
    dsn = settings.mysql_dsn

    if dsn.startswith("mysql"):
        return create_async_engine(
            dsn,
            echo=settings.DB_ECHO,
            future=True,
            pool_pre_ping=True,  # 断线自动重连，避免长时间空闲后第一个请求失败
            pool_size=settings.DB_POOL_SIZE,
            max_overflow=settings.DB_MAX_OVERFLOW,
            pool_recycle=3600,  # MySQL 默认 wait_timeout 8h，提前回收
        )

    # 非 MySQL：仅用于自动化测试或本地无 MySQL 时的回退
    if dsn.startswith("sqlite"):
        logger.warning("当前使用 SQLite（%s）——生产环境请配置 MySQL", dsn)
        return create_async_engine(
            dsn,
            echo=settings.DB_ECHO,
            future=True,
            connect_args={"check_same_thread": False},
        )

    return create_async_engine(dsn, echo=settings.DB_ECHO, future=True)


engine = _build_engine()

SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI 依赖：每个请求一个会话。"""
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def _ensure_database_exists() -> None:
    """MySQL 下若目标库不存在则自动创建。

    连不上 MySQL 时抛出可读错误 —— 这比让 SQLAlchemy 抛一长串驱动异常友好得多，
    也是本地最容易卡住的一步（没装 MySQL / 密码不对 / 服务没启动）。
    """
    if not settings.is_mysql:
        return

    try:
        import aiomysql
    except ImportError:
        logger.warning("未安装 aiomysql，跳过库自动创建检查")
        return

    try:
        connection = await aiomysql.connect(
            host=settings.MYSQL_HOST,
            port=settings.MYSQL_PORT,
            user=settings.MYSQL_USER,
            password=settings.MYSQL_PASSWORD,
            charset="utf8mb4",
            autocommit=True,
        )
    except Exception as exc:
        raise RuntimeError(
            "无法连接 MySQL："
            f"{exc}\n"
            f"        请确认：1) MySQL 服务已启动；2) {settings.MYSQL_HOST}:{settings.MYSQL_PORT} 可达；"
            f"3) 用户名/密码正确（当前用户 {settings.MYSQL_USER}）；"
            f"4) 库 {settings.MYSQL_DATABASE} 可创建。\n"
            "        配置见 server/.env 的 MYSQL_* 项。"
        ) from exc

    try:
        async with connection.cursor() as cursor:
            await cursor.execute(
                f"CREATE DATABASE IF NOT EXISTS `{settings.MYSQL_DATABASE}` "
                "DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
        logger.info("MySQL 库已就绪：%s", settings.MYSQL_DATABASE)
    finally:
        connection.close()


async def init_db() -> None:
    """建库建表（开发期用；生产建议改用 Alembic 迁移）。"""
    # 必须先导入模型，元数据里才会有表定义
    from app import models  # noqa: F401

    if settings.is_mysql:
        await _ensure_database_exists()

    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except Exception as exc:
        if settings.ALLOW_SQLITE_FALLBACK:
            logger.warning("MySQL 初始化失败（%s），回退到 SQLite", exc)
            raise
        raise RuntimeError(
            f"建表失败：{exc}\n"
            "        若本机没有 MySQL，可临时在 .env 设置 DATABASE_URL=sqlite+aiosqlite:///./data/app.db"
        ) from exc


def describe() -> dict:
    """给 /api/health 用的数据库自检信息（不含密码）。"""
    if settings.is_mysql:
        return {
            "kind": "mysql",
            "host": settings.MYSQL_HOST,
            "port": settings.MYSQL_PORT,
            "database": settings.MYSQL_DATABASE,
            "user": settings.MYSQL_USER,
            "driver": "aiomysql",
        }
    return {"kind": "sqlite", "dsn": settings.mysql_dsn}
