"""FastAPI 应用入口。

启动：
    uvicorn app.main:app --host 0.0.0.0 --port 3000 --reload

前端 Vite 会把 /api 代理到 http://localhost:3000（见 client/vite.config.js）。
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import (
    auth,
    chat,
    conversations,
    documents,
    health,
    keys,
    knowledge_bases,
    teams,
)
from app.core.config import settings
from app.core.database import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 建表 + 写入演示数据（已存在则跳过）
    await init_db()
    try:
        from app.db.seed import seed_demo_data

        await seed_demo_data()
    except Exception as exc:  # 种子数据失败不应阻止服务启动
        logger.warning("演示数据初始化失败（不影响启动）：%s", exc)

    logger.info("服务已启动：http://%s:%s%s", settings.HOST, settings.PORT, settings.API_PREFIX)
    yield
    logger.info("服务已停止")


app = FastAPI(
    title="创智杯 RAG 知识问答系统 · 后端",
    description=(
        "Python + FastAPI 应用服务层：JWT 鉴权、Celery 异步文档处理、"
        "LangChain 文本切片与多轮记忆的 RAG 引擎。"
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Type"],
)


# --------------------------------------------------------------------------
# 统一错误响应
#
# 前端 client/src/api/request.js 依赖以下约定：
#   - 401 会清 token 并跳登录，因此鉴权失败必须是 401 而非 403；
#   - 错误体里读 message / error 字段作为提示文案，因此这里统一返回 message。
# --------------------------------------------------------------------------
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"ok": False, "message": exc.detail if isinstance(exc.detail, str) else "请求失败"},
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """把 Pydantic 校验错误转成可读文案，避免前端弹出 JSON 数组。"""
    first = (exc.errors() or [{}])[0]
    location = ".".join(str(part) for part in first.get("loc", ()) if part != "body")
    message = first.get("msg", "请求参数不合法")
    if location:
        message = f"{location}: {message}"
    return JSONResponse(status_code=422, content={"ok": False, "message": message})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("未捕获异常 %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"ok": False, "message": f"服务端异常：{exc}"},
    )


# --------------------------------------------------------------------------
# 路由注册：全部挂在 /api 下，与前端 API_BASE_URL 一致
# --------------------------------------------------------------------------
for router in (
    health.router,
    auth.router,
    conversations.router,
    knowledge_bases.router,
    documents.router,
    chat.router,
    teams.router,
    keys.router,
    # 团队密钥挂在 /api/teams/{team_id}/keys 下
    keys.team_router,
):
    app.include_router(router, prefix=settings.API_PREFIX)


@app.get("/")
async def root() -> dict:
    """根路径给出基本信息。

    注意这是 API 服务，不提供网页；直接打开 http://localhost:3000/ 只会看到这些信息，
    真正的界面在 http://localhost:5173/（Vite 开发服务器）。
    """
    return {
        "ok": True,
        "service": settings.APP_NAME,
        "message": "这是后端 API 服务，界面请访问前端 http://localhost:5173/",
        "docs": "/docs",
        "endpoints": [
            f"{settings.API_PREFIX}/health",
            f"{settings.API_PREFIX}/auth/login",
            f"{settings.API_PREFIX}/conversations",
            f"{settings.API_PREFIX}/knowledge-bases",
            f"{settings.API_PREFIX}/documents",
            f"{settings.API_PREFIX}/chat/stream",
        ],
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app", host=settings.HOST, port=settings.PORT, reload=settings.DEBUG
    )
