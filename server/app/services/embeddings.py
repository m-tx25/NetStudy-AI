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
MODE_DEFAULT = "chroma-default"

_embeddings = None
_mode: str | None = None


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
    return MODE_ZHIPU if resolve_api_key() else MODE_DEFAULT


def is_zhipu_configured() -> bool:
    return bool(resolve_api_key())


def get_embeddings():
    """返回 LangChain 兼容的 Embeddings 实例（进程内复用）。"""
    global _embeddings, _mode

    if _embeddings is not None:
        return _embeddings

    api_key = resolve_api_key()
    if api_key:
        try:
            from langchain_community.embeddings import ZhipuAIEmbeddings

            # LangChain 内部通过该环境变量取 key，这里显式写回，避免两处不一致
            os.environ["ZHIPUAI_API_KEY"] = api_key
            _embeddings = ZhipuAIEmbeddings(
                model=settings.ZHIPUAI_EMBEDDING_MODEL,
                api_key=api_key,
                dimensions=settings.ZHIPUAI_EMBEDDING_DIM,
            )
            _mode = MODE_ZHIPU
            logger.info(
                "向量化使用智谱 %s（dimensions=%s）",
                settings.ZHIPUAI_EMBEDDING_MODEL,
                settings.ZHIPUAI_EMBEDDING_DIM,
            )
            return _embeddings
        except ImportError:
            logger.warning(
                "未安装 langchain-community / zhipuai，降级为 Chroma 默认嵌入函数"
            )
        except Exception as exc:  # 模型名或维度不合法等
            logger.warning("智谱向量模型初始化失败（%s），降级为 Chroma 默认嵌入函数", exc)

    _mode = MODE_DEFAULT
    logger.info("向量化使用 Chroma 默认嵌入函数（未配置 ZHIPUAI_API_KEY）")
    _embeddings = None  # 交给 Chroma 使用其内置默认实现
    return _embeddings


def describe() -> dict:
    """给 /api/health 用的自检信息。"""
    configured = is_zhipu_configured()
    return {
        "mode": current_mode(),
        "model": settings.ZHIPUAI_EMBEDDING_MODEL if configured else "chroma-default-onnx",
        "dimensions": settings.ZHIPUAI_EMBEDDING_DIM if configured else None,
        "configured": configured,
        "hint": (
            ""
            if configured
            else "未配置 ZHIPUAI_API_KEY：当前使用 Chroma 默认嵌入函数（英文语料尚可，中文效果一般）。"
            "生产环境请到 https://open.bigmodel.cn/ 申请 Key 后写入 server/.env"
        ),
    }
