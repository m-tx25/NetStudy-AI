# -*- coding: utf-8 -*-
"""清理「孤儿向量」：数据库里已不存在的文档/知识库，在 Chroma 里还留着切片。

成因：早期删除文档/知识库的路径没有同步清向量（已在 cleanup 与 delete 接口修好），
历史上留下的残留会让统计虚高，严重时检索会召回「已删除文档」的片段。

用法：
    .\\.venv\\Scripts\\python.exe prune_orphan_vectors.py          # 只统计
    .\\.venv\\Scripts\\python.exe prune_orphan_vectors.py --yes    # 执行删除
"""
from __future__ import annotations

import sys

# Windows 控制台默认 GBK，脚本里的 emoji（✅/❌）会直接抛 UnicodeEncodeError。
# 这里让不可编码的字符降级为 '?'，而不是让整个脚本崩掉。
try:
    sys.stdout.reconfigure(errors='replace')
    sys.stderr.reconfigure(errors='replace')
except Exception:
    pass

import pymysql

sys.path.insert(0, '.')

from app.core.config import settings  # noqa: E402
from app.services import vectorstore  # noqa: E402

DB = dict(host='127.0.0.1', user='root', password='root',
          database='chuangzhibei', charset='utf8mb4')


def main() -> int:
    execute = '--yes' in sys.argv

    conn = pymysql.connect(**DB)
    cur = conn.cursor()
    cur.execute('SELECT id FROM documents')
    live_docs = {r[0] for r in cur.fetchall()}
    cur.execute('SELECT id FROM knowledge_bases')
    live_kbs = {r[0] for r in cur.fetchall()}
    conn.close()

    print('=' * 58)
    print('  清理孤儿向量')
    print('=' * 58)
    print(f'  存活文档 {len(live_docs)} 个，存活知识库 {len(live_kbs)} 个')

    client = vectorstore.get_client()
    total = 0
    orphans_by_doc: dict[str, int] = {}
    orphans_by_kb: dict[str, int] = {}

    for name in [c for c in ['knowledge_chunks_zhipu2048', 'knowledge_chunks_offline512']]:
        try:
            col = client.get_collection(name)
        except Exception:
            continue
        n = col.count()
        if not n:
            continue
        print(f'  集合 {name}: {n} 条')
        data = col.get(include=['metadatas'], limit=n)
        ids = data.get('ids') or []
        metas = data.get('metadatas') or []
        bad_ids = []
        for cid, meta in zip(ids, metas):
            doc_id = (meta or {}).get('document_id') or ''
            kb_id = (meta or {}).get('knowledge_base_id') or ''
            if doc_id not in live_docs:
                bad_ids.append(cid)
                orphans_by_doc[doc_id or '(空)'] = orphans_by_doc.get(doc_id or '(空)', 0) + 1
                if kb_id and kb_id not in live_kbs:
                    orphans_by_kb[kb_id] = orphans_by_kb.get(kb_id, 0) + 1
        total += len(bad_ids)
        if bad_ids and execute:
            for i in range(0, len(bad_ids), 200):
                col.delete(ids=bad_ids[i:i + 200])
            print(f'    已删除 {len(bad_ids)} 条孤儿')

    print()
    print(f'  孤儿向量合计: {total} 条')
    for doc_id, n in sorted(orphans_by_doc.items(), key=lambda x: -x[1])[:10]:
        print(f'    文档 {doc_id}: {n}')

    if not execute:
        print()
        print('  [dry-run] 未做修改。加 --yes 执行。')
        return 0

    conn = pymysql.connect(**DB)
    cur = conn.cursor()
    after = 0
    for name in ['knowledge_chunks_zhipu2048', 'knowledge_chunks_offline512']:
        try:
            after += client.get_collection(name).count()
        except Exception:
            pass
    print()
    print(f'  清理后集合总数: {after}')
    conn.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
