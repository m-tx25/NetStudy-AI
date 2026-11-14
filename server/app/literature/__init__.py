"""学术文献检索：统一数据接入层。

设计目标：
  - 外部数据源（OpenAlex / Crossref / arXiv / Semantic Scholar）各自实现
    `PaperSource` 协议，输出统一的 `PaperDTO`；
  - 聚合层负责并行请求、去重、排序、分页与部分失败降级；
  - 上层 API / 前端只认识 `PaperDTO`，新增数据源不必改调用方。

与现有 RAG 的关系：本包只负责「发现文献」，不碰库内的切片与向量；
检索到的论文导入个人文献库后，才进入 documents / Chroma 的解析链路。
"""

from app.literature.dto import AuthorDTO, OaInfo, PaperDTO, SearchQuery, SearchResponse
from app.literature.registry import available_sources, get_source

__all__ = [
    "AuthorDTO",
    "OaInfo",
    "PaperDTO",
    "SearchQuery",
    "SearchResponse",
    "available_sources",
    "get_source",
]
