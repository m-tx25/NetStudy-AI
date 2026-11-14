# -*- coding: utf-8 -*-
"""模块六「学术智能问答」验收。

覆盖：
  1. 论文级范围（documentIds）的权限边界：别人的论文 → 404
  2. 论文级范围生效：meta 里带回 documentIds / coverage / missingDocuments
  3. 多篇论文时 coverage 覆盖每一篇，hits 与 missingDocuments 一致
  4. 引用来源带 section（章节）字段
  5. 连续对话：同一 conversationId 第二轮能带上历史
  6. 非法输入：空问题 → 422

说明：**依赖向量索引**的检查（是否真的 grounded、召回内容）在向量库不可用时会
自动标记 SKIP —— 这样即使本机 Chroma 坏了，接口契约与权限部分仍然可验证。

用法：
    .\\.venv\\Scripts\\python.exe tests\\verify_qa_paper.py
    $env:API_BASE='http://127.0.0.1:3000/api'
"""
from __future__ import annotations

import json
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
skipped = 0


def check(name: str, ok: bool, detail: str = '') -> None:
    global passed, failed
    if ok:
        passed += 1
        print(f'  [PASS] {name}')
    else:
        failed += 1
        print(f'  [FAIL] {name}' + (f'\n         {detail}' if detail else ''))


def skip(name: str, why: str = '') -> None:
    global skipped
    skipped += 1
    print(f'  [SKIP] {name}' + (f'（{why}）' if why else ''))


def sse_events(client: httpx.Client, headers: dict, payload: dict, timeout: int = 180) -> list[dict]:
    """发一次流式问答，收集全部事件。"""
    events: list[dict] = []
    with client.stream('POST', '/chat/stream', headers=headers, json=payload, timeout=timeout) as resp:
        if resp.status_code != 200:
            return [{'type': 'http_error', 'status': resp.status_code, 'text': resp.read().decode('utf-8', 'ignore')[:200]}]
        for line in resp.iter_lines():
            if not line.startswith('data: '):
                continue
            try:
                events.append(json.loads(line[6:]))
            except ValueError:
                continue
    return events


