"""统一文献数据结构（前后端唯一契约）。

字段命名用 snake_case，序列化时由 CamelModel 自动转 camelCase，
与项目既有 schema 约定保持一致。
"""

from __future__ import annotations

from pydantic import Field

from app.schemas import CamelModel


class AuthorDTO(CamelModel):
    name: str = ""
    affiliation: str = ""
    orcid: str = ""


class OaInfo(CamelModel):
    """开放获取信息：决定前端是否展示「原文 PDF」入口。"""

    is_oa: bool = False
    # 合法的开放全文地址（没有则为空，前端不展示下载按钮）
    pdf_url: str = ""
    # 出版商/仓储落地页
    landing_url: str = ""


class PaperDTO(CamelModel):
    """一篇论文的统一表示。

    id 的格式是 `<source>:<source_id>`，例如 `openalex:W2741809807`、
    `crossref:10.1038/nature12373`。前端只用这个 id 做详情/收藏。
    """

    id: str
    source: str
    source_id: str
    doi: str = ""
    title: str = ""
    abstract: str = ""
    authors: list[AuthorDTO] = Field(default_factory=list)
    venue: str = ""
    year: int | None = None
    cited_by: int = 0
    fields: list[str] = Field(default_factory=list)
    open_access: OaInfo = Field(default_factory=OaInfo)
    url: str = ""
    type: str = "article"


class SearchQuery(CamelModel):
    """一次检索的输入。

    `source` 为空表示聚合全部可用数据源；填具体名字则只查该源。
    """

    q: str = ""
    author: str = ""
    doi: str = ""
    year_from: int | None = None
    year_to: int | None = None
    venue: str = ""
    field: str = ""
    source: str = ""
    sort: str = "relevance"  # relevance | cited | year
    page: int = 1
    page_size: int = 20

    def normalized(self) -> "SearchQuery":
        """裁剪越界参数，避免把上游打爆。"""
        page = max(1, self.page)
        size = min(max(1, self.page_size), 50)
        return self.model_copy(update={"page": page, "page_size": size})

    @property
    def is_empty(self) -> bool:
        return not (self.q.strip() or self.author.strip() or self.doi.strip())


class SourceState(CamelModel):
    """单个数据源本次请求的结果，用于前端提示「哪个源没返回」。"""

    name: str
    label: str = ""
    ok: bool = True
    count: int = 0
    latency_ms: int = 0
    error: str = ""


class SearchResponse(CamelModel):
    items: list[PaperDTO] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 20
    cached: bool = False
    sources: list[SourceState] = Field(default_factory=list)
