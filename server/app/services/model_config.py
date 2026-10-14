"""用户自带模型（BYOM：Bring Your Own Model）。

需求：让用户在前端自己选择/添加生成模型 ——
  · 本地部署：Ollama / vLLM / LM Studio，只要知道 baseUrl 与服务名；
  · 云端 API：任意 OpenAI 兼容服务，密钥由用户自己填写。

安全设计（重要）：
  - 密钥在服务端**加密后**入库（见 app/core/crypto.py），绝不存明文；
  - 密钥**永不下发**给前端，接口只返回 `hasApiKey` / `configured` 布尔值；
  - 按 owner_id 隔离，且查询时同时按 id + owner_id 过滤，
    因此拿到别人的模型 id 也无法引用（避免越权）。

与环境变量里的内置模型（LLM_MODELS）的关系：
  内置模型全用户共享、不可改；用户模型是**附加**选项，两者合并后供前端选择。
"""

from __future__ import annotations

import logging

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import ModelConfig, settings
from app.core.crypto import decrypt, encrypt
from app.models import UserModelConfig
from app.utils.ids import new_id

logger = logging.getLogger(__name__)

# 用户模型 id 前缀，便于与环境变量里的内置模型区分，也方便解析时判断查哪张表
USER_MODEL_PREFIX = "user:"


def is_user_model(model_id: str | None) -> bool:
    return bool(model_id) and str(model_id).startswith(USER_MODEL_PREFIX)


def _to_model_config(row: UserModelConfig) -> ModelConfig:
    return ModelConfig(
        id=row.id,
        label=row.label,
        base_url=row.base_url,
        api_key=decrypt(row.api_key),
        model=row.model_name,
        temperature=row.temperature,
        kind="local" if row.is_local else "api",
    )


async def list_user_models(db: AsyncSession, user_id: str) -> list[UserModelConfig]:
    rows = (
        await db.execute(
            select(UserModelConfig)
            .where(UserModelConfig.owner_id == user_id)
            .order_by(UserModelConfig.created_at.asc())
        )
    ).scalars().all()
    return list(rows)


async def public_list(db: AsyncSession, user_id: str) -> list[dict]:
    """下发给前端的完整清单（内置 + 用户自带）。

    **只含元信息，不含密钥**：
      - configured / hasApiKey 用于界面提示；
      - baseUrl 回显是必要的（用户需要知道自己填的是什么），密钥则绝不下发。
    """
    items: list[dict] = []

    for model in settings.available_models():
        items.append(
            {
                "id": model.id,
                "label": model.label,
                "model": model.model,
                "kind": model.kind,
                "configured": model.is_configured,
                "isDefault": model.id == settings.resolve_model(None).id,
                "builtin": True,
                "editable": False,
            }
        )

    for row in await list_user_models(db, user_id):
        items.append(
            {
                "id": row.id,
                "label": row.label,
                "model": row.model_name,
                "kind": "local" if row.is_local else "api",
                "configured": bool(row.base_url and row.model_name and decrypt(row.api_key)),
                "isDefault": False,
                "builtin": False,
                "editable": True,
                "baseUrl": row.base_url,
                "hasApiKey": bool(row.api_key),
                "isLocal": bool(row.is_local),
                "temperature": row.temperature,
            }
        )

    return items


async def resolve(db: AsyncSession, user_id: str, model_id: str | None) -> ModelConfig:
    """解析出实际使用的模型。

    优先级：用户自带模型 → 内置模型 → 内置默认模型。
    任何找不到的情况都回退到默认模型，保证问答不会因为 id 失效而直接失败。
    """
    wanted = (model_id or settings.LLM_DEFAULT_MODEL_ID or "").strip()

    if wanted and is_user_model(wanted):
        row = (
            await db.execute(
                select(UserModelConfig)
                .where(UserModelConfig.id == wanted)
                .where(UserModelConfig.owner_id == user_id)
            )
        ).scalar_one_or_none()
        if row is not None:
            return _to_model_config(row)
        logger.warning("用户模型不存在或不属于该用户：%s，回退到默认模型", wanted)

    return settings.resolve_model(wanted)


async def create(
    db: AsyncSession,
    user_id: str,
    *,
    label: str,
    base_url: str,
    api_key: str,
    model_name: str,
    is_local: bool = False,
    temperature: float | None = None,
) -> UserModelConfig:
    from app.services.llm import normalize_base_url

    row = UserModelConfig(
        id=f"{USER_MODEL_PREFIX}{new_id('um')}",
        owner_id=user_id,
        label=label.strip()[:64],
        # 保存时就规范化：剥掉误填的 /chat/completions 等端点后缀并补齐 /v1，
        # 这样界面回显的也是真正会被调用的地址
        base_url=normalize_base_url(base_url)[:255],
        api_key=encrypt(api_key.strip()),
        model_name=model_name.strip()[:128],
        is_local=is_local,
        temperature=settings.LLM_TEMPERATURE if temperature is None else float(temperature),
    )
    db.add(row)
    await db.flush()
    return row


