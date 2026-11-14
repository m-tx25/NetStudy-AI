# -*- coding: utf-8 -*-
"""学术成果生成与导出（模块八）。

## 三类生成物

| kind | 输入 | 产物 |
| --- | --- | --- |
| ``reading`` | 1 篇论文 | 阅读报告：研究问题/方法/实验/结论/局限/可追问点 |
| ``review`` | 2~8 篇 | 文献综述初稿：引言/按主题分组/横向比较/研究空白/参考文献 |
| ``status`` | 2~8 篇 | 研究现状：按主题、方法、发展阶段三段式整理 |
| ``comparison`` | 1 条已有对比 | 直接复用对比报告，不重新生成 |

## 核心要求：不能伪造

1. **参考文献只从真实论文卡片生成**：题名/作者/年份/来源均取自解析结果，
   缺字段就留空并标注，绝不编造 DOI、卷期、页码；
2. 生成物里的每条带文献依据的结论都用 `[n]` 编号，编号→论文映射单独存
   （``sources_json``），导出时附「参考文献」节；
3. 报告末尾固定输出「引用溯源」表（论文名 / 页码 / 章节）。

## 导出

- Markdown：原样导出
- DOCX：python-docx 转换（标题、列表、表格、引用块）
- PDF：**通过浏览器打印生成**（后端同时给一份打印用 HTML）。
  原因：环境里没有可用的 PDF 生成库，而 HTML 打印是离线可用的规范做法，
  中文排版也不会因为缺少中文字体而变成方块。
"""

from __future__ import annotations

import logging
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Comparison, Document, PaperProfile, Report, now_utc
from app.services import compare
from app.utils.ids import new_id

logger = logging.getLogger(__name__)

KINDS = ("reading", "review", "status", "comparison")


# ---------------------------------------------------------------------------
# 参考文献格式化
# ---------------------------------------------------------------------------
def _venue_type(venue: str) -> str:
    """据来源判断文献类型标记（GB/T 7714 用）。

    只做保守判断：arXiv 视为电子资源，含 conference/proceedings/workshop 视为会议，
    其余按期刊处理。**不猜测卷期与页码**。
    """
    text = (venue or "").lower()
    if "arxiv" in text or "preprint" in text:
        return "EB/OL"
    if any(word in text for word in ("conference", "proceedings", "workshop", "symposium")):
        return "C"
    return "J"


def _split_authors(authors: str) -> list[str]:
    parts = re.split(r"[,;，；]| and ", authors or "")
    return [p.strip() for p in parts if p.strip()]


def format_reference(profile: PaperProfile, style: str, index: int) -> str:
    """把论文卡片格式化成一条参考文献。

    缺字段（作者/年份/来源）时留空或用「佚名」「出版信息缺失」，
    **绝不编造 DOI 与卷期**。
    """
    authors = _split_authors(profile.authors)
    title = (profile.title or "（题名缺失）").strip()
    year = str(profile.year) if profile.year else "出版年缺失"
    venue = (profile.venue or "").strip()

    if style == "apa":
        author_text = ", ".join(authors) if authors else "佚名"
        venue_text = f" {venue}." if venue else ""
        return f"{author_text} ({year}). {title}.{venue_text}"
    if style == "ieee":
        author_text = ", ".join(authors) if authors else "佚名"
        venue_text = f", {venue}" if venue else ""
        return f'[{index}] {author_text}, "{title}"{venue_text}, {year}.'
    # 默认 GB/T 7714
    author_text = ", ".join(authors[:3]) + (", 等" if len(authors) > 3 else "")
    if not authors:
        author_text = "佚名"
    type_mark = _venue_type(venue)
    venue_text = f" {venue}," if venue else ""
    return f"[{index}] {author_text}. {title}[{type_mark}].{venue_text} {year}."


def build_references(profiles: list[PaperProfile], style: str = "gbt") -> list[str]:
    return [format_reference(p, style, i) for i, p in enumerate(profiles, 1)]


