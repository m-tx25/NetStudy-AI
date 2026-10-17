# -*- coding: utf-8 -*-
"""验证：删除知识库 / 解散团队时，ChromaDB 里的向量与磁盘文件是否真被清理。"""
import sys
import uuid

import httpx

BASE = 'http://127.0.0.1:3000/api'
results = []


def step(name, ok, note=''):
    results.append((name, ok, note))
    print(f"{'PASS' if ok else 'FAIL'}  {name:<38} {note}")


def new_user(c, prefix):
    username = f'{prefix}_{uuid.uuid4().hex[:8]}'
    r = c.post('/auth/register', json={
        'username': username, 'email': f'{username}@t.com', 'password': 'test123456'})
    token = r.json().get('access_token') or r.json().get('token')
    return username, {'Authorization': f'Bearer {token}'}, token


def total_chunks(c, h):
    """从 /health 读向量库总切片数。"""
    r = c.get('/health', headers=h, timeout=60)
    return r.json().get('vectorStore', {}).get('totalChunks')


def wait_ready(c, h, doc_id, kb_id, tries=40):
    import time
    for _ in range(tries):
        time.sleep(3)
        docs = c.get('/documents', headers=h, params={'knowledgeBaseId': kb_id}).json()
        cur = next((d for d in docs if d['id'] == doc_id), None)
        if cur and cur['status'] in ('ready', 'failed'):
            return cur
    return None


def main() -> int:
    with httpx.Client(base_url=BASE, timeout=120) as c:
        name, H, _ = new_user(c, 'clean')

        before = total_chunks(c, H)

        # ---------- 场景一：删除知识库 ----------
        kb = c.post('/knowledge-bases', headers=H, json={'name': f'清理测试{uuid.uuid4().hex[:4]}'}).json()
        kb_id = kb['id']
        r = c.post('/documents/upload', headers=H, data={'knowledgeBaseId': kb_id},
                   files={'file': (f'clean_{uuid.uuid4().hex[:4]}.txt',
                                   '清理验证文档\n关键事实：代号是「归零二号」。\n'.encode('utf-8'),
                                   'text/plain')})
        doc_id = r.json().get('id')
        step('创建知识库并上传文档', r.status_code == 200, f'doc={doc_id}')

        cur = wait_ready(c, H, doc_id, kb_id)
        step('文档向量化完成', bool(cur) and cur.get('status') == 'ready',
             f"status={cur.get('status') if cur else '?'} chunks={cur.get('chunks') if cur else '?'}")

        after_upload = total_chunks(c, H)
        step('向量库切片数增加', (after_upload or 0) > (before or 0),
             f'{before} -> {after_upload}')

        # 记录磁盘文件
        import os
        import pathlib
        hits = list(pathlib.Path('data/uploads').glob(f'{doc_id}*'))
        step('磁盘上存在上传文件', len(hits) > 0, f'{len(hits)} 个')

        r = c.delete(f'/knowledge-bases/{kb_id}', headers=H)
        step('删除知识库', r.status_code == 200, f'HTTP {r.status_code}')

        after_delete = total_chunks(c, H)
        step('向量已清理（切片数回落）', (after_delete or 0) <= (before or 0),
             f'{after_upload} -> {after_delete}')

        hits_after = list(pathlib.Path('data/uploads').glob(f'{doc_id}*'))
        step('磁盘文件已删除', len(hits_after) == 0, f'剩余 {len(hits_after)} 个')

        # ---------- 场景二：解散团队 ----------
        before2 = total_chunks(c, H)
        team = c.post('/teams', headers=H, json={
            'name': f'清理团队{uuid.uuid4().hex[:4]}', 'visibility': 'public',
            'joinPolicy': 'approval'}).json()
        tid = team['id']

        kb2 = c.post('/knowledge-bases', headers=H, json={
            'name': f'团队清理库{uuid.uuid4().hex[:4]}', 'teamId': tid}).json()
        kb2_id = kb2['id']
        r = c.post('/documents/upload', headers=H, data={'knowledgeBaseId': kb2_id},
                   files={'file': (f'teamclean_{uuid.uuid4().hex[:4]}.txt',
                                   '团队清理文档\n关键事实：代号是「归零三号」。\n'.encode('utf-8'),
                                   'text/plain')})
        doc2 = r.json().get('id')
        cur2 = wait_ready(c, H, doc2, kb2_id)
        step('团队库文档向量化完成', bool(cur2) and cur2.get('status') == 'ready',
             f"status={cur2.get('status') if cur2 else '?'}")

        after2 = total_chunks(c, H)
        step('团队库向量已写入', (after2 or 0) > (before2 or 0), f'{before2} -> {after2}')

        hits2 = list(pathlib.Path('data/uploads').glob(f'{doc2}*'))
        r = c.delete(f'/teams/{tid}', headers=H)
        step('解散团队', r.status_code == 200, f'HTTP {r.status_code}')

        after3 = total_chunks(c, H)
        step('团队库向量已清理', (after3 or 0) <= (before2 or 0), f'{after2} -> {after3}')

        hits2_after = list(pathlib.Path('data/uploads').glob(f'{doc2}*'))
        step('团队文件已删除', len(hits2_after) == 0, f'剩余 {len(hits2_after)} 个')

    passed = sum(1 for _, ok, _ in results if ok)
    print(f'\n===== 通过 {passed}/{len(results)} =====')
    for n, ok, note in results:
        if not ok:
            print(f'  FAIL: {n}  {note}')
    return 0 if passed == len(results) else 1


if __name__ == '__main__':
    sys.exit(main())
