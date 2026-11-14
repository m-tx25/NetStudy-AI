"""向量库：ChromaDB 持久化客户端。

方案来源：协作者的 `rag/build_db.py` / `rag/query_db.py`，本模块把它生产化：
  1. 用**单一集合 + 元数据过滤**实现多用户/多知识库隔离
     （他们的脚本是单文件单集合，没有 owner 概念）；
  2. 保留 rpd 的**混合检索**：0.5×向量相似度 + 0.5×词面命中，
     术语/公式/手册类文档下比纯向量稳；
  3. 文档停用/删除时同步从向量库移除，避免检索到已失效内容。

与 rag 脚本的差异（有意为之）：
  - 集合名带后缀区分向量空间：智谱 embedding-3（2048 维）与内置离线哈希
    （512 维）的向量**不可混用**，Chroma 在集合创建时就固定了维度，
    混用会直接报维度错误。
  - 距离转相似度：Chroma 默认 L2 距离，做 1 - d/2 归一化到 0~1，
    以便前端按百分比展示（前端对 0~1 与 0~100 都能识别）。
"""

from __future__ import annotations

import logging
import math
import os
import re
import time
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.services import embeddings

logger = logging.getLogger(__name__)

# 候选池：混合检索需要多取一些再重排（与 rag/query_db.py 的 pool=40 一致）
HYBRID_POOL = 40
# 向量相似度与词面得分在混合排序中的权重
VECTOR_WEIGHT = 0.5
LEXICAL_WEIGHT = 0.5


class VectorStoreUnavailable(RuntimeError):
    """向量库不可用（未安装依赖、目录不可写等），消息可直接展示给用户。"""


_client = None


def _vector_space_suffixes() -> list[str]:
    """所有可能的向量空间后缀。

    用于「不知道该用哪个空间」的场景（删除、统计）：
    同一份数据可能存在于 zhipu2048（配了 Key）或 offline512（没配 Key）里，
    两种空间不可混用，所以这些操作要**遍历所有空间**才不会漏。
    """
    return ["zhipu2048", f"offline{embeddings.offline_dimensions()}"]


def collection_name(api_key: str | None = None) -> str:
    """按向量化模式区分集合，避免两种向量空间混入同一集合。

    「是否智谱模式」不只取决于服务端配置 —— 团队/用户自备智谱 Key 时同样是智谱模式
    （同一 embedding-3 模型，向量空间一致，可共用集合）。
    没有任何 Key 时用**内置离线向量化**，维度与语义空间都不同，必须独立集合。

    因此调用方**必须**把本次实际使用的 embedding key 传进来
    （add_chunks / search 都传了 embedding_api_key），否则会出现
    「用 2048 维向量写进 512 维集合」的维度错误。
    """
    configured = embeddings.is_zhipu_configured() or bool((api_key or "").strip())
    if configured:
        suffix = "zhipu2048"
    else:
        suffix = f"offline{embeddings.offline_dimensions()}"
    return f"{settings.CHROMA_COLLECTION}_{suffix}"


