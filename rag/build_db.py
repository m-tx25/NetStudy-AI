#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
build_db.py — 把 PDF 切片并向量化，写入本地 ChromaDB。

流程：
    读取 ./test.pdf
      -> 切分（RecursiveCharacterTextSplitter, chunk_size=500, chunk_overlap=50）
      -> 向量化（智谱 embedding-3，或本地中文 embedding 模型）
      -> 存入 ./chroma_db

用法：
    # 本地模型（默认，免费、不需要 API Key；首次会下载模型）
    python build_db.py

    # 智谱 embedding-3（需 ZHIPUAI_API_KEY）
    python build_db.py --provider zhipu

    # 换成本地 m3e-base
    python build_db.py --local-model moka-ai/m3e-base

    # 先拿 20 页试跑，避免大文件白等
    python build_db.py --limit-pages 20 --rebuild

依赖安装：
    pip install langchain-community langchain-chroma chromadb pypdf langchain-text-splitters
    # 智谱：pip install zhipuai python-dotenv
    # 本地模型：pip install sentence-transformers

【重要】DeepSeek 不能用于向量化
    DeepSeek 开放平台只提供文本生成模型（deepseek-flash / deepseek-v4-pro），
    **没有 /embeddings 接口**（实测请求该端点返回 404）。
    因此 DeepSeek 的 Key 无法用来建向量库，只能用在后续的「检索 + 生成」问答环节。
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
import time
import unicodedata
from pathlib import Path

# ---------------------------------------------------------------- 默认配置
DEFAULT_FILE = "./test.pdf"
DEFAULT_PERSIST_DIR = "./chroma_db"
DEFAULT_COLLECTION = "test_pdf"
DEFAULT_CHUNK_SIZE = 500
DEFAULT_CHUNK_OVERLAP = 50
DEFAULT_ZHIPU_MODEL = "embedding-3"
# 智谱 embedding-3 支持 256/512/1024/2048，默认 2048
DEFAULT_ZHIPU_DIMENSIONS = 2048
# 本地默认模型：中文效果好、体积小（约 95MB）
DEFAULT_LOCAL_MODEL = "BAAI/bge-small-zh-v1.5"
# 智谱单次请求最多 64 条文本，留出余量
BATCH_SIZE = 32


def log(msg: str = "") -> None:
    print(msg, flush=True)


def load_env_file(path: Path) -> dict:
    """
    读取 .env，返回本次实际设置/发现的键值（用于打印诊断信息，避免静默失败）。

    坑点：Windows 上用 PowerShell 的 `Set-Content -Encoding UTF8` 写文件会**带 UTF-8 BOM**
    （开头的 EF BB BF）。此时变量名会变成 '\\ufeffZHIPUAI_API_KEY'，看起来就像"没设置"。
    注意 python-dotenv 遇到 BOM **不会报错**，只是静默读不到——所以这里一律用
    utf-8-sig 解码，并且自己解析一遍，不把成败完全交给它。
    """
    found: dict = {}
    if not path.exists():
        return found

    # 1) 手工解析：稳妥，能明确知道到底读到了什么
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        text = path.read_text(encoding="utf-8", errors="replace")
    text = text.lstrip("\ufeff")  # 双保险

    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if not key:
            continue
        os.environ[key] = value
        found[key] = value

    # 2) 再让 python-dotenv 跑一遍（若已安装），兼容 ${VAR} 展开等高级写法
    try:
        from dotenv import load_dotenv

        load_dotenv(path, encoding="utf-8-sig", override=True)
    except ImportError:
        pass
    except Exception:  # noqa: BLE001
        pass

    return found


def die(msg: str, code: int = 1) -> None:
    log(f"\n[错误] {msg}")
    sys.exit(code)


def chunk_id(source: str, index: int, text: str) -> str:
    """稳定 ID：同一文件重复建库不会产生重复条目。"""
    digest = hashlib.sha1(f"{source}|{index}|{text}".encode("utf-8")).hexdigest()
    return f"{Path(source).stem}-{index:05d}-{digest[:12]}"


