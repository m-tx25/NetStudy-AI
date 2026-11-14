"""表格与图表识别。

能力边界（要诚实）：
  - 表格：PDF 用 pdfplumber 抽取规则表格；DOCX 用 python-docx 读表格结构。
    复杂跨页/合并单元格会有缺失，但足以支撑「实验数据表」的基本展示。
  - 图：不裁剪图片本体（需要 PyMuPDF），只识别正文中的图注（Figure N / 图 N），
    保留页码与说明，供分析时引用；后续如需缩略图再加。
"""

from __future__ import annotations

import json
import logging
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from langchain_core.documents import Document

logger = logging.getLogger(__name__)

_TABLE_CAPTION = re.compile(r"(?i)\btable\s*(\d+)[:.]?\s*([^\n]{0,160})")
_FIGURE_LINE = re.compile(r"(?i)^(?:figure|fig\.?)\s*(\d+)[:.]?\s*(.{0,200})")
_CN_FIGURE_LINE = re.compile(r"^图\s*(\d+)[:：]?\s*(.{0,200})")
_MAX_TABLES = 40


@dataclass
class Asset:
    kind: str  # table / figure
    page: int | None
    caption: str = ""
    content_json: str = ""
    storage_path: str = ""


def _rows_from_cells(cells: list[list[str | None]]) -> list[list[str]]:
    rows = [[(cell or "").strip() for cell in row] for row in cells]
    rows = [row for row in rows if any(cell for cell in row)]
    return rows


def _table_caption(text: str) -> str:
    match = _TABLE_CAPTION.search(text or "")
    return f"Table {match.group(1)} {match.group(2).strip()}".strip() if match else ""


def _is_meaningful_table(rows: list[list[str]]) -> bool:
    """过滤「把双栏正文当成表格」的假阳性。

    pdfplumber 的表格检测对双栏/LaTeX 排版很敏感，常把两栏文字识别成
    「左列空、右列一句话」的表格。特征很明显：几乎所有行都只有一个非空单元格。
    真正的表格应当有多行、多列、且多数行有 ≥2 个非空单元格。
    """
    if len(rows) < 2:
        return False
    widths = [len(row) for row in rows]
    if max(widths) < 2:
        return False

    multi_cell_rows = sum(
        1 for row in rows if sum(1 for cell in row if cell.strip()) >= 2
    )
    if multi_cell_rows < max(2, len(rows) // 2):
        return False

    # 列数应基本一致，避免零散文本块被拼成「表格」
    common_width, common_count = Counter(widths).most_common(1)[0]
    if common_width < 2 or common_count / len(rows) < 0.6:
        return False

    non_empty = sum(1 for row in rows for cell in row if cell.strip())
    if non_empty / max(1, len(rows) * common_width) < 0.4:
        return False
    return True


def _extract_pdf_tables(path: Path) -> list[Asset]:
    try:
        import pdfplumber
    except ImportError:  # pragma: no cover - 未装依赖时跳过而不是报错
        logger.warning("未安装 pdfplumber，跳过 PDF 表格抽取")
        return []

    assets: list[Asset] = []
    try:
        with pdfplumber.open(str(path)) as pdf:
            for page_number, page in enumerate(pdf.pages, start=1):
                if len(assets) >= _MAX_TABLES:
                    break
                try:
                    tables = page.extract_tables() or []
                except Exception:  # noqa: BLE001 - 单页失败不影响其它页
                    continue
                page_text = ""
                try:
                    page_text = page.extract_text() or ""
                except Exception:  # noqa: BLE001
                    page_text = ""
                for cells in tables:
                    rows = _rows_from_cells(cells)
                    if not _is_meaningful_table(rows):
                        continue
                    assets.append(
                        Asset(
                            kind="table",
                            page=page_number,
                            caption=_table_caption(page_text),
                            content_json=json.dumps(rows, ensure_ascii=False)[:20000],
                        )
                    )
                    if len(assets) >= _MAX_TABLES:
                        break
    except Exception as exc:  # noqa: BLE001 - 表格是增强信息，失败不阻断解析
        logger.warning("PDF 表格抽取失败 %s: %s", path.name, exc)
    return assets


def _extract_docx_tables(path: Path) -> list[Asset]:
    try:
        from docx import Document as DocxDocument
    except ImportError:  # pragma: no cover
        return []

    assets: list[Asset] = []
    try:
        document = DocxDocument(str(path))
        for table in document.tables[:_MAX_TABLES]:
            rows = _rows_from_cells([[cell.text for cell in row.cells] for row in table.rows])
            if len(rows) < 2 or max(len(row) for row in rows) < 2:
                continue
            assets.append(
                Asset(kind="table", page=None, content_json=json.dumps(rows, ensure_ascii=False)[:20000])
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("DOCX 表格抽取失败 %s: %s", path.name, exc)
    return assets


def extract_tables(path: str | Path) -> list[Asset]:
    target = Path(path)
    suffix = target.suffix.lower()
    if suffix == ".pdf":
        return _extract_pdf_tables(target)
    if suffix in (".docx", ".doc"):
        return _extract_docx_tables(target)
    return []


def _page_of(document: Document) -> int | None:
    metadata = document.metadata or {}
    label = metadata.get("page_label") or metadata.get("page")
    try:
        value = int(label)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def extract_figure_captions(documents: list[Document]) -> list[Asset]:
    """按行识别图注（Figure 1 / Fig. 2 / 图 3），保留页码。"""
    assets: list[Asset] = []
    seen: set[str] = set()
    for document in documents:
        page = _page_of(document)
        for line in (document.page_content or "").splitlines():
            text = line.strip()
            if not text or len(text) > 240:
                continue
            match = _FIGURE_LINE.match(text) or _CN_FIGURE_LINE.match(text)
            if not match:
                continue
            caption = text[:220]
            if caption in seen:
                continue
            seen.add(caption)
            assets.append(Asset(kind="figure", page=page, caption=caption))
    return assets[:60]
