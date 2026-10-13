"""LLM 客户端：OpenAI 兼容的 /chat/completions，支持流式增量。

**生成模型与向量化模型是两件事**：
  - 本模块只负责「生成」；
  - 向量化见 app/services/embeddings.py（智谱 embedding-3）。
二者可以来自不同厂商 —— 例如向量化用智谱、生成用 DeepSeek 或本地 Ollama。

适配任何兼容实现：DeepSeek、通义千问、智谱、Moonshot、vLLM、Ollama、LM Studio、
One-API 等。本地部署只需把 base_url 指向本机端口（如 http://127.0.0.1:11434/v1）。
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from typing import Any

import httpx

from app.core.config import ModelConfig, settings


class LLMNotConfigured(RuntimeError):
    """未配置大模型，属于可预期的使用状态而非程序缺陷。"""


class LLMError(RuntimeError):
    """调用大模型失败（网络、鉴权、限流等）。"""


def list_models() -> list[ModelConfig]:
    return settings.available_models()


def resolve_model(model_id: str | None = None) -> ModelConfig:
    return settings.resolve_model(model_id)


def is_configured(model: ModelConfig | None = None) -> bool:
    """未指定模型时检查默认模型。"""
    target = model or settings.resolve_model(None)
    return target.is_configured


def _endpoint(model: ModelConfig) -> str:
    base = model.base_url.rstrip("/")
    # 兼容两种写法：给了 .../v1 或只给域名
    if not base.endswith("/v1") and "/v1" not in base:
        base = f"{base}/v1"
    return f"{base}/chat/completions"


def _headers(model: ModelConfig) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if model.api_key:
        headers["Authorization"] = f"Bearer {model.api_key}"
    return headers


def _payload(
    model: ModelConfig,
    messages: list[dict[str, str]],
    stream: bool,
    temperature: float | None = None,
) -> dict[str, Any]:
    return {
        "model": model.model,
        "messages": messages,
        "stream": stream,
        "temperature": model.temperature if temperature is None else temperature,
    }


def _not_configured_message(model: ModelConfig) -> str:
    return (
        f"未配置大模型「{model.label}」：请在 server/.env 中设置 LLM_API_KEY"
        "（可选 LLM_BASE_URL / LLM_MODEL），"
        "或在 LLM_MODELS 中补充该模型的 baseUrl 与 apiKey。"
        "若使用本地模型（Ollama / vLLM），把 baseUrl 指向本机端口并将 apiKey 填任意非空值即可。"
    )


async def stream_chat(
    messages: list[dict[str, str]],
    *,
    model: ModelConfig | None = None,
    temperature: float | None = None,
) -> AsyncGenerator[str, None]:
    """流式生成，逐段 yield 增量文本。

    解析 OpenAI 风格 SSE：`data: {"choices":[{"delta":{"content":"…"}}]}`
    """
    target = model or settings.resolve_model(None)
    if not target.is_configured:
        raise LLMNotConfigured(_not_configured_message(target))

    timeout = httpx.Timeout(settings.LLM_TIMEOUT, connect=15.0)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream(
                "POST",
                _endpoint(target),
                json=_payload(target, messages, True, temperature),
                headers=_headers(target),
            ) as response:
                if response.status_code >= 400:
                    detail = (await response.aread()).decode("utf-8", errors="replace")
                    raise LLMError(
                        f"大模型「{target.label}」返回 HTTP {response.status_code}：{detail[:300]}"
                    )

                async for line in response.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    raw = line[5:].strip()
                    if not raw:
                        continue
                    if raw == "[DONE]":
                        break
                    try:
                        chunk = json.loads(raw)
                    except json.JSONDecodeError:
                        continue

                    choices = chunk.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta") or {}
                    content = delta.get("content")
                    if content:
                        yield str(content)
    except (LLMNotConfigured, LLMError):
        raise
    except httpx.HTTPError as exc:
        raise LLMError(f"无法连接大模型服务「{target.label}」：{exc}") from exc


async def complete(
    messages: list[dict[str, str]],
    *,
    model: ModelConfig | None = None,
    temperature: float | None = None,
) -> str:
    """非流式一次性生成（用于生成会话标题等轻量场景）。"""
    target = model or settings.resolve_model(None)
    if not target.is_configured:
        raise LLMNotConfigured(_not_configured_message(target))

    timeout = httpx.Timeout(settings.LLM_TIMEOUT, connect=15.0)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                _endpoint(target),
                json=_payload(target, messages, False, temperature),
                headers=_headers(target),
            )
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPError as exc:
        raise LLMError(f"无法连接大模型服务「{target.label}」：{exc}") from exc

    choices = data.get("choices") or []
    if not choices:
        raise LLMError("大模型返回内容为空")
    return str((choices[0].get("message") or {}).get("content") or "")
