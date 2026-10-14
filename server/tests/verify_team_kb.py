# -*- coding: utf-8 -*-
"""团队知识库端到端测试：成员创建团队库、成员都能看到并上传、非成员看不到。"""
import json
import sys
import time
import uuid

import httpx

BASE = 'http://127.0.0.1:3000/api'
results = []


def step(name, ok, note=''):
    results.append((name, ok, note))
    print(f"{'PASS' if ok else 'FAIL'}  {name:<40} {note}")


def new_user(c, prefix):
    username = f'{prefix}_{uuid.uuid4().hex[:8]}'
    r = c.post('/auth/register', json={
        'username': username, 'email': f'{username}@t.com', 'password': 'test123456'})
    token = r.json().get('access_token') or r.json().get('token')
    return username, {'Authorization': f'Bearer {token}'}, token


def main() -> int:
    with httpx.Client(base_url=BASE, timeout=120) as c:
        owner_name, H1, _ = new_user(c, 'kbown')
        member_name, H2, _ = new_user(c, 'kbmem')
        outsider_name, H3, _ = new_user(c, 'kbout')

        # 建团队 + 拉一个成员
        r = c.post('/teams', headers=H1, json={
            'name': f'知识库团队{uuid.uuid4().hex[:4]}', 'visibility': 'public',
            'join_policy': 'approval'})
        tid = r.json()['id']
        step('准备：创建团队', r.status_code == 200, f'team={tid}')
        r = c.post(f'/teams/{tid}/members', headers=H1,
                   json={'username': member_name, 'role': 'member'})
        step('准备：加入一个成员', r.status_code == 200, f'HTTP {r.status_code}')

        # 1) 创建团队知识库
        r = c.post('/knowledge-bases', headers=H1, json={
            'name': f'团队资料库{uuid.uuid4().hex[:4]}', 'description': '团队共享',
            'teamId': tid})
        step('1.创建团队知识库', r.status_code == 200, f'HTTP {r.status_code}')
        if r.status_code != 200:
            print('   ', r.text[:300])
            return 1
        kb = r.json()
        kb_id = kb['id']
        step('1.ownerType=team', kb.get('ownerType') == 'team', f"ownerType={kb.get('ownerType')}")
        step('1.ownerId=团队id', kb.get('ownerId') == tid, f"ownerId={kb.get('ownerId')}")

        # 2) 成员能看到团队库
        r = c.get('/knowledge-bases', headers=H2)
        if not isinstance(r.json(), list):
            print('   ❌ 成员列表接口返回非数组:', r.status_code, str(r.json())[:400])
            return 1
        ids = [b['id'] for b in r.json()]
        step('2.成员能看到团队库', kb_id in ids, f'成员可见 {len(ids)} 个知识库')
        kb_seen = next((b for b in r.json() if b['id'] == kb_id), None)
        step('2.成员看到 ownerType', (kb_seen or {}).get('ownerType') == 'team',
             f"ownerType={(kb_seen or {}).get('ownerType')}")

        # 3) 非成员看不到
        r = c.get('/knowledge-bases', headers=H3)
        ids3 = [b['id'] for b in r.json()]
        step('3.非成员看不到团队库', kb_id not in ids3, f'非成员可见 {len(ids3)} 个')
        r = c.get(f'/knowledge-bases/{kb_id}', headers=H3)
        step('3.非成员直接访问返回 404', r.status_code == 404, f'HTTP {r.status_code}')

        # 4) 成员可以上传文档到团队库
        content = '团队知识库验证文档\n关键事实：团队项目代号是「海豚三号」，端口 8848。\n'
        r = c.post('/documents/upload', headers=H2,
                   data={'knowledgeBaseId': kb_id},
                   files={'file': (f'team_{uuid.uuid4().hex[:4]}.txt',
                                   content.encode('utf-8'), 'text/plain')})
        step('4.成员可上传到团队库', r.status_code == 200, f'HTTP {r.status_code}')
        doc = r.json() if r.status_code == 200 else {}
        doc_id = doc.get('id')
        step('4.文档归属团队库', doc.get('knowledgeBaseId') == kb_id,
             f"kbId={doc.get('knowledgeBaseId')}")

        # 5) 非成员上传被拒绝
        r = c.post('/documents/upload', headers=H3,
                   data={'knowledgeBaseId': kb_id},
                   files={'file': ('x.txt', b'test', 'text/plain')})
        step('5.非成员上传返回 404', r.status_code == 404, f'HTTP {r.status_code}')

        # 6) 成员能看到团队库的文档
        if doc_id:
            r = c.get('/documents', headers=H2, params={'knowledgeBaseId': kb_id})
            docs = r.json() if r.status_code == 200 else []
            step('6.成员能看到团队库文档', any(d['id'] == doc_id for d in docs),
                 f'共 {len(docs)} 个文档')

        # 7) 个人库与团队库共存
        r = c.post('/knowledge-bases', headers=H1, json={'name': '我的个人库'})
        personal_id = r.json()['id']
        step('7.创建个人库', r.status_code == 200,
             f"ownerType={r.json().get('ownerType')}")
        r = c.get('/knowledge-bases', headers=H1)
        all_ids = [b['id'] for b in r.json()]
        step('7.同时看到个人库与团队库',
             kb_id in all_ids and personal_id in all_ids,
             f'共 {len(all_ids)} 个')

        # 8) 非成员建团队库应拒绝
        r = c.post('/knowledge-bases', headers=H3, json={'name': '不该成功', 'teamId': tid})
        step('8.非成员不能建团队库', r.status_code == 403, f'HTTP {r.status_code}')

        # 9) RAG 检索：成员提问应能召回团队库内容
        if doc_id:
            print('  ... 等待团队库文档向量化')
            ready = False
            for _ in range(40):
                time.sleep(3)
                docs = c.get('/documents', headers=H2, params={'knowledgeBaseId': kb_id}).json()
                cur = next((d for d in docs if d['id'] == doc_id), None)
                if cur and cur['status'] in ('ready', 'failed'):
                    ready = cur['status'] == 'ready'
                    step('9.团队库文档向量化完成', ready,
                         f"status={cur['status']} chunks={cur.get('chunks')}"
                         + (f" err={str(cur.get('error'))[:80]}" if cur.get('error') else ''))
                    break
            if not ready:
                step('9.团队库文档向量化完成', False, '超时未完成')

            # 由「另一个成员」提问（不是上传者），验证团队共享生效
            question = '团队项目代号是什么？端口是多少？'
            sources = None
            answer = ''
            with c.stream('POST', '/chat/stream', headers=H2, timeout=180, json={
                'content': question, 'knowledgeBaseIds': [kb_id], 'topK': 3,
            }) as resp:
                buf = ''
                for chunk in resp.iter_text():
                    buf += chunk
                    while '\n\n' in buf:
                        raw, buf = buf.split('\n\n', 1)
                        ev, data_line = 'message', ''
                        for line in raw.split('\n'):
                            if line.startswith('event:'):
                                ev = line[6:].strip()
                            elif line.startswith('data:'):
                                data_line += line[5:].strip()
                        if not data_line:
                            continue
                        try:
                            d = json.loads(data_line)
                        except Exception:
                            continue
                        if ev == 'sources':
                            sources = d.get('sources')
                        elif ev == 'delta':
                            answer += d.get('content', '')

            step('9.成员提问召回团队库切片', bool(sources),
                 f"{len(sources)} 条" + (f" 首条={sources[0].get('documentName')}" if sources else ''))
            step('9.回答含团队库事实', ('海豚三号' in answer) or ('8848' in answer),
                 f'{len(answer)} 字：{answer[:70].strip()}')

        # 10) 非成员提问不应召回团队库内容
        if doc_id:
            with c.stream('POST', '/chat/stream', headers=H3, timeout=180, json={
                'content': '团队项目代号是什么？', 'knowledgeBaseIds': [kb_id], 'topK': 3,
            }) as resp:
                buf, out_sources = '', None
                for chunk in resp.iter_text():
                    buf += chunk
                    while '\n\n' in buf:
                        raw, buf = buf.split('\n\n', 1)
                        ev, data_line = 'message', ''
                        for line in raw.split('\n'):
                            if line.startswith('event:'):
                                ev = line[6:].strip()
                            elif line.startswith('data:'):
                                data_line += line[5:].strip()
                        if data_line and ev == 'sources':
                            try:
                                out_sources = json.loads(data_line).get('sources')
                            except Exception:
                                pass
            step('10.非成员检索不到团队库', not out_sources,
                 f'召回 {len(out_sources) if out_sources else 0} 条')

        # 9) 清理
        r = c.delete(f'/knowledge-bases/{kb_id}', headers=H1)
        step('9.删除团队库', r.status_code in (200, 204), f'HTTP {r.status_code}')
        r = c.delete(f'/knowledge-bases/{personal_id}', headers=H1)
        step('9.删除个人库', r.status_code in (200, 204), f'HTTP {r.status_code}')
        r = c.delete(f'/teams/{tid}', headers=H1)
        step('9.解散团队', r.status_code == 200, f'HTTP {r.status_code}')

    passed = sum(1 for _, ok, _ in results if ok)
    print(f'\n===== 通过 {passed}/{len(results)} =====')
    for n, ok, note in results:
        if not ok:
            print(f'  FAIL: {n}  {note}')
    return 0 if passed == len(results) else 1


if __name__ == '__main__':
    sys.exit(main())
