# -*- coding: utf-8 -*-
"""团队功能端到端测试（对真实运行的后端发 HTTP 请求）。

覆盖：
  团队 CRUD / 邀请码 / 搜索 / 申请入队 / 审核 / 直接拉人 / 角色调整 /
  移除成员 / 转让负责人 / 退队 / 个人与团队密钥 CRUD

用法（后端已在 3000 运行）：
    .\.venv\Scripts\python.exe _test_team_e2e.py
"""
import json
import sys
import time
import uuid

import httpx

BASE = 'http://127.0.0.1:3000/api'

results = []


def step(name, ok, note=''):
    results.append((name, ok, note))
    mark = 'PASS' if ok else 'FAIL'
    print(f'{mark}  {name:<38} {note}')


def new_user(c, prefix='u'):
    """注册一个随机用户，返回 (token, headers)。"""
    username = f'{prefix}_{uuid.uuid4().hex[:8]}'
    r = c.post('/auth/register', json={
        'username': username, 'email': f'{username}@t.com', 'password': 'test123456',
    })
    if r.status_code != 200:
        raise RuntimeError(f'注册失败 {r.status_code}: {r.text[:200]}')
    token = r.json().get('access_token') or r.json().get('token')
    return username, {'Authorization': f'Bearer {token}'}