def _persist_dir() -> Path:
    directory = Path(settings.CHROMA_PERSIST_DIR)
    if not directory.is_absolute():
        directory = Path.cwd() / directory
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def get_client():
    """获取 ChromaDB 客户端。

    两种形态，由 settings.CHROMA_HOST 决定：
      - 为空：嵌入式 PersistentClient，数据落在 CHROMA_PERSIST_DIR（本地开发）
      - 非空：HttpClient 连接独立的 Chroma 服务（Docker 部署，
              数据库容器化、数据由该容器持久化，后端镜像本身无状态）

    Docker 部署时用 HttpClient 还有一个好处：不需要 ~/.cache/chroma 可写，
    也不存在内置 ONNX 模型下载的问题（向量一律由我们自己算好传入）。
    """
    global _client
    if _client is not None:
        return _client

    if settings.CHROMA_DISABLED:
        raise VectorStoreUnavailable(
            "向量库已被配置禁用（server/.env 里 CHROMA_DISABLED=true）："
            "当前环境无法运行 ChromaDB 原生索引库，检索能力不可用。"
        )

    try:
        import chromadb
    except ImportError as exc:  # pragma: no cover
        raise VectorStoreUnavailable(
            "未安装 chromadb，请执行 pip install -r requirements.txt"
        ) from exc

    host = (settings.CHROMA_HOST or "").strip()
    if host:
        # 【关键】连本机/内网的 Chroma 必须绕过系统代理。
        # chromadb 的 HttpClient 内部用 httpx，默认 trust_env=True ——
        # 会把 WinINET/环境变量里的代理（如 Clash 的 127.0.0.1:7897）套在
        # 发往 127.0.0.1:8000 的请求上，代理不认识这个目标，
        # 于是返回 **502 Bad Gateway**，表现为「连接 Chroma 服务失败」或
        # 「打开向量集合失败」，与索引损坏的现象极易混淆。
        _ensure_proxy_bypass(host)
        try:
            _client = chromadb.HttpClient(host=host, port=settings.CHROMA_PORT)
            logger.info("向量库：连接 Chroma 服务 %s:%s", host, settings.CHROMA_PORT)
        except Exception as exc:
            raise VectorStoreUnavailable(
                f"连接 Chroma 服务失败（{host}:{settings.CHROMA_PORT}）：{exc}\n"
                "        请确认 chroma 容器已启动且端口可达"
            ) from exc
        return _client

    try:
        _client = chromadb.PersistentClient(path=str(_persist_dir()))
        logger.info("向量库：嵌入式模式，数据目录 %s", _persist_dir())
    except Exception as exc:  # 目录不可写、版本不兼容等
        raise VectorStoreUnavailable(f"初始化 ChromaDB 失败：{exc}") from exc
    return _client


def _ensure_proxy_bypass(host: str) -> None:
    """把 Chroma 的目标地址加入 NO_PROXY，避免本机请求被系统代理劫持。

    为什么必须做：Windows 上只要开着 Clash 之类（系统代理 127.0.0.1:7897），
    `httpx` 默认 `trust_env=True` 会连 127.0.0.1:8000 也走代理，
    代理返回 **502 Bad Gateway**，而 chromadb 把响应体当错误抛出，
    最终报成「连接 Chroma 服务失败」—— 和「索引损坏」表现几乎一样。
    实测：同一份数据，加不加这条绕过，一个报 502 一个正常。

    只改本进程的环境变量，不触碰系统设置；已存在的 NO_PROXY 会被保留。
    """
    targets = [host, "127.0.0.1", "localhost", "::1"]
    current = os.environ.get("NO_PROXY") or os.environ.get("no_proxy") or ""
    existing = {item.strip() for item in current.split(",") if item.strip()}
    merged = existing.union(targets)
    if merged != existing:
        value = ",".join(sorted(merged))
        os.environ["NO_PROXY"] = value
        os.environ["no_proxy"] = value


def _reset_client() -> None:
    """丢弃缓存的客户端。

    为什么必须有：`_client` 是**进程级单例**，而 Chroma 服务重启后，
    HttpClient 连接池里的连接会全部失效。不丢弃的话，后端会一直读不到集合
    —— 表现为 `/api/health` 的 collections 为空、检索恒 0 条，
    但 Chroma 里数据明明都在（实测：只能靠重启后端恢复，
    而重启 Chroma 容器在 Docker 部署里是常规操作）。
    """
    global _client
    _client = None


# 连接类异常的典型特征词（httpx / httpcore / socket 的报错都落在这里）
_CONNECTION_MARKERS = (
    'connect',
    'connection',
    'timeout',
    'timed out',
    'closed',
    'eof',
    'reset',
    'broken pipe',
    'remote protocol',
    'server disconnected',
)


