"""论文结构识别：把按页解析出的文本切成「章节」。

为什么需要它：
  - 单篇分析（摘要/方法/实验/局限）要按章节取数，而不是在全文里盲搜；
  - 引用溯源要能说明「这句话来自 Method 第 3 页」；
  - 章节也是后续「按章节问答」的过滤条件。

识别策略（规则优先，不依赖版面分析）：
  1. 去掉行首编号（1. / 2.1 / III. / 一、）后与已知章节名做精确或前缀匹配；
  2. 只接受短行（≤80 字符）、不带句末标点的候选，降低正文误判；
  3. 识别不到任何章节时退化为单段「全文」，不抛错。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace

from langchain_core.documents import Document

# 章节别名 → 规范类型。顺序有意义：先匹配到的先用。
_SECTION_ALIASES: list[tuple[str, tuple[str, ...]]] = [
    ("abstract", ("abstract", "摘要")),
    ("introduction", ("introduction", "引言", "前言", "绪论")),
    (
        "related",
        ("related work", "related works", "literature review", "相关工作", "文献综述", "研究现状"),
    ),
    ("background", ("background", "背景", "理论基础")),
    (
        "method",
        (
            "method", "methods", "methodology", "approach", "proposed method",
            "our method", "materials and methods", "方法", "研究方法", "方法设计",
            "模型", "算法", "技术路线",
        ),
    ),
    (
        "experiment",
        ("experiment", "experiments", "experimental setup", "experimental results",
         "实验", "实验设置", "实验设计"),
    ),
    ("result", ("result", "results", "results and discussion", "结果", "实验结果")),
    ("discussion", ("discussion", "讨论", "分析与讨论")),
    (
        "conclusion",
        ("conclusion", "conclusions", "concluding remarks", "结论", "总结", "结语"),
    ),
    ("references", ("references", "bibliography", "参考文献")),
    ("acknowledgments", ("acknowledgment", "acknowledgements", "acknowledgments", "致谢")),
    ("appendix", ("appendix", "appendices", "附录")),
]

_ALIAS_MAP: dict[str, str] = {}
for _canonical, _aliases in _SECTION_ALIASES:
    for _alias in _aliases:
        _ALIAS_MAP[_alias] = _canonical

# 行首编号：1 / 2.1 / III. / 一、
_NUMBERING = re.compile(
    r"^\s*(?:\d+(?:\.\d+)*|[IVXLC]{1,6}|[一二三四五六七八九十]{1,3})[\.\、\)]?\s*"
)
# 通用编号小标题（技术文档/论文子章节），例如 "1 项目概述"、"2.1 数据集"
_GENERIC_HEADING = re.compile(r"^(?:\d{1,2}(?:\.\d{1,2}){0,3})[\.\、]?\s*[^\d\s].{1,40}$")
_MD_HEADING = re.compile(r"^#{1,6}\s+\S.{0,60}$")
_DATE_LIKE = re.compile(r"^\d{1,2}\s*[年月日]")
_TAIL_PUNCT = " \t:：.。;；-—"


@dataclass(frozen=True)
class Section:
    section_type: str
    heading: str
    text: str
    page_start: int | None
    page_end: int | None
    ordinal: int


def normalize_heading(line: str) -> str:
    """去掉编号与首尾标点，返回用于匹配的规范串（小写）。"""
    text = _NUMBERING.sub("", line.strip())
    return text.strip(_TAIL_PUNCT).lower()


def detect_section_type(line: str) -> str | None:
    """一行是否是章节标题；是则返回规范类型，否则 None。"""
    stripped = line.strip()
    if not stripped or len(stripped) > 80:
        return None
    # 标题不应以句号结尾（但允许 "1. Introduction" 这种编号里的点）
    if stripped.endswith(("。", ".", "！", "？", "!", "?")):
        return None
    normalized = normalize_heading(stripped)
    if not normalized or len(normalized) > 60:
        return None
    if normalized in _ALIAS_MAP:
        return _ALIAS_MAP[normalized]
    for alias, canonical in _ALIAS_MAP.items():
        if normalized.startswith(alias + " ") or normalized.startswith(alias + "："):
            return canonical

    # Markdown 标题：## 消息传递
    if _MD_HEADING.match(stripped):
        return "other"

    # 通用编号小标题：只在「不像日期」且足够短时生效，避免把正文列表当章节
    if (
        _GENERIC_HEADING.match(stripped)
        and not _DATE_LIKE.match(stripped)
        and not stripped.endswith("。")
    ):
        return "other"
    return None


def _page_of(document: Document) -> int | None:
    metadata = document.metadata or {}
    label = metadata.get("page_label") or metadata.get("page")
    try:
        value = int(label)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def build_sections(documents: list[Document]) -> list[Section]:
    """按章节切分。返回的 ordinal 从 0 递增，text 已清理首尾空白。"""
    sections: list[Section] = []
    current_type = "front"
    current_heading = "题名与作者"
    current_lines: list[str] = []
    current_pages: list[int] = []

    def flush() -> None:
        text = "\n".join(current_lines).strip()
        if not text:
            return
        sections.append(
            Section(
                section_type=current_type,
                heading=current_heading,
                text=text,
                page_start=min(current_pages) if current_pages else None,
                page_end=max(current_pages) if current_pages else None,
                ordinal=len(sections),
            )
        )

    found_heading = False
    for document in documents:
        page = _page_of(document)
        for line in (document.page_content or "").splitlines():
            stripped = line.strip()
            section_type = detect_section_type(stripped) if stripped else None
            # 参考文献区里的编号条目（"1. Author..."）不是章节标题，别把列表切碎
            if section_type == "other" and current_type == "references":
                section_type = None
            if section_type is not None:
                found_heading = True
                flush()
                current_type = section_type
                current_heading = stripped[:120]
                current_lines = []
                current_pages = [page] if page else []
                continue
            if stripped:
                current_lines.append(stripped)
                if page and (not current_pages or current_pages[-1] != page):
                    current_pages.append(page)
            elif current_lines:
                current_lines.append("")

    flush()

    if not found_heading:
        text = "\n".join(
            (document.page_content or "").strip()
            for document in documents
            if (document.page_content or "").strip()
        )
        pages = [page for page in (_page_of(item) for item in documents) if page]
        return [
            Section(
                section_type="other",
                heading="全文",
                text=text,
                page_start=min(pages) if pages else None,
                page_end=max(pages) if pages else None,
                ordinal=0,
            )
        ]

    # 只丢弃「标题后没有正文」的空段；短段落（如一句话结论）是合法的，不能按长度过滤
    cleaned = [section for section in sections if section.text.strip()]
    return [replace(section, ordinal=index) for index, section in enumerate(cleaned)]


def section_labels() -> dict[str, str]:
    """中文展示名，供前端与提示词使用。"""
    return {
        "front": "题名与作者",
        "abstract": "摘要",
        "introduction": "引言",
        "related": "相关工作",
        "background": "研究背景",
        "method": "研究方法",
        "experiment": "实验",
        "result": "结果",
        "discussion": "讨论",
        "conclusion": "结论",
        "references": "参考文献",
        "acknowledgments": "致谢",
        "appendix": "附录",
        "other": "全文",
    }
