"""个人文献库 API（M2）。

定位：把「检索到的论文」和「上传的 PDF」统一进同一个库。
  - 外部论文：只有元数据（+ 可选 OA PDF 链接）；
  - 上传 PDF：复用 documents 的上传/解析/向量化管线，挂到自动创建的
    「我的文献库」知识库下，这样问答检索能直接用到。

去重规则：同一用户对同一篇论文只保留一条；论文本身先按
(source, source_id) → DOI → 标题+年份 匹配已有记录，避免跨源重复。
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbSession
from app.literature.dto import AuthorDTO, OaInfo, PaperDTO
from app.literature.normalize import normalize_doi
from app.models import (
    Collection,
    KnowledgeBase,
    LibraryItem,
    LibraryItemTag,
    Paper,
    ReadingNote,
    Tag,
    now_utc,
)
from app.schemas_library import (
    CitationOut,
    CollectionIn,
    CollectionOut,
    LibraryItemIn,
    LibraryItemOut,
    LibraryItemUpdate,
    LibraryPage,
    NoteIn,
    NoteOut,
    TagIn,
    TagOut,
)
from app.services import citation, uploads as upload_service
from app.utils.ids import new_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/library", tags=["library"])

# 上传的 PDF 统一归档到这个个人知识库，复用现有解析/检索链路
LIBRARY_KB_NAME = "我的文献库"

VALID_STATUS = {"unread", "reading", "read"}


# --------------------------------------------------------------------------
# 序列化辅助
# --------------------------------------------------------------------------
def _paper_payload(row: Paper) -> PaperDTO:
    try:
        authors = [AuthorDTO(**item) for item in json.loads(row.authors_json or "[]")]
    except (TypeError, ValueError):
        authors = []
    try:
        fields = list(json.loads(row.fields_json or "[]"))
    except (TypeError, ValueError):
        fields = []
    return PaperDTO(
        id=row.id,
        source=row.source,
        source_id=row.source_id,
        doi=row.doi or "",
        title=row.title or "",
        abstract=row.abstract or "",
        authors=authors,
        venue=row.venue or "",
        year=row.year,
        cited_by=row.cited_by or 0,
        fields=fields,
        open_access=OaInfo(
            is_oa=bool(row.is_oa), pdf_url=row.pdf_url or "", landing_url=row.landing_url or ""
        ),
        url=row.landing_url or "",
        type=row.type or "article",
    )


async def _ensure_paper(db: DbSession, dto: PaperDTO) -> tuple[Paper, bool]:
    """按 source+id → DOI → 标题+年份 的顺序匹配已有论文，没有则新建。"""
    row = (
        await db.execute(
            select(Paper).where(Paper.source == dto.source, Paper.source_id == dto.source_id)
        )
    ).scalar_one_or_none()

    doi = normalize_doi(dto.doi)
    if row is None and doi:
        row = (
            await db.execute(select(Paper).where(Paper.doi == doi).limit(1))
        ).scalar_one_or_none()
    if row is None and dto.title:
        row = (
            await db.execute(
                select(Paper)
                .where(Paper.title == dto.title[:512])
                .where(Paper.year == dto.year)
                .limit(1)
            )
        ).scalar_one_or_none()

    if row is None:
        row = Paper(
            id=dto.id,
            source=dto.source,
            source_id=dto.source_id,
            doi=doi,
            title=(dto.title or "")[:512],
            abstract=dto.abstract or "",
            authors_json=json.dumps(
                [author.model_dump() for author in dto.authors], ensure_ascii=False
            ),
            fields_json=json.dumps(dto.fields, ensure_ascii=False),
            venue=(dto.venue or "")[:255],
            year=dto.year,
            cited_by=dto.cited_by,
            is_oa=bool(dto.open_access.is_oa),
            pdf_url=dto.open_access.pdf_url or "",
            landing_url=dto.open_access.landing_url or dto.url or "",
            type=dto.type or "article",
        )
        db.add(row)
        await db.flush()
        return row, True

    # 已存在：用新数据补全空字段（跨源合并时很常见）
    if not row.abstract and dto.abstract:
        row.abstract = dto.abstract
    if not row.authors_json or row.authors_json == "[]":
        row.authors_json = json.dumps(
            [author.model_dump() for author in dto.authors], ensure_ascii=False
        )
    if not row.venue and dto.venue:
        row.venue = dto.venue[:255]
    if not row.year and dto.year:
        row.year = dto.year
    if not row.is_oa and dto.open_access.is_oa:
        row.is_oa = True
        row.pdf_url = dto.open_access.pdf_url or ""
    return row, False


async def _tags_of(db: DbSession, item_id: str) -> list[Tag]:
    rows = await db.execute(
        select(Tag)
        .join(LibraryItemTag, LibraryItemTag.tag_id == Tag.id)
        .where(LibraryItemTag.library_item_id == item_id)
    )
    return list(rows.scalars().all())


async def _serialize(db: DbSession, item: LibraryItem, *, duplicated: bool = False) -> LibraryItemOut:
    paper_row = (
        await db.execute(select(Paper).where(Paper.id == item.paper_id))
    ).scalar_one()
    tags = await _tags_of(db, item.id)
    return LibraryItemOut(
        id=item.id,
        paper=_paper_payload(paper_row),
        document_id=item.document_id or "",
        collection_id=item.collection_id or "",
        status=item.status,
        progress=item.progress,
        note=item.note or "",
        tags=[TagOut(id=tag.id, name=tag.name, color=tag.color) for tag in tags],
        has_pdf=bool(item.document_id),
        added_at=item.added_at,
        updated_at=item.updated_at,
        last_read_at=item.last_read_at,
        duplicated=duplicated,
    )


async def _get_item(db: DbSession, item_id: str, user_id: str) -> LibraryItem:
    item = (
        await db.execute(
            select(LibraryItem)
            .where(LibraryItem.id == item_id)
            .where(LibraryItem.user_id == user_id)
        )
    ).scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文献不存在")
    return item


# --------------------------------------------------------------------------
# 文献条目
# --------------------------------------------------------------------------
@router.get("/items", response_model=LibraryPage)
async def list_items(
    user: CurrentUser,
    db: DbSession,
    status_filter: str = Query(default="", alias="status"),
    tag: str = "",
    collection: str = "",
    q: str = "",
    page: int = 1,
    page_size: int = Query(default=20, alias="pageSize", ge=1, le=100),
) -> LibraryPage:
    """按状态 / 标签 / 分类 / 关键词筛选个人文献库。"""
    stmt = select(LibraryItem).where(LibraryItem.user_id == user.id)
    if status_filter:
        stmt = stmt.where(LibraryItem.status == status_filter)
    if collection:
        stmt = stmt.where(LibraryItem.collection_id == collection)
    if tag:
        stmt = stmt.join(
            LibraryItemTag, LibraryItemTag.library_item_id == LibraryItem.id
        ).where(LibraryItemTag.tag_id == tag)
    if q.strip():
        stmt = stmt.join(Paper, Paper.id == LibraryItem.paper_id).where(
            Paper.title.ilike(f"%{q.strip()}%") | Paper.abstract.ilike(f"%{q.strip()}%")
        )

    total = (
        await db.execute(select(func.count()).select_from(stmt.subquery()))
    ).scalar_one()
    rows = (
        await db.execute(
            stmt.order_by(LibraryItem.added_at.desc())
            .offset((max(page, 1) - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()

    items = [await _serialize(db, row) for row in rows]
    return LibraryPage(items=items, total=total, page=max(page, 1), page_size=page_size)


@router.post("/items", response_model=LibraryItemOut)
async def add_item(payload: LibraryItemIn, user: CurrentUser, db: DbSession) -> LibraryItemOut:
    """收藏一篇外部检索到的论文；已收藏时返回已有条目（duplicated=true）。"""
    paper_row, _ = await _ensure_paper(db, payload.paper)
    existing = (
        await db.execute(
            select(LibraryItem)
            .where(LibraryItem.user_id == user.id)
            .where(LibraryItem.paper_id == paper_row.id)
        )
    ).scalar_one_or_none()
    if existing is not None:
        await db.commit()
        return await _serialize(db, existing, duplicated=True)

    item = LibraryItem(
        id=new_id("lib"),
        user_id=user.id,
        paper_id=paper_row.id,
        document_id="",
        collection_id="",
        status="unread",
        progress=0,
        note="",
        added_at=now_utc(),
    )
    db.add(item)
    await db.commit()
    return await _serialize(db, item)


@router.patch("/items/{item_id}", response_model=LibraryItemOut)
async def update_item(
    item_id: str, payload: LibraryItemUpdate, user: CurrentUser, db: DbSession
) -> LibraryItemOut:
    item = await _get_item(db, item_id, user.id)

    if payload.status is not None:
        if payload.status not in VALID_STATUS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"状态只能是 {', '.join(sorted(VALID_STATUS))}",
            )
        item.status = payload.status
        if payload.status in ("reading", "read"):
            item.last_read_at = now_utc()
            if payload.status == "read" and payload.progress is None:
                item.progress = 100

    if payload.progress is not None:
        item.progress = max(0, min(100, payload.progress))
    if payload.collection_id is not None:
        if payload.collection_id:
            owned = (
                await db.execute(
                    select(Collection)
                    .where(Collection.id == payload.collection_id)
                    .where(Collection.user_id == user.id)
                )
            ).scalar_one_or_none()
            if owned is None:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="分类不存在")
        item.collection_id = payload.collection_id
    if payload.note is not None:
        item.note = payload.note

    if payload.tag_ids is not None:
        # 整体替换：先删旧关联，再按新集合写入（只允许本人标签）
        await db.execute(
            LibraryItemTag.__table__.delete().where(
                LibraryItemTag.library_item_id == item.id
            )
        )
        if payload.tag_ids:
            owned_tags = (
                await db.execute(
                    select(Tag.id)
                    .where(Tag.user_id == user.id)
                    .where(Tag.id.in_(payload.tag_ids))
                )
            ).scalars().all()
            for tag_id in owned_tags:
                db.add(LibraryItemTag(library_item_id=item.id, tag_id=tag_id))

    item.updated_at = now_utc()
    await db.commit()
    return await _serialize(db, item)


@router.delete("/items/{item_id}")
async def delete_item(item_id: str, user: CurrentUser, db: DbSession) -> dict:
    item = await _get_item(db, item_id, user.id)
    await db.execute(
        LibraryItemTag.__table__.delete().where(LibraryItemTag.library_item_id == item.id)
    )
    await db.execute(
        ReadingNote.__table__.delete().where(ReadingNote.library_item_id == item.id)
    )
    await db.delete(item)
    await db.commit()
    return {"ok": True}


@router.post("/items/upload", response_model=LibraryItemOut)
async def upload_item(
    user: CurrentUser,
    db: DbSession,
    file: UploadFile = File(...),
    title: str = Form(default=""),
    collection_id: str = Form(default=""),
) -> LibraryItemOut:
    """上传本地 PDF/Word，自动归档到「我的文献库」并进入解析管线。"""
    base = (
        await db.execute(
            select(KnowledgeBase)
            .where(KnowledgeBase.owner_type == "user")
            .where(KnowledgeBase.owner_id == user.id)
            .where(KnowledgeBase.name == LIBRARY_KB_NAME)
            .limit(1)
        )
    ).scalar_one_or_none()
    if base is None:
        base = KnowledgeBase(
            id=new_id("kb"),
            owner_type="user",
            owner_id=user.id,
            name=LIBRARY_KB_NAME,
            description="文献库上传的文件自动归档到这里",
            embedding_model="embedding-3",
        )
        db.add(base)
        await db.commit()
        await db.refresh(base)

    document, _ = await upload_service.store_upload(
        db, user_id=user.id, base=base, file=file
    )

    dto = PaperDTO(
        id=f"upload:{document.id}",
        source="upload",
        source_id=document.id,
        title=(title.strip() or document.name)[:512],
        url="",
        # 本地上传的文件本身就是可用的全文
        open_access=OaInfo(is_oa=True, pdf_url="", landing_url=""),
        type="article",
    )
    paper_row, _ = await _ensure_paper(db, dto)

    existing = (
        await db.execute(
            select(LibraryItem)
            .where(LibraryItem.user_id == user.id)
            .where(LibraryItem.paper_id == paper_row.id)
        )
    ).scalar_one_or_none()
    if existing is not None:
        if not existing.document_id:
            existing.document_id = document.id
        if collection_id:
            existing.collection_id = collection_id
        await db.commit()
        return await _serialize(db, existing, duplicated=True)

    item = LibraryItem(
        id=new_id("lib"),
        user_id=user.id,
        paper_id=paper_row.id,
        document_id=document.id,
        collection_id=collection_id,
        status="unread",
        progress=0,
        note="",
        added_at=now_utc(),
    )
    db.add(item)
    await db.commit()
    return await _serialize(db, item)


# --------------------------------------------------------------------------
# 分类 / 标签
# --------------------------------------------------------------------------
@router.get("/collections", response_model=list[CollectionOut])
async def list_collections(user: CurrentUser, db: DbSession) -> list[CollectionOut]:
    rows = (
        await db.execute(
            select(Collection)
            .where(Collection.user_id == user.id)
            .order_by(Collection.sort, Collection.created_at)
        )
    ).scalars().all()
    counts = dict(
        (
            await db.execute(
                select(LibraryItem.collection_id, func.count())
                .where(LibraryItem.user_id == user.id)
                .group_by(LibraryItem.collection_id)
            )
        ).all()
    )
    return [
        CollectionOut(
            id=row.id,
            name=row.name,
            parent_id=row.parent_id or "",
            sort=row.sort or 0,
            count=int(counts.get(row.id, 0)),
        )
        for row in rows
    ]


@router.post("/collections", response_model=CollectionOut)
async def create_collection(
    payload: CollectionIn, user: CurrentUser, db: DbSession
) -> CollectionOut:
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="分类名不能为空")
    row = Collection(
        id=new_id("col"),
        user_id=user.id,
        name=name[:128],
        parent_id=payload.parent_id or "",
        sort=payload.sort,
    )
    db.add(row)
    await db.commit()
    return CollectionOut(id=row.id, name=row.name, parent_id=row.parent_id, sort=row.sort, count=0)


@router.patch("/collections/{collection_id}", response_model=CollectionOut)
async def rename_collection(
    collection_id: str, payload: CollectionIn, user: CurrentUser, db: DbSession
) -> CollectionOut:
    row = (
        await db.execute(
            select(Collection)
            .where(Collection.id == collection_id)
            .where(Collection.user_id == user.id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="分类不存在")
    if payload.name.strip():
        row.name = payload.name.strip()[:128]
    row.sort = payload.sort
    await db.commit()
    return CollectionOut(id=row.id, name=row.name, parent_id=row.parent_id, sort=row.sort)


@router.delete("/collections/{collection_id}")
async def delete_collection(collection_id: str, user: CurrentUser, db: DbSession) -> dict:
    row = (
        await db.execute(
            select(Collection)
            .where(Collection.id == collection_id)
            .where(Collection.user_id == user.id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="分类不存在")
    # 分类删除不删文献：条目回到「未分类」
    await db.execute(
        LibraryItem.__table__.update()
        .where(LibraryItem.collection_id == collection_id)
        .values(collection_id="")
    )
    await db.delete(row)
    await db.commit()
    return {"ok": True}


@router.get("/tags", response_model=list[TagOut])
async def list_tags(user: CurrentUser, db: DbSession) -> list[TagOut]:
    rows = (
        await db.execute(select(Tag).where(Tag.user_id == user.id).order_by(Tag.name))
    ).scalars().all()
    return [TagOut(id=row.id, name=row.name, color=row.color) for row in rows]


@router.post("/tags", response_model=TagOut)
async def create_tag(payload: TagIn, user: CurrentUser, db: DbSession) -> TagOut:
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="标签名不能为空")
    existing = (
        await db.execute(
            select(Tag).where(Tag.user_id == user.id).where(Tag.name == name)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return TagOut(id=existing.id, name=existing.name, color=existing.color)
    row = Tag(id=new_id("tag"), user_id=user.id, name=name[:64], color=payload.color or "")
    db.add(row)
    await db.commit()
    return TagOut(id=row.id, name=row.name, color=row.color)


@router.delete("/tags/{tag_id}")
async def delete_tag(tag_id: str, user: CurrentUser, db: DbSession) -> dict:
    row = (
        await db.execute(select(Tag).where(Tag.id == tag_id).where(Tag.user_id == user.id))
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="标签不存在")
    await db.execute(
        LibraryItemTag.__table__.delete().where(LibraryItemTag.tag_id == tag_id)
    )
    await db.delete(row)
    await db.commit()
    return {"ok": True}


# --------------------------------------------------------------------------
# 引用导出 / 笔记
# --------------------------------------------------------------------------
@router.get("/items/{item_id}/citation", response_model=CitationOut)
async def export_citation(
    item_id: str,
    user: CurrentUser,
    db: DbSession,
    format: str = Query(default="bibtex"),
) -> CitationOut:
    item = await _get_item(db, item_id, user.id)
    paper_row = (
        await db.execute(select(Paper).where(Paper.id == item.paper_id))
    ).scalar_one()
    try:
        content = citation.format_citation(_paper_payload(paper_row), format)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return CitationOut(format=format, content=content)


@router.get("/items/{item_id}/notes", response_model=list[NoteOut])
async def list_notes(item_id: str, user: CurrentUser, db: DbSession) -> list[NoteOut]:
    await _get_item(db, item_id, user.id)
    rows = (
        await db.execute(
            select(ReadingNote)
            .where(ReadingNote.library_item_id == item_id)
            .order_by(ReadingNote.created_at)
        )
    ).scalars().all()
    return [
        NoteOut(id=row.id, page=row.page, content=row.content, created_at=row.created_at)
        for row in rows
    ]


@router.post("/items/{item_id}/notes", response_model=NoteOut)
async def add_note(
    item_id: str, payload: NoteIn, user: CurrentUser, db: DbSession
) -> NoteOut:
    await _get_item(db, item_id, user.id)
    if not payload.content.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="笔记内容不能为空")
    row = ReadingNote(
        id=new_id("note"),
        library_item_id=item_id,
        page=payload.page,
        content=payload.content.strip(),
        created_at=now_utc(),
    )
    db.add(row)
    await db.commit()
    return NoteOut(id=row.id, page=row.page, content=row.content, created_at=row.created_at)


@router.delete("/notes/{note_id}")
async def delete_note(note_id: str, user: CurrentUser, db: DbSession) -> dict:
    row = (
        await db.execute(select(ReadingNote).where(ReadingNote.id == note_id))
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="笔记不存在")
    await _get_item(db, row.library_item_id, user.id)
    await db.delete(row)
    await db.commit()
    return {"ok": True}
