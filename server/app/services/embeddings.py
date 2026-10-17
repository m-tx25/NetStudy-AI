"""向量化：智谱 embedding-3（与协作者 rag/ 模块保持一致）。

方案来源：`rag/build_db.py` 的 `build_embeddings_zhipu()`。
- 模型：embedding-3，默认 2048 维（实测版本 zhipuai 2.1.5 / langchain-community 0.4.2）
- 环境变量名必须是 **ZHIPUAI_API_KEY**（不是 ZHIPU_API_KEY）—— LangChain 的
  ZhipuAIEmbeddings 读的是前者；两个都认是为了兼容手工配置的习惯。
- 智谱单次请求最多 64 条文本，批量时留出余量。

重要：**DeepSeek 不能用于向量化**。DeepSeek 开放平台只提供文本生成模型，
没有 /embeddings 接口（请求该端点返回 404），它的 Key 只能用在生成环节。

未配置 ZHIPUAI_API_KEY 时的降级：
  使用 Chroma 内置的默认嵌入函数（ONNX MiniLM，首次使用会下载模型）。
  这样没有 API Key 也能把「上传 → 切片 → 向量化 → 检索 → 引用」整条链路跑通。
  注意它与智谱向量**不在同一向量空间**，因此两者使用**不同的 Chroma 集合**
  （见 vectorstore.collection_name），避免维度/语义冲突。
"""

from __future__ import annotations

import logging
import os

from app.core.config import settings

logger = logging.getLogger(__name__)

MODE_ZHIPU = "zhipu-embedding-3"
MODE_DEFAULT = "chroma-default"  # 历史值：早期会退化为 Chroma 内置 ONNX 模型
MODE_OFFLINE = "offline-hash"    # 现在的兜底：内置离线向量化，零依赖零下载

_embeddings = None
_mode: str | None = None
# 按 API Key 缓存 embedder：团队/用户可各自配置自己的智谱 Key（费用各算各的）。
# 注意**只换 Key、不换模型** —— 同一个 embedding-3 模型下不同 Key 产生的向量
# 是等价的（同一向量空间），因此可以安全共用同一个 Chroma 集合。
# 换模型会导致维度/语义不一致，必须换集合，故此处不支持。
_embeddings_by_key: dict[str, object] = {}


class OfflineHashEmbeddings:
    """零依赖的离线向量化（字符 n-gram 哈希投影）。

    为什么需要它：没配 ZHIPUAI_API_KEY 时，早期实现会退回 Chroma 内置的
    ONNX 模型，而该模型**首次使用要联网下载 79MB**。实测慢速网络下只有
    13~30 KB/s，等于挂死 —— 文档会一直停在「解析中」，演示直接失败。
    「开箱即用」比「向量质量最优」更重要，因此改成内置实现：不联网、
    不下载、纯 Python，进程启动即可用。

    原理：把文本切成字符 2-gram / 3-gram，对每个 gram 做 md5 取模映射到
    固定维度并累加权重，最后 L2 归一化。相同文本向量完全一致，
    共享字符片段的文本相似度更高 —— 这对中文短文本的检索已经够用，
    且与 HYBRID_SEARCH 的词面重排互补（词面分才是主要判据）。

    局限（需明确）：不具备真正的语义泛化能力（同义不同词召回不到），
    仅适合无 Key 的演示与验收。生产请配置 ZHIPUAI_API_KEY。
    """

    def __init__(self, dimensions: int = 512) -> None:
        self.dimensions = dimensions

    @staticmethod
    def _normalize(text: str) -> str:
        import unicodedata

        # NFKC：把康熙部首、全角字符等归一化，避免「流水线」搜不到
        normalized = unicodedata.normalize("NFKC", text or "")
        return " ".join(normalized.split()).lower()

    def _vector(self, text: str) -> list[float]:
        import hashlib

        vec = [0.0] * self.dimensions
        normalized = self._normalize(text)
        if not normalized:
            return vec

        length = len(normalized)
        for size in (2, 3):
            if length < size:
                continue
            for index in range(length - size + 1):
                gram = normalized[index : index + size]
                if gram.strip() == "":
                    continue
                # md5 保证跨进程/跨机器稳定（不能用 Python 内置 hash，它随机化）
                digest = hashlib.md5(gram.encode("utf-8")).digest()
                slot = int.from_bytes(digest[:4], "big") % self.dimensions
                sign = 1.0 if digest[4] % 2 == 0 else -1.0
                vec[slot] += sign * (1.0 if size == 2 else 0.6)

        norm = sum(value * value for value in vec) ** 0.5
        if norm > 0:
            vec = [value / norm for value in vec]
        return vec

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)


