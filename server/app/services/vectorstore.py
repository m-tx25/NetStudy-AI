"""向量库：ChromaDB 持久化客户端。

方案来源：协作者的 `rag/build_db.py` / `rag/query_db.py`，本模块把它生产化：
  1. 用**单一集合 + 元数据过滤**实现多用户/多知识库隔离
     （他们的脚本是单文件单集合，没有 owner 概念）；
  2. 保留 rpd 的**混合检索**：0.5×向量相似度 + 0.5×词面命中，
     术语/公式/手册类文档下比纯向量稳；
  3. 文档停用/删除时同步从向量库移除，避免检索到已失效内容。

与 rag 脚本的差异（有意为之）：
  - 集合名带后缀区分向量空间：智谱 embedding-3 与 Chroma 默认 ONNX 模型的向量
    **不可混用**，Chroma 在集合创建时就固定了维度，混用会直接报维度错误。
  - 距离转相似度：Chroma 默认 L2 距离，做 1 - d/2 归一化到 0~1，
    以便前端按百分比展示（前端对 0~1 与 0~100 都能识别）。
"""

from __future__ import annotations

import logging
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


def collection_name() -> str:
    """按向量化模式区分集合，避免两种向量空间混入同一集合。"""
    suffix = "zhipu2048" if embeddings.is_zhipu_configured() else "default"
    return f"{settings.CHROMA_COLLECTION}_{suffix}"


def _persist_dir() -> Path:
    directory = Path(settings.CHROMA_PERSIST_DIR)
    if not directory.is_absolute():
        directory = Path.cwd() / directory
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def get_client():
    global _client
    if _client is not None:
        return _client
    try:
        import chromadb
    except ImportError as exc:  # pragma: no cover
        raise VectorStoreUnavailable(
            "未安装 chromadb，请执行 pip install -r requirements.txt"
        ) from exc

    try:
        _client = chromadb.PersistentClient(path=str(_persist_dir()))
    except Exception as exc:  # 目录不可写、版本不兼容等
        raise VectorStoreUnavailable(f"初始化 ChromaDB 失败：{exc}") from exc
    return _client


def get_collection():
    """获取（必要时创建）集合。

    注意：这里**不传 embedding_function**。
    本模块用的是原生 `chromadb.PersistentClient`，而 chromadb 1.5.x 要求
    embedding function 实现其自有接口（`name()` / `__call__` / `is_legacy` …）。
    LangChain 的 `ZhipuAIEmbeddings` 只实现了 `embed_query` / `embed_documents`，
    传进来会在集合创建时抛：

        'ZhipuAIEmbeddings' object has no attribute 'name'

    因此统一改为**调用方自己算向量再显式传入**（与 search() 的写法一致）：
      - `upsert(..., embeddings=[...])`  ← 见 upsert_document
      - `query(query_embeddings=[...])`  ← 见 search
    需要 Chroma 默认嵌入（未配置智谱 Key 时）的场景，则传 `query_texts` / 不传
    embeddings，让 Chroma 用内置 ONNX 模型自行处理。
    """
    client = get_client()
    kwargs: dict[str, Any] = {
        "name": collection_name(),
        # 显式声明距离度量，便于日后换 cosine 时行为可预期
        "metadata": {"hnsw:space": "l2", "embedding": embeddings.current_mode()},
    }

    try:
        return client.get_or_create_collection(**kwargs)
    except Exception as exc:
        raise VectorStoreUnavailable(f"打开向量集合失败：{exc}") from exc


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
    chunks: list[tuple[int, str, int | None]],
    team_id: str | None = None,
) -> int:
    """写入切片。chunks 为 [(ordinal, content, page_label)]。

    page_label 是人类可读页码（1 基）；Markdown/Word 无分页概念时传 None。

    owner_id 恒为**操作人（上传者）的用户 id**；团队知识库额外传 team_id。
    这样检索时既能按人过滤（个人库），也能按团队过滤（团队库），
    而不会出现「团队库的 owner_id 是团队 id、和用户 id 对不上」的错位。
    """
    if not chunks:
        return 0

    collection = get_collection()

    ids: list[str] = []
    documents: list[str] = []
    metadatas: list[dict[str, Any]] = []

    for ordinal, content, page in chunks:
        text = (content or "").strip()
        if not text:
            continue
        # 稳定 ID：同一文档重复写入会覆盖而不是堆积
        chunk_id = f"{document_id}:{ordinal:05d}"
        ids.append(chunk_id)
        documents.append(text)
        metadatas.append(
            {
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
            }
        )

    if not ids:
        return 0

    # 分批写入，避免单次请求过大（智谱 embedding 单次最多 64 条）
    batch = 32
    written = 0
    embedder = embeddings.get_embeddings()  # 智谱时为 LangChain Embeddings；未配置时为 None

    for start in range(0, len(ids), batch):
        end = start + batch
        payload: dict[str, Any] = {
            "ids": ids[start:end],
            "documents": documents[start:end],
            "metadatas": metadatas[start:end],
        }
        # 智谱模式：自己算向量后显式传入（不依赖集合上的 embedding_function，
        # 原生 chromadb 与 LangChain 的 Embeddings 接口并不兼容，见 get_collection 注释）
        if embedder is not None:
            payload["embeddings"] = embedder.embed_documents(documents[start:end])
        # 未配置智谱 Key 时不传 embeddings，交给 Chroma 内置 ONNX 模型
        collection.upsert(**payload)
        written += len(ids[start:end])

    return written


