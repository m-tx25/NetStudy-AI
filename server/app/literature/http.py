"""外部请求的公共 HTTP 客户端。

统一超时、User-Agent、重试与错误信息，避免每个适配器各写一套。
"""

from __future__ import annotations

import asyncio
from typing import Any
from urllib.parse import urlencode

import httpx

from app.core.config import settings
from app.literature.base import SourceError

_client: httpx.AsyncClient | None = None


def _user_agent() -> str:
    mailto = settings.LITERATURE_MAILTO.strip()
    base = "NetStudy-AI/0.1"
    return f"{base} (mailto:{mailto})" if mailto else base


def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(settings.LITERATURE_TIMEOUT, connect=5.0),
            headers={"User-Agent": _user_agent(), "Accept": "application/json"},
            follow_redirects=True,
            # 部分网络下 Crossref / arXiv 需要走代理；留空则直连
            proxy=settings.LITERATURE_PROXY or None,
        )
    return _client


async def close_client() -> None:
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
    _client = None


async def get_json(
    url: str,
    params: dict[str, Any] | None = None,
    *,
    headers: dict[str, str] | None = None,
    label: str = "",
) -> Any:
    """GET 一个 JSON 接口，失败统一抛 `SourceError`（带可读原因）。

    对 429 的处理按 `Retry-After`：短暂限流（≤2.5s）自动等一次再试，
    长时间限流直接失败并把「请 N 秒后重试」带给前端，避免把请求挂在
    一个源上拖慢整次检索（OpenAlex 的匿名 search 会间歇性限流）。
    """
    client = get_client()
    last_error = ""
    for attempt in range(2):
        try:
            response = await client.get(url, params=params, headers=headers)
        except httpx.TimeoutException as exc:
            last_error = f"{label or url} 请求超时"
            if attempt == 1:
                raise SourceError(last_error) from exc
            await asyncio.sleep(0.4)
            continue
        except httpx.HTTPError as exc:
            last_error = f"{label or url} 网络错误：{exc}"
            if attempt == 1:
                raise SourceError(last_error) from exc
            await asyncio.sleep(0.4)
            continue

        if response.status_code in (429, 503):
            wait = _retry_after_seconds(response)
            if attempt == 0 and wait <= 2.5:
                await asyncio.sleep(wait)
                continue
            suffix = f"，请 {int(wait)} 秒后重试" if wait > 0 else "，请稍后重试"
            raise SourceError(
                f"{label or url} 限流（HTTP {response.status_code}）{suffix}"
            )
        if response.status_code >= 400:
            raise SourceError(
                f"{label or url} 返回 HTTP {response.status_code}：{response.text[:160]}"
            )
        return response.json()
    raise SourceError(last_error or f"{label or url} 请求失败")


def _retry_after_seconds(response: httpx.Response) -> float:
    raw = (response.headers.get("retry-after") or "").strip()
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 0.0


async def get_text(
    url: str,
    params: dict[str, Any] | None = None,
    *,
    headers: dict[str, str] | None = None,
    label: str = "",
) -> str:
    """GET 文本（arXiv 的 Atom XML 用这个）。"""
    client = get_client()
    try:
        response = await client.get(url, params=params, headers=headers)
    except httpx.HTTPError as exc:
        raise SourceError(f"{label or url} 网络错误：{exc}") from exc
    if response.status_code >= 400:
        raise SourceError(f"{label or url} 返回 HTTP {response.status_code}")
    return response.text


def build_url(base: str, params: dict[str, Any]) -> str:
    """把参数拼到 URL 上（仅用于日志/缓存键的可读展示）。"""
    clean = {k: v for k, v in params.items() if v not in (None, "", [])}
    if not clean:
        return base
    return f"{base}?{urlencode(clean)}"
