"""检索结果缓存（进程内 TTL）。

为什么先做进程内：开发/演示环境不一定有 Redis，而外部检索是最贵的一步
（3 个源、每个 1~3 秒）。先挡住同一查询的重复请求，收益最大。
接口保持 async + JSON 可序列化，后续换 Redis 只需替换 `get_cache()` 的实现。
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from app.core.config import settings


class TTLCache:
    def __init__(self, default_ttl: int = 600, max_entries: int = 512) -> None:
        self._default_ttl = default_ttl
        self._max_entries = max_entries
        self._data: dict[str, tuple[float, Any]] = {}
        self._lock = asyncio.Lock()
        self._hits = 0
        self._misses = 0

    async def get(self, key: str) -> Any | None:
        async with self._lock:
            item = self._data.get(key)
            if item is None:
                self._misses += 1
                return None
            expires_at, value = item
            if expires_at < time.monotonic():
                self._data.pop(key, None)
                self._misses += 1
                return None
            self._hits += 1
            return value

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        async with self._lock:
            if len(self._data) >= self._max_entries:
                self._prune()
            expires = time.monotonic() + (ttl or self._default_ttl)
            self._data[key] = (expires, value)

    def _prune(self) -> None:
        now = time.monotonic()
        expired = [key for key, (expires, _) in self._data.items() if expires < now]
        for key in expired:
            self._data.pop(key, None)
        # 仍然超限就按写入顺序丢弃最旧的一批（dict 保持插入序）
        if len(self._data) >= self._max_entries:
            for key in list(self._data)[: max(1, self._max_entries // 4)]:
                self._data.pop(key, None)

    @property
    def stats(self) -> dict[str, int]:
        return {"hits": self._hits, "misses": self._misses, "size": len(self._data)}


_cache: TTLCache | None = None


def get_cache() -> TTLCache:
    global _cache
    if _cache is None:
        _cache = TTLCache(default_ttl=settings.LITERATURE_CACHE_TTL)
    return _cache
