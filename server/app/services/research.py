# -*- coding: utf-8 -*-
"""学术研究辅助（模块七）：从「读懂已有论文」到「辅助开展自己的研究」。

## 设计原则（对应需求的「核心要求」）

> 所有研究建议都应该以已有文献证据为基础，并明确区分已有研究结论与 AI 提出的假设或建议，
> 不能保证某个方向一定具有创新性。

因此**每个条目都强制带两类标记**：

| 字段 | 取值 | 含义 |
| --- | --- | --- |
| `kind` | `evidence` | 已有文献明确写了（必须给 documentId + 页码） |
|  | `hypothesis` | AI 推测的研究假设（**没有**文献直接支撑） |
|  | `suggestion` | AI 给出的可执行建议（路线/计划类） |
| `evidence` | `[{documentId, page}]` | 支撑证据；`kind=evidence` 时不允许为空 |

`novelty`（创新性）单独处理：只描述「现有文献覆盖到哪、哪里没覆盖」，
并固定附带免责说明——**不输出「这个方向一定创新」这种结论**。

## 流程

    A. 论文卡片（复用 compare.extract_card，带缓存）
    B. 研究方向（每条带 kind + evidence）
    C. 研究问题 + 研究思路
    D. 技术路线与阶段性计划
    E. 创新空间分析（对比已有工作）+ 相关工作梳理
    F. 相关文献补充（本地库内推荐；外部检索失败不影响主流程）
    G. 拼装 Markdown 报告
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Document, PaperProfile, ResearchBrief, now_utc
from app.services import compare, llm
from app.utils.ids import new_id

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 提示词
# ---------------------------------------------------------------------------
BASE_RULES = """硬性规则（违反即视为错误）：
1. 每条结论都要标注类型：
   - "evidence"：已有文献明确写了（必须在 evidence 里给 documentId 与原文页码）
   - "hypothesis"：你的推测/假设（**不得**伪造文献支撑）
   - "suggestion"：可执行建议
2. 不要把「你的推测」写成「文献表明」。没有证据支撑就必须标 hypothesis。
3. 不要断言某个方向「一定创新」「一定能发论文」。创新性只能用
   「现有文献尚未覆盖 X」这种**相对表述**，并说明依据。
4. 只使用给定的论文卡片信息，不要引入卡片外的文献。
5. 输出必须是合法 JSON，不要 Markdown 围栏，不要解释性文字。"""

DIRECTIONS_USER = """以下是 {count} 篇论文的结构化卡片：

{cards}

用户的研究目标：{goal}

请据此给出 **3~5 个值得探索的研究方向**。每个方向要说明：
- 它建立在哪些已有工作之上（引用具体论文与页码）
- 现有文献已经做到了什么、还缺什么
- 探索这个方向的门槛与风险

输出 JSON：
{{
  "directions": [
    {{
      "title": "方向名（不超过 24 字）",
      "kind": "evidence 或 hypothesis",
      "rationale": "为什么值得做（2~3 句，必须提到具体论文）",
      "already_done": "现有文献已经做到什么",
      "gap": "还缺什么",
      "risk": "门槛与风险",
      "evidence": [{{"documentId": "doc_xxx", "page": 页码}}]
    }}
  ]
}}
"""

QUESTIONS_USER = """以下是 {count} 篇论文的结构化卡片：

{cards}

用户的研究目标：{goal}

请给出 **3~6 个具体可研究的问题**，每个问题配 **1~2 条研究思路**。

输出 JSON：
{{
  "questions": [
    {{
      "question": "问题（不超过 40 字，要具体到可验证）",
      "kind": "evidence 或 hypothesis",
      "why": "为什么这个问题值得研究（结合已有文献）",
      "evidence": [{{"documentId": "doc_xxx", "page": 页码}}],
      "approaches": [
        {{
          "title": "思路名（不超过 20 字）",
          "kind": "suggestion 或 hypothesis",
          "how": "怎么做（2~3 句，给出关键步骤）",
          "cost": "低/中/高",
          "risk": "主要风险"
        }}
      ]
    }}
  ]
}}
"""

ROADMAP_USER = """以下是 {count} 篇论文的结构化卡片：

{cards}

用户的研究目标：{goal}

请给出：
1. **技术路线建议**（3~4 条候选路线，说明各自适用条件与代价）
2. **阶段性研究计划**（3~5 个阶段，能落地到月/周）

