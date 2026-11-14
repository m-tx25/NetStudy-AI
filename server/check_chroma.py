# -*- coding: utf-8 -*-
"""向量库体检：把「连接失败 / 索引损坏 / 空库」三种情况区分开。

为什么需要这个脚本：这三种情况的报错都长得像「连接 Chroma 服务失败」，
但处理方式完全不同 ——
  - 连不上      → 服务没起 / 端口被占 / 被系统代理劫持
  - 索引损坏    → HNSW 索引文件缺失，必须重建向量库（写进去也没用）
  - 空库        → 只是没索引，跑 reindex 即可，**不需要删库**

误判代价很大：把「空库」当「损坏」去删库重建，会白花一遍 embedding 费用。

用法：
    .\\.venv\\Scripts\\python.exe check_chroma.py
"""
from __future__ import annotations

import pathlib
import sqlite3
import sys

# 本机请求绕过系统代理（Clash 会把 127.0.0.1 也代理掉，表现为 502）
import os

os.environ['NO_PROXY'] = ','.join(
    filter(None, [os.environ.get('NO_PROXY', ''), '127.0.0.1', 'localhost'])
)

from app.core.config import settings  # noqa: E402

# HNSW 索引由 4 个文件组成；缺任何一个，Chroma 加载时都会报
# "Error loading hnsw index"。实测损坏时目录里只剩 index_metadata.pickle。
HNSW_FILES = ("header.bin", "data_level0.bin", "length.bin", "link_lists.bin")


def data_dir() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parent / "data" / "chroma_db"


def check_files() -> tuple[bool, list[str]]:
    """检查本地 segment 目录里的 HNSW 文件是否齐全。"""
    root = data_dir() / "chroma.sqlite3"
    if not root.exists():
        return False, ["数据库文件不存在（还没建过库）"]

    problems: list[str] = []
    segment_dirs = [p for p in data_dir().iterdir() if p.is_dir() and len(p.name) == 36]
    if not segment_dirs:
        return False, ["没有 segment 目录（库是空的，需要 reindex）"]

    for seg in segment_dirs:
        present = {p.name for p in seg.iterdir() if p.is_file()}
        missing = [name for name in HNSW_FILES if name not in present]
        if missing:
            problems.append(f"segment {seg.name[:8]} 缺少 {', '.join(missing)}")
    return not problems, problems


def check_sqlite() -> tuple[int, int]:
    """返回（集合数, 向量行数）。向量行数 > 0 但索引文件缺失 = 索引损坏。"""
    db = data_dir() / "chroma.sqlite3"
    if not db.exists():
        return 0, 0
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        cur = con.cursor()
        cur.execute("SELECT COUNT(*) FROM collections")
        collections = cur.fetchone()[0]
        try:
            cur.execute("SELECT COUNT(*) FROM embeddings")
            embeddings = cur.fetchone()[0]
        except sqlite3.Error:
            embeddings = -1
        con.close()
        return collections, embeddings
    except sqlite3.Error:
        return -1, -1


def check_service() -> tuple[bool, str]:
    """能否连上 Chroma 服务，以及集合里有多少条向量。"""
    try:
        from app.services import vectorstore

        client = vectorstore.get_client()
        name = vectorstore.collection_name()
        try:
            collection = client.get_collection(name)
            return True, f"集合 {name} 可读，共 {collection.count()} 条向量"
        except Exception as exc:  # 集合不存在或索引损坏
            return True, f"服务在，但集合 {name} 打不开：{type(exc).__name__}: {str(exc)[:120]}"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {str(exc)[:160]}"


def main() -> int:
    print("=" * 60)
    print(" 向量库体检")
    print("=" * 60)
    print(f"  数据目录：{data_dir()}")
    print(f"  连接目标：{settings.CHROMA_HOST or '(嵌入式)'}:{settings.CHROMA_PORT}")
    print()

    files_ok, problems = check_files()
    collections, embeddings = check_sqlite()
    service_ok, service_msg = check_service()

    print(f"  服务：[{'OK' if service_ok else '!!'}] {service_msg}")
    print(f"  sqlite：{collections} 个集合，{embeddings} 条向量记录")
    print(f"  索引文件：[{'OK' if files_ok else '!!'}] " + ('完整' if files_ok else '；'.join(problems)))
    print()

    if not service_ok:
        print("  诊断：连不上 Chroma 服务。")
        print("  处理：")
        print("    1) 确认服务在跑：netstat -ano | findstr :8000")
        print("    2) 若后端报 502，是系统代理劫持（代码已自动绕过，需重启后端）")
        print("    3) 重启：cd server && .\\dev.cmd")
        return 1

    if files_ok:
        if embeddings > 0:
            print("  诊断：一切正常。")
            return 0
        print("  诊断：索引文件在，但没有任何向量（空库）。")
        print("  处理：.\\dev.cmd --reindex   ← 不要删库，重索引即可")
        return 1

    # 索引文件缺失：区分「真有数据却坏了」和「本来就是空的」
    if embeddings > 0:
        print("  诊断：**索引损坏**。sqlite 里有向量记录，但 HNSW 索引文件不见了。")
        print("  这说明上次写入/压缩过程被强行打断（例如 taskkill /F 杀掉 Chroma），")
        print("  或有两个进程同时写同一个目录。写进去也不会恢复，必须重建。")
        print("  处理：.\\dev.cmd --rebuild --reindex")
        return 2

    print("  诊断：库是空的（既没向量也没索引）。")
    print("  处理：.\\dev.cmd --reindex")
    return 1


if __name__ == "__main__":
    sys.exit(main())