def all_styles(profiles: list[PaperProfile]) -> dict[str, list[str]]:
    return {
        "gbt": build_references(profiles, "gbt"),
        "apa": build_references(profiles, "apa"),
        "ieee": build_references(profiles, "ieee"),
    }


# ---------------------------------------------------------------------------
# 提示词
# ---------------------------------------------------------------------------
COMMON_RULES = """硬性规则：
1. 只依据给定的论文卡片内容写作，**不得编造**论文、实验数据、DOI、卷期页码。
2. 引用已有结论时用编号标注，如 [1][2]，编号对应给定的论文顺序。
3. 卡片里没有的信息（例如作者、年份、指标）就不要写，宁可缺失也不编。
4. 用 Markdown 输出：结论先行，必要时用表格。不要输出 JSON，不要输出解释性前言。
"""

READING_PROMPT = """下面是论文《{title}》的结构化卡片：

{card}

请写一份**论文阅读报告**，Markdown 结构如下：

# 《{title}》阅读报告

## 一、基本信息
（题名 / 作者 / 年份 / 来源，只用卡片里有的字段；缺失就写「原文未提供」）

## 二、研究问题
## 三、方法与技术路线
## 四、实验设置与主要结果
（有具体指标就写数字，没有就说明「原文未提供量化结果」）

## 五、创新点
## 六、局限与可追问之处
## 七、我的阅读笔记（留空，供用户补充）
"""

REVIEW_PROMPT = """下面是 {count} 篇论文的结构化卡片（编号即引用编号）：

{cards}

请写一份**文献综述初稿**，Markdown 结构：

# 文献综述：{topic}

## 一、引言
（这个方向在解决什么问题，为什么重要；可用 [1][2] 引用）

## 二、研究脉络
（按时间或技术路线梳理，指出前后继承关系）

## 三、主题分组
（按主题归类，每组说明该组论文的核心做法与差异）

## 四、方法对比
（用表格对比：论文 / 方法 / 数据 / 评价指标）

## 五、研究空白
（现有文献尚未解决的问题，明确标为「作者观点」而非文献结论）

## 六、结论
"""

STATUS_PROMPT = """下面是 {count} 篇论文的结构化卡片（编号即引用编号）：

{cards}

请整理**研究现状**，Markdown 结构：

# 研究现状：{topic}

## 一、按主题
## 二、按方法
（表格：方法族 / 代表论文 / 适用场景 / 局限）

## 三、按发展阶段
（时间轴式叙述，说明每个阶段的代表工作与转变原因）

## 四、总体判断
（哪些方向已趋饱和，哪些仍在早期；明确这是基于所选文献的判断）
"""


# ---------------------------------------------------------------------------
# 生成
# ---------------------------------------------------------------------------
def _numbered_cards(profiles: list[PaperProfile], names: dict[str, str]) -> str:
    blocks = []
    for index, profile in enumerate(profiles, 1):
        blocks.append(f"[{index}] {compare.card_brief(profile, names.get(profile.document_id, ''))}")
    return "\n\n".join(blocks)


def _sources_of(profiles: list[PaperProfile]) -> list[dict[str, Any]]:
    """引用溯源表：论文 + 卡片里给出的页码。"""
    result = []
    for index, profile in enumerate(profiles, 1):
        citations = compare._loads(profile.citations_json, {})
        pages = sorted({v for v in citations.values() if isinstance(v, int)})
        result.append(
            {
                "index": index,
                "documentId": profile.document_id,
                "title": profile.title,
                "year": profile.year,
                "pages": pages,
            }
        )
    return result


