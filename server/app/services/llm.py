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
import re
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


# 用户可能把「完整端点」当成 baseUrl 填进来，例如：
#   https://api.deepseek.com/v1/chat/completions
#   https://api.deepseek.com/chat/completions
# 这些后缀必须剥掉，否则会拼成 .../chat/completions/chat/completions，
# 请求落到不存在的路径上，服务端通常返回 401/404 —— 表现为「密钥无效」，但其实是路径错了。
_ENDPOINT_SUFFIXES = (
    "/chat/completions",
    "/completions",
    "/embeddings",
    "/responses",
)


def normalize_base_url(raw: str) -> str:
    """把用户填写的地址规范成可直接拼接端点的 base。

    处理三类常见写法：
      1. https://api.deepseek.com                  → 补 /v1
      2. https://api.deepseek.com/v1               → 原样
      3. https://api.deepseek.com/v1/chat/completions → 剥掉端点后缀，保留 /v1
    """
    base = (raw or "").strip().rstrip("/")
    if not base:
        return ""

    # 1) 先剥掉误填的端点后缀（可重复，容忍 .../v1/chat/completions/ 这类）
    lowered = base.lower()
    changed = True
    while changed:
        changed = False
        for suffix in _ENDPOINT_SUFFIXES:
            if lowered.endswith(suffix):
                base = base[: -len(suffix)].rstrip("/")
                lowered = base.lower()
                changed = True
                break

    # 2) 再补 /v1。只在「路径为空」或「末段不是 vX 形式的版本号」时补，
    #    以免把 https://host/v1beta 这类地址误改成 /v1beta/v1。
    if base and not re.search(r"/v\d+[a-z0-9.-]*$", base, flags=re.IGNORECASE):
        base = f"{base}/v1"
    elif not base:
        return ""

    return base


def _endpoint(model: ModelConfig) -> str:
    return f"{normalize_base_url(model.base_url)}/chat/completions"


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
