# -*- coding: utf-8 -*-
"""修复「索引文件缺失」导致的 Error loading hnsw index —— 不需要重建向量库。

## 原理

Chroma 1.x 把向量存在 ``chroma.sqlite3`` 的 ``embeddings`` 表里，
HNSW 图另外存成每个 segment 目录下的 ``*.bin`` 文件，
再由 ``index_metadata.pickle`` 记录「这份索引包含哪些文件、多少条」。

强制结束进程（``taskkill /F``）时，pickle 写了、``*.bin`` 没写 ——
于是元数据声称「有索引」，实际文件不存在，启动时加载失败，报
``Error loading hnsw index``。

**关键点**：向量本身还在 sqlite 里。把那个半截的 ``index_metadata.pickle``
挪走，Chroma 会认为「这个 segment 还没有索引」，于是从 sqlite **重新构建**，
数据一条不丢、也不用再调 embedding 接口（实测 2850 条秒级恢复）。

## 用法

    .\\.venv\\Scripts\\python.exe repair_chroma.py

脚本自己会：停 Chroma → 挪走半截 pickle → 重新启动 → 验证条数。
"""
from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys
import time

os.environ['NO_PROXY'] = ','.join(
    filter(None, [os.environ.get('NO_PROXY', ''), '127.0.0.1', 'localhost'])
)

ROOT = pathlib.Path(__file__).resolve().parent
DATA = ROOT / "data" / "chroma_db"
PICKLE = "index_metadata.pickle"
PORT = 8000

HNSW_FILES = ("header.bin", "data_level0.bin", "length.bin", "link_lists.bin")


def listening(port: int) -> bool:
    import socket

    sock = socket.socket()
    sock.settimeout(0.3)
    try:
        return sock.connect_ex(("127.0.0.1", port)) == 0
    finally:
        sock.close()


def pid_on_port(port: int) -> str:
    """从 netstat 里找出监听该端口的 PID。

    不要用 ``findstr ":8000 "``：netstat 的列宽不固定，
    在部分环境下匹配不到，会得到空 PID，进而误开第二个 Chroma 实例。
    """
    out = subprocess.run(
        ["netstat", "-ano"], capture_output=True, text=True
    ).stdout
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 5 and parts[1].endswith(f":{port}") and parts[3] == "LISTENING":
            return parts[4]
    return ""


def stop_chroma() -> None:
    if not listening(PORT):
        print("  Chroma 未运行")
        return
    pid = pid_on_port(PORT)
    print(f"  停止 Chroma（PID {pid}）...")
    subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True)


def move_pickles() -> int:
    """把每个 segment 里的 index_metadata.pickle 改名（保留现场，可回滚）。"""
    moved = 0
    stamp = time.strftime("%Y%m%d-%H%M%S")
    for seg in DATA.iterdir() if DATA.exists() else []:
        if not seg.is_dir():
            continue
        pickle = seg / PICKLE
        if pickle.exists():
            target = seg / f"{PICKLE}.stale-{stamp}"
            pickle.rename(target)
            moved += 1
            print(f"  挪走 {seg.name[:8]}/{PICKLE} -> {target.name}")
    return moved


def start_chroma() -> None:
    env = dict(os.environ)
    tmp = ROOT / "data" / "tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    # 实测：TEMP 不可写会让 Chroma 建库/迁移直接 CANTOPEN，固定到项目内目录
    env["TEMP"] = str(tmp)
    env["TMP"] = str(tmp)

    log = ROOT / "data" / "chroma.log"
    print("  启动 Chroma ...")
    subprocess.Popen(
        [str(ROOT / ".venv" / "Scripts" / "chroma.exe"),
         "run", "--path", str(DATA), "--port", str(PORT)],
        cwd=str(ROOT),
        env=env,
        stdout=log.open("w", encoding="utf-8"),
        stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    for _ in range(40):
        if listening(PORT):
            return
        time.sleep(1)
    print("  ERROR: Chroma 30 秒内没起来，见 data/chroma.log")


def verify() -> bool:
    import chromadb

    try:
        client = chromadb.HttpClient(host="127.0.0.1", port=PORT)
        name = "knowledge_chunks_zhipu2048"
        collection = client.get_collection(name)
        count = collection.count()
        print(f"  ✅ 集合 {name} 可读，count = {count}")
        return count > 0
    except Exception as exc:
        print(f"  ❌ 仍然打不开：{type(exc).__name__}: {str(exc)[:160]}")
        return False


def prepare_mode() -> int:
    """``--prepare``：只在「元数据在、索引文件不在」时清理，不动服务。

    dev.cmd 在启动 Chroma 之前调用它 —— 强制结束留下的半截元数据会被自动挪走，
    Chroma 启动时就会从 sqlite 重建索引，于是「重启机器后索引失效」变成自愈。
    """
    if not DATA.exists():
        return 0
    healed = 0
    for seg in DATA.iterdir():
        if not seg.is_dir():
            continue
        pickle = seg / PICKLE
        if not pickle.exists():
            continue
        bins = [p for p in seg.iterdir() if p.name.endswith(".bin")]
        if bins:
            continue  # 元数据与索引文件配套，正常
        target = seg / f"{PICKLE}.stale-{time.strftime('%Y%m%d-%H%M%S')}"
        pickle.rename(target)
        healed += 1
        print(f"  [prepare] {seg.name[:8]} 元数据缺索引文件，已挪走 -> {target.name}")
    if healed:
        print(f"  [prepare] 共修复 {healed} 个 segment，Chroma 会从 sqlite 重建索引")
    return 0


def main() -> int:
    if "--prepare" in sys.argv:
        return prepare_mode()

    print("=" * 60)
    print(" 修复向量库索引（不需要重新 embedding）")
    print("=" * 60)

    if not DATA.exists():
        print("  数据目录不存在，先跑 dev.cmd --rebuild --reindex")
        return 1

    stop_chroma()
    time.sleep(2)

    moved = move_pickles()
    if not moved:
        print("  没找到 index_metadata.pickle —— 可能不是这个原因，建议 dev.cmd --check")
    else:
        print(f"  共挪走 {moved} 个半截索引元数据")

    start_chroma()
    print()
    ok = verify()
    print()
    if ok:
        print("  修复成功：向量都在，只是让 Chroma 重建了 HNSW 索引。")
        print("  建议立刻打快照：dev.cmd --snapshot")
    else:
        print("  修复失败。可以回滚：把 *.stale-* 改回 index_metadata.pickle，")
        print("  或者直接重建：dev.cmd --rebuild --reindex")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
