"""按数据源限流（异步令牌桶）。

外部学术 API 普遍有速率限制（OpenAlex 秒级、arXiv 要求 3 秒一次、
Semantic Scholar 无 Key 时 1 次/秒）。这里做进程内限速，避免把上游打挂
之后被整段封禁 —— 被封的代价比慢几百毫秒大得多。
"""

from __future__ import annotations

import asyncio
import time


class TokenBucket:
    """容量 capacity、每秒补充 rate 个令牌。"""

    def __init__(self, rate: float, capacity: float | None = None) -> None:
        self.rate = max(rate, 0.01)
        self.capacity = capacity if capacity is not None else max(rate, 1.0)
        self._tokens = self.capacity
        self._updated = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self, tokens: float = 1.0) -> None:
        while True:
            async with self._lock:
                now = time.monotonic()
                elapsed = now - self._updated
                self._tokens = min(self.capacity, self._tokens + elapsed * self.rate)
                self._updated = now
                if self._tokens >= tokens:
                    self._tokens -= tokens
                    return
                wait = (tokens - self._tokens) / self.rate
            await asyncio.sleep(min(wait, 5.0))


class LimiterRegistry:
    """每个数据源一个桶，参数在这里集中配置。"""

    def __init__(self) -> None:
        self._buckets: dict[str, TokenBucket] = {}

    def get(self, name: str) -> TokenBucket:
        if name not in self._buckets:
            rate = {
                "openalex": 8.0,
                "crossref": 4.0,
                "arxiv": 0.34,       # 官方建议 3 秒一次
                "semantic_scholar": 1.0,
            }.get(name, 2.0)
            self._buckets[name] = TokenBucket(rate=rate, capacity=max(rate, 1.0))
        return self._buckets[name]


_limiters = LimiterRegistry()


def limiter_for(name: str) -> TokenBucket:
    return _limiters.get(name)