# ---------------------------------------------------------------- 1. 读取 PDF
def normalize_text(text: str) -> str:
    """
    Unicode NFKC 归一化 —— 修复 PDF 提取出的"变体字"。

    Chrome/Skia 导出的 PDF，其文本层常把汉字写成 **Unicode 兼容码位**，例如：

        '⼀' U+2F00 (康熙部首)  vs  '一' U+4E00 (标准汉字)
        '⼆' U+2F02            vs  '二' U+4E8C
        '⻓' U+2ED3 (CJK部首补充) vs  '长' U+957F

    它们在屏幕上看起来一模一样，但码位不同。后果很严重：

      - 用标准汉字搜关键词会**搜不到**（'流水线' 命中 0 次，归一化后 12 次）
      - embedding 模型看到的是变体字，与标准中文对不齐，**检索质量下降**

    NFKC 会把这些兼容字符映射回标准形式；对已经是标准汉字的文本几乎无影响。
    """
    return unicodedata.normalize("NFKC", text)


def load_documents(target: Path, limit_pages: int | None):
    try:
        from langchain_community.document_loaders import PyPDFLoader
    except ImportError:
        die("缺少依赖，请先安装：pip install langchain-community pypdf")

    if not target.exists():
        die(f"找不到文件：{target.resolve()}")

    log(f"[1/4] 读取 PDF：{target}")
    started = time.time()
    docs = PyPDFLoader(str(target), extraction_mode="plain").load()
    log(f"      共 {len(docs)} 页，耗时 {time.time() - started:.1f}s")

    if limit_pages:
        docs = docs[:limit_pages]
        log(f"      （--limit-pages 限制为前 {len(docs)} 页）")

    # ---- Unicode 归一化：修复 PDF 文本层里的变体字 ----
    changed_chars = 0
    changed_pages = 0
    for d in docs:
        raw = d.page_content or ""
        fixed = normalize_text(raw)
        if fixed != raw:
            changed_pages += 1
            changed_chars += sum(1 for a, b in zip(raw, fixed) if a != b)
        d.page_content = fixed
    if changed_pages:
        log(f"      已做 Unicode 归一化(NFKC)：{changed_pages}/{len(docs)} 页有变化，"
            f"共修正 {changed_chars} 个变体字符")
    else:
        log("      文本已是标准 Unicode，无需归一化")

    empty_pages = sum(1 for d in docs if not (d.page_content or "").strip())
    lens = [len(d.page_content or "") for d in docs]
    total_chars = sum(lens)
    avg = total_chars / len(docs) if docs else 0
    log(f"      其中空页 {empty_pages} 页")
    log(f"      提取到文本共 {total_chars} 字符，平均 {avg:.1f} 字符/页")
    if lens:
        log(f"      单页字符数：最少 {min(lens)}，最多 {max(lens)}")

    if docs and empty_pages == len(docs):
        log()
        log("      ⚠ 所有页面都没提取到文本，这个 PDF 很可能是扫描件（图片）。")
        log("        需要先做 OCR（如 ocrmypdf / PaddleOCR）再建库。")
    elif empty_pages > len(docs) * 0.5:
        log(f"      ⚠ 空页比例较高（{empty_pages}/{len(docs)}），可能含大量扫描页。")

    # 页数多但文本极少 —— 典型的"扫描件 / 图片型 PDF"
    if docs and avg < 100:
        log()
        log(f"      ⚠ 警告：平均每页只有 {avg:.1f} 个字符，文本层几乎为空。")
        log("        该 PDF 很可能主要是图片（扫描件），直接建库只能得到极少、")
        log("        且高度重复的内容，检索没有意义。")
        log("        处理办法：先 OCR（ocrmypdf / PaddleOCR / 智谱 GLM-OCR）后重建。")

    return docs


# ---------------------------------------------------------------- 2. 切分
def split_documents(docs, chunk_size: int, overlap: int):
    try:
        from langchain_text_splitters import RecursiveCharacterTextSplitter
    except ImportError:
        try:
            from langchain.text_splitter import RecursiveCharacterTextSplitter
        except ImportError:
            die("缺少依赖，请先安装：pip install langchain-text-splitters")

    log(f"[2/4] 切分文本：chunk_size={chunk_size}, chunk_overlap={overlap}")
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=overlap,
        length_function=len,
        # 中文优先的分隔符（默认是英文标点，对中文 PDF 切得不好）
        separators=["\n\n", "\n", "。", "！", "？", "；", ". ", " ", ""],
    )
    chunks = [c for c in splitter.split_documents(docs) if (c.page_content or "").strip()]
    log(f"      得到 {len(chunks)} 个切片")

    if chunks:
        sizes = [len(c.page_content) for c in chunks]
        log(f"      切片长度：最小 {min(sizes)}，最大 {max(sizes)}，平均 {sum(sizes) // len(sizes)}")
    return chunks