def _append_tail(
    content: str,
    profiles: list[PaperProfile],
    style: str = "gbt",
) -> str:
    """给报告追加「参考文献」与「引用溯源」两节（确定性内容，不由模型生成）。"""
    lines = [content.rstrip(), "", "---", "", "## 参考文献", ""]
    lines.extend(build_references(profiles, style))
    lines.append("")
    lines.append("## 引用溯源")
    lines.append("")
    lines.append("| 编号 | 论文 | 年份 | 卡片中出现的页码 |")
    lines.append("| --- | --- | --- | --- |")
    for item in _sources_of(profiles):
        pages = "、".join(f"p{p}" for p in item["pages"]) or "—"
        lines.append(
            f"| [{item['index']}] | {item['title']} | {item['year'] or '—'} | {pages} |"
        )
    lines.append("")
    lines.append(
        "> 参考文献由系统从论文解析结果生成，未提供 DOI 与卷期信息；"
        "缺失字段如实留空，不做推测。"
    )
    lines.append("")
    return "\n".join(lines)


async def _save(db: AsyncSession, report: Report, **fields: Any) -> None:
    for key, value in fields.items():
        setattr(report, key, value)
    report.updated_at = now_utc()
    db.add(report)
    await db.commit()


async def run_report(report_id: str) -> None:
    from app.core.database import SessionLocal

    async with SessionLocal() as db:
        report = (
            await db.execute(select(Report).where(Report.id == report_id))
        ).scalar_one_or_none()
        if report is None:
            return

        document_ids = compare._loads(report.document_ids_json, [])
        try:
            await _save(db, report, status="running", stage="cards", progress=5, error="")

            # comparison 类型直接复用已有对比报告
            if report.kind == "comparison":
                comparison = (
                    await db.execute(
                        select(Comparison).where(Comparison.id == report.comparison_id)
                    )
                ).scalar_one_or_none()
                if comparison is None or not comparison.report_md:
                    raise ValueError("对比报告不存在或尚未生成完成")
                await _save(
                    db,
                    report,
                    content_md=comparison.report_md,
                    title=comparison.topic or "多论文对比报告",
                    status="ready",
                    stage="done",
                    progress=100,
                )
                return

            documents = list(
                (
                    await db.execute(select(Document).where(Document.id.in_(document_ids)))
                ).scalars()
            )
            if not documents:
                raise ValueError("没有可用论文（原文可能已被删除）")

            names = {d.id: d.name for d in documents}
            model = await compare.resolve_compare_model(db, report.user_id, report.team_id)

            profiles: list[PaperProfile] = []
            for index, document in enumerate(documents, 1):
                profiles.append(await compare.extract_card(db, document, model=model))
                await _save(db, report, progress=5 + int(35 * index / len(documents)))

            usable = [p for p in profiles if p.status == "ready"]
            if not usable:
                raise ValueError("论文卡片抽取失败，请检查 PDF 是否为扫描件")

            await _save(db, report, stage="generate", progress=50)

            if report.kind == "reading":
                if len(usable) != 1:
                    raise ValueError("阅读报告只能针对单篇论文")
                profile = usable[0]
                prompt = READING_PROMPT.format(
                    title=profile.title or names.get(profile.document_id, "论文"),
                    card=compare.card_brief(profile, names.get(profile.document_id, "")),
                )
                topic = profile.title or "论文阅读报告"
            elif report.kind == "review":
                prompt = REVIEW_PROMPT.format(
                    count=len(usable),
                    cards=_numbered_cards(usable, names),
                    topic=report.title or "所选文献",
                )
                topic = report.title or "文献综述"
            else:  # status
                prompt = STATUS_PROMPT.format(
                    count=len(usable),
                    cards=_numbered_cards(usable, names),
                    topic=report.title or "所选文献",
                )
                topic = report.title or "研究现状"

            content = await compare.llm.complete(
                [
                    {"role": "system", "content": COMMON_RULES},
                    {"role": "user", "content": prompt},
                ],
                model=model,
                temperature=0.3,
            )
            await _save(db, report, progress=85)

            if not content or len(content.strip()) < 80:
                raise ValueError("模型输出过短，请重试")

            final = _append_tail(content.strip(), usable)
            refs = all_styles(usable)
            await _save(
                db,
                report,
                title=topic[:500],
                content_md=final,
                sources_json=compare._dumps(_sources_of(usable)),
                refs_json=compare._dumps(refs),
                status="ready",
                stage="done",
                progress=100,
            )
            logger.info("报告生成完成 %s：%s，%s 字", report_id, report.kind, len(final))
        except Exception as exc:
            logger.exception("报告生成失败 %s", report_id)
            try:
                await db.rollback()
                report = (
                    await db.execute(select(Report).where(Report.id == report_id))
                ).scalar_one_or_none()
                if report is not None:
                    await _save(
                        db,
                        report,
                        status="failed",
                        error=f"{type(exc).__name__}: {exc}"[:1500],
                    )
            except Exception:
                logger.exception("写失败状态时又出错 %s", report_id)


