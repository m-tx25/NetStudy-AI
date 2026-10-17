#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
query_db.py — 检索验证脚本：在 ChromaDB 向量库里做相似度检索。

用途：
    1. 确认建库成功、能召回正确内容
    2. 交互式提问，看每条的来源页码与距离
    3. 输出 JSON，便于接给大模型做 RAG 问答

重要：检索时用的 embedding 模型必须与建库时一致（本项目是智谱 embedding-3），
      否则向量空间不同，检索结果无意义。

用法：
    # 单次提问
    python query_db.py -q "综合布线的长度限制"

    # 返回 5 条、显示完整内容
    python query_db.py -q "RISC 和 CISC 的区别" -k 5 --full

    # 交互模式（连续提问，输入 exit 退出）
    python query_db.py

    # 输出 JSON（给程序用）
    python query_db.py -q "二进制转换" --json

    # 只看统计信息，不做检索
    python query_db.py --info

依赖：
    pip install chromadb zhipuai python-dotenv
    （与 build_db.py 共用 rag/.env 里的 ZHIPUAI_API_KEY）
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

DEFAULT_PERSIST_DIR = "./chroma_db"
DEFAULT_COLLECTION = "test_pdf"
DEFAULT_MODEL = "embedding-3"
DEFAULT_K = 3


def log(msg: str = "") -> None:
    print(msg, flush=True)


def die(msg: str, code: int = 1) -> None:
    log(f"\n[错误] {msg}")
    sys.exit(code)


def load_env_file(path: Path) -> dict:
    """读取 .env；用 utf-8-sig 剥离 BOM（PowerShell 写的文件常带 BOM）。"""
    found: dict = {}
    if not path.exists():
        return found
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        text = path.read_text(encoding="utf-8", errors="replace")
    text = text.lstrip("\ufeff")
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key:
            os.environ[key] = value
            found[key] = value
    try:
        from dotenv import load_dotenv

        load_dotenv(path, encoding="utf-8-sig", override=True)
    except Exception:  # noqa: BLE001
        pass
    return found


def get_api_key() -> str:
    key = os.getenv("ZHIPUAI_API_KEY") or os.getenv("ZHIPU_API_KEY")
    if not key:
        die(
            "未找到智谱 API Key。任选一种方式设置：\n"
            "        1) 在 rag/ 目录建 .env，写入：ZHIPUAI_API_KEY=你的key\n"
            "        2) PowerShell：$env:ZHIPUAI_API_KEY=\"你的key\""
        )
    return key


def open_collection(persist_dir: str, collection: str):
    try:
        import chromadb
    except ImportError:
        die("缺少依赖，请先安装：pip install chromadb")

    path = Path(persist_dir)
    if not path.exists():
        die(
            f"向量库不存在：{path.resolve()}\n"
            f"        请先建库：python build_db.py --provider zhipu"
        )
    client = chromadb.PersistentClient(path=str(path))
    try:
        return client.get_collection(collection)
    except Exception as exc:  # noqa: BLE001
        names = [c.name for c in client.list_collections()]
        die(f"找不到集合 {collection}：{exc}\n        现有集合：{names}")


def embed_query(client, model: str, text: str) -> list:
    resp = client.embeddings.create(model=model, input=[text])
    return resp.data[0].embedding


def extract_terms(question: str) -> list:
    """
    从问题里抽词：中文按 2-gram，英文/数字按单词。无需分词器，避免额外依赖。

    中文用 2-gram 是常用近似：'流水线的加速比' -> 流水/水线/线的/的加/加速/速比
    虽然会引入一些无意义组合，但它们几乎不会同时出现在正文里，不影响排序。
    """
    terms = set()
    # 英文单词、数字、字母数字混合（长度 >= 2）
    for tok in re.findall(r"[A-Za-z0-9_]{2,}", question):
        terms.add(tok.lower())
    # 中文及其他 CJK 连续段取 2-gram
    for seg in re.findall(r"[\u3400-\u9fff\u2e80-\u2fdf]{2,}", question):
        for i in range(len(seg) - 1):
            terms.add(seg[i:i + 2])
    return list(terms)


def lexical_score(question: str, text: str) -> int:
    """词面命中打分：命中词数 + 词频，长词加权。"""
    if not text:
        return 0
    low = text.lower()
    score = 0
    for t in extract_terms(question):
        count = low.count(t)
        if count:
            score += count * (2 if len(t) >= 3 else 1)
    return score