# ---------------------------------------------------------------- 3. 向量模型
def build_embeddings_zhipu(dimensions: int):
    try:
        from langchain_community.embeddings import ZhipuAIEmbeddings
    except ImportError:
        die("缺少依赖，请先安装：pip install langchain-community zhipuai")

    # 注意：LangChain 的 ZhipuAIEmbeddings 读的是 ZHIPUAI_API_KEY（不是 ZHIPU_API_KEY）
    api_key = os.getenv("ZHIPUAI_API_KEY") or os.getenv("ZHIPU_API_KEY")
    if not api_key:
        die(
            "未找到智谱 API Key。任选一种方式设置：\n"
            "        1) 在 rag/ 目录建 .env，写入：ZHIPUAI_API_KEY=你的key\n"
            "        2) PowerShell：$env:ZHIPUAI_API_KEY=\"你的key\"\n"
            "        Key 申请：https://open.bigmodel.cn/"
        )
    os.environ["ZHIPUAI_API_KEY"] = api_key

    log(f"[3/4] 向量模型：智谱 {DEFAULT_ZHIPU_MODEL}（dimensions={dimensions}）")
    return ZhipuAIEmbeddings(
        model=DEFAULT_ZHIPU_MODEL,
        api_key=api_key,
        dimensions=dimensions,
    )


def build_embeddings_local(model_name: str, cache_dir: str | None):
    # 新版在 langchain-huggingface，旧版在 langchain-community，两个都试
    HuggingFaceEmbeddings = None
    try:
        from langchain_huggingface import HuggingFaceEmbeddings  # type: ignore
    except ImportError:
        try:
            from langchain_community.embeddings import HuggingFaceEmbeddings  # type: ignore
        except ImportError:
            die("缺少依赖，请先安装：pip install sentence-transformers langchain-community")

    log(f"[3/4] 向量模型：本地 {model_name}")
    log("      首次运行需下载模型；国内网络若失败，先设置镜像：")
    log('      $env:HF_ENDPOINT="https://hf-mirror.com"')

    kwargs = {"device": "cpu"}
    if cache_dir:
        kwargs["cache_folder"] = cache_dir

    try:
        return HuggingFaceEmbeddings(
            model_name=model_name,
            model_kwargs=kwargs,
            encode_kwargs={"normalize_embeddings": True},
        )
    except Exception as exc:  # noqa: BLE001
        die(
            f"加载本地模型失败：{exc}\n"
            f"        排查建议：\n"
            f"        1) 确认已安装：pip install sentence-transformers\n"
            f"        2) 设置镜像后重试：$env:HF_ENDPOINT=\"https://hf-mirror.com\"\n"
            f"        3) 或改用智谱：python build_db.py --provider zhipu"
        )


# ---------------------------------------------------------------- 4. 写入 Chroma
def build_vector_store(chunks, embeddings, persist_dir: Path, collection: str, rebuild: bool):
    try:
        from langchain_chroma import Chroma
    except ImportError:
        die("缺少依赖，请先安装：pip install langchain-chroma chromadb")

    persist_dir.mkdir(parents=True, exist_ok=True)
    log(f"[4/4] 写入 ChromaDB：{persist_dir}（collection={collection}）")

    if rebuild:
        try:
            Chroma(
                collection_name=collection,
                embedding_function=embeddings,
                persist_directory=str(persist_dir),
            ).delete_collection()
            log("      已删除同名集合（--rebuild）")
        except Exception:  # noqa: BLE001
            pass  # 集合本就不存在

    store = Chroma(
        collection_name=collection,
        embedding_function=embeddings,
        persist_directory=str(persist_dir),
    )

    total = len(chunks)
    started = time.time()
    for start in range(0, total, BATCH_SIZE):
        batch = chunks[start : start + BATCH_SIZE]
        ids = [
            chunk_id(c.metadata.get("source", "unknown"), start + i, c.page_content)
            for i, c in enumerate(batch)
        ]
        store.add_documents(documents=batch, ids=ids)

        done = min(start + BATCH_SIZE, total)
        ratio = done / total
        elapsed = time.time() - started
        eta = (elapsed / ratio - elapsed) if ratio else 0
        log(f"      {done}/{total} ({ratio:6.1%})  已用 {elapsed:6.1f}s  预计剩余 {eta:6.1f}s")

    return store, time.time() - started


