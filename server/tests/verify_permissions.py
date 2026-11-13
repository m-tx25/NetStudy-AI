# -*- coding: utf-8 -*-
"""权限收口验收：团队知识库与文档的管理动作。

背景：`DELETE /knowledge-bases/{id}` 原先只校验「是不是团队成员」，
任何普通成员直接调 API 就能删掉整个团队知识库（连同全部文档与向量）。
本次修复后，管理动作（改名/删库）只允许 owner/admin；
文档的管理动作允许「本人上传的」或管理员。

本脚本用真实 HTTP 验证，不 mock：
    个人库/团队库 × 成员/管理员 × 改/删
运行前需：后端已启动（默认 http://127.0.0.1:3000）、MySQL 可用。

用法：
    .\\.venv\\Scripts\\python.exe tests\\verify_permissions.py
"""
from __future__ import annotations

import os
import sys
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
        print(f'  [FAIL] {name}' + (f'  -> {detail}' if detail else ''))


def main() -> int:
    suffix = uuid.uuid4().hex[:8]
    client = httpx.Client(base_url=BASE, timeout=120, trust_env=False)

    def register(prefix: str) -> tuple[str, str]:
        username = f'{prefix}_{suffix}'
        r = client.post('/auth/register', json={
            'username': username,
            'email': f'{username}@perm.test',
            'password': 'test123456',
        })
        data = r.json()
        token = data.get('accessToken') or data.get('access_token') or data.get('token')
        assert token, f'注册失败: {data}'
        return username, token

    def hdr(token: str) -> dict:
        return {'Authorization': f'Bearer {token}'}

    print('=== 准备账号 ===')
    owner_name, owner_tok = register('permowner')
    member_name, member_tok = register('permmember')
    outsider_name, outsider_tok = register('permout')
    print(f'  owner={owner_name} member={member_name} outsider={outsider_name}')

    print('=== owner 建团队并拉 member 入队 ===')
    r = client.post('/teams', headers=hdr(owner_tok), json={
        'name': f'权限团队{suffix}',
        'description': '权限验收',
        'visibility': 'private',
        'joinPolicy': 'approval',
    })
    team = r.json()
    team_id = team['id']
    check('创建团队', r.status_code == 200, r.text[:120])

    r = client.post(f'/teams/{team_id}/members', headers=hdr(owner_tok), json={
        'username': member_name, 'role': 'member',
    })
    check('owner 直接拉成员入队', r.status_code == 200, r.text[:120])

    print('=== owner 建团队知识库 ===')
    r = client.post('/knowledge-bases', headers=hdr(owner_tok), json={
        'name': f'权限库{suffix}', 'teamId': team_id,
    })
    kb = r.json()
    kb_id = kb['id']
    check('创建团队知识库', r.status_code == 200 and kb.get('ownerType') == 'team', r.text[:120])

    print('=== 上传文档：owner 一份、member 一份 ===')
    r = client.post('/documents/upload', headers=hdr(owner_tok),
                    data={'knowledgeBaseId': kb_id},
                    files={'file': ('owner_doc.txt', b'owner doc content', 'text/plain')})
    owner_doc = r.json().get('id') if r.status_code == 200 else None
    check('owner 上传文档', r.status_code == 200, r.text[:120])

    r = client.post('/documents/upload', headers=hdr(member_tok),
                    data={'knowledgeBaseId': kb_id},
                    files={'file': ('member_doc.txt', b'member doc content', 'text/plain')})
    member_doc = r.json().get('id') if r.status_code == 200 else None
    check('member 上传文档（团队库成员可写）', r.status_code == 200, r.text[:120])

    print('=== 成员：不能删/改团队知识库 ===')
    r = client.delete(f'/knowledge-bases/{kb_id}', headers=hdr(member_tok))
    check('member 删除团队知识库 → 403', r.status_code == 403, f'{r.status_code} {r.text[:120]}')

    r = client.patch(f'/knowledge-bases/{kb_id}', headers=hdr(member_tok),
                     json={'name': '被成员改掉的名字'})
    check('member 重命名团队知识库 → 403', r.status_code == 403, f'{r.status_code} {r.text[:120]}')

    r = client.get(f'/knowledge-bases/{kb_id}', headers=hdr(member_tok))
    check('member 仍可读团队知识库', r.status_code == 200, r.text[:120])

    print('=== 成员：不能动别人的文档，能动自己的 ===')
    r = client.delete(f'/documents/{owner_doc}', headers=hdr(member_tok))
    check('member 删除他人文档 → 403', r.status_code == 403, f'{r.status_code} {r.text[:120]}')

    r = client.patch(f'/documents/{owner_doc}', headers=hdr(member_tok),
                     json={'name': '被成员改名'})
    check('member 重命名他人文档 → 403', r.status_code == 403, f'{r.status_code} {r.text[:120]}')

    r = client.delete(f'/documents/{member_doc}', headers=hdr(member_tok))
    check('member 删除自己上传的文档 → 200', r.status_code == 200, f'{r.status_code} {r.text[:120]}')

    print('=== 管理员：可以管理任意文档与整库 ===')
    me = client.get('/auth/me', headers=hdr(member_tok)).json()
    member_id = me.get('id')
    r = client.patch(f'/teams/{team_id}/members/{member_id}', headers=hdr(owner_tok),
                     json={'role': 'admin'})
    became_admin = r.status_code == 200

    if became_admin:
        r = client.delete(f'/documents/{owner_doc}', headers=hdr(member_tok))
        check('admin 删除他人文档 → 200', r.status_code == 200, f'{r.status_code} {r.text[:120]}')
        r = client.patch(f'/knowledge-bases/{kb_id}', headers=hdr(member_tok),
                         json={'description': 'admin 修改描述'})
        check('admin 修改团队知识库 → 200', r.status_code == 200, f'{r.status_code} {r.text[:120]}')
    else:
        check('提升为管理员', False, r.text[:120])

    print('=== 非成员：看不到也动不了 ===')
    r = client.get(f'/knowledge-bases/{kb_id}', headers=hdr(outsider_tok))
    check('非成员访问团队知识库 → 404', r.status_code == 404, f'{r.status_code}')

    print('=== owner 删除团队知识库 ===')
    r = client.delete(f'/knowledge-bases/{kb_id}', headers=hdr(owner_tok))
    check('owner 删除团队知识库 → 200', r.status_code == 200, f'{r.status_code} {r.text[:120]}')

    print('=== 个人库：他人一律 404 ===')
    r = client.post('/knowledge-bases', headers=hdr(owner_tok),
                    json={'name': f'个人库{suffix}'})
    personal_id = r.json()['id']
    r = client.delete(f'/knowledge-bases/{personal_id}', headers=hdr(member_tok))
    check('他人删除个人库 → 404', r.status_code == 404, f'{r.status_code}')
    r = client.delete(f'/knowledge-bases/{personal_id}', headers=hdr(owner_tok))
    check('本人删除个人库 → 200', r.status_code == 200, f'{r.status_code} {r.text[:120]}')

    print('=== 清理团队 ===')
    r = client.delete(f'/teams/{team_id}', headers=hdr(owner_tok))
    check('owner 解散团队', r.status_code == 200, r.text[:120])

    client.close()
    print()
    print(f'结果：{passed} 通过 / {failed} 失败')
    return 0 if failed == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
