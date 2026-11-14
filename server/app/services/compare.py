# -*- coding: utf-8 -*-
"""多篇论文智能对比（模块五 / P0）。

## 为什么必须两阶段

需求里最关键的一句是「不能简单地把几篇论文分别总结后放在一起」。
如果把 N 篇全文直接塞给模型让它「对比」，模型几乎必然退化成逐篇罗列 ——
既超上下文，又拿不到真正的横向结论。

因此拆成：

    阶段 A  每篇论文 → 结构化卡片（研究问题/方法/实验/指标/创新/局限/未来工作，带页码）
    阶段 B  卡片集合 → ① 自动归纳对比维度  ② 逐维度填矩阵
                       ③ 演进时间轴 + 研究空白  ④ 场景胜负结论

阶段 A 的结果按 document_id 缓存（`paper_profiles` 表），
同一篇论文重复参与对比不会重复烧钱；阶段 B 的产物全部落库，
重新打开对比页不再调用模型。

## 防幻觉的三道闸

1. 取样文本带 `[[PAGE n]]` 标记，要求模型按页码引用；
2. 落库前校验引用页码是否落在该论文实际页数内，越界即丢弃；
3. 矩阵单元格带 `confidence`：`explicit`（原文明确写了）/ `inferred`（推断）/
   `missing`（未提及）—— 前端对后两种做淡色标注，避免把推断当事实。
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import Comparison, Document, PaperProfile, now_utc
from app.services import keyring, llm, parser
from app.utils.ids import new_id

logger = logging.getLogger(__name__)

PROMPT_VERSION = "v1"

# 每篇论文取样上限（字符）。英文约 28k 字符 ≈ 7k token，
# 足够覆盖「摘要 + 引言 + 方法/实验 + 结论」，且单篇一次调用不会超上下文。
MAX_SAMPLE_CHARS = 28000
# 单篇卡片压缩后进入阶段 B 的字符上限
MAX_CARD_CHARS = 2200

# 用于挑选「方法/实验」页的关键词（英文论文为主，中文论文也覆盖常见词）
_SECTION_HINTS = (
    "experiment",
    "evaluation",
    "results",
    "dataset",
    "method",
    "approach",
    "实验",
    "结果",
    "方法",
    "数据集",
)


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------
def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _loads(text: str, default: Any) -> Any:
    if not text:
        return default
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return default


def _loads_llm_json(text: str) -> Any:
    """从模型输出里抠出 JSON。

    模型常见毛病：外面裹 ```json 围栏、前后加一句「好的，以下是结果」、
    或者在 JSON 后面再补一段解释。这里逐个兜底。
    """
    raw = (text or "").strip()
    if not raw:
        return None
    # 去掉代码围栏
    fence = re.search(r"```(?:json)?\s*(.+?)```", raw, re.S)
    if fence:
        raw = fence.group(1).strip()
    try:
        return json.loads(raw)
    except ValueError:
        pass
    # 取第一个 { 到最后一个 } / 第一个 [ 到最后一个 ]
    for left, right in (("{", "}"), ("[", "]")):
        start, end = raw.find(left), raw.rfind(right)
        if start != -1 and end > start:
            try:
                return json.loads(raw[start : end + 1])
            except ValueError:
                continue
    return None


def _as_text(value: Any, limit: int = 4000) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()[:limit]
    if isinstance(value, (list, tuple)):
        return "\n".join(_as_text(item, limit) for item in value if item)[:limit]
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)[:limit]
    return str(value)[:limit]


def _as_list(value: Any, limit: int = 8) -> list[str]:
    if isinstance(value, list):
        items = [str(item).strip() for item in value if str(item).strip()]
    elif isinstance(value, str) and value.strip():
        items = [line.strip(" -•") for line in value.splitlines() if line.strip()]
    else:
        items = []
    return items[:limit]


def _as_page(value: Any, page_count: int) -> int | None:
    """把模型给的页码解析成正整数。

    模型很爱写 `"p1"` / `"p.5"` / `"第 3 页"` —— 直接 int() 会失败，
    于是页码全被丢掉（实测：矩阵 0 个单元格带页码，就是这么来的）。
    这里只从字符串里抠出第一个整数。
    """
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, str):
        match = re.search(r"\d+", value)
        if not match:
            return None
        value = match.group(0)
    try:
        page = int(value)
    except (TypeError, ValueError):
        return None
    if page < 1 or (page_count and page > page_count):
        return None
    return page


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# 阶段 A：抽样一篇论文
# ---------------------------------------------------------------------------
@dataclass
class SampledPaper:
    text: str
    page_count: int


def _page_no(meta: dict[str, Any]) -> int | None:
    """从解析元数据里取「人类可读页码」（1 基）。

    注意：PyPDFLoader 给的 `page_label` 是**字符串**（如 "1"），
    而 `page` 是 0 基整数。两种都要兼容，否则会一条都取不到
    （踩过：只判 isinstance(int) 导致取样结果为空）。
    """
    label = meta.get("page_label")
    if label is not None:
        try:
            value = int(str(label).strip())
            if value >= 1:
                return value
        except (TypeError, ValueError):
            pass
    page = meta.get("page")
    if isinstance(page, int):
        return page + 1
    try:
        return int(page) + 1
    except (TypeError, ValueError):
        return None


def sample_paper(path: str | Path) -> SampledPaper:
    """把论文 PDF 取成「有页标记的片段集」。

    取样策略（不是简单截断，也不是全文）：
      1. 前 3 页 —— 标题/作者/摘要/引言；
      2. 含 experiment / results / dataset 等关键词的页，最多 3 页 —— 实验设置与指标；
      3. 最后 2 页 —— 结论与 future work；
    去重后按页码排序，拼成带 `[[PAGE n]]` 标记的文本，再按字符上限截断。
    """
    documents = parser.parse_document(path)
    pages: dict[int, str] = {}
    for item in documents:
        meta = item.metadata or {}
        page = _page_no(meta)
        if page is None:
            continue
        pages[page] = (pages.get(page, "") + "\n" + (item.page_content or "")).strip()

    if not pages:
        return SampledPaper(text="", page_count=0)

    ordered = sorted(pages)
    page_count = max(ordered)

    def block_of(page: int) -> str:
        return f"\n[[PAGE {page}]]\n{pages[page].strip()}\n"

    # 优先级 1：首 2 页（标题/摘要/引言）+ 末 2 页（结论/future work）—— 必取
    essential = list(dict.fromkeys(ordered[:2] + ordered[-2:]))
    # 优先级 2：中段里提到 experiment / results / dataset 的页 —— 对比的原料
    middle = [
        p
        for p in ordered
        if p not in essential
        and any(hint in pages[p].lower() for hint in _SECTION_HINTS)
    ][:4]

    chosen: list[int] = []
    used = 0
    for page in essential:
        chunk = block_of(page)
        if used + len(chunk) > MAX_SAMPLE_CHARS:
            chosen.append(page)
            break
        chosen.append(page)
        used += len(chunk)
    for page in middle:
        chunk = block_of(page)
        if used + len(chunk) > MAX_SAMPLE_CHARS:
            continue
        chosen.append(page)
        used += len(chunk)

    text = "".join(block_of(page) for page in sorted(set(chosen)))
    if len(text) > MAX_SAMPLE_CHARS:
        text = text[:MAX_SAMPLE_CHARS]
    return SampledPaper(text=text, page_count=page_count)


# ---------------------------------------------------------------------------
# 阶段 A：抽取卡片
# ---------------------------------------------------------------------------
CARD_SYSTEM = """你是一名严谨的学术论文信息抽取助手。
只依据用户给出的论文原文片段作答，**不要补充原文没有的信息**。
输出必须是合法 JSON，不要任何解释性文字、不要 Markdown 围栏。"""

CARD_USER = """下面是论文《{name}》的原文片段（含 [[PAGE n]] 页标记）。

请抽取以下字段，输出 JSON：

{{
  "title": "论文标题（原文语言）",
  "authors": "作者，逗号分隔；看不出就留空",
  "year": 发表年份（整数，看不出填 0）,
  "venue": "期刊/会议/arXiv，看不出留空",
  "research_problem": "这篇论文要解决什么问题（2~4 句）",
  "method_family": "方法大类，如 检索增强生成 / 调度算法 / 联邦学习（不超过 20 字）",
  "key_technique": "关键技术或算法（具体名称 + 一句话说明）",
  "dataset": "数据集与实验环境（列出名称）",
  "metrics": [{{"name": "指标名", "value": "数值", "page": 页码}}],
  "main_results": "主要实验结果（带具体数字）",
  "innovations": ["创新点 1", "创新点 2"],
  "limitations": ["局限 1", "局限 2"],
  "future_work": ["作者提出的未来方向 1"],
  "citations": {{"research_problem": 页码, "key_technique": 页码, "main_results": 页码}}
}}

要求：
- 页码必须是 `[[PAGE n]]` 里真实出现的数字；
- 原文确实没写的字段填 "" 或 []，**不要编造**；
- metrics 最多 6 条，innovations/limitations 最多 5 条，future_work 最多 4 条；
- 全部用中文表述（标题、作者、venue 保留原文）。

论文片段：
{text}
"""


async def extract_card(
    db: AsyncSession,
    document: Document,
    *,
    model: llm.ModelConfig | None = None,
    force: bool = False,
) -> PaperProfile:
    """抽取（或复用）一篇论文的结构化卡片。"""
    existing = (
        await db.execute(
            select(PaperProfile).where(PaperProfile.document_id == document.id)
        )
    ).scalar_one_or_none()

    if existing is not None and not force and existing.status == "ready":
        return existing

    profile = existing or PaperProfile(
        id=new_id("paper"),
        document_id=document.id,
        knowledge_base_id=document.knowledge_base_id,
    )
    profile.extractor_version = PROMPT_VERSION

    path = Path(document.stored_path)
    if not document.stored_path or not path.exists():
        profile.status = "failed"
        profile.error = "原始文件不存在，无法抽取"
        db.add(profile)
        await db.commit()
        return profile

    try:
        sampled = await asyncio.to_thread(sample_paper, path)
        if not sampled.text.strip():
            raise ValueError("未能从 PDF 中解析出可用文本（可能是扫描件）")

        answer = await llm.complete(
            [
                {"role": "system", "content": CARD_SYSTEM},
                {
                    "role": "user",
                    "content": CARD_USER.format(
                        name=document.name, text=sampled.text
                    ),
                },
            ],
            model=model,
            temperature=0.1,
        )
        data = _loads_llm_json(answer)
        if not isinstance(data, dict):
            raise ValueError("模型返回的不是合法 JSON")

        citations = data.get("citations") if isinstance(data.get("citations"), dict) else {}
        valid_citations = {}
        for key, value in citations.items():
            page = _as_page(value, sampled.page_count)
            if page:
                valid_citations[str(key)] = page

        metrics = []
        for item in (data.get("metrics") or [])[:6]:
            if not isinstance(item, dict):
                continue
            metrics.append(
                {
                    "name": _as_text(item.get("name"), 120),
                    "value": _as_text(item.get("value"), 120),
                    "page": _as_page(item.get("page"), sampled.page_count),
                }
            )

        profile.title = _as_text(data.get("title"), 500) or document.name
        profile.authors = _as_text(data.get("authors"), 500)
        try:
            profile.year = int(data.get("year") or 0)
        except (TypeError, ValueError):
            profile.year = 0
        if not profile.year:
            # 模型没给出年份时用文件名兜底（arXiv 文件名带 YYMM）
            profile.year = _infer_year(document.name) or _infer_year(profile.title)
        profile.venue = _as_text(data.get("venue"), 200)
        profile.research_problem = _as_text(data.get("research_problem"))
        profile.method_family = _as_text(data.get("method_family"), 200)
        profile.key_technique = _as_text(data.get("key_technique"))
        profile.dataset = _as_text(data.get("dataset"))
        profile.main_results = _as_text(data.get("main_results"))
        profile.metrics_json = _dumps(metrics)
        profile.innovations_json = _dumps(_as_list(data.get("innovations")))
        profile.limitations_json = _dumps(_as_list(data.get("limitations")))
        profile.future_work_json = _dumps(_as_list(data.get("future_work")))
        profile.citations_json = _dumps(valid_citations)
        profile.page_count = sampled.page_count
        profile.status = "ready"
        profile.error = ""
        profile.updated_at = now_utc()

        db.add(profile)
        await db.commit()
        await db.refresh(profile)
        logger.info(
            "论文卡片抽取完成：%s（%s 页，%s 条指标）",
            document.name, sampled.page_count, len(metrics),
        )
        return profile
    except Exception as exc:  # 单篇失败不应让整次对比崩掉
        logger.warning("论文卡片抽取失败 %s: %s", document.name, exc)
        profile.status = "failed"
        profile.error = f"{type(exc).__name__}: {exc}"[:1000]
        profile.updated_at = now_utc()
        db.add(profile)
        await db.commit()
        return profile


def card_brief(profile: PaperProfile, document_name: str) -> str:
    """把卡片压成紧凑文本，用于阶段 B 的提示词。

    **必须带上页码索引**：阶段 B 的矩阵要求逐格引用原文页码，
    如果这里不给页码，模型只能返回 null（实测第一版就是 0 个单元格带页码）。
    """
    metrics = _loads(profile.metrics_json, [])
    metric_text = "; ".join(
        f"{m.get('name')}={m.get('value')}" + (f"(p{m['page']})" if m.get("page") else "")
        for m in metrics
        if m.get("name")
    )
    citations = _loads(profile.citations_json, {})
    page_hint = ", ".join(
        f"{key}=p{value}" for key, value in citations.items() if value
    )
    brief = (
        f"【论文 documentId={profile.document_id}】\n"
        f"标题: {profile.title or document_name}\n"
        f"年份: {profile.year or '未知'}  来源: {profile.venue or '未知'}\n"
        f"方法大类: {profile.method_family}\n"
        f"研究问题: {profile.research_problem}\n"
        f"关键技术: {profile.key_technique}\n"
        f"数据集: {profile.dataset}\n"
        f"评价指标: {metric_text}\n"
        f"主要结果: {profile.main_results}\n"
        f"创新点: {' / '.join(_loads(profile.innovations_json, []))}\n"
        f"局限: {' / '.join(_loads(profile.limitations_json, []))}\n"
        f"未来工作: {' / '.join(_loads(profile.future_work_json, []))}\n"
        f"页码索引: {page_hint or '无'}\n"
    )
    return brief[:MAX_CARD_CHARS]


# ---------------------------------------------------------------------------
# 阶段 B：维度 / 矩阵 / 趋势 / 空白 / 结论
# ---------------------------------------------------------------------------
SHARED_RULES = """硬性要求：
1. 这是**多篇论文的横向对比**，不是逐篇总结。禁止写成「论文 A 讲了…论文 B 讲了…」的流水账。
2. 每一条结论都必须**至少涉及两篇论文**的关系（相同点、差异、优劣、先后演进）。
3. 引用页码时只能用卡片的 documentId + 原文页码；不确定就标 missing。
4. 只说卡片里有的内容，不要补充常识。
5. 输出必须是合法 JSON，不要任何解释性文字或 Markdown 围栏。"""

DIMENSION_USER = """下面是 {count} 篇论文的结构化卡片：

{cards}

请归纳出 **{min_dims}~{max_dims} 个真正能区分这些论文的对比维度**（不要用「标题」「作者」这类无意义维度）。
优先覆盖：研究目标、方法/算法路线、实验环境与数据、评价指标、创新点、局限。

输出 JSON：
{{
  "dimensions": [
    {{"key": "英文短语，如 optimization_objective", "label": "中文维度名，不超过 10 字", "why": "为什么这个维度能区分它们（一句话）"}}
  ]
}}
"""

MATRIX_USER = """下面是 {count} 篇论文的结构化卡片：

{cards}

需要按以下维度逐格填写：

{dimensions}

输出 JSON：
{{
  "matrix": [
    {{
      "dimension": "维度 label",
      "cells": [
        {{"documentId": "doc_xxx", "value": "该论文在这个维度上的具体做法/数据（不超过 80 字）", "page": 页码或 null, "confidence": "explicit|inferred|missing"}}
      ]
    }}
  ]
}}

要求：
- 每行必须覆盖**全部** {count} 篇论文，缺一篇都不行；
- `confidence`：原文明确写了=explicit；由原文推断=inferred；没提到=missing（value 留空）；
- `page` 必须取自该论文卡片里的「页码索引」或指标后的 `(pN)`；
  确实没有页码依据就填 null，**不要瞎猜**；
- 数值类结论必须带数字（如「mAP 提升 3.2」），不要写「效果更好」这种空话。
"""

TREND_AND_GAP_USER = """下面是 {count} 篇论文的结构化卡片：

{cards}

请完成两件事：

1. **研究方向演进**：按年份梳理这一领域怎么发展（能力/范式的变化），不是罗列论文。
2. **研究空白**：找出这些论文**共同**没有充分解决的问题，或提出但没人做的方向。

输出 JSON：
{{
  "timeline": [
    {{"year": 2020, "documentId": "doc_xxx", "label": "该论文的定位（不超过 20 字）", "method": "方法大类"}}
  ],
  "trends": [
    {{"period": "2020 → 2023", "summary": "演进描述，必须提到至少两篇论文的差异", "evidence": [{{"documentId": "doc_xxx", "page": 页码}}]}}
  ],
  "gaps": [
    {{"gap": "空白/未解决问题（不超过 60 字）", "kind": "common_limitation|open_question|unexplored", "evidence": [{{"documentId": "doc_xxx", "page": 页码}}], "why": "为什么说它是空白（一句话）"}}
  ]
}}

要求：timeline 覆盖全部论文；gaps 给 3~5 条，必须能追溯到具体论文的 limitations / future_work。
"""

VERDICT_USER = """下面是 {count} 篇论文的结构化卡片：

{cards}

请给出**可操作的横向结论**：

1. `verdict`：一段话总结这批论文的总体格局（谁提出什么范式、后续怎么演进），不超过 200 字。
2. `scenarios`：在 3~5 个具体场景下，哪篇/哪类方法更合适，并说明理由（必须引用指标或实验条件）。

输出 JSON：
{{
  "verdict": "...",
  "scenarios": [
    {{"scenario": "场景描述（不超过 30 字）", "better": "documentId 或方法名", "reason": "为什么（带数字或实验条件）"}}
  ]
}}

{shared_rules}
"""


async def _chat_json(
    prompt: str,
    *,
    model: llm.ModelConfig | None,
    temperature: float = 0.2,
) -> Any:
    answer = await llm.complete(
        [
            {"role": "system", "content": "你是学术综述写作与对比分析专家，输出严格 JSON。"},
            {"role": "user", "content": prompt},
        ],
        model=model,
        temperature=temperature,
    )
    data = _loads_llm_json(answer)
    if data is None:
        raise ValueError(f"模型输出无法解析为 JSON（前 120 字：{answer[:120]}）")
    return data


async def resolve_compare_model(db: AsyncSession, user_id: str, team_id: str) -> Any:
    """对比用哪把 Key：团队库优先团队 Key，否则用提问者个人 Key，最后服务端。"""
    try:
        resolved = await keyring.resolve_chat_key(
            db, team_id=team_id or None, user_id=None if team_id else user_id
        )
    except Exception:
        return None
    if resolved.usable and resolved.source in ("team", "user"):
        from dataclasses import replace

        return replace(
            settings.resolve_model(None),
            api_key=resolved.secret,
            model=resolved.model or settings.resolve_model(None).model,
            base_url=resolved.base_url or settings.resolve_model(None).base_url,
        )
    return None


# ---------------------------------------------------------------------------
# 报告渲染（确定性：由结构化结果拼装，不由模型直接写）
# ---------------------------------------------------------------------------
def _infer_year(name: str) -> int:
    """从文件名推断发表年份（模型没给出年份时的兜底）。

    arXiv 文件名形如 `2312.10997v5.pdf`，前四位是 YYMM → 2023 年 12 月。
    实测综述类 PDF 首页常拿不到年份，时间轴会因此丢掉一两条。
    """
    if not name:
        return 0
    base = name.rsplit("\\", 1)[-1].rsplit("/", 1)[-1]
    # 必须先判 arXiv 格式：`2005.11401` 的前四位会被下面的「显式年份」
    # 误判成 2005 年（实测踩过），实际是 2020 年 5 月。
    arxiv = re.match(r"(\d{2})(\d{2})\.\d{4,5}", base)
    if arxiv:
        year = 2000 + int(arxiv.group(1))
        if 2000 <= year <= 2100:
            return year
    explicit = re.search(r"(?<!\d)(20\d{2})(?!\d)", base)
    if explicit:
        return int(explicit.group(1))
    return 0


def _short_title(profile: PaperProfile, limit: int = 34) -> str:
    """给表格/结论用的短标题：主标题（冒号前）+ 年份。

    完整标题在表格里会挤成一坨，用户反而认不出是哪篇。
    """
    title = (profile.title or profile.document_id).split(":")[0].strip()
    if len(title) > limit:
        title = title[:limit].rstrip() + "…"
    if profile.year:
        return f"{title} ({profile.year})"
    return title


def _humanize_refs(text: str, profiles: list[PaperProfile]) -> str:
    """把正文里的 documentId 换成论文短标题。

    模型很爱在结论文本里直接写 `doc_xxx`；对用户毫无意义。
    """
    if not text:
        return text
    for profile in profiles:
        if not profile.document_id:
            continue
        text = text.replace(profile.document_id, f"《{_short_title(profile)}》")
    return text


def render_report_md(
    comparison: Comparison,
    profiles: list[PaperProfile],
    document_names: dict[str, str],
) -> str:
    dimensions = _loads(comparison.dimensions_json, [])
    matrix = _loads(comparison.matrix_json, [])
    trends = _loads(comparison.trends_json, {})
    gaps = _loads(comparison.gaps_json, [])
    scenarios = _loads(comparison.scenarios_json, [])

    name_of = {p.document_id: (p.title or document_names.get(p.document_id, p.document_id)) for p in profiles}

    lines: list[str] = []
    title = comparison.topic.strip() or "多篇论文对比报告"
    lines.append(f"# {title}")
    lines.append("")
    lines.append(f"> 由 NetStudy-AI 自动生成 · {_now_iso()[:19]} · 共 {len(profiles)} 篇论文")
    lines.append("")

    if comparison.verdict:
        lines.append("## 一、总体结论")
        lines.append("")
        lines.append(comparison.verdict.strip())
        lines.append("")

    if scenarios:
        lines.append("## 二、场景适配建议")
        lines.append("")
        lines.append("| 场景 | 更合适 | 理由 |")
        lines.append("| --- | --- | --- |")
        for item in scenarios:
            better = str(item.get("better") or "")
            better_name = item.get("betterLabel") or name_of.get(better, better)
            lines.append(
                f"| {item.get('scenario', '')} | {better_name} | {item.get('reason', '')} |"
            )
        lines.append("")

    if matrix:
        lines.append("## 三、对比矩阵")
        lines.append("")
        header = "| 维度 | " + " | ".join(
            _short_title(p) for p in profiles
        ) + " |"
        lines.append(header)
        lines.append("| --- | " + " | ".join("---" for _ in profiles) + " |")
        for row in matrix:
            cells = {c.get("documentId"): c for c in (row.get("cells") or [])}
            values = []
            for profile in profiles:
                cell = cells.get(profile.document_id) or {}
                value = str(cell.get("value") or "")
                if cell.get("confidence") == "missing" or not value:
                    values.append("未提及")
                else:
                    page = cell.get("page")
                    suffix = f" (p.{page})" if page else ""
                    values.append(value + suffix)
            lines.append(f"| {row.get('dimension', '')} | " + " | ".join(values) + " |")
        lines.append("")
        lines.append("> `(p.N)` 为该结论在原文的页码；「未提及」表示论文没有涉及该维度。")
        lines.append("")

    timeline = (trends or {}).get("timeline") or []
    if timeline:
        lines.append("## 四、研究方向演进")
        lines.append("")
        for item in sorted(timeline, key=lambda x: x.get("year") or 0):
            lines.append(
                f"- **{item.get('year', '未知')}** · {name_of.get(item.get('documentId'), '')}"
                f"：{item.get('label', '')}（{item.get('method', '')}）"
            )
        lines.append("")
        for item in (trends or {}).get("trends") or []:
            lines.append(f"- **{item.get('period', '')}**：{item.get('summary', '')}")
        lines.append("")

    if gaps:
        lines.append("## 五、研究空白")
        lines.append("")
        for index, item in enumerate(gaps, 1):
            lines.append(f"{index}. **{item.get('gap', '')}** —— {item.get('why', '')}")
        lines.append("")

    lines.append("## 六、参与对比的论文")
    lines.append("")
    lines.append("| 论文 | 年份 | 来源 | 方法大类 |")
    lines.append("| --- | --- | --- | --- |")
    for profile in sorted(profiles, key=lambda p: p.year or 0):
        lines.append(
            f"| {profile.title or document_names.get(profile.document_id, '')} "
            f"| {profile.year or '—'} | {profile.venue or '—'} | {profile.method_family or '—'} |"
        )
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
async def _save(db: AsyncSession, comparison: Comparison, **fields: Any) -> None:
    for key, value in fields.items():
        setattr(comparison, key, value)
    comparison.updated_at = now_utc()
    db.add(comparison)
    await db.commit()


async def run_comparison(comparison_id: str) -> None:
    """执行一次对比（后台任务入口）。"""
    from app.core.database import SessionLocal

    async with SessionLocal() as db:
        comparison = (
            await db.execute(select(Comparison).where(Comparison.id == comparison_id))
        ).scalar_one_or_none()
        if comparison is None:
            logger.warning("对比任务不存在：%s", comparison_id)
            return

        document_ids = _loads(comparison.document_ids_json, [])
        try:
            await _save(db, comparison, status="running", stage="cards", progress=5, error="")

            documents = list(
                (
                    await db.execute(
                        select(Document).where(Document.id.in_(document_ids))
                    )
                ).scalars()
            )
            if len(documents) < 2:
                raise ValueError("至少需要两篇可用论文（可能原文文件已删除）")

            document_names = {d.id: d.name for d in documents}
            model = await resolve_compare_model(db, comparison.user_id, comparison.team_id)

            # ---- 阶段 A：逐篇卡片 ----
            profiles: list[PaperProfile] = []
            for index, document in enumerate(documents, 1):
                profile = await extract_card(db, document, model=model)
                profiles.append(profile)
                progress = 5 + int(45 * index / len(documents))
                await _save(db, comparison, progress=progress, stage="cards")

            usable = [p for p in profiles if p.status == "ready"]
            if len(usable) < 2:
                raise ValueError("可用论文不足两篇：卡片抽取全部失败，请检查 PDF 是否为扫描件")

            cards = "\n\n".join(
                card_brief(p, document_names.get(p.document_id, "")) for p in usable
            )
            count = len(usable)

            # ---- 阶段 B1：维度 ----
            await _save(db, comparison, stage="dimensions", progress=58)
            dim_data = await _chat_json(
                DIMENSION_USER.format(
                    count=count, cards=cards,
                    min_dims=4, max_dims=8,
                ),
                model=model,
            )
            dimensions = [
                {
                    "key": _as_text(d.get("key"), 64) or f"dim_{i}",
                    "label": _as_text(d.get("label"), 40) or f"维度 {i}",
                    "why": _as_text(d.get("why"), 200),
                }
                for i, d in enumerate(dim_data.get("dimensions") or [], 1)
                if isinstance(d, dict)
            ][:8]
            if not dimensions:
                raise ValueError("模型未能归纳出对比维度")
            await _save(
                db, comparison, dimensions_json=_dumps(dimensions), progress=66
            )

            # ---- 阶段 B2：矩阵 ----
            await _save(db, comparison, stage="matrix", progress=70)
            dim_text = "\n".join(
                f"- {d['label']}：{d.get('why', '')}" for d in dimensions
            )
            matrix_data = await _chat_json(
                MATRIX_USER.format(count=count, cards=cards, dimensions=dim_text),
                model=model,
            )
            matrix = _normalize_matrix(matrix_data.get("matrix"), usable)
            await _save(db, comparison, matrix_json=_dumps(matrix), progress=80)

            # ---- 阶段 B3：演进 + 空白 ----
            await _save(db, comparison, stage="trends", progress=84)
            trend_data = await _chat_json(
                TREND_AND_GAP_USER.format(count=count, cards=cards), model=model
            )
            timeline = _normalize_evidence(trend_data.get("timeline") or [], usable)
            trends = _normalize_evidence(trend_data.get("trends") or [], usable)
            gaps = _normalize_evidence(trend_data.get("gaps") or [], usable)
            for collection in (trends, gaps):
                for item in collection:
                    for key in ("summary", "gap", "why", "period", "label", "scenario"):
                        if item.get(key):
                            item[key] = _humanize_refs(str(item[key]), usable)
            await _save(
                db,
                comparison,
                trends_json=_dumps({"timeline": timeline, "trends": trends}),
                gaps_json=_dumps(gaps),
                progress=90,
            )

            # ---- 阶段 B4：结论 ----
            await _save(db, comparison, stage="verdict", progress=93)
            verdict_data = await _chat_json(
                VERDICT_USER.format(count=count, cards=cards, shared_rules=SHARED_RULES),
                model=model,
            )
            verdict = _as_text(verdict_data.get("verdict"), 2000)
            scenarios = _normalize_evidence(
                verdict_data.get("scenarios") or [], usable, better_field=True
            )
            # 把正文里裸露的 doc_xxx 换成《论文标题》，否则用户读不懂
            verdict = _humanize_refs(verdict, usable)
            title_of = {p.document_id: _short_title(p) for p in usable}
            for item in scenarios:
                for key in ("reason", "scenario"):
                    if item.get(key):
                        item[key] = _humanize_refs(str(item[key]), usable)
                # better 保留 documentId（前端可据此高亮/跳转），另给一个可读标签
                better = item.get("better") or ""
                if better in title_of:
                    item["betterLabel"] = title_of[better]
            await _save(
                db,
                comparison,
                verdict=verdict,
                scenarios_json=_dumps(scenarios),
                stage="done",
                progress=97,
            )

            # ---- 报告 ----
            report = render_report_md(comparison, usable, document_names)
            await _save(
                db,
                comparison,
                report_md=report,
                status="ready",
                stage="done",
                progress=100,
            )
            logger.info(
                "对比完成 %s：%s 篇 / %s 个维度 / %s 条空白",
                comparison_id, len(usable), len(dimensions), len(gaps),
            )
        except Exception as exc:
            logger.exception("对比失败 %s", comparison_id)
            try:
                await db.rollback()
                comparison = (
                    await db.execute(
                        select(Comparison).where(Comparison.id == comparison_id)
                    )
                ).scalar_one_or_none()
                if comparison is not None:
                    await _save(
                        db,
                        comparison,
                        status="failed",
                        error=f"{type(exc).__name__}: {exc}"[:1500],
                    )
            except Exception:  # 写失败状态时再次出错，只能记日志
                logger.exception("写对比失败状态时又出错 %s", comparison_id)


def _normalize_matrix(rows: Any, profiles: list[PaperProfile]) -> list[dict[str, Any]]:
    """校验矩阵：只保留真实存在的 documentId，页码越界置空。"""
    valid = {p.document_id: p for p in profiles}
    result: list[dict[str, Any]] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        cells = []
        seen = set()
        for cell in row.get("cells") or []:
            if not isinstance(cell, dict):
                continue
            doc_id = str(cell.get("documentId") or "")
            if doc_id not in valid or doc_id in seen:
                continue
            seen.add(doc_id)
            profile = valid[doc_id]
            confidence = str(cell.get("confidence") or "inferred").lower()
            if confidence not in ("explicit", "inferred", "missing"):
                confidence = "inferred"
            cells.append(
                {
                    "documentId": doc_id,
                    "value": _as_text(cell.get("value"), 300),
                    "page": _as_page(cell.get("page"), profile.page_count),
                    "confidence": confidence,
                }
            )
        # 模型漏掉的论文补成 missing，保证表格不缺格
        for doc_id in valid:
            if doc_id not in seen:
                cells.append(
                    {
                        "documentId": doc_id,
                        "value": "",
                        "page": None,
                        "confidence": "missing",
                    }
                )
        if cells:
            result.append(
                {
                    "dimension": _as_text(row.get("dimension"), 40) or "未命名维度",
                    "cells": cells,
                }
            )
    return result


def _normalize_evidence(
    items: Any, profiles: list[PaperProfile], *, better_field: bool = False
) -> list[dict[str, Any]]:
    """校验时间轴/趋势/空白/场景：清掉不存在的 documentId 与越界页码。"""
    valid = {p.document_id: p for p in profiles}
    result: list[dict[str, Any]] = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        record = {
            key: _as_text(value, 400)
            for key, value in item.items()
            if key not in ("evidence", "documentId") and not isinstance(value, (list, dict))
        }
        evidence = []
        for ev in item.get("evidence") or []:
            if not isinstance(ev, dict):
                continue
            doc_id = str(ev.get("documentId") or "")
            if doc_id not in valid:
                continue
            evidence.append(
                {
                    "documentId": doc_id,
                    "page": _as_page(ev.get("page"), valid[doc_id].page_count),
                }
            )
        if evidence:
            record["evidence"] = evidence
        doc_id = str(item.get("documentId") or "")
        if doc_id in valid:
            record["documentId"] = doc_id
        if better_field:
            better = str(item.get("better") or "")
            record["better"] = better if (better in valid or not better.startswith("doc_")) else ""
        if record:
            result.append(record)
    return result


async def create_comparison(
    db: AsyncSession,
    *,
    user_id: str,
    document_ids: list[str],
    topic: str,
    team_id: str = "",
) -> Comparison:
    """建一条对比任务（不执行，执行由 tasks 层调度）。"""
    comparison = Comparison(
        id=new_id("cmp"),
        user_id=user_id,
        team_id=team_id,
        topic=topic[:255],
        document_ids_json=_dumps(document_ids),
        knowledge_base_ids_json="[]",
        status="pending",
        stage="cards",
        progress=0,
    )
    db.add(comparison)
    await db.commit()
    await db.refresh(comparison)
    return comparison