# ---------------------------------------------------------------- 主流程
def parse_args():
    parser = argparse.ArgumentParser(
        description="读取 PDF，切片并向量化后存入 ChromaDB（DeepSeek 不支持 embedding，见文末说明）",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--file", default=DEFAULT_FILE, help="待处理的 PDF 路径")
    parser.add_argument("--provider", default="local", choices=["local", "zhipu"],
                        help="向量模型来源：local（本地模型，免费）或 zhipu（智谱 API）")
    parser.add_argument("--local-model", default=DEFAULT_LOCAL_MODEL,
                        help="本地模型名，如 BAAI/bge-small-zh-v1.5 或 moka-ai/m3e-base")
    parser.add_argument("--model-cache", default=None,
                        help="本地模型缓存目录（默认 ~/.cache/huggingface）")
    parser.add_argument("--persist-dir", default=DEFAULT_PERSIST_DIR, help="ChromaDB 持久化目录")
    parser.add_argument("--collection", default=DEFAULT_COLLECTION, help="集合名称")
    parser.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE, help="切片长度")
    parser.add_argument("--chunk-overlap", type=int, default=DEFAULT_CHUNK_OVERLAP, help="切片重叠长度")
    parser.add_argument("--dimensions", type=int, default=DEFAULT_ZHIPU_DIMENSIONS,
                        help="智谱向量维度（仅 embedding-3 及以后支持）")
    parser.add_argument("--limit-pages", type=int, default=None,
                        help="只处理前 N 页（大文件试跑用）")
    parser.add_argument("--dry-run", action="store_true",
                        help="只读取并切分，打印切片样例，不调用向量模型、不写库")
    parser.add_argument("--rebuild", action="store_true",
                        help="建库前先删除同名集合，避免重复数据")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    env_keys = load_env_file(Path(".env"))

    log("=" * 64)
    log("构建向量库 build_db.py")
    log("=" * 64)

    # 环境诊断：把 key 的来源说清楚，避免"明明写了却说没有"
    if env_keys:
        masked = {
            k: (v[:8] + "..." + v[-4:]) if len(v) > 16 else "***"
            for k, v in env_keys.items()
        }
        log(f"[env] 已从 .env 读取：{masked}")
    else:
        log("[env] 未从 .env 读到任何配置（文件不存在或为空）")
    for name in ("ZHIPUAI_API_KEY", "ZHIPU_API_KEY"):
        val = os.getenv(name)
        if val:
            log(f"[env] {name} 已就绪（来自 .env 或系统环境变量）")
    log()

    docs = load_documents(Path(args.file), args.limit_pages)
    if not docs:
        die("PDF 没有可用的内容。")

    chunks = split_documents(docs, args.chunk_size, args.chunk_overlap)
    if not chunks:
        die("切分后没有产生任何文本块（很可能是扫描件，请先 OCR）。")

    if args.dry_run:
        log()
        log("-" * 64)
        log("--dry-run：不调用向量模型，也不写库。切片样例：")
        log("-" * 64)
        for i, c in enumerate(chunks[:5]):
            log(f"[切片 {i + 1}] 第 {c.metadata.get('page')} 页，{len(c.page_content)} 字符")
            log("  " + c.page_content[:200].replace("\n", " "))
        log("-" * 64)
        log(f"共 {len(chunks)} 个切片。样例如上，若中文可读即正常。")
        log("去掉 --dry-run 即可正式建库。")
        return 0

    if args.provider == "zhipu":
        embeddings = build_embeddings_zhipu(args.dimensions)
    else:
        embeddings = build_embeddings_local(args.local_model, args.model_cache)

    store, elapsed = build_vector_store(
        chunks, embeddings, Path(args.persist_dir), args.collection, args.rebuild
    )

    try:
        count = store._collection.count()  # noqa: SLF001 （仅用于统计输出）
    except Exception:  # noqa: BLE001
        count = "未知"

    log()
    log("=" * 64)
    log("完成")
    log(f"  向量模型  : {args.provider} / "
        f"{args.local_model if args.provider == 'local' else DEFAULT_ZHIPU_MODEL}")
    log(f"  切片数    : {len(chunks)}")
    log(f"  耗时      : {elapsed:.1f}s")
    log(f"  集合      : {args.collection}")
    log(f"  库中总条数: {count}")
    log(f"  存储位置  : {Path(args.persist_dir).resolve()}")
    log("=" * 64)
    log()
    log("检索验证（embedding 必须与建库时相同）：")
    log("    from langchain_chroma import Chroma")
    log("    db = Chroma(persist_directory='./chroma_db',")
    log("               embedding_function=<与建库时相同的 embedding>)")
    log("    for d in db.similarity_search('你的问题', k=3):")
    log("        print(d.metadata.get('page'), d.page_content[:80])")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        log("\n已中断。")
        sys.exit(130)