def _looks_like_connection_error(exc: BaseException) -> bool:
    """判断异常是否属于「连不上/连接已断」，而不是「集合不存在」等业务错误。"""
    text = f'{type(exc).__module__}.{type(exc).__name__}: {exc}'.lower()
    return any(marker in text for marker in _CONNECTION_MARKERS)


def _call_with_reset(fn):
    """执行 fn(client)；若判定为连接类错误，丢弃客户端后重试一次。

    只重试一次：避免 Chroma 真的挂掉时无限重试把请求拖死。
    """
    try:
        return fn(get_client())
    except VectorStoreUnavailable:
        raise
    except Exception as exc:
        if not _looks_like_connection_error(exc):
            raise
        logger.warning('向量库连接异常，丢弃客户端并重连一次：%s', exc)
        _reset_client()
        return fn(get_client())


def get_collection(api_key: str | None = None):
    """获取（必要时创建）集合。

    参数 api_key 是**本次实际使用的 embedding key**，用于决定集合的向量空间：
      - 服务端配了 Key，或传入了团队/用户自备 Key → zhipu2048（2048 维）
      - 两者都没有 → offline512（512 维，内置离线实现）
    不传就按服务端配置判断，**因此凡是「用户可能自备 Key」的路径都必须传**，
    否则会出现「用 2048 维向量写进 512 维集合」的维度错误。

    注意：这里**不传 embedding_function**。
    本模块用的是原生 chromadb 客户端，而 chromadb 1.5.x 要求
    embedding function 实现其自有接口（`name()` / `__call__` / `is_legacy` …）。
    LangChain 的 `ZhipuAIEmbeddings` 只实现了 `embed_query` / `embed_documents`，
    传进来会在集合创建时抛：

        'ZhipuAIEmbeddings' object has no attribute 'name'

    因此统一改为**调用方自己算向量再显式传入**（与 search() 的写法一致）：
      - `upsert(..., embeddings=[...])`  ← 见 add_chunks
      - `query(query_embeddings=[...])`  ← 见 search
    两种模式（智谱 / 内置离线）都实现了 `embed_documents` 与 `embed_query`，
    所以调用方总能拿到向量，不会退回到 Chroma 的 ONNX 模型。
    """
    kwargs: dict[str, Any] = {
        "name": collection_name(api_key),
        # 显式声明距离度量，便于日后换 cosine 时行为可预期
        "metadata": {"hnsw:space": "l2", "embedding": embeddings.current_mode()},
    }

    try:
        # 连接类错误会自动丢弃客户端重连一次（见 _call_with_reset）
        return _call_with_reset(lambda c: c.get_or_create_collection(**kwargs))
    except Exception as exc:
        raise VectorStoreUnavailable(f"打开向量集合失败：{exc}") from exc


def _existing_collections() -> list[Any]:
    """列出当前实际存在、且属于本系统的所有集合（按向量空间后缀）。

    用于删除与统计：调用方不知道该数据当初用的是哪个向量空间，
    因此需要在所有空间上都操作一遍。

    实现上**不依赖 client.list_collections()**，而是按已知名称逐个探测：
      - list_collections() 在部分 chromadb 版本/客户端实例上有缓存，
        会漏掉「进程启动后新建的集合」，导致删除漏数据、统计偏小；
      - 已知名称只有两个（zhipu2048 / offline512），逐个 get_collection 成本极低。
    """
    prefix = settings.CHROMA_COLLECTION

    def _probe(client) -> list[Any]:
        found = []
        for suffix in _vector_space_suffixes():
            name = f"{prefix}_{suffix}"
            try:
                found.append(client.get_collection(name))
            except Exception as exc:
                # 「集合不存在」是常态（只用了其中一种向量空间）；
                # 但**连接类错误必须抛出去**，否则会被误判成「没有集合」，
                # 表现为计数恒为 0、删除漏数据、检索空结果（本次踩坑点）。
                if _looks_like_connection_error(exc):
                    raise
                continue
        return found

    return _call_with_reset(_probe)


