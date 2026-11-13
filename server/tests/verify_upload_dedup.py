# -*- coding: utf-8 -*-
"""上传去重 + 批量删除 的端到端验收。

覆盖：
  1. 同一知识库内，内容相同的文件第二次上传被跳过（返回已有记录，duplicated=true）
  2. 不同内容 / 不同知识库不受影响（各自保留）
  3. 批量删除：逐条判定权限，返回 deleted / forbidden / missing 三类
  4. 团队库：成员只能删自己上传的，管理员可删他人上传的
  5. 批量删除后文档列表与知识库计数同步归零

用法（后端已启动）：
    .\\.venv\\Scripts\\python.exe tests\\verify_upload_dedup.py
    $env:API_BASE='http://127.0.0.1:3000/api'
"""
from __future__ import annotations

import os
import sys
import time
import uuid

import httpx

# 本机验收：绕过系统代理，避免 Clash 之类把 127.0.0.1 也代理掉（否则 502 / 空响应）
os.environ['NO_PROXY'] = ','.join(
    filter(None, [os.environ.get('NO_PROXY', ''), '127.0.0.1', 'localhost'])
)

BASE = os.environ.get('API_BASE', 'http://127.0.0.1:3000/api')

passed = 0
failed = 0


def check(name: str, ok: bool, detail: str = '') -> None:
    global passed, failed
    if ok:
        passed += 1
        print(f'  [PASS] {name}')
    else:
        failed += 1
        print(f'  [FAIL] {name}' + (f'\n         {detail}' if detail else ''))