输出 JSON：
{{
  "routes": [
    {{
      "title": "路线名",
      "kind": "suggestion",
      "when": "什么条件下选它",
      "how": "关键步骤",
      "cost": "低/中/高",
      "risk": "风险"
    }}
  ],
  "roadmap": [
    {{
      "phase": "阶段名（如「第 1-2 月」）",
      "goal": "这一阶段要达成什么",
      "tasks": ["任务 1", "任务 2"],
      "deliverable": "产出物（数据集/代码/实验报告/论文草稿）",
      "risk": "可能卡住的地方"
    }}
  ]
}}
"""

NOVELTY_USER = """以下是 {count} 篇论文的结构化卡片：

{cards}

用户的研究目标：{goal}

请做「**创新空间分析**」：对比已有工作，指出哪些组合/场景/指标尚未被覆盖。

**禁止**断言某个方向一定创新。只用「现有文献中未见到 X」这种表述，并给出依据。

输出 JSON：
{{
  "coverage": [
    {{"aspect": "研究维度（如 检索器训练方式）", "covered": "这些论文覆盖到什么程度", "evidence": [{{"documentId": "doc_xxx", "page": 页码}}]}}
  ],
  "openings": [
    {{"opening": "尚未被覆盖的点（不超过 40 字）", "why_open": "为什么说它没被覆盖（依据）", "confidence": "low/medium/high", "evidence": [{{"documentId": "doc_xxx", "page": 页码}}]}}
  ],
  "caveat": "免责说明：以上只是基于所选文献的相对判断，不代表该方向一定具有创新性。"
}}
"""

RELATED_USER = """以下是 {count} 篇论文的结构化卡片：

{cards}

用户的研究目标：{goal}

请**基于这些卡片**总结「相关工作」，按主题分组；再给出 3~5 个「后续应该去读/去查的方向」
（只是检索建议，不是文献引用）。

