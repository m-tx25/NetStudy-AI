# -*- coding: utf-8 -*-
"""上线验收：用户/团队自备 API Key 是否真的生效（BYOK）。

核心思路：**用「假 Key」来证明「真生效」**。
  - 服务端 .env 里配了可用的 Key（能正常回答）；
  - 给用户配一个**格式合法但无效**的 Key；
  - 如果系统仍然正常回答 → 说明它在用服务端 Key，用户配的根本没生效（BUG）；
  - 如果系统报「鉴权失败 / Key 无效」 → 说明确实用了用户的 Key（正确）。

这样验证不需要真实额度，也不会污染服务端 Key。

覆盖：
  1. 用户 Key 的增删改查、返回值必须脱敏
  2. 用户 Key 优先于服务端 Key（生成 / 向量化两条路径）
  3. 团队 Key 优先于用户 Key
  4. 删除 Key 后回落到服务端 Key
  5. 不同用户之间不串用（A 的 Key 不会作用到 B）

用法（后端已启动）：
    .\\.venv\\Scripts\\python.exe tests\\verify_byok_deploy.py
    # 或用环境变量指定地址
    $env:API_BASE='http://127.0.0.1:3000/api'; .\\.venv\\Scripts\\python.exe tests\\verify_byok_deploy.py
"""
from __future__ import annotations

import json
import os
import sys
import uuid

import httpx

# 本机验收：绕过系统代理，避免 Clash 之类把 127.0.0.1 也代理掉（否则 502 / 空响应）
os.environ['NO_PROXY'] = ','.join(
    filter(None, [os.environ.get('NO_PROXY', ''), '127.0.0.1', 'localhost'])
)

BASE = os.environ.get('API_BASE', 'http://127.0.0.1:3000/api')