def main() -> int:
    suffix = uuid.uuid4().hex[:8]
    c = httpx.Client(base_url=BASE, timeout=180, trust_env=False)

    def register(prefix: str) -> tuple[str, str]:
        username = f'dedup_{prefix}_{suffix}'
        r = c.post('/auth/register', json={
            'username': username,
            'email': f'{username}@dedup.test',
            'password': 'test123456',
        })
        d = r.json()
        tok = d.get('accessToken') or d.get('access_token') or d.get('token')
        assert tok, f'注册失败: {d}'
        return username, tok

    def hdr(tok: str) -> dict:
        return {'Authorization': f'Bearer {tok}'}

    def upload(tok: str, kb_id: str, name: str, content: bytes):
        r = c.post('/documents/upload', headers=hdr(tok),
                   data={'knowledgeBaseId': kb_id},
                   files={'file': (name, content, 'text/plain')})
        return r

    def list_docs(tok: str, kb_id: str) -> list[dict]:
        return c.get('/documents', headers=hdr(tok), params={'knowledgeBaseId': kb_id}).json()

    print('=' * 62)
    print(' 上传去重 + 批量删除 验收')
    print('=' * 62)

    alice_name, alice = register('alice')
    bob_name, bob = register('bob')
    print(f'  账号: {alice_name} / {bob_name}')

    print('\n=== 1. 准备知识库 ===')
    r = c.post('/knowledge-bases', headers=hdr(alice), json={'name': f'去重库{suffix}'})
    kb = r.json()
    kb_id = kb.get('id')
    check('创建个人知识库', bool(kb_id), r.text[:150])

    content_a = f'去重测试内容 A {suffix}'.encode()
    content_b = f'去重测试内容 B {suffix}'.encode()

    print('\n=== 2. 首次上传 ===')
    r = upload(alice, kb_id, 'a.txt', content_a)
    first = r.json() if r.status_code == 200 else {}
    check('首次上传成功', r.status_code == 200, r.text[:200])
    check('首次上传 duplicated=false', first.get('duplicated') is False,
          str(first.get('duplicated')))
    first_id = first.get('id')

    print('\n=== 3. 同内容再传（不同文件名）===')
    r = upload(alice, kb_id, 'a-again.txt', content_a)
    second = r.json() if r.status_code == 200 else {}
    check('第二次上传成功返回', r.status_code == 200, r.text[:200])
    check('第二次上传 duplicated=true', second.get('duplicated') is True,
          str(second.get('duplicated')))
    check('返回的是已有那条记录（id 相同）', second.get('id') == first_id,
          f"{second.get('id')} vs {first_id}")

    docs = list_docs(alice, kb_id)
    check('知识库里只有 1 个文档（未重复入库）', len(docs) == 1, f'实际 {len(docs)}')

    print('\n=== 4. 不同内容不受去重影响 ===')
    r = upload(alice, kb_id, 'b.txt', content_b)
    third = r.json() if r.status_code == 200 else {}
    check('不同内容正常新建', r.status_code == 200 and third.get('duplicated') is False,
          str(third.get('duplicated')))
    docs = list_docs(alice, kb_id)
    check('此时知识库有 2 个文档', len(docs) == 2, f'实际 {len(docs)}')

    print('\n=== 5. 同一内容放进另一个知识库（应各自保留）===')
    r = c.post('/knowledge-bases', headers=hdr(alice), json={'name': f'去重库2-{suffix}'})
    kb2_id = r.json().get('id')
    r = upload(alice, kb2_id, 'a.txt', content_a)
    other = r.json() if r.status_code == 200 else {}
    check('跨知识库不误判为重复', other.get('duplicated') is False, str(other.get('duplicated')))

    print('\n=== 6. 批量删除（含不存在 / 他人文档）===')
    # bob 的文档：alice 无权删除
    r = c.post('/knowledge-bases', headers=hdr(bob), json={'name': f'bob库{suffix}'})
    bob_kb = r.json().get('id')
    r = upload(bob, bob_kb, 'bob.txt', b'bob content')
    bob_doc = r.json().get('id') if r.status_code == 200 else None

    ids_to_delete = [first_id, third.get('id'), bob_doc, 'doc_not_exist_xxx']
    r = c.post('/documents/batch-delete', headers=hdr(alice),
               json={'documentIds': ids_to_delete})
    result = r.json() if r.status_code == 200 else {}
    check('批量删除接口返回 200', r.status_code == 200, r.text[:200])
    deleted = set(result.get('deleted') or [])
    missing = set(result.get('missing') or [])
    check('删除了自己的 2 个文档', {first_id, third.get('id')} <= deleted, str(deleted))
    check('不存在的 id 归入 missing', 'doc_not_exist_xxx' in missing, str(missing))
    check('他人文档不会被删（归入 missing 或 forbidden）',
          bob_doc not in deleted, str(result))

    docs = list_docs(alice, kb_id)
    check('删除后个人库文档数归零', len(docs) == 0, f'实际 {len(docs)}')

    bob_docs = list_docs(bob, bob_kb)
    check('bob 的文档仍在', any(d['id'] == bob_doc for d in bob_docs), str(bob_docs)[:150])

    print('\n=== 7. 团队库：成员只能删自己上传的 ===')
    r = c.post('/teams', headers=hdr(alice), json={
        'name': f'去重团队{suffix}', 'description': '验收', 'visibility': 'private',
        'joinPolicy': 'approval',
    })
    team = r.json()
    team_id = team.get('id')
    c.post(f'/teams/{team_id}/members', headers=hdr(alice),
           json={'username': bob_name, 'role': 'member'})

    r = c.post('/knowledge-bases', headers=hdr(alice),
               json={'name': f'团队库{suffix}', 'teamId': team_id})
    team_kb = r.json().get('id')
    check('创建团队知识库', bool(team_kb), r.text[:150])

    r = upload(alice, team_kb, 'owner_doc.txt', b'owner doc content')
    owner_doc = r.json().get('id') if r.status_code == 200 else None
    r = upload(bob, team_kb, 'member_doc.txt', b'member doc content')
    member_doc = r.json().get('id') if r.status_code == 200 else None
    check('owner 上传成功', bool(owner_doc), '')
    check('成员上传成功', bool(member_doc), '')

    r = c.post('/documents/batch-delete', headers=hdr(bob),
               json={'documentIds': [owner_doc, member_doc]})
    res = r.json() if r.status_code == 200 else {}
    check('成员批量删除：自己的被删、他人的被拒',
          (res.get('deleted') == [member_doc]) and (owner_doc in (res.get('forbidden') or [])),
          str(res))

    print('\n=== 8. 团队库：管理员可删他人上传的 ===')
    me_bob = c.get('/auth/me', headers=hdr(bob)).json().get('id')
    c.patch(f'/teams/{team_id}/members/{me_bob}', headers=hdr(alice), json={'role': 'admin'})
    r = c.post('/documents/batch-delete', headers=hdr(bob),
               json={'documentIds': [owner_doc]})
    res2 = r.json() if r.status_code == 200 else {}
    check('管理员可删除他人文档', res2.get('deleted') == [owner_doc], str(res2))

    print('\n=== 9. 清理 ===')
    for kid in (kb_id, kb2_id, bob_kb, team_kb):
        if kid:
            c.delete(f'/knowledge-bases/{kid}', headers=hdr(alice))
    if team_id:
        c.delete(f'/teams/{team_id}', headers=hdr(alice))
    print('  已清理')

    c.close()
    print()
    print(f'结果：{passed} 通过 / {failed} 失败')
    return 0 if failed == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