输出 JSON：
{{
  "groups": [
    {{"theme": "主题名", "summary": "这个主题下这些论文做了什么（2~3 句）", "papers": ["documentId"], "evidence": [{{"documentId": "doc_xxx", "page": 页码}}]}}
  ],
  "further_reading": [
    {{"topic": "应该去找什么（不超过 30 字）", "why": "为什么要找", "keywords": ["检索关键词"]}}
  ]
}}
"""


# ---------------------------------------------------------------------------
# 归一化：强制 kind / evidence 的约束
# ---------------------------------------------------------------------------
VALID_KINDS = ("evidence", "hypothesis", "suggestion")


def _normalize_items(
    items: Any,
    profiles: list[PaperProfile],
    *,
    default_kind: str = "hypothesis",
    require_evidence_for_evidence: bool = True,
) -> list[dict[str, Any]]:
    """校验条目：kind 合法、evidence 里的 documentId 真实存在、页码不越界。

    `kind=evidence` 却没有有效证据时，**降级为 hypothesis** ——
    宁可标成推测，也不能把无依据的话伪装成文献结论。
    """
    valid = {p.document_id: p for p in profiles}
    result: list[dict[str, Any]] = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        record: dict[str, Any] = {}
        for key, value in item.items():
            if key in ("evidence", "kind", "approaches"):
                continue
            if isinstance(value, (str, int, float, bool)):
                record[key] = compare._as_text(value, 600)
            elif isinstance(value, list):
                record[key] = [
                    compare._as_text(v, 300) for v in value if isinstance(v, (str, int, float))
                ][:8]

        evidence = []
        for ev in item.get("evidence") or []:
            if not isinstance(ev, dict):
                continue
            doc_id = str(ev.get("documentId") or "")
            if doc_id not in valid:
                continue
            page = compare._as_page(ev.get("page"), valid[doc_id].page_count)
            evidence.append({"documentId": doc_id, "page": page})
        if evidence:
            record["evidence"] = evidence

        kind = str(item.get("kind") or default_kind).lower()
        if kind not in VALID_KINDS:
            kind = default_kind
        if kind == "evidence" and require_evidence_for_evidence and not evidence:
            kind = "hypothesis"
            record["kindNote"] = "原文未能确认，已降级为推测"
        record["kind"] = kind

        # 嵌套的 approaches（研究思路）
        approaches = item.get("approaches")
        if isinstance(approaches, list):
            record["approaches"] = _normalize_items(
                approaches, profiles, default_kind="suggestion"
            )[:3]

        # 保留判定：不同分节的主键名不一样（title/question/phase/theme/aspect/opening/topic），
        # 只认其中几个会把整节内容过滤成空列表（实测：创新分析变成 0 条）。
        key_fields = ("title", "question", "phase", "theme", "aspect", "opening", "topic")
        if any(record.get(field) for field in key_fields):
            result.append(record)
    return result


def _normalize_novelty(data: Any, profiles: list[PaperProfile]) -> dict[str, Any]:
    if not isinstance(data, dict):
        return {}
    coverage = _normalize_items(data.get("coverage"), profiles, default_kind="evidence")
    openings = _normalize_items(data.get("openings"), profiles, default_kind="hypothesis")
    for item in openings:
        confidence = str(item.get("confidence") or "low").lower()
        item["confidence"] = confidence if confidence in ("low", "medium", "high") else "low"
        # 创新性判断永远只能算假设，不允许被标成 evidence
        item["kind"] = "hypothesis"
    return {
        "coverage": coverage,
        "openings": openings,
        "caveat": compare._as_text(
            data.get("caveat")
            or "以上判断只基于所选文献，不代表这些方向一定具有创新性。",
            300,
        ),
    }


# ---------------------------------------------------------------------------
# 相关文献补充（本地库内推荐，不依赖外部网络）
# ---------------------------------------------------------------------------
async def _local_related_docs(
    db: AsyncSession, document_ids: list[str], limit: int = 6
) -> list[dict[str, Any]]:
    """从库里挑「没被选中但可能相关」的文档。

    做法：取已选论文的卡片关键词，与其它文档名做词面重合度排序。
    只是**候选推荐**，所以不放进证据体系，前端单独展示。
    """
    rows = (
        await db.execute(
            select(Document).where(Document.stored_path != "").limit(200)
        )
    ).scalars().all()
    chosen = set(document_ids)
    selected_titles = " ".join(
        (d.name or "") for d in rows if d.id in chosen
    ).lower()

    def score(name: str) -> int:
        tokens = [t for t in name.lower().replace(".pdf", "").split() if len(t) > 1]
        return sum(1 for token in tokens if token in selected_titles)

    candidates = [
        {"documentId": d.id, "name": d.name, "score": score(d.name)}
        for d in rows
        if d.id not in chosen and d.name
    ]
    candidates.sort(key=lambda item: item["score"], reverse=True)
    return candidates[:limit]


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
async def _save(db: AsyncSession, brief: ResearchBrief, **fields: Any) -> None:
    for key, value in fields.items():
        setattr(brief, key, value)
    brief.updated_at = now_utc()
    db.add(brief)
    await db.commit()


def render_report(brief: ResearchBrief, profiles: list[PaperProfile], names: dict[str, str]) -> str:
    directions = compare._loads(brief.directions_json, [])
    questions = compare._loads(brief.questions_json, [])
    roadmap = compare._loads(brief.roadmap_json, [])
    novelty = compare._loads(brief.novelty_json, {})
    related = compare._loads(brief.related_work_json, [])
    related_docs = compare._loads(brief.related_docs_json, [])

    def evidence_text(item: dict[str, Any]) -> str:
        parts = []
        for ev in item.get("evidence") or []:
            name = names.get(ev.get("documentId"), "")
            page = f" p{ev['page']}" if ev.get("page") else ""
            parts.append(f"《{name}》{page}")
        return "、".join(parts)

    def kind_badge(kind: str) -> str:
        return {"evidence": "📄 文献依据", "hypothesis": "💭 AI 假设", "suggestion": "🛠 建议"}.get(
            kind, "💭 AI 假设"
        )

    lines = [f"# 研究辅助报告：{brief.goal or '（未指定研究目标）'}", ""]
    lines.append(f"> 基于 {len(profiles)} 篇论文 · 由 NetStudy-AI 生成")
    lines.append("> **注意**：📄 为文献直接支撑；💭 / 🛠 为 AI 推测与建议，不代表文献结论，也不保证创新性。")
    lines.append("")

    lines.append("## 一、研究目标")
    lines.append("")
    lines.append(brief.goal or "（未填写，以下建议基于所选论文自动推断）")
    lines.append("")

    if directions:
        lines.append("## 二、值得探索的研究方向")
        lines.append("")
        for index, item in enumerate(directions, 1):
            lines.append(f"### {index}. {item.get('title', '')} {kind_badge(item.get('kind', 'hypothesis'))}")
            lines.append("")
            lines.append(f"- **为什么值得做**：{item.get('rationale', '')}")
            lines.append(f"- **现有文献已做到**：{item.get('already_done', '')}")
            lines.append(f"- **尚未覆盖**：{item.get('gap', '')}")
            lines.append(f"- **门槛与风险**：{item.get('risk', '')}")
            ev = evidence_text(item)
            if ev:
                lines.append(f"- **依据**：{ev}")
            lines.append("")

    if questions:
        lines.append("## 三、可研究的问题与研究思路")
        lines.append("")
        for index, item in enumerate(questions, 1):
            lines.append(f"### 问题 {index}：{item.get('question', '')} {kind_badge(item.get('kind', 'hypothesis'))}")
            lines.append("")
            if item.get("why"):
                lines.append(f"{item['why']}")
                lines.append("")
            ev = evidence_text(item)
            if ev:
                lines.append(f"> 依据：{ev}")
                lines.append("")
            for approach in item.get("approaches") or []:
                lines.append(
                    f"- **思路：{approach.get('title', '')}**（成本 {approach.get('cost', '?')}）"
                    f" —— {approach.get('how', '')}（风险：{approach.get('risk', '')}）"
                )
            lines.append("")

    if novelty:
        lines.append("## 四、创新空间分析")
        lines.append("")
        for item in novelty.get("coverage") or []:
            lines.append(f"- **已覆盖 · {item.get('aspect', '')}**：{item.get('covered', '')}")
        lines.append("")
        for item in novelty.get("openings") or []:
            lines.append(
                f"- **尚未覆盖 · {item.get('opening', '')}**（把握度 {item.get('confidence', 'low')}）"
                f" —— {item.get('why_open', '')}"
            )
        lines.append("")
        lines.append(f"> ⚠️ {novelty.get('caveat', '')}")
        lines.append("")

    if roadmap:
        lines.append("## 五、技术路线与阶段计划")
        lines.append("")
        for route in roadmap.get("routes") or []:
            lines.append(
                f"- **路线：{route.get('title', '')}**（成本 {route.get('cost', '?')}）"
                f" —— 适用：{route.get('when', '')}；怎么做：{route.get('how', '')}；风险：{route.get('risk', '')}"
            )
        lines.append("")
        lines.append("| 阶段 | 目标 | 主要任务 | 产出 | 风险 |")
        lines.append("| --- | --- | --- | --- | --- |")
        for phase in roadmap.get("roadmap") or []:
            tasks = "；".join(phase.get("tasks") or [])
            lines.append(
                f"| {phase.get('phase', '')} | {phase.get('goal', '')} | {tasks} "
                f"| {phase.get('deliverable', '')} | {phase.get('risk', '')} |"
            )
        lines.append("")

    if related:
        lines.append("## 六、相关工作梳理")
        lines.append("")
        for group in related.get("groups") or []:
            lines.append(f"- **{group.get('theme', '')}**：{group.get('summary', '')}")
        lines.append("")
        further = related.get("further_reading") or []
        if further:
            lines.append("**建议补充检索的方向**（只是检索建议，不是文献引用）：")
            lines.append("")
            for item in further:
                keywords = "、".join(item.get("keywords") or [])
                lines.append(
                    f"- {item.get('topic', '')} —— {item.get('why', '')}"
                    + (f"（关键词：{keywords}）" if keywords else "")
                )
            lines.append("")

    if related_docs:
        lines.append("## 七、库里可能相关的其它文献")
        lines.append("")
        for item in related_docs:
            lines.append(f"- {item.get('name', '')}")
        lines.append("")
        lines.append("> 这一节只是按标题相似度做的候选推荐，**没有**经过相关性验证。")
        lines.append("")

    lines.append("## 八、参考论文")
    lines.append("")
    lines.append("| 论文 | 年份 | 方法大类 |")
    lines.append("| --- | --- | --- |")
    for profile in sorted(profiles, key=lambda p: p.year or 0):
        lines.append(
            f"| {profile.title or names.get(profile.document_id, '')} "
            f"| {profile.year or '—'} | {profile.method_family or '—'} |"
        )
    lines.append("")
    return "\n".join(lines)


async def run_brief(brief_id: str) -> None:
    """执行一次研究辅助（后台任务入口）。"""
    from app.core.database import SessionLocal

    async with SessionLocal() as db:
        brief = (
            await db.execute(select(ResearchBrief).where(ResearchBrief.id == brief_id))
        ).scalar_one_or_none()
        if brief is None:
            logger.warning("研究辅助任务不存在：%s", brief_id)
            return

        document_ids = compare._loads(brief.document_ids_json, [])
        try:
            await _save(db, brief, status="running", stage="cards", progress=4, error="")

            documents = list(
                (
                    await db.execute(select(Document).where(Document.id.in_(document_ids)))
                ).scalars()
            )
            if not documents:
                raise ValueError("没有可用论文（原文文件可能已被删除）")

            names = {d.id: d.name for d in documents}
            model = await compare.resolve_compare_model(db, brief.user_id, brief.team_id)

            profiles: list[PaperProfile] = []
            for index, document in enumerate(documents, 1):
                profiles.append(await compare.extract_card(db, document, model=model))
                await _save(db, brief, progress=4 + int(26 * index / len(documents)))

            usable = [p for p in profiles if p.status == "ready"]
            if not usable:
                raise ValueError("论文卡片抽取全部失败，请检查 PDF 是否为扫描件")

            cards = "\n\n".join(
                compare.card_brief(p, names.get(p.document_id, "")) for p in usable
            )
            count = len(usable)
            goal = brief.goal.strip() or "（未指定，请根据这些论文推断一个有价值的研究方向）"

            def fmt(template: str) -> str:
                return template.format(count=count, cards=cards, goal=goal)

            # ---- 方向 ----
            await _save(db, brief, stage="directions", progress=34)
            data = await compare._chat_json(fmt(DIRECTIONS_USER), model=model)
            directions = _normalize_items(data.get("directions"), usable)
            for item in directions:
                for key in ("title", "rationale", "already_done", "gap", "risk"):
                    if item.get(key):
                        item[key] = compare._humanize_refs(item[key], usable)
            await _save(db, brief, directions_json=compare._dumps(directions), progress=48)

            # ---- 问题 + 思路 ----
            await _save(db, brief, stage="questions", progress=52)
            data = await compare._chat_json(fmt(QUESTIONS_USER), model=model)
            questions = _normalize_items(data.get("questions"), usable)
            for item in questions:
                for key in ("question", "why"):
                    if item.get(key):
                        item[key] = compare._humanize_refs(item[key], usable)
            await _save(db, brief, questions_json=compare._dumps(questions), progress=64)

            # ---- 路线 + 计划 ----
            await _save(db, brief, stage="roadmap", progress=68)
            data = await compare._chat_json(fmt(ROADMAP_USER), model=model)
            roadmap = {
                "routes": _normalize_items(data.get("routes"), usable, default_kind="suggestion"),
                "roadmap": _normalize_items(data.get("roadmap"), usable, default_kind="suggestion"),
            }
            await _save(db, brief, roadmap_json=compare._dumps(roadmap), progress=78)

            # ---- 创新空间 ----
            await _save(db, brief, stage="novelty", progress=82)
            data = await compare._chat_json(fmt(NOVELTY_USER), model=model)
            novelty = _normalize_novelty(data, usable)
            await _save(db, brief, novelty_json=compare._dumps(novelty), progress=88)

            # ---- 相关工作 + 相关文献 ----
            await _save(db, brief, stage="related", progress=90)
            data = await compare._chat_json(fmt(RELATED_USER), model=model)
            related = {
                "groups": _normalize_items(data.get("groups"), usable, default_kind="evidence"),
                "further_reading": _normalize_items(
                    data.get("further_reading"), usable, default_kind="suggestion"
                ),
            }
            related_docs = await _local_related_docs(db, [p.document_id for p in usable])
            await _save(
                db,
                brief,
                related_work_json=compare._dumps(related),
                related_docs_json=compare._dumps(related_docs),
                progress=95,
            )

            # ---- 报告 ----
            brief.directions_json = compare._dumps(directions)
            brief.questions_json = compare._dumps(questions)
            brief.roadmap_json = compare._dumps(roadmap)
            brief.novelty_json = compare._dumps(novelty)
            report = render_report(brief, usable, names)
            await _save(
                db,
                brief,
                report_md=report,
                status="ready",
                stage="done",
                progress=100,
            )
            logger.info(
                "研究辅助完成 %s：%s 篇 / %s 个方向 / %s 个问题",
                brief_id, len(usable), len(directions), len(questions),
            )
        except Exception as exc:
            logger.exception("研究辅助失败 %s", brief_id)
            try:
                await db.rollback()
                brief = (
                    await db.execute(
                        select(ResearchBrief).where(ResearchBrief.id == brief_id)
                    )
                ).scalar_one_or_none()
                if brief is not None:
                    await _save(
                        db,
                        brief,
                        status="failed",
                        error=f"{type(exc).__name__}: {exc}"[:1500],
                    )
            except Exception:
                logger.exception("写失败状态时又出错 %s", brief_id)


async def create_brief(
    db: AsyncSession,
    *,
    user_id: str,
    document_ids: list[str],
    goal: str,
    team_id: str = "",
) -> ResearchBrief:
    brief = ResearchBrief(
        id=new_id("rbrief"),
        user_id=user_id,
        team_id=team_id,
        goal=goal[:512],
        document_ids_json=compare._dumps(document_ids),
        status="pending",
        stage="cards",
        progress=0,
    )
    db.add(brief)
    await db.commit()
    await db.refresh(brief)
    return brief