async def create_report(
    db: AsyncSession,
    *,
    user_id: str,
    kind: str,
    document_ids: list[str],
    title: str = "",
    comparison_id: str = "",
    team_id: str = "",
) -> Report:
    if kind not in KINDS:
        raise ValueError(f"不支持的报告类型：{kind}")
    report = Report(
        id=new_id("rpt"),
        user_id=user_id,
        team_id=team_id,
        kind=kind,
        title=title[:500],
        document_ids_json=compare._dumps(document_ids),
        comparison_id=comparison_id,
        status="pending",
        stage="cards",
        progress=0,
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)
    return report


# ---------------------------------------------------------------------------
# 导出：Markdown → DOCX / HTML
# ---------------------------------------------------------------------------
def to_docx(markdown: str, title: str = "报告"):
    """Markdown → DOCX（python-docx）。

    支持：# 标题、段落、- 列表、| 表格 |、> 引用。够覆盖我们生成的内容。
    """
    from docx import Document as DocxDocument
    from docx.shared import Pt

    document = DocxDocument()
    document.core_properties.title = title

    lines = markdown.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index].rstrip()
        stripped = line.strip()

        if not stripped:
            index += 1
            continue

        if stripped.startswith("|") and index + 1 < len(lines) and re.match(
            r"^\s*\|[\s:|-]+\|\s*$", lines[index + 1]
        ):
            # 表格：收集到空行为止
            rows: list[list[str]] = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                raw = lines[index].strip()
                if re.match(r"^\|[\s:|-]+\|$", raw):
                    index += 1
                    continue
                cells = [c.strip() for c in raw.strip("|").split("|")]
                rows.append(cells)
                index += 1
            if rows:
                table = document.add_table(rows=len(rows), cols=len(rows[0]))
                table.style = "Table Grid"
                for r, row in enumerate(rows):
                    for c, cell in enumerate(row[: len(rows[0])]):
                        table.cell(r, c).text = cell
            continue

        if stripped.startswith("#"):
            level = len(stripped) - len(stripped.lstrip("#"))
            document.add_heading(stripped[level:].strip(), level=min(level, 4))
            index += 1
            continue

        if stripped.startswith(("- ", "* ", "· ")):
            paragraph = document.add_paragraph(stripped[2:].strip(), style="List Bullet")
            index += 1
            continue

        if re.match(r"^\d+\.\s", stripped):
            paragraph = document.add_paragraph(
                re.sub(r"^\d+\.\s*", "", stripped), style="List Number"
            )
            index += 1
            continue

        if stripped.startswith(">"):
            paragraph = document.add_paragraph(stripped.lstrip("> ").strip())
            paragraph.paragraph_format.left_indent = Pt(18)
            for run in paragraph.runs:
                run.italic = True
            index += 1
            continue

        if set(stripped) <= {"-", "*", "_"} and len(stripped) >= 3:
            document.add_page_break()
            index += 1
            continue

        document.add_paragraph(stripped)
        index += 1

    return document