def search(col, embed_client, model: str, question: str, k: int,
           hybrid: bool = False, pool: int = 40) -> dict:
    """
    检索。hybrid=False 时只做向量检索；True 时叠加关键词召回后合并重排。

    为什么要混合：纯向量检索对「表述模糊的提问」不够稳。实测同一份语料，
        「什么是流水线」        → 正确切片排名 8/148
        「流水线的加速比怎么算」 → 正确切片排名 1/148
    考试/手册类文档里大量是术语和公式，关键词命中往往比语义更可靠，因此叠加一层
    词面打分：把问题按字/词切分，统计切片里命中的词数与词频。
    """
    started = time.time()
    vector = embed_query(embed_client, model, question)

    # 候选池：向量检索多取一些，供混合重排
    n_fetch = max(k, pool) if hybrid else k
    res = col.query(
        query_embeddings=[vector],
        n_results=n_fetch,
        include=["documents", "metadatas", "distances"],
    )
    elapsed = (time.time() - started) * 1000

    docs = (res.get("documents") or [[]])[0]
    metas = (res.get("metadatas") or [[]])[0]
    dists = (res.get("distances") or [[]])[0]
    ids = (res.get("ids") or [[]])[0]

    candidates = []
    for i, text in enumerate(docs):
        meta = (metas[i] if i < len(metas) else {}) or {}
        candidates.append({
            "id": ids[i] if i < len(ids) else f"#{i}",
            "text": text,
            # page_label 是人类可读页码（1 基），page 是 0 基索引
            "page_label": meta.get("page_label"),
            "source": meta.get("source"),
            "distance": dists[i] if i < len(dists) else None,
            "lexical": lexical_score(question, text),
        })

    if hybrid:
        # 词面分数归一化到 0~1，与向量相似度线性组合
        # （向量距离越小越好，故相似度用 1-distance）
        max_lex = max((c["lexical"] for c in candidates), default=0) or 1
        for c in candidates:
            vec_sim = 1.0 - (c["distance"] or 0.0)
            c["score"] = 0.5 * vec_sim + 0.5 * (c["lexical"] / max_lex)
        candidates.sort(key=lambda c: c["score"], reverse=True)
    hits = candidates[:k]
    for h in hits:
        h.pop("id", None)
        h.pop("score", None)
    return {
        "question": question,
        "mode": "hybrid" if hybrid else "vector",
        "elapsed_ms": round(elapsed, 1),
        "hits": hits,
    }


def print_hits(result: dict, full: bool = False) -> None:
    hits = result["hits"]
    mode = result.get("mode", "vector")
    log(f"\n查询：{result['question']}   （{mode} 模式，{result['elapsed_ms']:.0f} ms，命中 {len(hits)} 条）")
    log("-" * 68)
    if not hits:
        log("  没有命中任何内容。")
        return
    for i, h in enumerate(hits, 1):
        dist = h["distance"]
        lex = h.get("lexical", 0)
        log(f"[{i}] 距离 {dist:.4f}  词面 {lex:>3}  来源 {h['source']}  第 {h['page_label']} 页")
        text = (h["text"] or "").replace("\n", " ")
        if full:
            log("    " + text)
        else:
            log("    " + text[:110] + ("…" if len(text) > 110 else ""))
    log("-" * 68)
    if mode == "hybrid":
        log("提示：hybrid 模式按 0.5×向量相似度 + 0.5×词面命中 重排；距离越小越相关。")
    else:
        log("提示：距离越小越相关（L2 距离，一般为 0.7~1.4 之间）。")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="在 ChromaDB 向量库中做相似度检索",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("-q", "--question", help="要检索的问题；省略则进入交互模式")
    parser.add_argument("-k", type=int, default=DEFAULT_K, help="返回条数")
    parser.add_argument("--persist-dir", default=DEFAULT_PERSIST_DIR, help="ChromaDB 目录")
    parser.add_argument("--collection", default=DEFAULT_COLLECTION, help="集合名称")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="embedding 模型（须与建库一致）")
    parser.add_argument("--hybrid", action="store_true",
                        help="混合检索：向量 + 关键词词面重排（术语/公式类文档推荐）")
    parser.add_argument("--full", action="store_true", help="显示完整切片内容")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出（便于程序调用）")
    parser.add_argument("--info", action="store_true", help="只显示库的统计信息，不检索")
    args = parser.parse_args()

    env_keys = load_env_file(Path(".env"))
    col = open_collection(args.persist_dir, args.collection)

    if args.info:
        log("=" * 68)
        log("向量库信息")
        log("=" * 68)
        log(f"  目录      : {Path(args.persist_dir).resolve()}")
        log(f"  集合      : {args.collection}")
        log(f"  切片条数  : {col.count()}")
        log(f"  元数据    : {col.metadata}")
        log(f"  .env 读到 : {list(env_keys.keys()) or '（无）'}")
        return 0

    if not args.json:
        log(f"[库] {Path(args.persist_dir).resolve()} / 集合 {args.collection} / {col.count()} 条切片")

    if args.question:
        try:
            from zhipuai import ZhipuAI
        except ImportError:
            die("缺少依赖，请先安装：pip install zhipuai")
        embed_client = ZhipuAI(api_key=get_api_key())

        result = search(col, embed_client, args.model, args.question, args.k,
                        hybrid=args.hybrid)
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print_hits(result, full=args.full)
        return 0

    # 交互模式
    try:
        from zhipuai import ZhipuAI
    except ImportError:
        die("缺少依赖，请先安装：pip install zhipuai")
    embed_client = ZhipuAI(api_key=get_api_key())

    log("交互模式：输入问题回车检索，输入 exit / q 退出。")
    while True:
        try:
            question = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            log("\n已退出。")
            break
        if question.lower() in ("exit", "quit", "q", ""):
            log("已退出。")
            break
        try:
            print_hits(search(col, embed_client, args.model, question, args.k,
                              hybrid=args.hybrid), full=args.full)
        except Exception as exc:  # noqa: BLE001
            log(f"[检索失败] {type(exc).__name__}: {exc}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        log("\n已中断。")
        sys.exit(130)
