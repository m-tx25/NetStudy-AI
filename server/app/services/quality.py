"""解析质量校验：给用户一个「这篇 PDF 解析得好不好」的判断依据。

为什么要做：扫描版 PDF、双栏排版、公式密集的论文，解析出来可能是乱码或
空文本。用户看到「已就绪」却检索不到内容，会以为系统坏了。这里提前把
可读原因写出来（并给出建议），前端直接展示。
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field

from langchain_core.documents import Document

from app.services.assets import Asset
from app.services.references import Reference
from app.services.sectionizer import Section


@dataclass
class QualityReport:
    char_count: int = 0
    page_count: int = 0
    section_count: int = 0
    reference_count: int = 0
    table_count: int = 0
    figure_count: int = 0
    garbage_ratio: float = 0.0
    warnings: list[str] = field(default_factory=list)


def _garbage_ratio(text: str, sample: int = 20000) -> float:
    sample_text = text[:sample]
    if not sample_text:
        return 0.0
    bad = 0
    for char in sample_text:
        if char in "\n\r\t":
            continue
        if char == "\ufffd":
            bad += 1
            continue
        if unicodedata.category(char) in ("Cc", "Cf", "Co", "Cn"):
            bad += 1
    return round(bad / len(sample_text), 4)


def evaluate(
    documents: list[Document],
    sections: list[Section],
    references: list[Reference],
    assets: list[Asset],
) -> QualityReport:
    text = "\n".join((document.page_content or "") for document in documents)
    char_count = len(text.strip())
    page_count = len(documents)
    section_count = len([item for item in sections if item.section_type != "front"])
    table_count = len([item for item in assets if item.kind == "table"])
    figure_count = len([item for item in assets if item.kind == "figure"])
    garbage = _garbage_ratio(text)

    warnings: list[str] = []
    if char_count < 500:
        warnings.append("文本过少：可能是扫描版 PDF（需要 OCR）或文件本身没有文本层")
    if section_count <= 1:
        warnings.append("未识别到章节结构，已按全文处理（分析结果的定位精度会下降）")
    if not any(item.section_type == "abstract" for item in sections):
        warnings.append("未识别到摘要章节")
    if not references:
        warnings.append("未识别到参考文献列表")
    if garbage > 0.05:
        warnings.append(f"文本存在较多异常字符（{garbage:.1%}），可能是编码或字体问题")

    return QualityReport(
        char_count=char_count,
        page_count=page_count,
        section_count=section_count,
        reference_count=len(references),
        table_count=table_count,
        figure_count=figure_count,
        garbage_ratio=garbage,
        warnings=warnings,
    )