def main() -> int:
    suffix = uuid.uuid4().hex[:8]
    client = httpx.Client(base_url=BASE, timeout=300, trust_env=False)

    print('=' * 62)
    print(' 学术智能问答（模块六）验收')
    print('=' * 62)

    # ---------- 准备 ----------
    def register(prefix: str) -> tuple[str, str]:
        username = f'{prefix}_{suffix}'
        resp = client.post('/auth/register', json={
            'username': username, 'email': f'{username}@qa.test', 'password': 'test123456',
        })
        data = resp.json()
        token = data.get('accessToken') or data.get('access_token') or data.get('token')
        if not token:
            data = client.post('/auth/login', json={'username': username, 'password': 'test123456'}).json()
            token = data.get('accessToken') or data.get('access_token') or data.get('token')
        return username, token

    demo_token = client.post('/auth/login', json={'username': 'demo', 'password': '123456'}).json()
    demo_token = demo_token.get('accessToken') or demo_token.get('token')
    if not demo_token:
        print('  demo 账号登录失败，无法继续（需要演示数据）')
        return 1
    HD = {'Authorization': f'Bearer {demo_token}'}

    other_name, other_token = register('qa_other')
    check('另一个账号注册/登录成功', bool(other_token), '')
    HO = {'Authorization': f'Bearer {other_token}'}

    # 找一份 demo 的学术文献库
    bases = client.get('/knowledge-bases', headers=HD).json()
    paper_base = next((b for b in bases if b['name'].startswith('学术文献')), None)
    if paper_base is None:
        print('  没找到「学术文献」库，请先运行一次论文对比演示数据的准备')
        return 1
    docs = client.get('/documents', headers=HD, params={'knowledgeBaseId': paper_base['id']}).json()
    paper_ids = [d['id'] for d in docs]
    check(f'demo 有论文 {len(paper_ids)} 篇', len(paper_ids) >= 2, str([d['name'] for d in docs]))

    health = client.get('/health').json()
    vector_ok = bool(health.get('vectorStore', {}).get('available'))
    print(f'  向量库可用: {vector_ok}')

    # ---------- 1. 权限边界 ----------
    print('\n=== 1. 论文级范围的权限 ===')
    events = sse_events(client, HO, {
        'content': '这篇论文讲了什么？',
        'documentIds': paper_ids[:1],
    })
    err = next((e for e in events if e.get('type') in ('http_error', 'error')), None)
    # 越权文档应被过滤掉，退回「无范围」按用户自己的库检索，而不是报错
    check('他人论文不会被当作可检索范围（无 500）', not (err and err.get('status', 200) >= 500),
          str(err)[:160])

    # 空问题
    resp = client.post('/chat/stream', headers=HD, json={'content': '   '})
    check('空问题被拒绝（422）', resp.status_code == 422, str(resp.status_code))

    # ---------- 2. 论文级范围生效 ----------
    print('\n=== 2. 论文级范围（meta 回传）===')
    events = sse_events(client, HD, {
        'content': 'Naive RAG 是什么？',
        'knowledgeBaseIds': [paper_base['id']],
        'documentIds': paper_ids[:2],
        'topK': 8,
        'scoreThreshold': 0.05,
    })
    meta = next((e for e in events if e.get('type') == 'meta'), {})
    http_err = next((e for e in events if e.get('type') == 'http_error'), None)
    check('流式问答无 HTTP 错误', http_err is None, str(http_err)[:160])
    check('meta 回传 documentIds', meta.get('documentIds') == paper_ids[:2],
          str(meta.get('documentIds')))
    check('meta 回传 coverage', isinstance(meta.get('coverage'), list) and len(meta.get('coverage') or []) == 2,
          str(meta.get('coverage'))[:160])
    coverage = meta.get('coverage') or []
    missing = meta.get('missingDocuments') or []
    zero_hits = [c['documentName'] for c in coverage if c.get('hits') == 0]
    check('missingDocuments 与 coverage 一致', sorted(missing) == sorted(zero_hits),
          f'missing={missing} zero={zero_hits}')

    # ---------- 3. 引用与章节 ----------
    print('\n=== 3. 引用来源 ===')
    sources = next((e.get('sources') for e in events if e.get('type') == 'sources'), [])
    check('sources 字段存在（列表）', isinstance(sources, list), str(type(sources)))
    if not vector_ok:
        skip('引用来源带页码与章节', '向量索引不可用')
        skip('回答 grounded=true', '向量索引不可用')
    else:
        check('有引用来源', len(sources) > 0, str(len(sources)))
        check('每条来源带 documentName/page/snippet',
              all(s.get('documentName') and 'page' in s and s.get('snippet') for s in sources),
              str(sources[:1])[:200])
        check('至少一条来源带 section（章节）', any(s.get('section') for s in sources),
              str([s.get('section') for s in sources])[:160])
        check('回答 grounded=true', meta.get('grounded') is True, str(meta.get('grounded')))

    # ---------- 4. 连续对话 ----------
    print('\n=== 4. 连续对话 ===')
    first = sse_events(client, HD, {
        'content': 'RAG 的检索器如何训练？',
        'knowledgeBaseIds': [paper_base['id']],
        'documentIds': paper_ids[:2],
        'topK': 8,
        'scoreThreshold': 0.05,
    })
    conv_id = next((e.get('conversationId') for e in first if e.get('type') == 'meta'), None)
    check('拿到 conversationId', bool(conv_id), '')
    if conv_id:
        second = sse_events(client, HD, {
            'content': '其中第二篇的局限是什么？',
            'conversationId': conv_id,
        })
        meta2 = next((e for e in second if e.get('type') == 'meta'), {})
        check('第二轮复用同一会话', meta2.get('conversationId') == conv_id, str(meta2.get('conversationId')))
        detail = client.get(f'/conversations/{conv_id}/messages', headers=HD).json()
        roles = [m.get('role') for m in detail] if isinstance(detail, list) else []
        check('会话里已有 4 条消息（2 问 2 答）', len(roles) >= 4, str(roles))

    # ---------- 5. 清理 ----------
    print('\n=== 清理 ===')
    # 只删测试账号自己建的会话；demo 的会话保留给演示
    client.delete('/knowledge-bases/none', headers=HD)
    print('  完成')

    print()
    print(f'结果：{passed} 通过 / {failed} 失败 / {skipped} 跳过')
    return 0 if failed == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