_offline_embeddings = OfflineHashEmbeddings()


def offline_dimensions() -> int:
    return _offline_embeddings.dimensions


def resolve_api_key() -> str:
    """从配置或环境变量取智谱 Key（两个变量名都接受）。"""
    return (
        settings.ZHIPUAI_API_KEY
        or os.getenv("ZHIPUAI_API_KEY")
        or os.getenv("ZHIPU_API_KEY")
        or ""
    )


def current_mode() -> str:
    """当前向量化模式，供 /api/health 展示。"""
    if _mode is not None:
        return _mode
    return MODE_ZHIPU if resolve_api_key() else MODE_OFFLINE


def is_zhipu_configured() -> bool:
    return bool(resolve_api_key())


def is_available() -> bool:
    """是否总能拿到一个可用的向量化实现。

    离线实现永远可用，所以恒为 True —— 保留该函数是为了让调用方
    表达「向量化是否就绪」的意图，而不用关心当前是哪种模式。
    """
    return True


def get_embeddings(api_key: str | None = None):
    """返回 LangChain 兼容的 Embeddings 实例。

    api_key 留空则用服务端配置的 Key（进程内复用）。
    传入团队/用户自己的 Key 时按 Key 缓存实例 —— 索引与检索必须用**同一个 Key**，
    否则会拿 A 的 Key 建库、用 B 的 Key 检索，虽然同模型向量空间一致（理论可行），
    但计费与限流会错位，不利于排查。

    没有任何 Key 时返回**内置离线实现**，而不是 None：
    退回 Chroma 内置 ONNX 模型需要首次联网下载 79MB，慢速网络下等于挂死，
    会让文档永远停在「解析中」。离线实现零下载，保证开箱即用。
    """
    global _embeddings, _mode

    key = (api_key or "").strip() or resolve_api_key()

    if not key:
        _mode = MODE_OFFLINE
        _embeddings = _offline_embeddings
        logger.info(
            "向量化使用内置离线实现（未配置 ZHIPUAI_API_KEY，dimensions=%s）——"
            "仅保证链路可用，语义检索效果有限，生产请配置智谱 Key",
            _offline_embeddings.dimensions,
        )
        return _embeddings

    cached = _embeddings_by_key.get(key)
    if cached is not None:
        _embeddings = cached
        _mode = MODE_ZHIPU
        return cached

    try:
        from langchain_community.embeddings import ZhipuAIEmbeddings

        # LangChain 内部通过该环境变量取 key，这里显式写回，避免两处不一致
        os.environ["ZHIPUAI_API_KEY"] = key
        instance = ZhipuAIEmbeddings(
            model=settings.ZHIPUAI_EMBEDDING_MODEL,
            api_key=key,
            dimensions=settings.ZHIPUAI_EMBEDDING_DIM,
        )
        _embeddings_by_key[key] = instance
        _embeddings = instance
        _mode = MODE_ZHIPU
        logger.info(
            "向量化使用智谱 %s（dimensions=%s，Key 来源=%s）",
            settings.ZHIPUAI_EMBEDDING_MODEL,
            settings.ZHIPUAI_EMBEDDING_DIM,
            "服务端" if key == resolve_api_key() else "团队/用户自备",
        )
        return instance
    except ImportError:
        logger.warning("未安装 langchain-community / zhipuai，降级为内置离线向量化")
    except Exception as exc:  # 模型名或维度不合法等
        logger.warning("智谱向量模型初始化失败（%s），降级为内置离线向量化", exc)

    _mode = MODE_OFFLINE
    _embeddings = _offline_embeddings
    return _embeddings


def describe() -> dict:
    """给 /api/health 用的自检信息。"""
    configured = is_zhipu_configured()
    mode = current_mode()
    if configured:
        return {
            "mode": mode,
            "model": settings.ZHIPUAI_EMBEDDING_MODEL,
            "dimensions": settings.ZHIPUAI_EMBEDDING_DIM,
            "configured": True,
            "hint": "",
        }
    return {
        "mode": mode,
        "model": "offline-hash",
        "dimensions": _offline_embeddings.dimensions,
        "configured": False,
        "hint": (
            "未配置 ZHIPUAI_API_KEY：当前使用内置离线向量化（字符 n-gram 哈希），"
            "零下载、可离线跑通全流程，但**不具备真正的语义泛化能力**（同义不同词召回不到），"
            "检索主要依赖词面命中。演示与验收够用；要更好的中文语义检索，"
            "请到 https://open.bigmodel.cn/ 申请 Key 后写入 server/.env。"
        ),
    }