def to_html(markdown: str, title: str = "报告") -> str:
    """Markdown → 打印用 HTML（PDF 由浏览器「另存为 PDF」生成）。

    自己写一个极简转换：够用、无依赖，且不会把中文搞坏。
    """
    import html as html_lib

    def inline(text: str) -> str:
        escaped = html_lib.escape(text)
        escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
        escaped = re.sub(r"`(.+?)`", r"<code>\1</code>", escaped)
        return escaped

    out: list[str] = []
    lines = markdown.splitlines()
    index = 0
    in_list = False
    while index < len(lines):
        stripped = lines[index].strip()

        if in_list and not (stripped.startswith(("- ", "* ")) or re.match(r"^\d+\.\s", stripped)):
            out.append("</ul>")
            in_list = False

        if not stripped:
            index += 1
            continue

        if stripped.startswith("|") and index + 1 < len(lines) and re.match(
            r"^\s*\|[\s:|-]+\|\s*$", lines[index + 1]
        ):
            rows = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                raw = lines[index].strip()
                if re.match(r"^\|[\s:|-]+\|$", raw):
                    index += 1
                    continue
                rows.append([c.strip() for c in raw.strip("|").split("|")])
                index += 1
            if rows:
                out.append("<table>")
                out.append("<thead><tr>" + "".join(f"<th>{inline(c)}</th>" for c in rows[0]) + "</tr></thead>")
                out.append("<tbody>")
                for row in rows[1:]:
                    out.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in row) + "</tr>")
                out.append("</tbody></table>")
            continue

        if stripped.startswith("#"):
            level = len(stripped) - len(stripped.lstrip("#"))
            out.append(f"<h{min(level, 4)}>{inline(stripped[level:].strip())}</h{min(level, 4)}>")
            index += 1
            continue

        if stripped.startswith(("- ", "* ")) or re.match(r"^\d+\.\s", stripped):
            if not in_list:
                out.append("<ul>")
                in_list = True
            text = re.sub(r"^(- |\* |\d+\.\s)", "", stripped)
            out.append(f"<li>{inline(text)}</li>")
            index += 1
            continue

        if stripped.startswith(">"):
            out.append(f"<blockquote>{inline(stripped.lstrip('> ').strip())}</blockquote>")
            index += 1
            continue

        if set(stripped) <= {"-", "*", "_"} and len(stripped) >= 3:
            out.append("<hr/>")
            index += 1
            continue

        out.append(f"<p>{inline(stripped)}</p>")
        index += 1

    if in_list:
        out.append("</ul>")

    body = "\n".join(out)
    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"/>
<title>{html_lib.escape(title)}</title>
<style>
  @page {{ size: A4; margin: 20mm 16mm; }}
  body {{ font-family: "Songti SC","SimSun","Microsoft YaHei",serif; line-height: 1.75;
         color:#1a1a1a; max-width: 820px; margin: 0 auto; padding: 24px; }}
  h1 {{ font-size: 24px; border-bottom: 2px solid #0f9b7a; padding-bottom: 8px; }}
  h2 {{ font-size: 18px; margin-top: 22px; color:#0f7a61; }}
  h3, h4 {{ font-size: 15px; margin-top: 16px; }}
  table {{ border-collapse: collapse; width: 100%; margin: 12px 0; font-size: 13px; }}
  th, td {{ border: 1px solid #ccc; padding: 6px 8px; text-align: left; }}
  th {{ background: #f2f6f4; }}
  blockquote {{ margin: 10px 0; padding: 8px 12px; background: #f7f9f8;
                border-left: 3px solid #0f9b7a; color: #444; }}
  code {{ background: #f0f0f0; padding: 1px 4px; border-radius: 3px; }}
  hr {{ border: none; border-top: 1px dashed #bbb; margin: 18px 0; }}
  @media print {{ body {{ padding: 0; }} }}
</style></head>
<body>{body}</body></html>"""