# --------------------------------------------------------------------------
# 词面打分（移植自 rag/query_db.py，用于混合检索重排）
# --------------------------------------------------------------------------
def extract_terms(question: str) -> list[str]:
    """抽词：中文按 2-gram，英文/数字按单词，无需分词器。"""
    terms: set[str] = set()
    for token in re.findall(r"[A-Za-z0-9_]{2,}", question):
        terms.add(token.lower())
    for segment in re.findall(r"[\u3400-\u9fff\u2e80-\u2fdf]{2,}", question):
        for index in range(len(segment) - 1):
            terms.add(segment[index : index + 2])
    return list(terms)


def lexical_score(question: str, text: str) -> int:
    """词面命中打分：命中词数 + 词频，长词加权。"""
    if not text:
        return 0
    lowered = text.lower()
    score = 0
    for term in extract_terms(question):
        count = lowered.count(term)
        if count:
            score += count * (2 if len(term) >= 3 else 1)
    return score


def _distance_to_similarity(distance: float | None) -> float:
    """L2 距离 → 0~1 相似度（归一化向量下 L2 距离范围约 0~2）。"""
    if distance is None:
        return 0.0
    return max(0.0, min(1.0, 1.0 - float(distance) / 2.0))


# --------------------------------------------------------------------------
# 数据结构
# --------------------------------------------------------------------------
class RetrievedChunk:
    __slots__ = (
        "chunk_id",
        "document_id",
        "document_name",
        "knowledge_base_id",
        "knowledge_base_name",
        "content",
        "page",
        "score",
        "ordinal",
        "lexical",
        # 章节类型（method/abstract…）与原文标题（如「3 Method」）
        "section",
        "section_heading",
    )

    def __init__(
        self,
        *,
        chunk_id: str,
        document_id: str,
        document_name: str,
        knowledge_base_id: str,
        knowledge_base_name: str,
        content: str,
        page: int | None,
        score: float,
        ordinal: int,
        lexical: int = 0,
        section: str = "",
        section_heading: str = "",
    ) -> None:
        self.chunk_id = chunk_id
        self.document_id = document_id
        self.document_name = document_name
        self.knowledge_base_id = knowledge_base_id
        self.knowledge_base_name = knowledge_base_name
        self.content = content
        self.page = page
        self.score = score
        self.ordinal = ordinal
        # 词面命中得分（问题词在片段中出现的加权次数）
        self.lexical = lexical
        # 章节类型（M3 起写入；旧切片为空串）
        self.section = section
        # 章节原文标题（如 "2.2.1 BM25"），展示时优先于类型名
        self.section_heading = section_heading

    def snippet(self, limit: int = 160) -> str:
        text = " ".join(self.content.split())
        return text if len(text) <= limit else f"{text[:limit]}…"

    def is_evidence(self, min_lexical: int, min_score: float) -> bool:
        """该片段是否构成「知识库依据」。

        为什么不能只看向量分：实测弱向量模型（Chroma 默认 ONNX）下，
        无关问题（"量子纠缠"）也能拿到 0.83，而有关问题（"RAG 流程"）只有 0.67 ——
        **两个区间完全重叠，向量分无法区分**。
        词面命中则是干净信号：有关问题 ≥9，无关问题 ≤2。

        判据：词面命中达阈值，或向量分非常高（强向量模型下的纯语义命中）。
        """
        if self.lexical >= min_lexical:
            return True
        return self.score >= min_score


