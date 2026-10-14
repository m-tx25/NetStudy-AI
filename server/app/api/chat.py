"""流式问答路由：POST /api/chat/stream（SSE）。

返回 Content-Type: text/event-stream，逐事件推送增量内容。
前端用 fetch + ReadableStream 手工解析（见 client/src/utils/sse.js），
因此这里必须关闭缓冲并保持连接为 chunked。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.api.deps import CurrentUser, DbSession
from app.core.config import settings
from app.rag.engine import sse, stream_answer
from app.schemas import StreamChatIn, UserModelIn, UserModelUpdateIn
from app.services import model_config

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
                model_id=payload.model_id,
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


@router.get("/models")
async def chat_models(user: CurrentUser, db: DbSession) -> dict:
    """可选生成模型清单（内置 + 用户自带）。

    **不含任何密钥**：只返回 configured / hasApiKey 供界面提示。
    生成模型与向量化模型相互独立：这里只影响回答由谁生成，
    检索仍统一使用 ZHIPUAI_* 配置的向量化模型。
    """
    models = await model_config.public_list(db, user.id)
    return {
        "models": models,
        "defaultId": settings.resolve_model(settings.LLM_DEFAULT_MODEL_ID or None).id,
        "fallbackToModel": settings.RAG_FALLBACK_TO_MODEL,
        # 本地模型的常见预填值，前端可做「一键填入」
        "presets": model_config.LOCAL_PRESETS,
    }


@router.post("/models", status_code=201)
async def create_user_model(payload: UserModelIn, user: CurrentUser, db: DbSession) -> dict:
    """新增一个用户自带的模型（本地部署或云端 API）。"""
    row = await model_config.create(
        db,
        user.id,
        label=payload.label,
        base_url=payload.base_url,
        api_key=payload.api_key,
        model_name=payload.model,
        is_local=payload.is_local,
        temperature=payload.temperature,
    )
    return {
        "id": row.id,
        "label": row.label,
        "model": row.model_name,
        "kind": "local" if row.is_local else "api",
        "configured": True,
    }


@router.patch("/models/{model_id}")
async def update_user_model(
    model_id: str, payload: UserModelUpdateIn, user: CurrentUser, db: DbSession
) -> dict:
    """更新用户模型。apiKey 留空表示不修改（界面不回显密钥）。"""
    row = await model_config.update(
        db,
        user.id,
        model_id,
        label=payload.label,
        base_url=payload.base_url,
        api_key=payload.api_key,
        model_name=payload.model,
        is_local=payload.is_local,
        temperature=payload.temperature,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="模型不存在或不属于当前用户")
    return {
        "id": row.id,
        "label": row.label,
        "model": row.model_name,
        "kind": "local" if row.is_local else "api",
        "configured": True,
    }


@router.delete("/models/{model_id}")
async def delete_user_model(model_id: str, user: CurrentUser, db: DbSession) -> dict:
    """删除用户自带模型（内置模型会被拒绝）。"""
    if not model_config.is_user_model(model_id):
        raise HTTPException(status_code=400, detail="内置模型不可删除")
    ok = await model_config.remove(db, user.id, model_id)
    if not ok:
        raise HTTPException(status_code=404, detail="模型不存在或不属于当前用户")
    return {"ok": True}


@router.post("/models/{model_id}/probe")
async def probe_user_model(model_id: str, user: CurrentUser, db: DbSession) -> dict:
    """连通性自检：发一次极小请求，立刻告诉用户该模型能否使用。

    本地模型最常见的失败原因是「服务没启动」或「模型名写错」，
    保存后立即探测比等到提问时才报错友好得多。
    """
    return await model_config.probe(db, user.id, model_id)


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
        "fallbackToModel": settings.RAG_FALLBACK_TO_MODEL,
    }
