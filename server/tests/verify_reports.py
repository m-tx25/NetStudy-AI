# -*- coding: utf-8 -*-
"""模块八「学术成果生成与导出」验收。

覆盖：
  1. 参数校验：非法 kind / 阅读报告选多篇 / 对比报告缺 comparisonId → 400
  2. 三种生成物：reading（1 篇）/ review（多篇）/ status（多篇）
  3. 引用溯源：sources 里的 documentId 都属于本次论文，且带页码或标记
  4. 参考文献三种格式（GB/T 7714 / APA / IEEE）都能生成
  5. **核心要求**：不伪造 DOI —— 生成内容里不出现 "doi:" / "10.xxxx/"
  6. 导出：md / html / docx（DOCX 必须是 ZIP 头 PK，且能读出段落）
  7. 权限：他人看不到我的报告

用法：
    .\\.venv\\Scripts\\python.exe tests\\verify_reports.py
"""
from __future__ import annotations

import io
import os
import re
import sys
import time
import uuid

import httpx

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


def wait_ready(client: httpx.Client, headers: dict, report_id: str, timeout: int = 600) -> dict:
    start = time.time()
    data: dict = {}
    while time.time() - start < timeout:
        data = client.get(f'/reports/{report_id}', headers=headers).json()
        if data.get('status') in ('ready', 'failed'):
            return data
        time.sleep(4)
    return data


