# -*- coding: utf-8 -*-
"""重建向量库后，把所有文档重新索引一遍。

为什么用脚本而不是调 API：
  reindex 接口按「文档归属」鉴权，demo 账号只能重索引自己的文档，
  而库里还有大量其他账号（历史上的测试账号）的文档。
  这里直接在服务端进程内跑 pipeline，逐条重建。

关键约束：
  - **必须只用一个事件循环**（asyncio.run 一次，内部循环处理全部文档），
    否则 SQLAlchemy 的异步引擎会跨 loop 复用连接而报错；
  - 运行时不要同时开后端，避免两个进程并发写 Chroma（正是之前损坏的原因）。

用法（在 server/ 目录、且后端已停止时执行）：
    .\\.venv\\Scripts\\python.exe _reindex_all.py
"""
from __future__ import annotations

import asyncio
import socket
import sys
import time
from pathlib import Path

sys.path.insert(0, '.')

import pymysql  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.services import pipeline  # noqa: E402


def _port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(('127.0.0.1', port)) == 0


def preflight(force: bool) -> bool:
    """执行前的安全检查，避免两个进程同时写坏向量库。"""
    host = (settings.CHROMA_HOST or '').strip()
    if host:
        print(f'Chroma 模式: 服务模式（HTTP {host}:{settings.CHROMA_PORT}）——多进程安全')
        if _port_in_use(settings.CHROMA_PORT):
            print('  ✅ Chroma 服务可达')
        else:
            print(f'  ❌ 连不上 Chroma 服务 {host}:{settings.CHROMA_PORT}')
            print('     请先在另一个终端运行： .\\start-chroma.ps1')
            return False
        return True

    print('Chroma 模式: 嵌入式（直接写本地 SQLite）')
    backend_up = _port_in_use(3000)
    if backend_up and not force:
        print('  ❌ 检测到后端正在 3000 端口运行。')
        print('     嵌入式模式下后端与脚本会同时写同一个数据库，')
        print('     会导致 chromadb compactor 永久卡死（正是本脚本存在的原因）。')
        print()
        print('     请二选一：')
        print('       1) 先停掉后端（Ctrl+C），再重跑本脚本；')
        print('       2) 或改用服务模式：先 .\\start-chroma.ps1，')
        print('          并在 .env 设置 CHROMA_HOST=127.0.0.1 / CHROMA_PORT=8000')
        print()
        print('     确实要强制继续：加 --force')
        return False
    if backend_up:
        print('  ⚠️ 后端正在运行，已按 --force 强制继续（有损坏风险）')
    return True


def load_documents() -> list[tuple[str, str, str]]:
    """返回 [(document_id, name, stored_path)]，只取磁盘文件仍存在的。"""
    conn = pymysql.connect(
        host='127.0.0.1', user='root', password='root',
        database='chuangzhibei', charset='utf8mb4',
    )
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT id, name, stored_path FROM documents ORDER BY uploaded_at')
            rows = cur.fetchall()
        existing = []
        missing = []
        for doc_id, name, stored_path in rows:
            if not stored_path:
                missing.append((doc_id, name, '无路径'))
                continue
            path = Path(stored_path)
            if not path.is_absolute():
                path = Path.cwd() / path
            if path.exists():
                existing.append((doc_id, name, str(path)))
            else:
                missing.append((doc_id, name, '文件不存在'))
        return existing, missing  # type: ignore[return-value]
    finally:
        conn.close()


async def run_all(docs: list[tuple[str, str, str]]) -> None:
    total = len(docs)
    ok = failed = 0
    started = time.time()

    for index, (doc_id, name, _path) in enumerate(docs, 1):
        prefix = f'[{index}/{total}]'
        try:
            result = await pipeline._process(doc_id, reindex=True)
            if result.get('ok'):
                ok += 1
                print(f'  {prefix} OK   {name[:40]:<42} chunks={result.get("chunks")}')
            else:
                failed += 1
                err = str(result.get('error', ''))[:100].replace('\n', ' ')
                print(f'  {prefix} FAIL {name[:40]:<42} {err}')
        except Exception as exc:  # 单条失败不影响整体
            failed += 1
            print(f'  {prefix} EXC  {name[:40]:<42} {type(exc).__name__}: {str(exc)[:80]}')

    elapsed = time.time() - started
    print()
    print(f'完成：成功 {ok}，失败 {failed}，用时 {elapsed:.0f} 秒')


def main() -> int:
    force = '--force' in sys.argv

    print('=' * 60)
    print(' 重建向量库 / 重新索引全部文档')
    print('=' * 60)
    if not preflight(force):
        return 2

    docs, missing = load_documents()
    print()
    print(f'待重建文档: {len(docs)} 个')
    if missing:
        print(f'跳过（文件缺失）: {len(missing)} 个')
        for doc_id, name, why in missing[:5]:
            print(f'  - {name[:50]}  ({why})')
    if not docs:
        print('没有可重建的文档')
        return 1
    print()
    asyncio.run(run_all(docs))
    return 0


if __name__ == '__main__':
    sys.exit(main())
