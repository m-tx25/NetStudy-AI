"""LLM 客户端：OpenAI 兼容的 /chat/completions，支持流式增量。

适配任何兼容实现：DeepSeek、通义千问、智谱、Moonshot、vLLM、Ollama、One-API 等。
未配置 LLM_API_KEY 时返回可读错误，由上层转成 SSE 的 error 事件。
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from typing import Any

import httpx

from app.core.config import settings


class LLMNotConfigured(RuntimeError):
    """未配置大模型，属于可预期的使用状态而非程序缺陷。"""


class LLMError(RuntimeError):
    """调用大模型失败（网络、鉴权、限流等）。"""


def is_configured() -> bool:
    return bool(settings.LLM_API_KEY and settings.LLM_BASE_URL)


def _endpoint() -> str:
    base = settings.LLM_BASE_URL.rstrip("/")
    if not base.endswith("/v1") and "/v1" not in base:
        base = f"{base}/v1"
    return f"{base}/chat/completions"


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.LLM_API_KEY}",
        "Content-Type": "application/json",
    }


def _payload(messages: list[dict[str, str]], stream: bool) -> dict[str, Any]:
    return {
        "model": settings.LLM_MODEL,
        "messages": messages,
        "stream": stream,
        "temperature": settings.LLM_TEMPERATURE,
    }


async def stream_chat(messages: list[dict[str, str]]) -> AsyncGenerator[str, None]:
    """流式生成，逐段 yield 增量文本。

    解析 OpenAI 风格的 SSE：`data: {"choices":[{"delta":{"content":"…"}}]}`
    """
    if not is_configured():
        raise LLMNotConfigured(
            "未配置大模型：请在 server/.env 中设置 LLM_API_KEY（可选 LLM_BASE_URL / LLM_MODEL）"
        )

    timeout = httpx.Timeout(settings.LLM_TIMEOUT, connect=15.0)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream(
                "POST", _endpoint(), json=_payload(messages, True), headers=_headers()
            ) as response:
                if response.status_code >= 400:
                    detail = (await response.aread()).decode("utf-8", errors="replace")
                    raise LLMError(f"大模型返回 HTTP {response.status_code}：{detail[:300]}")

                async for line in response.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    raw = line[5:].strip()
                    if not raw or raw == "[DONE]":
                        if raw == "[DONE]":
                            break
                        continue
                    try:
                        payload = json.loads(raw)
                    except json.JSONDecodeError:
                        continue

                    choices = payload.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta") or {}
                    content = delta.get("content")
                    if content:
                        yield str(content)
    except (LLMNotConfigured, LLMError):
        raise
    except httpx.HTTPError as exc:
        raise LLMError(f"无法连接大模型服务：{exc}") from exc


async def complete(messages: list[dict[str, str]]) -> str:
    """非流式一次性生成（当前用于生成会话标题等轻量场景）。"""
    if not is_configured():
        raise LLMNotConfigured("未配置大模型")

    timeout = httpx.Timeout(settings.LLM_TIMEOUT, connect=15.0)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                _endpoint(), json=_payload(messages, False), headers=_headers()
            )
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPError as exc:
        raise LLMError(f"无法连接大模型服务：{exc}") from exc

    choices = data.get("choices") or []
    if not choices:
        raise LLMError("大模型返回内容为空")
    return str((choices[0].get("message") or {}).get("content") or "")
