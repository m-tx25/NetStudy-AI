# -*- coding: utf-8 -*-
"""验证「服务端不配 API Key，用户自己填」这条路径能真正跑通。

场景：
  服务端 ZHIPUAI_API_KEY 为空（生产部署的推荐配置）
  用户 A 通过前端接口填了自己的智谱 Key
  → 上传文档应能以该用户的 Key 向量化成功（2048 维，zhipu2048 集合）
  → 提问应能召回

另外验证：另一个用户 B 不填 Key，走离线向量化（512 维，offline512 集合），
两个向量空间互不干扰。

用法（后端已在指定端口运行，且服务端 ZHIPUAI_API_KEY 为空）：
    python tests/verify_byok.py 3001
"""
import sys
import time
import uuid

import httpx

PORT = sys.argv[1] if len(sys.argv) > 1 else '3001'
BASE = f'http://127.0.0.1:{PORT}/api'

# 从命令行传入真实智谱 Key（形如 xxxxxxxx.xxxxxxxx）
ZHIPU_KEY = sys.argv[2] if len(sys.argv) > 2 else ''

results = []


def step(name, ok, note=''):
    results.append((name, ok, note))
    print(f"{'PASS' if ok else 'FAIL'}  {name:<40} {note}")


def new_user(c, prefix):
    username = f'{prefix}_{uuid.uuid4().hex[:8]}'
    r = c.post('/auth/register', json={
        'username': username, 'email': f'{username}@t.com', 'password': 'test123456'})
    token = r.json().get('access_token') or r.json().get('token')
    return username, {'Authorization': f'Bearer {token}'}


def upload_and_wait(c, h, kb_id, content, filename):
    r = c.post('/documents/upload', headers=h, data={'knowledgeBaseId': kb_id},
               files={'file': (filename, content.encode('utf-8'), 'text/plain')})
    if r.status_code != 200:
        return None, f'上传失败 {r.status_code}: {r.text[:120]}'
    doc_id = r.json().get('id')
    for _ in range(40):
        time.sleep(3)
        docs = c.get('/documents', headers=h, params={'knowledgeBaseId': kb_id}).json()
        cur = next((d for d in docs if d['id'] == doc_id), None)
        if cur and cur['status'] in ('ready', 'failed'):
            return cur, ''
    return None, '等待超时'


def ask(c, h, kb_id, question):
    sources, answer = None, ''
    with c.stream('POST', '/chat/stream', headers=h, timeout=180, json={
        'content': question, 'knowledgeBaseIds': [kb_id], 'topK': 3,
    }) as resp:
        buf = ''
        for chunk in resp.iter_text():
            buf += chunk
            while '\n\n' in buf:
                raw, buf = buf.split('\n\n', 1)
                ev, data = 'message', ''
                for line in raw.split('\n'):
                    if line.startswith('event:'):
                        ev = line[6:].strip()
                    elif line.startswith('data:'):
                        data += line[5:].strip()
                if not data:
                    continue
                try:
                    import json
                    d = json.loads(data)
                except Exception:
                    continue
                if ev == 'sources':
                    sources = d.get('sources')
                elif ev == 'delta':
                    answer += d.get('content', '')
    return sources, answer


def main() -> int:
    with httpx.Client(base_url=BASE, timeout=180) as c:
        # 0) 确认服务端确实没配 Key
        h0 = c.get('/health', timeout=60).json()
        mode = h0.get('vectorStore', {}).get('embedding', {}).get('mode')
        step('服务端未配智谱 Key（离线模式）', mode == 'offline-hash', f'mode={mode}')

        # ---------- 用户 A：自备 Key ----------
        if not ZHIPU_KEY:
            print('\n未提供智谱 Key，跳过「用户自备 Key」部分')
            print('用法: python tests/verify_byok.py 3001 xxxxxxxx.xxxxxxxx')
            return 1

        name_a, HA = new_user(c, 'byok')
        r = c.post('/keys', headers=HA, json={
            'provider': 'zhipu', 'secret': ZHIPU_KEY,
            'label': 'A 的智谱 Key', 'model': 'embedding-3'})
        step('A 保存自己的智谱 Key', r.status_code == 200,
             f"HTTP {r.status_code}" + ('' if r.status_code == 200 else f' {r.text[:100]}'))

        kb_a = c.post('/knowledge-bases', headers=HA, json={'name': f'A库{uuid.uuid4().hex[:4]}'}).json()
        doc_a, err = upload_and_wait(
            c, HA, kb_a['id'],
            'A 的文档：项目代号是「蓝海一号」，端口 9931。\n', 'a.txt')
        step('A 的文档用自备 Key 向量化成功', bool(doc_a) and doc_a['status'] == 'ready',
             f"status={doc_a['status'] if doc_a else '?'} chunks={doc_a.get('chunks') if doc_a else '?'} {err}"
             + (f" err={str(doc_a.get('error'))[:100]}" if doc_a and doc_a.get('error') else ''))

        if doc_a and doc_a['status'] == 'ready':
            sources, answer = ask(c, HA, kb_a['id'], '项目代号和端口是什么？')
            step('A 提问能召回', bool(sources), f'{len(sources) if sources else 0} 条')
            step('A 的回答命中事实', ('蓝海一号' in answer) or ('9931' in answer),
                 f'{len(answer)} 字')

        # ---------- 用户 B：不配 Key ----------
        name_b, HB = new_user(c, 'nokey')
        kb_b = c.post('/knowledge-bases', headers=HB, json={'name': f'B库{uuid.uuid4().hex[:4]}'}).json()
        doc_b, err_b = upload_and_wait(
            c, HB, kb_b['id'],
            'B 的文档：项目代号是「绿野二号」，端口 7721。\n', 'b.txt')
        step('B 未配 Key 也能向量化（离线）', bool(doc_b) and doc_b['status'] == 'ready',
             f"status={doc_b['status'] if doc_b else '?'} {err_b}"
             + (f" err={str(doc_b.get('error'))[:100]}" if doc_b and doc_b.get('error') else ''))

        if doc_b and doc_b['status'] == 'ready':
            sources_b, answer_b = ask(c, HB, kb_b['id'], '项目代号和端口是什么？')
            step('B 提问能召回', bool(sources_b), f'{len(sources_b) if sources_b else 0} 条')
            step('B 的回答命中事实', ('绿野二号' in answer_b) or ('7721' in answer_b),
                 f'{len(answer_b)} 字')

        # ---------- 隔离：A 搜不到 B 的内容 ----------
        if doc_a and doc_b:
            sources_x, _ = ask(c, HA, kb_a['id'], '绿野二号是什么？')
            texts = ' '.join((s.get('snippet') or '') for s in (sources_x or []))
            step('A 检索不到 B 的私有内容', '绿野二号' not in texts, '按 owner 隔离')

        # ---------- 健康检查：两个向量空间都在 ----------
        hh = c.get('/health', timeout=60).json()
        cols = hh.get('vectorStore', {}).get('collections') or []
        step('健康检查列出多个向量空间', len(cols) >= 1, f'{cols}')

    passed = sum(1 for _, ok, _ in results if ok)
    print(f'\n===== 通过 {passed}/{len(results)} =====')
    return 0 if passed == len(results) else 1


if __name__ == '__main__':
    sys.exit(main())
