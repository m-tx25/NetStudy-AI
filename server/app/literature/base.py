"""数据源协议与统一错误类型。

新增数据源只需继承 `PaperSource` 并实现 search/get/get_by_doi/related，
然后在 `registry.py` 注册即可，聚合层与 API 无需改动。
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.literature.dto import PaperDTO, SearchQuery


class SourceError(RuntimeError):
    """数据源不可用（限流、超时、返回格式异常等）。

    聚合层捕获它并降级为「该源无结果」，不会让整次检索失败。
    """


class PaperSource(ABC):
    """一个外部学术数据源。"""

    name: str = ""
    label: str = ""

    # 单次请求的礼貌间隔（秒），None 表示不限
    min_interval: float = 0.0

    @abstractmethod
    async def search(self, query: SearchQuery, *, limit: int) -> list[PaperDTO]:
        """按关键词/作者/DOI/年份检索，返回统一结构。"""

    async def get(self, source_id: str) -> PaperDTO | None:
        """按数据源内部 id 取单篇详情。"""
        return None

    async def get_by_doi(self, doi: str) -> PaperDTO | None:
        """按 DOI 精确取单篇。"""
        return None

    async def related(self, source_id: str, *, limit: int = 10) -> list[PaperDTO]:
        """相关论文推荐（数据源不支持时返回空列表）。"""
        return []

    def describe(self) -> dict:
        return {"name": self.name, "label": self.label}
