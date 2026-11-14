"""个人文献库的接口契约（输入/输出模型）。"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.literature.dto import PaperDTO
from app.schemas import CamelModel


class TagOut(CamelModel):
    id: str
    name: str
    color: str = ""


class CollectionOut(CamelModel):
    id: str
    name: str
    parent_id: str = ""
    sort: int = 0
    count: int = 0


class CollectionIn(CamelModel):
    name: str
    parent_id: str = ""
    sort: int = 0


class TagIn(CamelModel):
    name: str
    color: str = ""


class LibraryItemIn(CamelModel):
    """收藏一篇外部检索到的论文。"""

    paper: PaperDTO


class LibraryItemUpdate(CamelModel):
    status: str | None = None
    progress: int | None = None
    collection_id: str | None = None
    note: str | None = None
    tag_ids: list[str] | None = None


class LibraryItemOut(CamelModel):
    id: str
    paper: PaperDTO
    document_id: str = ""
    collection_id: str = ""
    status: str = "unread"
    progress: int = 0
    note: str = ""
    tags: list[TagOut] = Field(default_factory=list)
    has_pdf: bool = False
    added_at: datetime | None = None
    updated_at: datetime | None = None
    last_read_at: datetime | None = None
    # 收藏时命中已有条目（前端提示「已在库中」）
    duplicated: bool = False


class LibraryPage(CamelModel):
    items: list[LibraryItemOut] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 20


class CitationOut(CamelModel):
    format: str
    content: str


class NoteIn(CamelModel):
    page: int | None = None
    content: str


class NoteOut(CamelModel):
    id: str
    page: int | None = None
    content: str = ""
    created_at: datetime | None = None