# --------------------------------------------------------------------------
# 写入
# --------------------------------------------------------------------------
def add_chunks(
    *,
    owner_id: str,
    knowledge_base_id: str,
    knowledge_base_name: str,
    document_id: str,
    document_name: str,
    chunks: list[tuple],
    team_id: str | None = None,
    embedding_api_key: str = "",
) -> int:
    """写入切片。chunks 为 `(ordinal, content, page_label[, extra_meta])`。

    page_label 是人类可读页码（1 基）；Markdown/Word 无分页概念时传 None。
    extra_meta 可带 `section / section_heading / page_start / page_end`（M3 结构解析）。

    owner_id 恒为**操作人（上传者）的用户 id**；团队知识库额外传 team_id。
    这样检索时既能按人过滤（个人库），也能按团队过滤（团队库），
    而不会出现「团队库的 owner_id 是团队 id、和用户 id 对不上」的错位。
    """
    if not chunks:
        return 0

    # 集合必须按「本次实际使用的 key」选：用户自备 Key 时是 zhipu2048，
    # 否则是 offline512。传错会导致向量维度与集合维度不一致。
    collection = get_collection(embedding_api_key)

    ids: list[str] = []
    documents: list[str] = []
    metadatas: list[dict[str, Any]] = []

    for item in chunks:
        ordinal, content, page = item[0], item[1], item[2]
        extra = item[3] if len(item) > 3 else None
        if isinstance(extra, dict):
            section_type = str(extra.get("section") or "")
            section_heading = str(extra.get("section_heading") or "")
        else:
            # 兼容远端旧形状：(ordinal, content, page, section_heading)
            section_type = ""
            section_heading = str(extra or "")
        text = (content or "").strip()
        if not text:
            continue
        # 稳定 ID：同一文档重复写入会覆盖而不是堆积
        chunk_id = f"{document_id}:{ordinal:05d}"
        ids.append(chunk_id)
        documents.append(text)
        metadata = {
            "owner_id": owner_id,
            # 团队知识库需带团队 id，供团队内任意成员检索到；
            # 个人库用空串占位（Chroma 元数据不接受 None）
            "team_id": team_id or "",
            "knowledge_base_id": knowledge_base_id,
            "knowledge_base_name": knowledge_base_name,
            "document_id": document_id,
            "document_name": document_name,
            "ordinal": ordinal,
            # Chroma 元数据只接受 str/int/float/bool，None 需转成 -1
            "page_label": int(page) if page else -1,
            # 章节：类型用于过滤（method/abstract…），标题用于引用展示
            "section": section_type,
            "section_heading": section_heading,
        }
        if isinstance(extra, dict):
            for key in ("page_start", "page_end"):
                value = extra.get(key)
                if isinstance(value, int):
                    metadata[key] = value
        metadatas.append(metadata)

    if not ids:
        return 0

    # 分批写入。倍数由 CHROMA_UPSERT_BATCH 控制（默认 8，见 config 里的说明）：
    # chromadb 1.x 的 compactor 在一次写入被打断后会永久卡死，
    # 批次越小越不容易触发。智谱 embedding 单次最多 64 条，默认值远低于该上限。
    batch = max(1, settings.CHROMA_UPSERT_BATCH)
    written = 0
    embedder = embeddings.get_embeddings(embedding_api_key or None)

    for start in range(0, len(ids), batch):
        end = start + batch
        payload: dict[str, Any] = {
            "ids": ids[start:end],
            "documents": documents[start:end],
            "metadatas": metadatas[start:end],
        }
        # 自己算向量后显式传入。
        # 不能依赖集合上的 embedding_function：原生 chromadb 与 LangChain 的
        # Embeddings 接口并不兼容（见 get_collection 注释）。
        # 离线模式下 embedder 同样是可用实例，所以这里恒有向量。
        if embedder is not None:
            payload["embeddings"] = embedder.embed_documents(documents[start:end])
        collection.upsert(**payload)
        written += len(ids[start:end])

    return written


