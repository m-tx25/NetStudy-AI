"""数据源注册表：按名字取实例，方便 API 层与测试替换。"""

from __future__ import annotations

from app.literature.base import PaperSource
from app.literature.sources.arxiv import ArxivSource
from app.literature.sources.crossref import CrossrefSource
from app.literature.sources.openalex import OpenAlexSource
from app.literature.sources.semantic_scholar import SemanticScholarSource

_CLASSES: dict[str, type[PaperSource]] = {
    OpenAlexSource.name: OpenAlexSource,
    CrossrefSource.name: CrossrefSource,
    ArxivSource.name: ArxivSource,
    SemanticScholarSource.name: SemanticScholarSource,
}

_instances: dict[str, PaperSource] = {}


def get_source(name: str) -> PaperSource | None:
    key = (name or "").strip().lower()
    if key not in _CLASSES:
        return None
    if key not in _instances:
        _instances[key] = _CLASSES[key]()
    return _instances[key]


def available_sources() -> list[PaperSource]:
    return [get_source(name) for name in _CLASSES]  # type: ignore[list-item]


def available_source_names() -> list[str]:
    return list(_CLASSES)