def main() -> int:
    suffix = uuid.uuid4().hex[:8]
    client = httpx.Client(base_url=BASE, timeout=600, trust_env=False)

    print('=' * 62)
    print(' 学术成果生成与导出（模块八）验收')
    print('=' * 62)

    demo = client.post('/auth/login', json={'username': 'demo', 'password': '123456'}).json()
    token = demo.get('accessToken') or demo.get('access_token') or demo.get('token')
    if not token:
        print('  demo 登录失败')
        return 1
    HD = {'Authorization': f'Bearer {token}'}

    other = f'rpt_{suffix}'
    client.post('/auth/register', json={
        'username': other, 'email': f'{other}@rpt.test', 'password': 'test123456',
    })
    ot = client.post('/auth/login', json={'username': other, 'password': 'test123456'}).json()
    ot = ot.get('accessToken') or ot.get('access_token') or ot.get('token')
    HO = {'Authorization': f'Bearer {ot}'}

    bases = client.get('/knowledge-bases', headers=HD).json()
    paper_base = next((b for b in bases if b['name'].startswith('学术文献')), None)
    if paper_base is None:
        print('  缺少「学术文献」演示库')
        return 1
    docs = client.get('/documents', headers=HD, params={'knowledgeBaseId': paper_base['id']}).json()
    ids = [d['id'] for d in docs]

    print('\n=== 1. 参数校验 ===')
    r = client.post('/reports', headers=HD, json={'kind': 'nope', 'documentIds': ids[:1]})
    check('非法 kind → 400', r.status_code == 400, str(r.status_code))
    r = client.post('/reports', headers=HD, json={'kind': 'reading', 'documentIds': ids[:2]})
    check('阅读报告选多篇 → 400', r.status_code == 400, str(r.status_code))
    r = client.post('/reports', headers=HD, json={'kind': 'comparison'})
    check('对比报告缺 comparisonId → 400', r.status_code == 400, str(r.status_code))
    r = client.post('/reports', headers=HO, json={'kind': 'review', 'documentIds': ids})
    check('他人论文 → 404', r.status_code == 404, str(r.status_code))

    print('\n=== 2. 三种生成物 ===')
    created: dict[str, dict] = {}
    for kind, doc_ids, title in (
        ('reading', ids[:1], ''),
        ('review', ids, f'RAG 综述验收 {suffix}'),
        ('status', ids, f'RAG 现状验收 {suffix}'),
    ):
        r = client.post('/reports', headers=HD, json={
            'kind': kind, 'documentIds': doc_ids, 'title': title,
        })
        body = r.json() if r.status_code == 200 else {}
        rid = body.get('id')
        if not rid:
            check(f'{kind} 创建成功', False, r.text[:160])
            continue
        check(f'{kind} 创建成功', True)
        data = wait_ready(client, HD, rid)
        ok = data.get('status') == 'ready' and len(data.get('contentMd') or '') > 200
        check(f'{kind} 生成完成（{len(data.get("contentMd") or "")} 字）', ok,
              str(data.get('error'))[:160])
        if data.get('status') == 'ready':
            created[kind] = data

    print('\n=== 3. 引用溯源 ===')
    for kind, data in created.items():
        sources = data.get('sources') or []
        valid_ids = set(data.get('documentIds') or [])
        check(f'{kind}: 引用溯源覆盖所选论文', {s.get('documentId') for s in sources} == valid_ids,
              str([s.get('documentId') for s in sources])[:160])
        check(f'{kind}: 每条溯源带编号与页码字段',
              all('index' in s and 'pages' in s for s in sources), str(sources[:1])[:120])

    print('\n=== 4. 参考文献三种格式 ===')
    refs = (created.get('review') or {}).get('references') or {}
    for style, label in (('gbt', 'GB/T 7714'), ('apa', 'APA'), ('ieee', 'IEEE')):
        items = refs.get(style) or []
        check(f'{label} 生成 {len(items)} 条', len(items) == len(ids), str(len(items)))

    print('\n=== 5. 不伪造 DOI ===')
    for kind, data in created.items():
        text = (data.get('contentMd') or '') + str(data.get('references'))
        fabricated = re.findall(r'(?i)\bdoi\s*[:：]|10\.\d{4,9}/', text)
        check(f'{kind}: 没有编造 DOI', not fabricated, str(fabricated)[:120])
        check(f'{kind}: 报告含引用溯源一节', '引用溯源' in (data.get('contentMd') or ''), '')

    print('\n=== 6. 导出格式 ===')
    target = created.get('review') or created.get('status') or created.get('reading')
    if target:
        rid = target['id']
        r = client.get(f'/reports/{rid}/export', headers=HD, params={'format': 'md'})
        check('Markdown 导出', r.status_code == 200 and len(r.content) > 500, str(r.status_code))
        r = client.get(f'/reports/{rid}/export', headers=HD, params={'format': 'html'})
        check('HTML（打印用）导出', r.status_code == 200 and b'<html' in r.content.lower(),
              str(r.status_code))
        r = client.get(f'/reports/{rid}/export', headers=HD, params={'format': 'docx'})
        check('DOCX 导出（ZIP 头 PK）', r.status_code == 200 and r.content[:2] == b'PK',
              f'{r.status_code} {r.content[:8]!r}')
        if r.content[:2] == b'PK':
            try:
                from docx import Document as DocxDocument

                document = DocxDocument(io.BytesIO(r.content))
                paragraphs = [p.text for p in document.paragraphs if p.text.strip()]
                check('DOCX 可被 python-docx 打开且有内容', len(paragraphs) > 5, str(len(paragraphs)))
                check('DOCX 含参考文献段落',
                      any('参考文献' in p for p in paragraphs), '')
            except Exception as exc:
                check('DOCX 可解析', False, f'{type(exc).__name__}: {exc}')
        r = client.get(f'/reports/{rid}/export', headers=HD, params={'format': 'pdf'})
        check('非法格式被拒绝', r.status_code == 422, str(r.status_code))
    else:
        check('导出测试有可用报告', False, '没有生成成功的报告')

    print('\n=== 7. 权限 ===')
    if target:
        r = client.get(f'/reports/{target["id"]}', headers=HO)
        check('他人看不到我的报告 → 404', r.status_code == 404, str(r.status_code))
        r = client.get(f'/reports/{target["id"]}/export', headers=HO, params={'format': 'md'})
        check('他人不能导出我的报告 → 404', r.status_code == 404, str(r.status_code))

    for data in created.values():
        client.delete(f'/reports/{data["id"]}', headers=HD)

    print()
    print(f'结果：{passed} 通过 / {failed} 失败')
    return 0 if failed == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