# --------------------------------------------------------------------------
# 删除
# --------------------------------------------------------------------------
def _delete_where(where: dict[str, Any]) -> int:
    """在**所有向量空间**上删除匹配的切片。

    调用方（删除文档/知识库/账号）并不知道这些切片当初是用智谱还是离线实现
    建的，所以两个集合都要清 —— 只删一个会留下查不到的孤儿向量。
    """
    removed = 0
    collections = _existing_collections()
    if not collections:
        return 0
    for collection in collections:
        try:
            existing = collection.get(where=where, include=[])
            count = len(existing.get("ids") or [])
            if count:
                collection.delete(where=where)
                removed += count
        except Exception as exc:  # 集合为空、过滤条件无匹配等
            logger.warning("删除向量失败 where=%s: %s", where, exc)
    return removed


def delete_document(document_id: str) -> int:
    return _delete_where({"document_id": document_id})


def delete_knowledge_base(knowledge_base_id: str) -> int:
    return _delete_where({"knowledge_base_id": knowledge_base_id})


def delete_owner(owner_id: str) -> int:
    return _delete_where({"owner_id": owner_id})


# --------------------------------------------------------------------------
# 统计
# --------------------------------------------------------------------------
def count_chunks(*, owner_id: str | None = None, knowledge_base_id: str | None = None,
                 document_id: str | None = None) -> int:
    where: dict[str, Any] = {}
    if owner_id:
        where["owner_id"] = owner_id
    if knowledge_base_id:
        where["knowledge_base_id"] = knowledge_base_id
    if document_id:
        where["document_id"] = document_id

    # 跨所有向量空间求和：数据可能分布在 zhipu2048 与 offline512 两个集合里
    total = 0
    try:
        collections = _existing_collections()
        if not collections:
            return 0
        for collection in collections:
            if not where:
                total += int(collection.count())
            else:
                result = collection.get(where=where, include=[])
                total += len(result.get("ids") or [])
        return total
    except Exception as exc:
        logger.warning("统计向量数量失败：%s", exc)
        return total


def count_by_knowledge_base(knowledge_base_ids: list[str]) -> dict[str, int]:
    """批量统计每个知识库的切片数，避免列表接口 N+1。"""
    if not knowledge_base_ids:
        return {}
    counts: dict[str, int] = {kb_id: 0 for kb_id in knowledge_base_ids}
    try:
        for collection in _existing_collections():
            # Chroma 的 $in 过滤器对空列表不友好，但这里已保证非空
            result = collection.get(
                where={"knowledge_base_id": {"$in": list(knowledge_base_ids)}},
                include=["metadatas"],
            )
            for metadata in result.get("metadatas") or []:
                kb_id = (metadata or {}).get("knowledge_base_id")
                if kb_id in counts:
                    counts[kb_id] += 1
        return counts
    except Exception as exc:
        logger.warning("按知识库统计向量失败：%s", exc)
        return counts


# --------------------------------------------------------------------------
# 检索
# --------------------------------------------------------------------------
def _apply_document_quota(
    candidates: list[RetrievedChunk],
    doc_ids: list[str],
    limit: int,
) -> list[RetrievedChunk]:
    """按论文配额裁剪候选集。

    为什么需要：多篇论文问答时，如果只取全局 Top-K，最相关的那篇会把名额吃光，
    其余论文一条都进不来 —— 用户选了 5 篇，模型却只看到 1 篇的内容，
    于是「跨文献关联」变成了「单篇总结」。

    规则：每篇论文保底 `ceil(limit / 篇数)` 条（且至少 2 条），
    再整体按相关度排序返回。某篇候选不足时有多少给多少，不影响其它篇。
    """
    if not doc_ids:
        return candidates

    quota = max(2, math.ceil(limit / len(doc_ids)))
    kept: list[RetrievedChunk] = []
    for doc_id in doc_ids:
        own = [item for item in candidates if item.document_id == doc_id]
        kept.extend(own[:quota])
    kept.sort(key=lambda item: item.score, reverse=True)
    return kept


