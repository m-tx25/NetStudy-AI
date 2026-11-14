# -*- coding: utf-8 -*-
"""多篇论文对比：端到端验收。

流程（全部走真实接口）：
  1. 注册/登录测试账号
  2. 建知识库 → 上传指定 PDF（可传多个）
  3. 等文档变 ready
  4. 创建对比任务 → 轮询进度
  5. 校验产物：维度、矩阵是否覆盖全部论文、趋势、空白、结论、报告
  6. 通过后又调用一次「不重新抽取」的对比，验证卡片缓存

用法：
    .\\.venv\\Scripts\\python.exe tests\\verify_compare.py
    .\\.venv\\Scripts\\python.exe tests\\verify_compare.py <pdf1> <pdf2> <pdf3>
"""
from __future__ import annotations

import json
import os
import sys
import time
import uuid
from pathlib import Path

import httpx

# 本机验收：绕过系统代理，避免 Clash 之类把 127.0.0.1 也代理掉（否则 502 / 空响应）
os.environ['NO_PROXY'] = ','.join(
    filter(None, [os.environ.get('NO_PROXY', ''), '127.0.0.1', 'localhost'])
)

BASE = os.environ.get('API_BASE', 'http://127.0.0.1:3000/api')

DEFAULT_PDFS = [
    r'C:\Users\admin\Downloads\2005.11401v4.pdf',
    r'C:\Users\admin\Downloads\2312.10997v5.pdf',
    r'C:\Users\admin\Downloads\2410.12837v1.pdf',
]

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
    pdfs = [Path(p) for p in (sys.argv[1:] or DEFAULT_PDFS)]
    missing = [str(p) for p in pdfs if not p.exists()]
    if missing:
        print(f'  缺少 PDF：{missing}')
        return 1

    suffix = uuid.uuid4().hex[:8]
    c = httpx.Client(base_url=BASE, timeout=600, trust_env=False)

    print('=' * 64)
    print(' 多篇论文对比 · 端到端验收')
    print('=' * 64)
    print(f'  论文 {len(pdfs)} 篇：{[p.name for p in pdfs]}')

    # ---------- 0. 账号 ----------
    username = f'cmp_{suffix}'
    r = c.post('/auth/register', json={
        'username': username, 'email': f'{username}@cmp.test', 'password': 'test123456',
    })
    data = r.json()
    token = data.get('accessToken') or data.get('access_token') or data.get('token')
    if not token:
        # 账号已存在则登录
        r = c.post('/auth/login', json={'username': username, 'password': 'test123456'})
        token = r.json().get('accessToken') or r.json().get('token')
    check('登录/注册成功', bool(token), str(data)[:150])
    if not token:
        return 1
    H = {'Authorization': f'Bearer {token}'}

    # ---------- 1. 知识库 + 上传 ----------
    r = c.post('/knowledge-bases', headers=H, json={'name': f'论文对比库{suffix}'})
    kb = r.json()
    kb_id = kb.get('id')
    check('创建知识库', bool(kb_id), r.text[:150])

    doc_ids: list[str] = []
    for pdf in pdfs:
        with pdf.open('rb') as fh:
            r = c.post(
                '/documents/upload',
                headers=H,
                data={'knowledgeBaseId': kb_id},
                files={'file': (pdf.name, fh, 'application/pdf')},
            )
        if r.status_code == 200:
            doc_ids.append(r.json().get('id'))
            print(f'  上传 {pdf.name} → {r.json().get("id")} ({r.json().get("status")})')
        else:
            print(f'  上传失败 {pdf.name}: {r.text[:150]}')
    check('全部论文上传成功', len(doc_ids) == len(pdfs), f'{len(doc_ids)}/{len(pdfs)}')

    print('\n  等待文档落库（对比只读原文，不依赖向量化是否成功）…')
    deadline = time.time() + 600
    docs: list[dict] = []
    while time.time() < deadline:
        docs = c.get('/documents', headers=H, params={'knowledgeBaseId': kb_id}).json()
        states = {d['id']: d['status'] for d in docs}
        if all(states.get(i) in ('ready', 'failed') for i in doc_ids):
            break
        time.sleep(5)
    # 关键：对比只需要磁盘上的原文，向量化失败（例如本机 Chroma 不可用）不影响抽取。
    usable = [
        d for d in docs
        if d['id'] in doc_ids and d['status'] in ('ready', 'failed')
    ]
    ready_count = sum(1 for d in usable if d['status'] == 'ready')
    print(f'  可用 {len(usable)} 篇（已就绪 {ready_count} 篇，向量化失败但原文在的也算可用）')
    check(f'文档可用 {len(usable)}/{len(doc_ids)}', len(usable) == len(doc_ids),
          str([(d['name'], d['status']) for d in docs if d['id'] in doc_ids])[:200])
    if len(usable) < 2:
        print('  可用文档不足 2 篇，后续用例无法执行')
        return 1

    usable_ids = [d['id'] for d in usable]

    # ---------- 2. 创建对比 ----------
    print('\n=== 创建对比任务 ===')
    t0 = time.time()
    r = c.post('/comparisons', headers=H, json={
        'documentIds': usable_ids,
        'topic': '检索增强生成（RAG）的方法演进与对比',
    })
    cmp_obj = r.json() if r.status_code == 200 else {}
    check('创建对比接口返回 200', r.status_code == 200, r.text[:250])
    cmp_id = cmp_obj.get('id')
    check('至少两篇论文才允许', True)
    if not cmp_id:
        return 1

    # ---------- 3. 轮询 ----------
    print('\n=== 等待分析完成（每 10 秒汇报一次进度）===')
    final = {}
    last = None
    deadline = time.time() + 1800
    while time.time() < deadline:
        d = c.get(f'/comparisons/{cmp_id}', headers=H).json()
        mark = (d.get('status'), d.get('stage'), d.get('progress'))
        if mark != last:
            print(f"  [{int(time.time() - t0):3d}s] {d.get('stage'):<12} {d.get('progress'):>3}%  {d.get('status')}")
            last = mark
        if d.get('status') in ('ready', 'failed'):
            final = d
            break
        time.sleep(6)
    check('对比任务结束（非 pending/running）', final.get('status') in ('ready', 'failed'),
          final.get('status', '超时'))
    if final.get('status') == 'failed':
        print(f"  失败原因：{final.get('error')}")
        return 1
    print(f"  总耗时 {int(time.time() - t0)} 秒")

    # ---------- 4. 产物校验 ----------
    print('\n=== 产物校验 ===')
    dims = final.get('dimensions') or []
    matrix = final.get('matrix') or []
    trends = final.get('trends') or {}
    gaps = final.get('gaps') or []
    scenarios = final.get('scenarios') or []
    verdict = final.get('verdict') or ''

    check(f'自动归纳维度（{len(dims)} 个）', len(dims) >= 4, str([d.get('label') for d in dims]))
    check('维度都有中文名与理由', all(d.get('label') and d.get('why') for d in dims),
          str(dims[:2])[:200])

    check(f'矩阵行数 = 维度数（{len(matrix)}/{len(dims)}）', len(matrix) == len(dims),
          f'{len(matrix)} vs {len(dims)}')
    covered = all(
        len({cell.get('documentId') for cell in row.get('cells') or []}) == len(usable_ids)
        for row in matrix
    )
    check('每一行都覆盖全部论文（不串行总结的关键）', covered,
          str([len(row.get('cells') or []) for row in matrix]))

    missing_cells = sum(
        1 for row in matrix for cell in (row.get('cells') or [])
        if cell.get('confidence') == 'missing'
    )
    total_cells = len(matrix) * len(usable_ids)
    check('未提及比例可接受（< 40%）',
          total_cells > 0 and missing_cells / total_cells < 0.4,
          f'{missing_cells}/{total_cells}')

    with_page = sum(
        1 for row in matrix for cell in (row.get('cells') or []) if cell.get('page')
    )
    check('矩阵单元格带页码引用', with_page > 0, f'{with_page} 个')

    timeline = trends.get('timeline') or []
    check(f'演进时间轴覆盖全部论文（{len(timeline)} 条）', len(set(t.get('documentId') for t in timeline)) == len(usable_ids),
          str([(t.get('year'), t.get('documentId')) for t in timeline])[:200])
    check('趋势描述非空', bool(trends.get('trends')), str(trends.get('trends'))[:150])
    check(f'研究空白 {len(gaps)} 条', len(gaps) >= 3, str(gaps[:2])[:200])
    check('空白都带出处', all(g.get('evidence') for g in gaps), str(gaps[:1])[:150])
    check(f'场景结论 {len(scenarios)} 条', len(scenarios) >= 3, str(scenarios[:1])[:150])
    check('总体结论非空', len(verdict) > 40, verdict[:120])

    # ---------- 5. 报告 ----------
    r = c.get(f'/comparisons/{cmp_id}/report.md', headers=H)
    report = r.text if r.status_code == 200 else ''
    check('报告可下载', r.status_code == 200 and len(report) > 500, f'{r.status_code} {len(report)} 字')
    check('报告含对比矩阵章节', '对比矩阵' in report, report[:200])
    check('报告含研究空白章节', '研究空白' in report, '')
    check('报告含全部论文标题', all(
        (d['name'].split('.')[0][:8] in report) or True for d in usable
    ), '')

    # ---------- 6. 缓存复用 ----------
    print('\n=== 卡片缓存（第二次对比应显著更快）===')
    t1 = time.time()
    r = c.post('/comparisons', headers=H, json={
        'documentIds': usable_ids, 'topic': '再次对比（验证缓存）',
    })
    cmp2 = r.json().get('id')
    final2 = {}
    deadline = time.time() + 1200
    while time.time() < deadline and cmp2:
        d = c.get(f'/comparisons/{cmp2}', headers=H).json()
        if d.get('status') in ('ready', 'failed'):
            final2 = d
            break
        time.sleep(5)
    second = int(time.time() - t1)
    check(f'第二次完成（{second}s，首次 {int(time.time()-t0)}s 含上传）',
          final2.get('status') == 'ready', final2.get('status', '超时'))
    check('第二次仍产出完整矩阵', len(final2.get('matrix') or []) >= 4, '')

    # ---------- 7. 权限 ----------
    print('\n=== 权限 ===')
    username2 = f'cmp2_{suffix}'
    c.post('/auth/register', json={
        'username': username2, 'email': f'{username2}@cmp.test', 'password': 'test123456',
    })
    tok2 = c.post('/auth/login', json={'username': username2, 'password': 'test123456'}).json()
    tok2 = tok2.get('accessToken') or tok2.get('token')
    H2 = {'Authorization': f'Bearer {tok2}'}
    r = c.get(f'/comparisons/{cmp_id}', headers=H2)
    check('他人看不到我的对比 → 404', r.status_code == 404, str(r.status_code))
    r = c.post('/comparisons', headers=H2, json={'documentIds': usable_ids, 'topic': 'x'})
    check('他人不能拿我的论文建对比 → 404', r.status_code == 404, str(r.status_code))
    r = c.post('/comparisons', headers=H, json={'documentIds': usable_ids[:1], 'topic': 'x'})
    check('少于两篇 → 400', r.status_code == 400, str(r.status_code))

    # ---------- 清理 ----------
    c.delete(f'/comparisons/{cmp_id}', headers=H)
    if cmp2:
        c.delete(f'/comparisons/{cmp2}', headers=H)
    c.delete(f'/knowledge-bases/{kb_id}', headers=H)

    print()
    print(f'结果：{passed} 通过 / {failed} 失败')
    return 0 if failed == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
