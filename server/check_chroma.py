# -*- coding: utf-8 -*-
"""向量库体检：区分「连不上 / 索引损坏 / 空库」三种情况。

为什么需要：这三种情况的报错都长得像「连接 Chroma 服务失败」，但处理方式完全不同 ——
  - 连不上      → 服务没起 / 端口被占 / 被系统代理劫持
  - 索引损坏    → 集合打不开且没有索引文件，必须重建（写进去也没用）
  - 空库        → 集合能打开但 0 条，跑 reindex 即可，**不需要删库**

**判据说明（踩过坑）**：HNSW 的 *.bin 文件是**延迟落盘**的 ——
刚重建完索引时目录里可能只有 `index_metadata.pickle`，
但集合读得出来、数量对得上，这时候库是健康的。
所以判据顺序是「集合能不能打开 + 条数是否 > 0」优先，文件是否存在只作参考。

用法：
    .\\.venv\\Scripts\\python.exe check_chroma.py
"""
from __future__ import annotations

import os
import pathlib
import sqlite3
import sys

# 本机请求绕过系统代理（Clash 会把 127.0.0.1 也代理掉，表现为 502）
os.environ['NO_PROXY'] = ','.join(
    filter(None, [os.environ.get('NO_PROXY', ''), '127.0.0.1', 'localhost'])
)

from app.core.config import settings  # noqa: E402

HNSW_FILES = ("header.bin", "data_level0.bin", "length.bin", "link_lists.bin")


def data_dir() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parent / "data" / "chroma_db"


def segment_report() -> list[str]:
    """每个 segment 目录里缺哪些 HNSW 文件（只作参考信息）。"""
    problems: list[str] = []
    root = data_dir()
    if not root.exists():
        return ["数据目录不存在"]
    for seg in root.iterdir():
        if not seg.is_dir() or len(seg.name) != 36:
            continue
        present = {p.name for p in seg.iterdir() if p.is_file()}
        missing = [name for name in HNSW_FILES if name not in present]
        if missing:
            problems.append(f"segment {seg.name[:8]} 缺少 {', '.join(missing)}")
    return problems


def sqlite_counts() -> tuple[int, int]:
    """返回（集合数, 向量行数）。-1 表示读不出来。"""
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


def service_status() -> tuple[bool, bool, int, str]:
    """返回（服务可达, 集合可读, 向量条数, 说明）。"""
    try:
        from app.services import vectorstore

        client = vectorstore.get_client()
        name = vectorstore.collection_name()
    except Exception as exc:
        return False, False, 0, f"{type(exc).__name__}: {str(exc)[:150]}"

    try:
        collection = client.get_collection(name)
        count = collection.count()
        return True, True, count, f"集合 {name} 可读，共 {count} 条向量"
    except Exception as exc:
        return True, False, 0, f"服务在，但集合 {name} 打不开：{type(exc).__name__}: {str(exc)[:120]}"


def main() -> int:
    print("=" * 60)
    print(" 向量库体检")
    print("=" * 60)
    print(f"  数据目录：{data_dir()}")
    print(f"  连接目标：{settings.CHROMA_HOST or '(嵌入式)'}:{settings.CHROMA_PORT}")
    print()

    service_ok, collection_ok, count, message = service_status()
    collections, embeddings = sqlite_counts()
    segments = segment_report()

    print(f"  服务：[{'OK' if service_ok else '!!'}] {message}")
    print(f"  sqlite：{collections} 个集合，{embeddings} 条向量记录")
    if segments:
        print(f"  索引文件：[信息] {'；'.join(segments)}（可能只是尚未落盘）")
    else:
        print("  索引文件：[OK] 齐全")
    print()

    if not service_ok:
        print("  诊断：连不上 Chroma 服务。")
        print("  处理：")
        print("    1) 确认服务在跑：netstat -ano | findstr :8000")
        print("    2) 若后端日志有 502，是系统代理劫持（代码已自动绕过，需重启后端）")
        print("    3) 重启：cd server && .\\dev.cmd")
        return 1

    if collection_ok:
        if count > 0:
            print(f"  诊断：一切正常（{count} 条向量可读）。")
            if segments:
                print("  说明：索引文件尚未落盘属正常现象 —— Chroma 在写入/退出时才写 *.bin，")
                print("        只要集合读得出、条数对，就不算损坏。")
            return 0
        print("  诊断：集合能打开但没有向量（空库）。")
        print("  处理：.\\dev.cmd --reindex   ← 不要删库，重索引即可")
        return 1

    # 服务在，但集合打不开
    if embeddings > 0:
        print("  诊断：**索引损坏**。sqlite 里有向量记录，但集合打不开。")
        print("  常见原因：写入过程中进程被强杀（taskkill /F）、或两个进程同时写同一目录。")
        print("  处理：")
        print("    .\\dev.cmd --restore            有快照时（几秒，零费用）")
        print("    .\\dev.cmd --rebuild --reindex  没有快照时")
        return 2

    print("  诊断：库是空的（既没向量也没索引）。")
    print("  处理：.\\dev.cmd --reindex")
    return 1


if __name__ == "__main__":
    sys.exit(main())