async def update(
    db: AsyncSession,
    user_id: str,
    model_id: str,
    *,
    label: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    model_name: str | None = None,
    is_local: bool | None = None,
    temperature: float | None = None,
) -> UserModelConfig | None:
    row = (
        await db.execute(
            select(UserModelConfig)
            .where(UserModelConfig.id == model_id)
            .where(UserModelConfig.owner_id == user_id)
        )
    ).scalar_one_or_none()
    if row is None:
        return None

    if label is not None:
        row.label = label.strip()[:64]
    if base_url is not None:
        from app.services.llm import normalize_base_url

        row.base_url = normalize_base_url(base_url)[:255]
    # 密钥留空 = 不修改：界面上不回显密钥，若把空串当修改会把密钥误清空
    if api_key:
        row.api_key = encrypt(api_key.strip())
    if model_name is not None:
        row.model_name = model_name.strip()[:128]
    if is_local is not None:
        row.is_local = is_local
    if temperature is not None:
        row.temperature = float(temperature)

    await db.flush()
    return row


async def remove(db: AsyncSession, user_id: str, model_id: str) -> bool:
    result = await db.execute(
        delete(UserModelConfig)
        .where(UserModelConfig.id == model_id)
        .where(UserModelConfig.owner_id == user_id)
    )
    return bool(result.rowcount)


async def probe(db: AsyncSession, user_id: str, model_id: str) -> dict:
    """连通性自检：向该模型发一次极小的请求，返回是否可用。

    为什么需要：用户填本地模型时最常见的失败原因是「服务没启动」或「模型名写错」，
    与其等到提问时看一句报错，不如保存后立刻告诉他。
    """
    import httpx

    from app.services.llm import normalize_base_url

    model = await resolve(db, user_id, model_id)
    if not model.is_configured:
        return {"ok": False, "reason": "未配置完成（缺少 baseUrl / 模型名 / 密钥）"}

    # 用与真实调用完全相同的拼接方式，避免「探测通过但提问失败」这类不一致
    url = f"{normalize_base_url(model.base_url)}/chat/completions"

    payload = {
        "model": model.model,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 1,
        "stream": False,
    }
    headers = {"Content-Type": "application/json"}
    if model.api_key:
        # 兜底：历史数据里可能存有含非 ASCII 字符的密钥（入口校验是后加的）。
        # HTTP 头只能承载 ASCII，直接发会抛 UnicodeEncodeError 变成 500，
        # 这里提前判定并给出可读原因。
        try:
            model.api_key.encode("ascii")
        except UnicodeEncodeError as exc:
            bad = model.api_key[exc.start : exc.end]
            return {
                "ok": False,
                "reason": f"API Key 含非 ASCII 字符（{bad!r}），无法用于请求头",
                "url": url,
                "hint": "请在「编辑模型」中重新粘贴密钥，只保留密钥本身，不要带中文说明或全角符号",
            }
        headers["Authorization"] = f"Bearer {model.api_key}"

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=6.0)) as client:
            response = await client.post(url, json=payload, headers=headers)
        if response.status_code >= 400:
            detail = response.text[:300]
            hint = ""
            # 模型名不受支持是最常见的 400 原因：服务商通常会在报错里列出可用名字，
            # 这里直接转成可操作的提示，省得用户去猜。
            lowered = detail.lower()
            if response.status_code == 400 and "model" in lowered:
                hint = (
                    "看起来是「模型名不受支持」。请把上面的报错读一下 —— "
                    "服务商一般会写明支持哪些模型名，把「模型名」改成其中之一再试。"
                )
            elif response.status_code == 401:
                hint = "密钥无效或已过期，请到服务商控制台重新生成一个。"
            elif response.status_code == 402 or "insufficient" in lowered:
                hint = "账户余额不足，请先充值。"
            elif response.status_code == 429:
                hint = "触发限流，稍后再试，或升级配额。"
            elif response.status_code == 404:
                hint = "接口路径不存在：请检查「接口地址」是否只填到 /v1，不要带 /chat/completions。"
            # 把实际请求的地址一并回显：路径或模型名拼错时一眼就能看出来
            return {
                "ok": False,
                "reason": f"HTTP {response.status_code}：{detail}",
                "url": url,
                "hint": hint,
            }
        return {"ok": True, "url": url, "model": model.model}
    except httpx.HTTPError as exc:
        return {
            "ok": False,
            "reason": f"无法连接：{exc}",
            "url": url,
            "hint": (
                "若为本地模型，请确认服务已启动（如 ollama serve），"
                "并核对 baseUrl 端口是否正确"
            ),
        }
    except Exception as exc:  # 兜底：任何异常都转成可读结果，不让接口 500
        logger.exception("探测模型时出现未预期错误 id=%s", model_id)
        return {"ok": False, "reason": f"探测失败：{exc}", "url": url}


# --------------------------------------------------------------------------
# 内置「本地模型」预设：让用户一键预填常见本地推理服务，不必记端口
# --------------------------------------------------------------------------
LOCAL_PRESETS: list[dict] = [
    {
        "id": "ollama",
        "label": "Ollama（本机）",
        "baseUrl": "http://127.0.0.1:11434/v1",
        "model": "qwen2.5:7b",
        "hint": "需先安装 Ollama，并执行 ollama pull qwen2.5:7b 拉取模型",
    },
    {
        "id": "vllm",
        "label": "vLLM（本机）",
        "baseUrl": "http://127.0.0.1:8000/v1",
        "model": "Qwen/Qwen2.5-7B-Instruct",
        "hint": "vLLM 默认监听 8000 端口",
    },
    {
        "id": "lmstudio",
        "label": "LM Studio（本机）",
        "baseUrl": "http://127.0.0.1:1234/v1",
        "model": "local-model",
        "hint": "LM Studio 需在设置中开启本地服务器（Developer → Start Server）",
    },
]