def search(
    db: Any,  # 保留形参以兼容既有调用签名（引擎层传入会话），当前实现不需要数据库
    query_text: str,
    *,
    owner_id: str,
    knowledge_base_ids: list[str] | None = None,
    document_ids: list[str] | None = None,
    top_k: int = 5,
    score_threshold: float = 0.2,
    hybrid: bool | None = None,
    team_ids: list[str] | None = None,
    embedding_api_key: str = "",
    sections: list[str] | None = None,
) -> list[RetrievedChunk]:
    """检索相关切片。

    实现要点：
      - owner_id / team_ids 在**向量库层面**过滤，确保不会跨用户、跨团队召回
        （安全边界）。团队知识库的切片带 team_id，只要提问者是该团队成员
        就应能召回 —— 这正是「团队知识库」的意义；
      - knowledge_base_ids / sections 在候选集上二次过滤
        （Chroma 的 $in 对动态列表较脆弱）；
      - **document_ids 命中时按论文配额召回**：每篇论文单独查询并保底配额，
        否则热门论文会吃掉全部 top_k，其余论文一条都进不来，
        「多篇论文问答 / 跨文献关联」就永远只有一篇的内容；
      - 混合检索开启时先取较大候选池，再用 0.5×向量 + 0.5×词面 重排。
    """
    use_hybrid = settings.HYBRID_SEARCH if hybrid is None else hybrid
    limit = max(1, top_k)
    docs = [item for item in dict.fromkeys(document_ids or []) if item]

    def scope_where(document_id: str | None = None) -> dict[str, Any]:
        conditions: list[dict[str, Any]] = [{"owner_id": owner_id}]
        if team_ids:
            conditions.append({"team_id": {"$in": list(team_ids)}})
        base = conditions[0] if len(conditions) == 1 else {"$or": conditions}
        if document_id:
            return {"$and": [base, {"document_id": {"$eq": document_id}}]}
        return base

    allowed = set(knowledge_base_ids) if knowledge_base_ids else None
    allowed_sections = set(sections) if sections else None

    def collect(
        collection: Any,
        query_vector: list[float],
        where: dict[str, Any],
        n_fetch: int,
        allowed_docs: set[str] | None = None,
    ) -> list[RetrievedChunk]:
        result = collection.query(
            query_embeddings=[query_vector],
            n_results=n_fetch,
            where=where,
            include=["documents", "metadatas", "distances"],
        )
        documents = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        ids = (result.get("ids") or [[]])[0]

        items: list[RetrievedChunk] = []
        for index, content in enumerate(documents):
            metadata = (metadatas[index] if index < len(metadatas) else {}) or {}
            if allowed is not None and metadata.get("knowledge_base_id") not in allowed:
                continue
            doc_id = str(metadata.get("document_id") or "")
            if allowed_docs is not None and doc_id not in allowed_docs:
                continue
            if (
                allowed_sections is not None
                and str(metadata.get("section") or "") not in allowed_sections
            ):
                continue

            distance = distances[index] if index < len(distances) else None
            page = metadata.get("page_label")
            items.append(
                RetrievedChunk(
                    chunk_id=ids[index] if index < len(ids) else f"#{index}",
                    document_id=doc_id,
                    document_name=str(metadata.get("document_name") or ""),
                    knowledge_base_id=str(metadata.get("knowledge_base_id") or ""),
                    knowledge_base_name=str(metadata.get("knowledge_base_name") or ""),
                    content=content or "",
                    page=int(page) if isinstance(page, int) and page > 0 else None,
                    score=_distance_to_similarity(distance),
                    ordinal=int(metadata.get("ordinal") or 0),
                    lexical=lexical_score(query_text, content or ""),
                    section=str(metadata.get("section") or ""),
                    section_heading=str(metadata.get("section_heading") or ""),
                )
            )
        return items

    try:
        # 集合按本次实际使用的 key 选（用户自备 Key → zhipu2048，否则 offline512）
        collection = get_collection(embedding_api_key)
        # 统一走「自己算查询向量」：离线实现与智谱实现都实现了 embed_query，
        # 不再需要 query_texts 分支（那会依赖集合上的 embedding_function，
        # 从而触发 Chroma 内置 ONNX 模型的 79MB 下载）。
        query_vector = embeddings.get_embeddings(embedding_api_key or None).embed_query(
            query_text
        )
        per_doc_pool = max(HYBRID_POOL, 6) if use_hybrid else 6
        if docs:
            # 每篇论文单独查一次，池子给够，再按配额截断（见下方裁剪）
            candidates: list[RetrievedChunk] = []
            for doc_id in docs:
                candidates.extend(
                    collect(
                        collection,
                        query_vector,
                        scope_where(doc_id),
                        max(per_doc_pool, limit),
                        allowed_docs={doc_id},
                    )
                )
        else:
            candidates = collect(
                collection,
                query_vector,
                scope_where(),
                max(limit, HYBRID_POOL) if use_hybrid else limit,
            )
    except VectorStoreUnavailable:
        raise
    except Exception as exc:
        logger.warning("向量检索失败：%s", exc)
        return []

    if not candidates:
        return []

    # 混合重排：向量分与归一化词面分线性组合。
    # 注意 lexical 字段始终保留**原始值**，因为证据门槛用的是原始命中次数，
    # 而不是归一化后的相对值（相对值在「全都无关」时也总有一个是 1.0）。
    if use_hybrid:
        max_lexical = max((item.lexical for item in candidates), default=0)
        if max_lexical > 0:
            for candidate in candidates:
                candidate.score = round(
                    VECTOR_WEIGHT * candidate.score
                    + LEXICAL_WEIGHT * (candidate.lexical / max_lexical),
                    4,
                )

    candidates.sort(key=lambda item: item.score, reverse=True)

    if docs:
        # 按论文配额保留：每篇至少 min(quota, 该篇候选数) 条，
        # 保证「多篇论文问答」里每篇都有发言权，而不是被最相关的那篇垄断。
        candidates = _apply_document_quota(candidates, docs, limit)

    filtered = [item for item in candidates if item.score >= score_threshold]
    if filtered:
        return filtered[:limit]

    # 阈值过滤后为空但确有候选：退化为 Top-K。
    # 原因见 docs/development-report.md 9.9：弱向量模型下相似度整体偏低，
    # 严格套用阈值会导致「传了文档却总说未找到依据」。
    return candidates[:limit]


