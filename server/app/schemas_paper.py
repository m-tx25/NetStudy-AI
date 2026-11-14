"""论文结构解析结果的接口契约（M3）。"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.schemas import CamelModel


class MetadataOut(CamelModel):
    title: str = ""
    authors: list[str] = Field(default_factory=list)
    doi: str = ""
    year: int | None = None
    abstract: str = ""
    venue: str = ""


class SectionOut(CamelModel):
    id: str
    type: str
    label: str = ""
    heading: str = ""
    ordinal: int = 0
    page_start: int | None = None
    page_end: int | None = None
    char_count: int = 0
    text: str = ""


class ReferenceOut(CamelModel):
    id: str
    ordinal: int = 0
    raw_text: str = ""
    doi: str = ""
    year: int | None = None
    title: str = ""


class AssetOut(CamelModel):
    id: str
    kind: str
    page: int | None = None
    caption: str = ""
    rows: list[list[str]] = Field(default_factory=list)


class QualityOut(CamelModel):
    char_count: int = 0
    page_count: int = 0
    section_count: int = 0
    reference_count: int = 0
    table_count: int = 0
    figure_count: int = 0
    garbage_ratio: float = 0.0
    warnings: list[str] = Field(default_factory=list)


class PaperStructureOut(CamelModel):
    document_id: str
    name: str = ""
    status: str = ""
    metadata: MetadataOut = Field(default_factory=MetadataOut)
    sections: list[SectionOut] = Field(default_factory=list)
    references: list[ReferenceOut] = Field(default_factory=list)
    assets: list[AssetOut] = Field(default_factory=list)
    quality: QualityOut = Field(default_factory=QualityOut)


# --------------------------------------------------------------------------
# 单篇分析（M4）
# --------------------------------------------------------------------------
class AnalysisKindOut(CamelModel):
    kind: str
    label: str


class CitationOut(CamelModel):
    index: int
    chunk_id: str = ""
    page: int | None = None
    section: str = ""
    section_label: str = ""
    section_heading: str = ""
    snippet: str = ""


class AnalysisOut(CamelModel):
    id: str
    document_id: str
    kind: str
    model: str = ""
    status: str = "ready"
    content_md: str = ""
    citations: list[CitationOut] = Field(default_factory=list)
    updated_at: datetime | None = None


class AnalysisStreamIn(CamelModel):
    model_id: str | None = None
    # True 表示忽略缓存重新生成
    force: bool = False


class PaperAskIn(CamelModel):
    content: str
    section: str = ""
    model_id: str | None = None