# --------------------------------------------------------------------------
# 删除
# --------------------------------------------------------------------------
def _delete_where(where: dict[str, Any]) -> int:
    collection = get_collection()
    try:
        existing = collection.get(where=where, include=[])
        count = len(existing.get("ids") or [])
        if count:
            collection.delete(where=where)
        return count
    except Exception as exc:  # 集合为空等
        logger.warning("删除向量失败 where=%s: %s", where, exc)
        return 0


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

    try:
        collection = get_collection()
        if not where:
            return int(collection.count())
        result = collection.get(where=where, include=[])
        return len(result.get("ids") or [])
    except Exception as exc:
        logger.warning("统计向量数量失败：%s", exc)
        return 0


def count_by_knowledge_base(knowledge_base_ids: list[str]) -> dict[str, int]:
    """批量统计每个知识库的切片数，避免列表接口 N+1。"""
    if not knowledge_base_ids:
        return {}
    try:
        collection = get_collection()
        counts: dict[str, int] = {kb_id: 0 for kb_id in knowledge_base_ids}
        # Chroma 的 $in 过滤器对空列表不友好，但这里已保证非空
        result = collection.get(
            where={"knowledge_base_id": {"$in": list(knowledge_base_ids)}}, include=["metadatas"]
        )
        for metadata in result.get("metadatas") or []:
            kb_id = (metadata or {}).get("knowledge_base_id")
            if kb_id in counts:
                counts[kb_id] += 1
        return counts
    except Exception as exc:
        logger.warning("按知识库统计向量失败：%s", exc)
        return {kb_id: 0 for kb_id in knowledge_base_ids}


# --------------------------------------------------------------------------
# 检索
# --------------------------------------------------------------------------
def search(
    db: Any,  # 保留形参以兼容既有调用签名（引擎层传入会话），当前实现不需要数据库
    query_text: str,
    *,
    owner_id: str,
    knowledge_base_ids: list[str] | None = None,
    top_k: int = 5,
    score_threshold: float = 0.2,
    hybrid: bool | None = None,
    team_ids: list[str] | None = None,
) -> list[RetrievedChunk]:
    """检索相关切片。

    实现要点：
      - owner_id / team_ids 在**向量库层面**过滤，确保不会跨用户、跨团队召回
        （安全边界）。团队知识库的切片带 team_id，只要提问者是该团队成员
        就应能召回 —— 这正是「团队知识库」的意义；
      - knowledge_base_ids 在候选集上二次过滤（Chroma 的 $in 对动态列表较脆弱）；
      - 混合检索开启时先取较大候选池，再用 0.5×向量 + 0.5×词面 重排。
    """
    use_hybrid = settings.HYBRID_SEARCH if hybrid is None else hybrid
    limit = max(1, top_k)

    # 归属过滤：我的个人库切片 + 我所在团队的团队库切片
    scope_conditions: list[dict[str, Any]] = [{"owner_id": owner_id}]
    if team_ids:
        scope_conditions.append({"team_id": {"$in": list(team_ids)}})
    where: dict[str, Any] = (
        scope_conditions[0] if len(scope_conditions) == 1 else {"$or": scope_conditions}
    )

    try:
        collection = get_collection()
        n_fetch = max(limit, HYBRID_POOL) if use_hybrid else limit

        if embeddings.is_zhipu_configured():
            query_vector = embeddings.get_embeddings().embed_query(query_text)
            result = collection.query(
                query_embeddings=[query_vector],
                n_results=n_fetch,
                where=where,
                include=["documents", "metadatas", "distances"],
            )
        else:
            result = collection.query(
                query_texts=[query_text],
                n_results=n_fetch,
                where=where,
                include=["documents", "metadatas", "distances"],
            )
    except VectorStoreUnavailable:
        raise
    except Exception as exc:
        logger.warning("向量检索失败：%s", exc)
        return []

    documents = (result.get("documents") or [[]])[0]
    metadatas = (result.get("metadatas") or [[]])[0]
    distances = (result.get("distances") or [[]])[0]
    ids = (result.get("ids") or [[]])[0]

    allowed = set(knowledge_base_ids) if knowledge_base_ids else None

    candidates: list[RetrievedChunk] = []
    for index, content in enumerate(documents):
        metadata = (metadatas[index] if index < len(metadatas) else {}) or {}
        if allowed is not None and metadata.get("knowledge_base_id") not in allowed:
            continue

        distance = distances[index] if index < len(distances) else None
        page = metadata.get("page_label")
        candidates.append(
            RetrievedChunk(
                chunk_id=ids[index] if index < len(ids) else f"#{index}",
                document_id=str(metadata.get("document_id") or ""),
                document_name=str(metadata.get("document_name") or ""),
                knowledge_base_id=str(metadata.get("knowledge_base_id") or ""),
                knowledge_base_name=str(metadata.get("knowledge_base_name") or ""),
                content=content or "",
                page=int(page) if isinstance(page, int) and page > 0 else None,
                score=_distance_to_similarity(distance),
                ordinal=int(metadata.get("ordinal") or 0),
                lexical=lexical_score(query_text, content or ""),
            )
        )

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

    filtered = [item for item in candidates if item.score >= score_threshold]
    if filtered:
        return filtered[:limit]

    # 阈值过滤后为空但确有候选：退化为 Top-K。
    # 原因见 docs/development-report.md 9.9：弱向量模型下相似度整体偏低，
    # 严格套用阈值会导致「传了文档却总说未找到依据」。
    return candidates[:limit]


def health() -> dict[str, Any]:
    """向量库自检，供 /api/health 展示。"""
    info: dict[str, Any] = {
        "collection": collection_name(),
        "persistDir": str(_persist_dir()),
        "embedding": embeddings.describe(),
        "hybridSearch": settings.HYBRID_SEARCH,
    }
    try:
        collection = get_collection()
        info["available"] = True
        info["totalChunks"] = int(collection.count())
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
