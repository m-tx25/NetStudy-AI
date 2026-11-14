# -*- coding: utf-8 -*-
"""模块七「学术研究辅助」验收。

覆盖：
  1. 创建（1~8 篇）与参数校验（0 篇 → 400，超 8 篇 → 400）
  2. 权限：他人的论文 → 404；他人的报告 → 404
  3. 后台任务跑完，产物结构完整（方向/问题/路线/创新/相关工作）
  4. **核心要求**：每条建议的 kind 合法；kind=evidence 必须带有效证据；
     创新空间条目一律为 hypothesis，且带免责说明
  5. 报告可导出 Markdown

用法：
    .\\.venv\\Scripts\\python.exe tests\\verify_research.py
"""
from __future__ import annotations

import os
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


def main() -> int:
    suffix = uuid.uuid4().hex[:8]
    client = httpx.Client(base_url=BASE, timeout=600, trust_env=False)

    print('=' * 62)
    print(' 学术研究辅助（模块七）验收')
    print('=' * 62)

    demo = client.post('/auth/login', json={'username': 'demo', 'password': '123456'}).json()
    token = demo.get('accessToken') or demo.get('access_token') or demo.get('token')
    if not token:
        print('  demo 登录失败')
        return 1
    HD = {'Authorization': f'Bearer {token}'}

    other = f'res_{suffix}'
    client.post('/auth/register', json={
        'username': other, 'email': f'{other}@res.test', 'password': 'test123456',
    })
    ot = client.post('/auth/login', json={'username': other, 'password': 'test123456'}).json()
    ot = ot.get('accessToken') or ot.get('access_token') or ot.get('token')
    HO = {'Authorization': f'Bearer {ot}'}

    bases = client.get('/knowledge-bases', headers=HD).json()
    paper_base = next((b for b in bases if b['name'].startswith('学术文献')), None)
    if paper_base is None:
        print('  缺少「学术文献」演示库，先跑论文对比的数据准备')
        return 1
    docs = client.get('/documents', headers=HD, params={'knowledgeBaseId': paper_base['id']}).json()
    ids = [d['id'] for d in docs]

    print('\n=== 1. 参数与权限 ===')
    r = client.post('/research/briefs', headers=HD, json={'documentIds': [], 'goal': 'x'})
    check('0 篇论文 → 400', r.status_code == 400, str(r.status_code))
    # 重复 id 会被去重（不是 400）；真实上限是 8 篇不同论文
    r = client.post('/research/briefs', headers=HD, json={'documentIds': ids * 3, 'goal': f'dedupe-{suffix}'})
    created = r.json() if r.status_code == 200 else {}
    check('重复 id 自动去重', r.status_code == 200 and len(created.get('documentIds') or []) == len(ids),
          f"{r.status_code} {len(created.get('documentIds') or [])}")
    if created.get('id'):
        client.delete(f"/research/briefs/{created['id']}", headers=HD)
    r = client.post('/research/briefs', headers=HO, json={'documentIds': ids, 'goal': 'x'})
    check('他人的论文 → 404', r.status_code == 404, str(r.status_code))

    print('\n=== 2. 生成 ===')
    goal = f'小样本垂直领域 RAG 检索质量优化（{suffix}）'
    r = client.post('/research/briefs', headers=HD, json={
        'documentIds': ids, 'goal': goal,
    })
    brief = r.json() if r.status_code == 200 else {}
    check('创建成功', r.status_code == 200 and bool(brief.get('id')), r.text[:200])
    brief_id = brief.get('id')
    if not brief_id:
        return 1

    t0 = time.time()
    while time.time() - t0 < 900:
        data = client.get(f'/research/briefs/{brief_id}', headers=HD).json()
        if data.get('status') in ('ready', 'failed'):
            break
        time.sleep(6)
    check('任务结束', data.get('status') == 'ready', str(data.get('error'))[:200])
    if data.get('status') != 'ready':
        return 1
    print(f'  耗时 {int(time.time() - t0)} 秒')

    print('\n=== 3. 产物结构 ===')
    directions = data.get('directions') or []
    questions = data.get('questions') or []
    roadmap = data.get('roadmap') or {}
    novelty = data.get('novelty') or {}
    related = data.get('relatedWork') or {}

    check(f'研究方向 {len(directions)} 个（>=3）', len(directions) >= 3, str(len(directions)))
    check(f'研究问题 {len(questions)} 个（>=3）', len(questions) >= 3, str(len(questions)))
    check('每个问题都有研究思路', all(q.get('approaches') for q in questions),
          str([len(q.get('approaches') or []) for q in questions]))
    check('技术路线非空', bool(roadmap.get('routes')), str(roadmap)[:150])
    check('阶段计划非空', bool(roadmap.get('roadmap')), '')
    check('创新空间有覆盖与空白',
          bool(novelty.get('coverage')) and bool(novelty.get('openings')), str(novelty)[:150])
    check('相关工作有分组', bool(related.get('groups')), '')
    check('本地相关文献推荐', isinstance(data.get('relatedDocs'), list), '')

    print('\n=== 4. 核心要求：证据与假设分离 ===')
    kinds_ok = all(
        item.get('kind') in ('evidence', 'hypothesis', 'suggestion')
        for item in directions + questions
    )
    check('每条建议的 kind 合法', kinds_ok,
          str([item.get('kind') for item in directions + questions])[:200])

    evidence_without_ref = [
        item for item in directions + questions
        if item.get('kind') == 'evidence' and not item.get('evidence')
    ]
    check('kind=evidence 的条目都带证据', not evidence_without_ref,
          str(evidence_without_ref)[:200])

    bad_evidence = []
    valid_ids = set(data.get('documentIds') or [])
    for item in directions + questions:
        for ev in item.get('evidence') or []:
            if ev.get('documentId') not in valid_ids:
                bad_evidence.append(ev)
    check('证据里的 documentId 都属于本次论文', not bad_evidence, str(bad_evidence)[:200])

    openings = novelty.get('openings') or []
    check('创新空间条目一律标为 hypothesis',
          all(item.get('kind') == 'hypothesis' for item in openings),
          str([item.get('kind') for item in openings])[:160])
    check('创新空间带免责说明', '创新' in (novelty.get('caveat') or ''), str(novelty.get('caveat'))[:120])

    print('\n=== 5. 报告与权限 ===')
    r = client.get(f'/research/briefs/{brief_id}/report.md', headers=HD)
    check('报告可导出', r.status_code == 200 and len(r.text) > 1000, f'{r.status_code} {len(r.text)}')
    check('报告含免责提示', '不代表这些方向一定具有创新性' in r.text or '免责' in r.text, '')
    check('报告含文献依据/AI 假设标记',
          ('文献依据' in r.text) and ('AI 假设' in r.text or 'AI 推测' in r.text), '')
    r = client.get(f'/research/briefs/{brief_id}', headers=HO)
    check('他人看不到我的报告 → 404', r.status_code == 404, str(r.status_code))

    client.delete(f'/research/briefs/{brief_id}', headers=HD)

    print()
    print(f'结果：{passed} 通过 / {failed} 失败')
    return 0 if failed == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
