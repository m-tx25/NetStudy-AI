# -*- coding: utf-8 -*-
"""零成本回填：给已入库的切片补 `section_heading`（章节标题）。

背景：章节标题此前只写进了 ``section``，而结构化解析（M3）约定的字段是
``section_heading``。引用里因此显示 "other"/"front" 这种分类，而不是
「A. Naive RAG」这样的标题。

为什么不用 reindex：重新索引要重新调 embedding（有费用、几分钟）。
这里只重解析 PDF 拿到「页码 → 标题」映射，然后用 Chroma 的
``collection.update()`` 改元数据 —— **不重算向量、零 API 费用、几十秒**。

用法：
    .\\.venv\\Scripts\\python.exe backfill_section_heading.py [--dry-run]
"""
from __future__ import annotations

import os
import sys
import time

try:
    sys.stdout.reconfigure(errors='replace')
except Exception:
    pass

os.environ['NO_PROXY'] = ','.join(
    filter(None, [os.environ.get('NO_PROXY', ''), '127.0.0.1', 'localhost'])
)

import pymysql  # noqa: E402

from app.services import parser, vectorstore  # noqa: E402

COLLECTION = 'knowledge_chunks_zhipu2048'


def page_headings(path: str) -> dict[int, str]:
    """返回「页码 → 章节标题」。页码 1 基，与切片元数据一致。"""
    documents = parser.parse_document(path)
    mapping: dict[int, str] = {}
    for document in documents:
        metadata = document.metadata or {}
        page = metadata.get('page_label')
        if page is None:
            continue
        try:
            page_no = int(str(page).strip())
        except (TypeError, ValueError):
            continue
        heading = metadata.get('section_heading') or metadata.get('section') or ''
        if heading:
            mapping[page_no] = str(heading)[:200]
    return mapping


def main() -> int:
    dry_run = '--dry-run' in sys.argv

    connection = pymysql.connect(
        host='127.0.0.1', user='root', password='root',
        database='chuangzhibei', charset='utf8mb4',
    )
    cursor = connection.cursor()
    cursor.execute(
        "SELECT id, name, stored_path FROM documents WHERE stored_path <> '' "
        "AND status = 'ready'"
    )
    documents = cursor.fetchall()
    connection.close()

    print('=' * 60)
    print(f' 回填 section_heading（{len(documents)} 个文档，dry_run={dry_run}）')
    print('=' * 60)

    client = vectorstore.get_client()
    collection = client.get_collection(COLLECTION)

    total_updated = 0
    for document_id, name, stored_path in documents:
        if not stored_path or not os.path.exists(stored_path):
            print(f'  跳过 {name}：文件不存在')
            continue
        try:
            headings = page_headings(stored_path)
        except Exception as exc:
            print(f'  跳过 {name}：解析失败 {type(exc).__name__}: {exc}')
            continue
        if not headings:
            print(f'  跳过 {name}：没有识别到章节')
            continue

        result = collection.get(where={'document_id': document_id}, include=['metadatas'])
        ids = result.get('ids') or []
        metadatas = result.get('metadatas') or []
        updated_ids: list[str] = []
        updated_meta: list[dict] = []
        for chunk_id, metadata in zip(ids, metadatas):
            metadata = dict(metadata or {})
            page = metadata.get('page_label')
            try:
                page_no = int(page)
            except (TypeError, ValueError):
                continue
            heading = headings.get(page_no)
            if not heading or metadata.get('section_heading') == heading:
                continue
            metadata['section_heading'] = heading
            updated_ids.append(chunk_id)
            updated_meta.append(metadata)

        if not updated_ids:
            print(f'  {name}：无需更新')
            continue

        if not dry_run:
            batch = 100
            for start in range(0, len(updated_ids), batch):
                collection.update(
                    ids=updated_ids[start:start + batch],
                    metadatas=updated_meta[start:start + batch],
                )
                time.sleep(0.05)
        total_updated += len(updated_ids)
        print(f'  {name}：更新 {len(updated_ids)} 条（页码映射 {len(headings)} 页）')

    print()
    print(f'  完成：共更新 {total_updated} 条切片元数据' + ('（dry-run 未写入）' if dry_run else ''))
    return 0


if __name__ == '__main__':
    sys.exit(main())
