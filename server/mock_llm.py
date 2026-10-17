"""本地 mock LLM：实现 OpenAI 兼容的 /v1/chat/completions（含流式）。

用途：在没有真实 API Key 的情况下验证「模型可选」与「无依据回退生成」两条链路，
同时也演示了**本地部署模型**的接入方式 —— 后端只需把 baseUrl 指向本机端口。

运行：
    python mock_llm.py            # 监听 127.0.0.1:11500
"""
from __future__ import annotations

import json

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse

app = FastAPI(title="mock-llm")

# 记录收到的请求，便于验证「系统提示是否切换」「温度是否变化」
RECEIVED: list[dict] = []


def _reply_for(messages: list[dict]) -> str:
    """根据 system 提示判断当前是哪种模式，回复不同内容，便于断言。"""
    system = ""
    user = ""
    for message in messages:
        if message.get("role") == "system":
            system = message.get("content") or ""
        if message.get("role") == "user":
            user = message.get("content") or ""

    grounded = "只依据「参考资料」回答" in system
    if grounded:
        return f"【知识库模式回答】依据资料回答：{user[:40]}"
    return f"（模型自身知识）这是通用回答：{user[:40]}"


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    body = await request.json()
    messages = body.get("messages") or []
    RECEIVED.append(
        {
            "model": body.get("model"),
            "temperature": body.get("temperature"),
            "stream": body.get("stream"),
            "systemHead": (messages[0].get("content") or "")[:40] if messages else "",
        }
    )
    text = _reply_for(messages)

    if not body.get("stream"):
        return {
            "id": "mock-1",
            "object": "chat.completion",
            "model": body.get("model"),
            "choices": [
                {"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}
            ],
        }

    async def stream():
        # 逐段下发，模拟真实流式
        for index in range(0, len(text), 6):
            chunk = {
                "id": "mock-1",
                "object": "chat.completion.chunk",
                "model": body.get("model"),
                "choices": [{"index": 0, "delta": {"content": text[index : index + 6]}}],
            }
            yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.get("/_received")
async def received():
    """测试用：查看后端实际发来的请求（含 system 提示与 temperature）。"""
    return {"count": len(RECEIVED), "items": RECEIVED[-5:]}


@app.post("/_reset")
async def reset():
    RECEIVED.clear()
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=11500, log_level="warning")