def chroma_target() -> dict[str, Any]:
    """向量库连接目标（供自检展示，且不会在服务端模式下误建本地目录）。"""
    host = (settings.CHROMA_HOST or "").strip()
    if host:
        return {
            "mode": "http",
            "host": host,
            "port": settings.CHROMA_PORT,
        }
    return {"mode": "embedded", "persistDir": str(_persist_dir())}


def health() -> dict[str, Any]:
    """向量库自检，供 /api/health 展示。"""
    info: dict[str, Any] = {
        "collection": collection_name(),
        "target": chroma_target(),
        "embedding": embeddings.describe(),
        "hybridSearch": settings.HYBRID_SEARCH,
    }
    try:
        # 统计所有向量空间（zhipu2048 + offline512），否则只报其中一个会少算
        collections = _existing_collections()
        info["available"] = True
        info["collections"] = [getattr(c, "name", "?") for c in collections]
        info["totalChunks"] = sum(int(c.count()) for c in collections)
    except VectorStoreUnavailable as exc:
        info["available"] = False
        info["error"] = str(exc)
    except Exception as exc:
        info["available"] = False
        info["error"] = str(exc)
    return info


def timed(fn, *args, **kwargs):
    """简易计时包装，便于日志观察检索耗时。"""
    started = time.time()
    result = fn(*args, **kwargs)
    return result, (time.time() - started) * 1000