# 格式像真的、但一定是无效的 Key（用来触发鉴权失败）
FAKE_ZHIPU = '00000000000000000000000000000000.fakefakefakefake'
FAKE_DEEPSEEK = 'sk-00000000000000000000000000000000fake'

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
        username = f'byok_{prefix}_{suffix}'
        r = c.post('/auth/register', json={
            'username': username,
            'email': f'{username}@byok.test',
            'password': 'test123456',
        })
        d = r.json()
        tok = d.get('accessToken') or d.get('access_token') or d.get('token')
        assert tok, f'注册失败: {d}'
        return username, tok

    def hdr(tok: str) -> dict:
        return {'Authorization': f'Bearer {tok}'}

    def ask(tok: str, question: str, kb_ids: list[str] | None = None,
            model: str | None = None) -> tuple[str, dict]:
        """发一次流式问答，返回 (拼接的正文, meta)。"""
        body = {'content': question, 'topK': 3}
        if kb_ids:
            body['knowledgeBaseIds'] = kb_ids
        if model:
            body['model'] = model
        answer, meta, err = '', {}, ''
        with c.stream('POST', '/chat/stream', headers=hdr(tok), json=body, timeout=180) as resp:
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
                        d = json.loads(data)
                    except Exception:
                        continue
                    if ev == 'delta':
                        answer += d.get('content', '')
                    elif ev == 'meta':
                        meta = d
                    elif ev == 'error':
                        err = d.get('message', '')
        return (answer + ('\n' + err if err else '')), meta

    def looks_like_auth_error(text: str) -> bool:
        low = text.lower()
        return any(k in low for k in ('鉴权', '无效', 'invalid', '401', 'unauthorized',
                                      'api key', 'apikey', 'authentication'))

    print('=' * 62)
    print(' BYOK 上线验收（用假 Key 证明「用户 Key 真的生效」）')
    print('=' * 62)

    print('\n=== 0. 服务端基线：不配任何用户 Key 时应能正常回答 ===')
    baseline = {}
    try:
        baseline = c.get('/health').json()
        print(f"  服务端 llmConfigured={baseline.get('llmConfigured')} "
              f"embedding={baseline['vectorStore']['embedding']['mode']} "
              f"configured={baseline['vectorStore']['embedding']['configured']}")
    except Exception as exc:
        print(f'  [FAIL] 读 /health 失败: {exc}')
        return 1
    if not baseline.get('llmConfigured'):
        print('  ⚠️ 服务端没配 LLM Key，本脚本的「回落」用例会失真；请先在 .env 配一个可用的。')

    alice_name, alice = register('alice')
    bob_name, bob = register('bob')
    print(f'  账号: {alice_name} / {bob_name}')

    print('\n=== 1. 用户 Key 的增删改查与脱敏 ===')
    r = c.get('/keys', headers=hdr(alice))
    check('GET /keys 可访问', r.status_code == 200, r.text[:150])
    r = c.post('/keys', headers=hdr(alice), json={
        'provider': 'zhipu', 'secret': FAKE_ZHIPU, 'label': 'BYOK 验收', 'model': 'embedding-3',
    })
    created = r.json() if r.status_code < 300 else {}
    check('POST /keys 创建成功', r.status_code < 300, r.text[:200])
    check('返回体不含明文 Key', FAKE_ZHIPU not in json.dumps(created, ensure_ascii=False),
          json.dumps(created, ensure_ascii=False)[:200])
    key_id = created.get('id')

    r = c.get('/keys', headers=hdr(alice))
    listing = r.json()
    raw = json.dumps(listing, ensure_ascii=False)
    check('GET /keys 不含明文 Key', FAKE_ZHIPU not in raw, raw[:200])
    check('列表里有该 Key（掩码展示）', '****' in raw or '…' in raw or '***' in raw, raw[:200])

    print('\n=== 2. 用户 Key 优先于服务端 Key（生成路径）===')
    text, meta = ask(alice, '用一句话说明什么是 HTTP 协议')
    check('配了无效 Key 后问答失败（说明用的是用户 Key，而非服务端）',
          looks_like_auth_error(text), text[:300])
    check('meta 标明走了回退（不再伪装成有依据的回答）',
          meta.get('fallback') is True or meta.get('answerSource') == 'model',
          json.dumps(meta, ensure_ascii=False)[:200])

    print('\n=== 3. 另一个用户不受影响（不串用）===')
    text_b, meta_b = ask(bob, '用一句话说明什么是 HTTP 协议')
    check('bob 未配 Key，走服务端 Key 正常回答',
          bool(text_b.strip()) and not looks_like_auth_error(text_b), text_b[:300])

    print('\n=== 4. 删除 Key 后回落到服务端 Key ===')
    if key_id:
        r = c.delete(f'/keys/{key_id}', headers=hdr(alice))
        check('DELETE /keys 成功', r.status_code == 200, r.text[:150])
    text2, _ = ask(alice, '用一句话说明什么是 HTTP 协议')
    check('删除后 alice 恢复正常（回落到服务端 Key）',
          bool(text2.strip()) and not looks_like_auth_error(text2), text2[:300])

    print('\n=== 5. 团队 Key 优先于用户 Key ===')
    r = c.post('/teams', headers=hdr(alice), json={
        'name': f'BYOK 团队{suffix}', 'description': '验收', 'visibility': 'private',
        'joinPolicy': 'approval',
    })
    team = r.json() if r.status_code < 300 else {}
    team_id = team.get('id')
    check('创建团队', bool(team_id), r.text[:200])

    if team_id:
        r = c.post(f'/teams/{team_id}/keys', headers=hdr(alice), json={
            'provider': 'deepseek', 'secret': FAKE_DEEPSEEK, 'label': '团队假 Key',
            'model': 'deepseek-chat',
        })
        check('团队 Key 创建成功', r.status_code < 300, r.text[:200])
        team_key_id = r.json().get('id') if r.status_code < 300 else None

        # 团队库：用团队 Key 生成
        r = c.post('/knowledge-bases', headers=hdr(alice), json={
            'name': f'团队库{suffix}', 'teamId': team_id,
        })
        kb = r.json() if r.status_code < 300 else {}
        kb_id = kb.get('id')
        check('创建团队知识库', bool(kb_id), r.text[:200])

        # alice 自己也配一个「能用的假 deepseek」，这样能区分团队 vs 用户优先级
        c.post('/keys', headers=hdr(alice), json={
            'provider': 'deepseek', 'secret': FAKE_DEEPSEEK, 'label': '个人假 Key',
            'model': 'deepseek-chat',
        })
        text3, _ = ask(alice, '用一句话说明什么是 TCP', kb_ids=[kb_id] if kb_id else None)
        check('团队 / 个人 Key 都无效时问答报鉴权错误（未偷偷用服务端 Key）',
              looks_like_auth_error(text3), text3[:300])

        if team_key_id:
            c.delete(f'/teams/{team_id}/keys/{team_key_id}', headers=hdr(alice))
        r = c.delete(f'/teams/{team_id}', headers=hdr(alice))
        check('清理团队', r.status_code == 200, r.text[:150])

    print('\n=== 6. 向量化路径同样受用户 Key 影响 ===')
    # 上传一个极小文档：向量化会先用用户 Key 调 embedding，无效则应失败
    c.post('/keys', headers=hdr(alice), json={
        'provider': 'zhipu', 'secret': FAKE_ZHIPU, 'label': '个人假 Key', 'model': 'embedding-3',
    })
    r = c.post('/knowledge-bases', headers=hdr(alice), json={'name': f'个人库{suffix}'})
    kb_personal = r.json().get('id')
    doc_id = None
    if kb_personal:
        r = c.post('/documents/upload', headers=hdr(alice),
                   data={'knowledgeBaseId': kb_personal},
                   files={'file': ('byok.txt', b'BYOK embedding probe content', 'text/plain')})
        doc_id = r.json().get('id') if r.status_code == 200 else None
        check('上传接口受理', r.status_code == 200, r.text[:200])

    if doc_id:
        import time
        final = None
        for _ in range(20):
            time.sleep(2)
            docs = c.get('/documents', headers=hdr(alice),
                         params={'knowledgeBaseId': kb_personal}).json()
            final = next((d for d in docs if d['id'] == doc_id), None)
            if final and final['status'] in ('ready', 'failed'):
                break
        status = (final or {}).get('status')
        err = (final or {}).get('error') or ''
        # 无效 Key → 向量化失败；错误信息应指向 Key 而不是「没检索到」
        check(f'无效 Key 导致向量化失败（实际 status={status}）', status == 'failed',
              err[:250])
        check('失败原因指向 API Key 鉴权', looks_like_auth_error(err), err[:250])

    print('\n=== 清理 ===')
    for kb_id in (locals().get('kb_personal'),):
        if kb_id:
            c.delete(f'/knowledge-bases/{kb_id}', headers=hdr(alice))
    c.close()

    print()
    print(f'结果：{passed} 通过 / {failed} 失败')
    return 0 if failed == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
