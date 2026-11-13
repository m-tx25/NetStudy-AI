# -*- coding: utf-8 -*-
"""清理自动化测试留下的账号与团队（保留真实账号）。

背景：开发期跑了大量 e2e / 验收脚本，库里堆了 170+ 测试账号与 11 个测试团队，
界面上「发现团队」「我的团队」都被污染。本脚本按**显式保留名单**清理其余数据。

保留名单（改这里即可）：
    用户：demo、test
    团队：team_u3rs1sn52fd7（名为「1」，demo 与 test 在用）

清理内容（按依赖顺序）：
    ChromaDB 向量 → 磁盘文件 → message_sources → messages
    → conversation_knowledge_bases → conversations → documents
    → knowledge_bases → api_keys → team_join_requests → team_members
    → teams → users

用法：
    .\\.venv\\Scripts\\python.exe cleanup_test_data.py            # 只统计，不删
    .\\.venv\\Scripts\\python.exe cleanup_test_data.py --yes      # 真正执行

注意：
  - 执行前请先 mysqldump 备份（脚本会在结束时提示备份文件名无关，备份请自行完成）
  - 需要后端不是必须的，但会用 Chroma 服务（HTTP）清理向量，因此
    start-chroma 必须先跑着；否则会跳过向量清理并给出警告。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pymysql

sys.path.insert(0, '.')

from app.core.config import settings  # noqa: E402

DB = dict(host='127.0.0.1', user='root', password='root',
          database='chuangzhibei', charset='utf8mb4')

# ------------------------------------------------------------------ 保留名单
KEEP_USERS = ('demo', 'test')
KEEP_TEAMS = ('team_u3rs1sn52fd7',)

CHUNK = 500


def chunks(seq, size=CHUNK):
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


def placeholders(seq):
    return ','.join(['%s'] * len(seq))


def main() -> int:
    execute = '--yes' in sys.argv

    conn = pymysql.connect(**DB)
    conn.autocommit(False)
    cur = conn.cursor()

    # ---------------------------------------------------------- 收集范围
    cur.execute('SELECT id, username FROM users')
    all_users = cur.fetchall()
    doomed_users = [(uid, name) for uid, name in all_users if name not in KEEP_USERS]

    cur.execute('SELECT id, name FROM teams')
    all_teams = cur.fetchall()
    doomed_teams = [(tid, name) for tid, name in all_teams if tid not in KEEP_TEAMS]

    user_ids = [u for u, _ in doomed_users]
    team_ids = [t for t, _ in doomed_teams]

    kb_ids: list[str] = []
    if user_ids:
        for part in chunks(user_ids):
            cur.execute(
                f'SELECT id FROM knowledge_bases '
                f"WHERE owner_type='user' AND owner_id IN ({placeholders(part)})",
                part,
            )
            kb_ids += [r[0] for r in cur.fetchall()]
    if team_ids:
        for part in chunks(team_ids):
            cur.execute(
                f'SELECT id FROM knowledge_bases '
                f"WHERE owner_type='team' AND owner_id IN ({placeholders(part)})",
                part,
            )
            kb_ids += [r[0] for r in cur.fetchall()]

    doc_rows: list[tuple[str, str]] = []
    if kb_ids:
        for part in chunks(kb_ids):
            cur.execute(
                f'SELECT id, stored_path FROM documents '
                f'WHERE knowledge_base_id IN ({placeholders(part)})',
                part,
            )
            doc_rows += [(r[0], r[1] or '') for r in cur.fetchall()]

    conv_ids: list[str] = []
    if user_ids:
        for part in chunks(user_ids):
            # conversations 的归属列是 owner_id，不是 user_id
            cur.execute(
                f'SELECT id FROM conversations WHERE owner_id IN ({placeholders(part)})',
                part,
            )
            conv_ids += [r[0] for r in cur.fetchall()]

    def count(sql: str, args) -> int:
        cur.execute(sql, args)
        return cur.fetchone()[0]

    stats = {
        '用户': len(doomed_users),
        '团队': len(doomed_teams),
        '知识库': len(kb_ids),
        '文档': len(doc_rows),
        '会话': len(conv_ids),
    }

    print('=' * 62)
    print('  清理测试数据')
    print('=' * 62)
    print(f'  保留用户: {KEEP_USERS}')
    print(f'  保留团队: {KEEP_TEAMS}')
    print('  将删除:')
    for k, v in stats.items():
        print(f'    {k:6} {v}')
    print()
    print(f'  Chroma 目标: {settings.CHROMA_HOST or "嵌入式"} '
          f'{":" + str(settings.CHROMA_PORT) if settings.CHROMA_HOST else ""}')

    if not execute:
        print()
        print('  [dry-run] 未做任何修改。确认无误后加 --yes 执行。')
        conn.close()
        return 0

    # ---------------------------------------------------------- 清向量
    print()
    print('--- 清理 ChromaDB 向量 ---')
    vector_ok = True
    try:
        from app.services import vectorstore

        removed_total = 0
        for kb_id in kb_ids:
            try:
                removed_total += vectorstore.delete_knowledge_base(kb_id)
            except Exception as exc:  # 单库失败不影响整体
                vector_ok = False
                print(f'  [WARN] 删除 {kb_id} 向量失败: {type(exc).__name__}: {str(exc)[:120]}')
        print(f'  已删除向量 {removed_total} 条（覆盖 {len(kb_ids)} 个知识库）')
    except Exception as exc:
        vector_ok = False
        print(f'  [WARN] 向量清理整体失败: {type(exc).__name__}: {str(exc)[:160]}')
        print('         请先启动 Chroma 服务（.\\start-chroma.cmd），再单独重跑本脚本')

    # ---------------------------------------------------------- 删文件
    print()
    print('--- 删除上传文件 ---')
    file_count = 0
    for _doc_id, stored in doc_rows:
        if not stored:
            continue
        path = Path(stored)
        if not path.is_absolute():
            path = Path.cwd() / path
        try:
            if path.exists():
                path.unlink()
                file_count += 1
        except OSError as exc:
            print(f'  [WARN] 删除文件失败 {path}: {exc}')
    print(f'  已删除文件 {file_count} 个')

    # ---------------------------------------------------------- 删数据
    print()
    print('--- 删除数据库记录 ---')

    def run(sql: str, args) -> int:
        cur.execute(sql, args)
        return cur.rowcount

    deleted = {}
    try:
        if conv_ids:
            n = 0
            for part in chunks(conv_ids):
                n += run(
                    f'DELETE FROM message_sources WHERE message_id IN '
                    f'(SELECT id FROM messages WHERE conversation_id IN ({placeholders(part)}))',
                    part,
                )
            deleted['message_sources'] = n

            n = 0
            for part in chunks(conv_ids):
                n += run(
                    f'DELETE FROM messages WHERE conversation_id IN ({placeholders(part)})',
                    part,
                )
            deleted['messages'] = n

            n = 0
            for part in chunks(conv_ids):
                n += run(
                    f'DELETE FROM conversation_knowledge_bases '
                    f'WHERE conversation_id IN ({placeholders(part)})',
                    part,
                )
            deleted['conversation_knowledge_bases'] = n

            n = 0
            for part in chunks(conv_ids):
                n += run(
                    f'DELETE FROM conversations WHERE id IN ({placeholders(part)})',
                    part,
                )
            deleted['conversations'] = n

        if doc_rows:
            ids = [d for d, _ in doc_rows]
            n = 0
            for part in chunks(ids):
                n += run(f'DELETE FROM documents WHERE id IN ({placeholders(part)})', part)
            deleted['documents'] = n

        if kb_ids:
            n = 0
            for part in chunks(kb_ids):
                n += run(
                    f'DELETE FROM knowledge_bases WHERE id IN ({placeholders(part)})', part
                )
            deleted['knowledge_bases'] = n

        # api_keys 用 scope_type/scope_id 表达归属，不能按 user_id/team_id 删
        if user_ids or team_ids:
            conds, args = [], []
            for part in chunks(user_ids or []):
                conds.append(f"(scope_type='user' AND scope_id IN ({placeholders(part)}))")
                args += list(part)
            for part in chunks(team_ids or []):
                conds.append(f"(scope_type='team' AND scope_id IN ({placeholders(part)}))")
                args += list(part)
            if conds:
                deleted['api_keys'] = run(
                    f"DELETE FROM api_keys WHERE {' OR '.join(conds)}", args
                )

        # 成员关系与入队申请：按 team_id 或 user_id
        if user_ids or team_ids:
            conds, args = [], []
            if user_ids:
                for part in chunks(user_ids):
                    conds.append(f'user_id IN ({placeholders(part)})')
                    args += list(part)
            if team_ids:
                for part in chunks(team_ids):
                    conds.append(f'team_id IN ({placeholders(part)})')
                    args += list(part)
            where = ' OR '.join(conds)
            deleted['team_members'] = run(f'DELETE FROM team_members WHERE {where}', args)

            conds, args = [], []
            if team_ids:
                for part in chunks(team_ids):
                    conds.append(f'team_id IN ({placeholders(part)})')
                    args += list(part)
            if user_ids:
                for part in chunks(user_ids):
                    conds.append(f'user_id IN ({placeholders(part)})')
                    args += list(part)
            where = ' OR '.join(conds)
            deleted['team_join_requests'] = run(
                f'DELETE FROM team_join_requests WHERE {where}', args
            )

        if team_ids:
            n = 0
            for part in chunks(team_ids):
                n += run(f'DELETE FROM teams WHERE id IN ({placeholders(part)})', part)
            deleted['teams'] = n

        if user_ids:
            n = 0
            for part in chunks(user_ids):
                n += run(f'DELETE FROM users WHERE id IN ({placeholders(part)})', part)
            deleted['users'] = n

        conn.commit()
    except Exception as exc:
        conn.rollback()
        print(f'  [ERROR] 删除失败已回滚: {type(exc).__name__}: {exc}')
        conn.close()
        return 1

    print()
    for table, n in deleted.items():
        print(f'    {table:28} -{n}')

    # ---------------------------------------------------------- 收尾统计
    print()
    print('--- 清理后剩余 ---')
    for table in ('users', 'teams', 'knowledge_bases', 'documents',
                  'conversations', 'messages', 'api_keys', 'team_members'):
        cur.execute(f'SELECT COUNT(*) FROM `{table}`')
        print(f'    {table:20} {cur.fetchone()[0]}')

    conn.close()
    print()
    if not vector_ok:
        print('  ⚠️ 向量清理未完全成功，请启动 Chroma 后重跑本脚本（此时数据已删，'
              '重跑会因没有对应知识库而跳过，需手动清空 chroma_db 再重建索引）')
    print('  完成')
    return 0


if __name__ == '__main__':
    sys.exit(main())
