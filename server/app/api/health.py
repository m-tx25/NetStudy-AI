"""健康检查与其他基础接口。"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter

from app.core import database
from app.core.config import settings
from app.services import chunking, llm, vectorstore
from app.tasks import check_queue_health

router = APIRouter(tags=["system"])


@router.get("/health")
async def health() -> dict:
    """健康检查。

    除连通性外，还报告四类最容易导致"跑不通"的配置状态，直接暴露可省去翻日志：
      - 大模型是否配置（未配置则只检索不生成）
      - 向量库与向量模型模式（智谱 embedding-3 / Chroma 默认 ONNX）
      - 关系型数据库（MySQL 连接目标）
      - 任务队列（Celery + Redis，或进程内同步执行）
    """
    return {
        "ok": True,
        "service": settings.APP_NAME,
        "time": datetime.now(timezone.utc).isoformat(),
        "llmConfigured": llm.is_configured(),
        "llmModel": settings.LLM_MODEL if llm.is_configured() else None,
        "database": database.describe(),
        "vectorStore": vectorstore.health(),
        "chunking": chunking.describe(),
        "queue": check_queue_health(),
        # 兼容早期字段：前端首页只读取 ok/service/time
        "embeddingMode": vectorstore.embeddings.current_mode(),
    }
