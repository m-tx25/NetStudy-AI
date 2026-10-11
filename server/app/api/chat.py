"""流式问答路由：POST /api/chat/stream（SSE）。

返回 Content-Type: text/event-stream，逐事件推送增量内容。
前端用 fetch + ReadableStream 手工解析（见 client/src/utils/sse.js），
因此这里必须关闭缓冲并保持连接为 chunked。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.api.deps import CurrentUser, DbSession
from app.core.config import settings
from app.rag.engine import sse, stream_answer
from app.schemas import StreamChatIn

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])

# 反向代理（nginx 等）常见的缓冲会破坏流式效果，显式声明禁用
SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


@router.post("/stream")
async def chat_stream(
    payload: StreamChatIn,
    request: Request,
    user: CurrentUser,
    db: DbSession,
) -> StreamingResponse:
    async def event_source():
        try:
            async for event in stream_answer(
                db,
                user=user,
                conversation_id=payload.conversation_id,
                question=payload.content,
                knowledge_base_ids=payload.knowledge_base_ids,
                top_k=payload.top_k,
                score_threshold=payload.score_threshold,
            ):
                # 客户端中断（用户点「停止生成」）时停止推流，
                # 已生成的内容已在 engine 内落库
                if await request.is_disconnected():
                    logger.info("客户端断开，停止生成 conversation=%s", payload.conversation_id)
                    break
                yield sse(event)
        except Exception as exc:  # 兜底：让前端收到可读错误而不是连接悬挂
            logger.exception("流式问答失败")
            yield sse({"type": "error", "message": f"服务端错误：{exc}"})

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream; charset=utf-8",
        headers=SSE_HEADERS,
    )


@router.get("/config")
async def chat_config(user: CurrentUser) -> dict:
    """把服务端的检索默认值告诉前端，避免两端参数各写一份。"""
    return {
        "topK": settings.TOP_K,
        "scoreThreshold": settings.SCORE_THRESHOLD,
        "chunkSize": settings.CHUNK_SIZE,
        "chunkOverlap": settings.CHUNK_OVERLAP,
        "memoryTurns": settings.MEMORY_TURNS,
        "maxUploadSizeMB": settings.MAX_UPLOAD_SIZE_MB,
    }