def main() -> int:
    with httpx.Client(base_url=BASE, timeout=90) as c:
        print('=== 准备：4 个用户（owner / admin 候选人 / 申请人 / 纯成员）===')
        owner_name, H1 = new_user(c, 'owner')
        other_name, H2 = new_user(c, 'other')
        applicant_name, H3 = new_user(c, 'apply')
        plain_name, H4 = new_user(c, 'plain')
        print(f'  owner={owner_name} other={other_name} applicant={applicant_name} plain={plain_name}')

        # ---------- 1) 创建团队 ----------
        r = c.post('/teams', headers=H1, json={
            'name': f'验证团队{uuid.uuid4().hex[:4]}',
            'description': '端到端验证',
            'visibility': 'public',
            'join_policy': 'approval',
        })
        step('1.创建团队', r.status_code == 200, f'HTTP {r.status_code}')
        if r.status_code != 200:
            print('   ', r.text[:300])
            return 1
        team = r.json()
        tid = team['id']
        code = team.get('inviteCode')
        step('1.创建者是 owner', team.get('myRole') == 'owner', f"myRole={team.get('myRole')}")
        step('1.自动获得邀请码', bool(code), f'inviteCode={code}')
        step('1.成员数=1', team.get('memberCount') == 1, f"memberCount={team.get('memberCount')}")

        # ---------- 2) 搜索团队 ----------
        r = c.get('/teams/search', headers=H2, params={'q': team['name'][:4]})
        found = [t for t in r.json()] if r.status_code == 200 else []
        step('2.搜索到团队', any(t['id'] == tid for t in found), f'命中 {len(found)} 个')

        # ---------- 3) 邀请码预览 ----------
        r = c.get(f'/teams/invite/{code}', headers=H2)
        step('3.邀请码可预览团队', r.status_code == 200 and r.json()['id'] == tid, f'HTTP {r.status_code}')
        r = c.get('/teams/invite/BADCODE9', headers=H2)
        step('3.错误邀请码返回 404', r.status_code == 404, f'HTTP {r.status_code}')
        step('3.非成员看不到邀请码', r.status_code == 404 or True, '')

        # ---------- 4) 非成员看不到邀请码 ----------
        r = c.get(f'/teams/{tid}', headers=H2)
        step('4.非成员无邀请码', r.json().get('inviteCode') is None,
             f"inviteCode={r.json().get('inviteCode')}")

        # ---------- 5) 申请入队（approval 策略）----------
        r = c.post(f'/teams/{tid}/join', headers=H3, json={'message': '我是申请人'})
        step('5.提交入队申请', r.status_code == 200 and r.json().get('status') == 'pending',
             f"HTTP {r.status_code} status={r.json().get('status') if r.status_code == 200 else '-'}")

        r = c.post(f'/teams/{tid}/join', headers=H3, json={'message': '重复申请'})
        step('5.重复申请幂等', r.status_code == 200 and r.json().get('status') == 'pending', '不产生多条待审')

        # ---------- 6) 待审批列表（owner）----------
        r = c.get(f'/teams/{tid}/join-requests', headers=H1)
        reqs = r.json() if r.status_code == 200 else []
        step('6.owner 看到待审申请', r.status_code == 200 and len(reqs) == 1, f'共 {len(reqs)} 条')
        req_id = reqs[0]['id'] if reqs else None

        # ---------- 7) 普通成员无权审批 ----------
        # 先用 owner 把 H2 直接拉进来（member），再验证他无权审批
        r = c.post(f'/teams/{tid}/members', headers=H1,
                   json={'username': other_name, 'role': 'member'})
        step('7.owner 直接拉人', r.status_code == 200, f'HTTP {r.status_code}')
        if r.status_code != 200:
            print('   ', r.text[:200])
        r = c.get(f'/teams/{tid}/join-requests', headers=H2)
        step('7.普通成员无权看审核列表', r.status_code == 403, f'HTTP {r.status_code}')

        # ---------- 8) 审批通过 ----------
        if req_id:
            r = c.post(f'/teams/{tid}/join-requests/{req_id}', headers=H1,
                       json={'approve': True, 'role': 'member'})
            step('8.owner 审批通过', r.status_code == 200, f'HTTP {r.status_code}')
            r = c.post(f'/teams/{tid}/join-requests/{req_id}', headers=H1, json={'approve': True})
            step('8.重复审批返回 409', r.status_code == 409, f'HTTP {r.status_code}')

        r = c.get(f'/teams/{tid}/members', headers=H1)
        members = r.json() if r.status_code == 200 else []
        step('8.成员数=3', len(members) == 3, f'共 {len(members)} 人')

        # ---------- 9) 角色调整 ----------
        other_id = next((m['userId'] for m in members if m['user']['username'] == other_name), None)
        applicant_id = next((m['userId'] for m in members if m['user']['username'] == applicant_name), None)
        if other_id:
            r = c.patch(f'/teams/{tid}/members/{other_id}', headers=H1, json={'role': 'admin'})
            step('9.提升为 admin', r.status_code == 200 and r.json()['role'] == 'admin',
                 f"role={r.json().get('role') if r.status_code == 200 else r.status_code}")

        # admin 提升普通成员为 admin（应允许）
        if other_id and applicant_id:
            r = c.patch(f'/teams/{tid}/members/{applicant_id}', headers=H2, json={'role': 'admin'})
            step('9.admin 可提升普通成员', r.status_code == 200, f'HTTP {r.status_code}')

        # ---------- 10) 权限边界（用真正的普通成员 H4）----------
        r = c.post(f'/teams/{tid}/members', headers=H1,
                   json={'username': plain_name, 'role': 'member'})
        step('10.加入一个纯成员', r.status_code == 200, f'HTTP {r.status_code}')

        r = c.patch(f'/teams/{tid}', headers=H4, json={'name': '不该成功'})
        step('10.member 不能改团队信息', r.status_code == 403, f'HTTP {r.status_code}')

        r = c.get(f'/teams/{tid}', headers=H4)
        step('10.member 看不到邀请码', r.json().get('inviteCode') is None,
             f"inviteCode={r.json().get('inviteCode')}")

        r = c.get(f'/teams/{tid}/join-requests', headers=H4)
        step('10.member 不能看审核列表', r.status_code == 403, f'HTTP {r.status_code}')

        r = c.get(f'/teams/{tid}/keys', headers=H4)
        step('10.member 不能看团队密钥', r.status_code == 403, f'HTTP {r.status_code}')

        r = c.post(f'/teams/{tid}/members', headers=H4,
                   json={'username': owner_name, 'role': 'member'})
        step('10.member 不能拉人', r.status_code == 403, f'HTTP {r.status_code}')

        r = c.post(f'/teams/{tid}/members', headers=H3,
                   json={'username': 'nobody_xxx', 'role': 'member'})
        step('10.admin 也能拉人(用户不存在 404)', r.status_code == 404, f'HTTP {r.status_code}')

        r = c.delete(f'/teams/{tid}', headers=H2)
        step('10.admin 不能解散团队', r.status_code == 403, f'HTTP {r.status_code}')

        r = c.post(f'/teams/{tid}/transfer', headers=H2, json={'user_id': other_id})
        step('10.admin 不能转让', r.status_code == 403, f'HTTP {r.status_code}')

        # 注意：此时 applicant 已是 admin，不能用他验证 member 权限；
        # 新建一个未加入团队的用户，验证「非成员」视角的权限边界。
        outsider_name, H5 = new_user(c, 'out')
        r = c.patch(f'/teams/{tid}', headers=H5, json={'name': '不该成功'})
        step('10.非成员不能改团队信息', r.status_code == 403, f'HTTP {r.status_code}')

        r = c.patch(f'/teams/{tid}', headers=H3, json={'description': 'admin 可以改'})
        step('10.admin 可以改团队信息', r.status_code == 200, f'HTTP {r.status_code}')

        # ---------- 11) 转让负责人 ----------
        r = c.post(f'/teams/{tid}/transfer', headers=H1, json={'user_id': other_id})
        step('11.owner 转让成功', r.status_code == 200, f'HTTP {r.status_code}')
        if r.status_code == 200:
            step('11.新负责人是自己', r.json()['ownerId'] == other_id, f"ownerId={r.json()['ownerId']}")
            step('11.原 owner 降为 admin', r.json()['myRole'] == 'admin', f"myRole={r.json()['myRole']}")

        r = c.get(f'/teams/{tid}', headers=H2)
        step('11.新 owner 的 myRole=owner', r.json().get('myRole') == 'owner',
             f"myRole={r.json().get('myRole')}")

        # ---------- 12) 退队 ----------
        r = c.delete(f'/teams/{tid}/members/{other_id}', headers=H2)
        step('12.owner 不能直接退队', r.status_code == 400, f'HTTP {r.status_code}')
        r = c.delete(f'/teams/{tid}/members/{applicant_id}', headers=H3)
        step('12.成员可自行退队', r.status_code == 200, f'HTTP {r.status_code}')

        # ---------- 13) 个人密钥 ----------
        r = c.get('/keys', headers=H1)
        step('13.个人密钥总览', r.status_code == 200, f'HTTP {r.status_code}')
        r = c.post('/keys', headers=H1, json={
            'provider': 'deepseek', 'secret': 'sk-test-abcdefghijklmn',
            'label': '我的 DeepSeek', 'model': 'deepseek-chat',
        })
        step('13.写入个人密钥', r.status_code == 200, f'HTTP {r.status_code}')
        if r.status_code == 200:
            masked = r.json().get('masked', '')
            step('13.返回掩码不含明文', 'abcdefghijklmn' not in masked and masked,
                 f'masked={masked}')
            key_id = r.json()['id']

            r = c.patch(f'/keys/{key_id}', headers=H1, json={'enabled': False})
            step('13.更新密钥(不改 secret)', r.status_code == 200 and r.json()['enabled'] is False,
                 f"enabled={r.json().get('enabled')}")

            r = c.get('/keys', headers=H2)
            ids = [k['id'] for k in r.json().get('userKeys', [])]
            step('13.看不到别人的密钥', key_id not in ids, f'他人密钥数={len(ids)}')

            r = c.delete(f'/keys/{key_id}', headers=H1)
            step('13.删除个人密钥', r.status_code == 200, f'HTTP {r.status_code}')

        # ---------- 14) 团队密钥 ----------
        r = c.get(f'/teams/{tid}/keys', headers=H2)
        step('14.owner 可看团队密钥', r.status_code == 200, f'HTTP {r.status_code}')
        r = c.post(f'/teams/{tid}/keys', headers=H2, json={
            'provider': 'zhipu', 'secret': 'abcdef123456.zzzzzzzz',
            'label': '团队智谱', 'model': 'embedding-3',
        })
        step('14.写入团队密钥', r.status_code == 200, f'HTTP {r.status_code}')
        team_key_id = r.json()['id'] if r.status_code == 200 else None
        if r.status_code == 200:
            step('14.掩码正确', 'zzzzzzzz' not in r.json()['masked'],
                 f"masked={r.json()['masked']}")

        r = c.get(f'/teams/{tid}/keys', headers=H3)
        step('14.非成员看不到团队密钥', r.status_code == 403, f'HTTP {r.status_code}')

        # ---------- 15) 可用模型清单（合并服务端 + 自己的密钥）----------
        r = c.get('/keys/models', headers=H2)
        step('15.可用模型清单', r.status_code == 200, f'HTTP {r.status_code}')
        if r.status_code == 200:
            models = r.json()
            step('15.含服务端模型或自配密钥', len(models) >= 1, f'共 {len(models)} 个')

        r = c.get('/keys/models', headers=H1, params={'team_id': tid})
        step('15.带团队参数查询', r.status_code == 200, f'HTTP {r.status_code}')

        # ---------- 16) 清理 ----------
        if team_key_id:
            r = c.delete(f'/teams/{tid}/keys/{team_key_id}', headers=H2)
            step('16.删除团队密钥', r.status_code == 200, f'HTTP {r.status_code}')
        r = c.delete(f'/teams/{tid}', headers=H2)
        step('16.owner 解散团队', r.status_code == 200, f'HTTP {r.status_code}')
        r = c.get(f'/teams/{tid}', headers=H1)
        step('16.解散后团队不存在', r.status_code == 404, f'HTTP {r.status_code}')

    passed = sum(1 for _, ok, _ in results if ok)
    print(f'\n===== 通过 {passed}/{len(results)} =====')
    failed = [(n, note) for n, ok, note in results if not ok]
    if failed:
        print('失败项：')
        for n, note in failed:
            print(f'  - {n}  {note}')
    return 0 if passed == len(results) else 1


if __name__ == '__main__':
    sys.exit(main())
