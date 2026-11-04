"""Bounded read-only Office/text ingestion for the WPS-suite porting (P1).

Contract: ``company_office_analyze`` (``company.office/2.0``, ``office.analyze``).
The slice covers the spec's L1 reading bounds without any cloud dependency:

- the access rail reuses the P0 foundation (``company_agent.workspace_files``):
  one lexical fence, one race-safe opener re-verified after open, no paths
  outside the mounted workspace root;
- caps follow WPS-SUITE-PORTING: 20MB per file, xlsx 32 sheets and 5000 rows
  per sheet; every cap hit is refused or truncated *with an explicit marker
  and flag*, never silently;
- the tool result stays inside the results.json budget by paging: docx
  paragraphs, pdf pages, text lines and xlsx sheets form one ``items`` array
  addressed through the ``offset`` argument;
- docx and xlsx are parsed with the standard library (zip + XML) only;
  pypdf is optional and lazily imported -- without it a pdf fails closed
  instead of returning a stand-in text;
- ``.doc`` and ``.xls`` are read in-process (piece table / BIFF values);
  ``.ppt`` and other legacy suffixes still refuse;
- images and a PDF whose text layer is empty go through local OCR
  (``COMPANY_AGENT_OCR_CMD``). Unconfigured or failed OCR refuses.
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Iterator
from typing import Any

from company_agent import office_binary, office_ocr, workspace_files

MAX_FILE_BYTES = 20_000_000
MAX_SHEETS = 32
MAX_ROWS_PER_SHEET = 5_000
MAX_PREVIEW_ROWS = 8
MAX_PREVIEW_COLS = 64
MAX_ITEM_TEXT_CHARS = 4_000
_COMPOUND_MAX_BYTES = 256
_RETURN_BUDGET_BYTES = 52_000
MAX_RETURN_ITEMS = 256
_ITEM_OVERHEAD_BYTES = 60
_MARK_INLINE = "…[行内截断]"

_W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_MAIN_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_A_NS = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
_REL_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_REL_R_NS = "{http://schemas.openxmlformats.org/package/2006/relationships}Relationship"

_KIND_BY_SUFFIX = {".docx": "docx", ".xlsx": "xlsx", ".pptx": "pptx", ".pdf": "pdf", ".txt": "text", ".md": "text"}
_MATTER_FILES = {
    "project.company-timeline.json": "timeline",
    "project.company-chronology.json": "chronology",
    "project.company-mindmap.json": "mindmap",
}

MAX_PPTX_SLIDES = 32


class OfficeIngestError(ValueError):
    """Refusal that names the boundary hit without echoing external paths."""


def analyze(args: dict) -> dict:
    """Contract entry point: bounded text extraction for one workspace file."""

    root = workspace_files.root()
    compound = _compound(args)
    resolved = workspace_files.resolve(root, compound)
    if not resolved.is_file():
        raise OfficeIngestError("workspace path is not a file")
    matter_kind = _MATTER_FILES.get(str(args.get("path") or ""))
    if matter_kind:
        data = _read_bounded(root, compound)
        payload = _matter_page(data, matter_kind, _offset(args))
        payload.update({
            "kind": "matter",
            "path": compound,
            "sha256": hashlib.sha256(data).hexdigest(),
            "bytes": len(data),
            "trust": "untrusted_reference_data",
        })
        return payload
    suffix = resolved.suffix.casefold()
    kind = _KIND_BY_SUFFIX.get(suffix)
    if suffix == ".doc":
        kind = "doc"
    elif suffix == ".xls":
        kind = "xls"
    elif suffix in office_ocr.image_suffixes():
        kind = "image"
    elif kind is None:
        raise OfficeIngestError(_refusal_message(suffix))
    data = _read_bounded(root, compound)
    payload = _analyze(data, suffix, _offset(args))
    payload.update({
        "kind": kind,
        "path": compound,
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
        "trust": "untrusted_reference_data",
    })
    return payload


def _analyze(data: bytes, suffix: str, offset: int) -> dict[str, Any]:
    if suffix == ".docx":
        return _docx_page(data, offset)
    if suffix == ".xlsx":
        return _xlsx_page(data, offset)
    if suffix == ".pptx":
        return _pptx_page(data, offset)
    if suffix == ".pdf":
        return _pdf_page(data, offset)
    if suffix == ".doc":
        return _doc_page(data, offset)
    if suffix == ".xls":
        return _xls_page(data, offset)
    if suffix in office_ocr.image_suffixes():
        return _image_page(data, suffix, offset)
    return _text_page(data, offset)


def _doc_page(data: bytes, offset: int) -> dict[str, Any]:
    try:
        parsed = office_binary.read_doc(data)
    except office_binary.OfficeBinaryError as exc:
        raise OfficeIngestError(str(exc)) from exc
    text = str(parsed["text"])
    lines = text.splitlines()
    payload = pack(
        ((number, "", line) for number, line in enumerate(lines, start=1)),
        offset,
        len(lines),
    )
    payload["revisions"] = parsed["revisions"]
    return payload


def _xls_page(data: bytes, offset: int) -> dict[str, Any]:
    try:
        sheets = office_binary.read_xls(data)
    except office_binary.OfficeBinaryError as exc:
        raise OfficeIngestError(str(exc)) from exc
    total = len(sheets)

    def units() -> Iterator[tuple[int, str, str]]:
        for index, (name, rows) in enumerate(sheets[:MAX_SHEETS], start=1):
            preview = ["\t".join(row[:MAX_PREVIEW_COLS]) for row in rows[:MAX_PREVIEW_ROWS]]
            yield index, name[:128], _xlsx_summary(len(rows), max((len(row) for row in rows), default=0), preview)

    payload = pack(units(), offset, min(total, MAX_SHEETS))
    if total > MAX_SHEETS:
        _append_marker(payload, f"[表页超出 32 张上限:第 {MAX_SHEETS + 1}-{total} 张未读取]")
        payload["truncated"] = True
    return payload


def _image_page(data: bytes, suffix: str, offset: int) -> dict[str, Any]:
    try:
        text = office_ocr.read_image(data, suffix)
    except office_ocr.OfficeOcrError as exc:
        raise OfficeIngestError(str(exc)) from exc
    lines = text.splitlines() or [text]
    return pack(
        ((number, "", line) for number, line in enumerate(lines, start=1)),
        offset,
        len(lines),
    )


def _compound(args: dict) -> str:
    project = args.get("project")
    path = args.get("path")
    if not isinstance(project, str) or not project.strip() or project != project.strip():
        raise OfficeIngestError("project is invalid")
    if not isinstance(path, str) or not path.strip() or path != path.strip():
        raise OfficeIngestError("workspace path is invalid")
    compound = f"{project}/{path}"
    if len(compound.encode("utf-8")) > _COMPOUND_MAX_BYTES:
        raise OfficeIngestError("project path exceeds the workspace path bound")
    return compound


def _offset(args: dict) -> int:
    raw = args.get("offset")
    if raw is None:
        return 0
    if not isinstance(raw, int) or isinstance(raw, bool) or raw < 0:
        raise OfficeIngestError("offset must be a non-negative integer")
    return raw


def _refusal_message(suffix: str) -> str:
    if suffix in {".ppt", ".wps", ".et", ".dps"}:
        return f"{suffix} 旧二进制格式未接入:请另存为 .docx/.xlsx/.pptx 后重试"
    return f"{suffix} 是不支持的摄取类型;支持 .docx .doc .xlsx .xls .pptx .pdf .txt .md 与图片 OCR"


def _pptx_page(data: bytes, offset: int) -> dict[str, Any]:
    entries = _pptx_slides(data)
    total = len(entries)
    entries = entries[:MAX_PPTX_SLIDES]

    def units() -> Iterator[tuple[int, str, str]]:
        for count, name, xml_bytes in entries:
            yield count, name, _pptx_slide_text(xml_bytes)

    payload = pack(units(), offset, total)
    if total > MAX_PPTX_SLIDES:
        marker = f"[幻灯片超出 {MAX_PPTX_SLIDES} 张上限:第 {MAX_PPTX_SLIDES + 1}-{total} 张未读取]"
        _append_marker(payload, marker)
        payload["total_units"] = MAX_PPTX_SLIDES
        payload["truncated"] = True
    return payload


def _pptx_slides(data: bytes) -> list[tuple[int, str, bytes]]:
    try:
        package = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise OfficeIngestError("pptx 数据包损坏:明确拒绝") from exc
    rows: list[tuple[int, str, bytes]] = []
    pattern = re.compile(r"^ppt/slides/slide([0-9]{1,4})\.xml$")
    for name in package.namelist():
        match = pattern.match(name)
        if match is None:
            continue
        try:
            rows.append((int(match.group(1)), f"slide{int(match.group(1))}", package.read(name)))
        except KeyError as exc:  # pragma: no cover - namelist/read mismatch
            raise OfficeIngestError("pptx 幻灯片实体无法读取") from exc
    return sorted(rows)


def _pptx_slide_text(xml_bytes: bytes) -> str:
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise OfficeIngestError("pptx 幻灯片 XML 无法解析") from exc
    lines: list[str] = []
    for node in root.iter(f"{_A_NS}t"):
        piece = (node.text or "").strip()
        if piece:
            lines.append(piece)
    if not lines:
        return "[本页无文本层内容]"
    return "\n".join(lines)[:MAX_ITEM_TEXT_CHARS]


def _read_bounded(root, relative: str) -> bytes:
    try:
        oversized = workspace_files.resolve(root, relative).stat().st_size > MAX_FILE_BYTES
    except OSError as exc:
        raise OfficeIngestError("workspace file is not available") from exc
    if oversized:
        raise OfficeIngestError("文件超过 20MB 摄取上限:该文件被拒绝(明示拒收,不出替身)")
    with workspace_files.open_file(root, relative) as stream:
        data = stream.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES:
        raise OfficeIngestError("文件超过 20MB 摄取上限:该文件被拒绝(明示拒收,不出替身)")
    return data


def pack(
    units: Iterator[tuple[int, str, str]], offset: int, total: int
) -> dict[str, Any]:
    """Page ``units`` (0-based unit indexes until ``total``) under the budget."""

    items: list[dict[str, Any]] = []
    used = 0
    iterator = iter(units)
    budget_stopped = False
    while True:
        try:
            index, label, text = next(iterator)
        except StopIteration:
            break
        if index <= offset:
            continue
        shown = _bounded_text(text)
        budget = len(shown.encode("utf-8")) + _ITEM_OVERHEAD_BYTES
        if items and (used + budget > _RETURN_BUDGET_BYTES or len(items) >= MAX_RETURN_ITEMS):
            budget_stopped = True
            break
        used += budget
        row: dict[str, Any] = {"index": index, "text": shown}
        if label:
            row["label"] = label
        items.append(row)
    return {
        "total_units": total,
        "offset": offset,
        "items": items,
        # 截断只来自"预算/条数打到了还要更多";生成器自然耗尽 = 已到末尾。
        "truncated": budget_stopped,
    }


def _bounded_text(text: str) -> str:
    if len(text) <= MAX_ITEM_TEXT_CHARS:
        return text
    return text[: MAX_ITEM_TEXT_CHARS - len(_MARK_INLINE)] + _MARK_INLINE


def _append_marker(payload: dict[str, Any], marker: str) -> None:
    items = payload["items"]
    if items:
        last = items[-1]
        joined = last["text"] + "\n" + marker
        if len(joined) > MAX_ITEM_TEXT_CHARS:
            head = last["text"][: MAX_ITEM_TEXT_CHARS - len(marker) - 1].rstrip()
            last["text"] = head + "…" + "\n" + marker
        else:
            last["text"] = joined
        return
    items.append({"index": MAX_SHEETS + 1, "text": marker})


def _docx_page(data: bytes, offset: int) -> dict[str, Any]:
    stream = list(_docx_stream(data))
    total = stream[-1][0] if stream else 0
    return pack(((count, "", text) for count, text in stream if text), offset, total)


def _docx_stream(data: bytes) -> Iterator[tuple[int, str]]:
    """Every ``w:p`` of the docx body, numbered in document order (anchor L{n})."""

    try:
        package = zipfile.ZipFile(io.BytesIO(data))
        xml_bytes = package.read("word/document.xml")
    except (zipfile.BadZipFile, KeyError, OSError) as exc:
        raise OfficeIngestError("docx 数据包损坏或缺少 word/document.xml") from exc
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise OfficeIngestError("docx 正文 XML 无法解析") from exc
    for count, paragraph in enumerate(root.iter(f"{_W_NS}p"), start=1):
        text = "".join(node.text or "" for node in paragraph.iter(f"{_W_NS}t"))
        yield count, text


def _xlsx_page(data: bytes, offset: int) -> dict[str, Any]:
    package, shared, entries = _xlsx_book(data)
    total = len(entries)
    entries = entries[:MAX_SHEETS]

    def units() -> Iterator[tuple[int, str, str]]:
        for count, name, target in entries:
            text = (
                _xlsx_sheet_text(package, target, shared)
                if target
                else "[未能定位该工作表的数据实体]"
            )
            yield count, name, text

    payload = pack(units(), offset, total)
    if total > MAX_SHEETS:
        marker = f"[表页超出 32 张上限:第 {MAX_SHEETS + 1}-{total} 张未读取]"
        _append_marker(payload, marker)
        payload["total_units"] = MAX_SHEETS
        payload["truncated"] = True
    if entries:
        _count, name, target = entries[0]
        columns, preview = _xlsx_profile(package, shared, name, target)
        if columns:
            payload["columns"] = columns
        if preview:
            payload["preview"] = preview
    return payload


def _xlsx_book(data: bytes) -> tuple[zipfile.ZipFile, list[str], list[tuple[int, str, str]]]:
    try:
        package = zipfile.ZipFile(io.BytesIO(data))
        shared = _xlsx_shared_strings(package)
        relations = ET.fromstring(package.read("xl/_rels/workbook.xml.rels"))
        targets = {node.get("Id"): node.get("Target") for node in relations.iter(_REL_R_NS)}
        book = ET.fromstring(package.read("xl/workbook.xml"))
    except (zipfile.BadZipFile, KeyError, OSError) as exc:
        raise OfficeIngestError("xlsx 数据包损坏或缺少工作表清单") from exc
    except ET.ParseError as exc:
        raise OfficeIngestError("xlsx 工作表清单 XML 无法解析") from exc
    entries: list[tuple[int, str, str]] = []
    for count, sheet in enumerate(book.iter(f"{_MAIN_NS}sheet"), start=1):
        name = str(sheet.get("name") or f"sheet{count}")[:128]
        target = targets.get(sheet.get(f"{_REL_NS}id") or "")
        entries.append((count, name, target or ""))
    return package, shared, entries


def _xlsx_shared_strings(package: zipfile.ZipFile) -> list[str]:
    try:
        root = ET.fromstring(package.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    except ET.ParseError as exc:
        raise OfficeIngestError("xlsx 共享字符串 XML 无法解析") from exc
    return [
        "".join(node.text or "" for node in item.iter(f"{_MAIN_NS}t"))
        for item in root.iter(f"{_MAIN_NS}si")
    ]


def _xlsx_sheet_text(package: zipfile.ZipFile, target: str, shared: list[str]) -> str:
    try:
        clean = target.lstrip("/")
        if not clean.startswith("xl/"):
            clean = "xl/" + clean
        root = ET.fromstring(package.read(clean))
    except KeyError as exc:
        raise OfficeIngestError("该工作表数据实体缺失") from exc
    except ET.ParseError as exc:
        raise OfficeIngestError("xlsx 工作表数据 XML 无法解析") from exc
    total_rows = sum(1 for _ in root.iter(f"{_MAIN_NS}row"))
    columns = 0
    preview: list[str] = []
    for count, row in enumerate(root.iter(f"{_MAIN_NS}row"), start=1):
        cells = list(row.iter(f"{_MAIN_NS}c"))
        if cells:
            columns = max(columns, _column_reference(cells[-1].get("r") or ""))
        if count <= MAX_PREVIEW_ROWS:
            values = [_xlsx_cell_value(node, shared) for node in cells]
            shown = values[:MAX_PREVIEW_COLS]
            extra = len(values) - len(shown)
            if extra > 0:
                shown.append(f"[列省略 {extra} 列]")
            preview.append("\t".join(shown))
    return _xlsx_summary(total_rows, columns, preview)


def _xlsx_summary(total_rows: int, columns: int, preview: list[str]) -> str:
    lines = [f"rows={total_rows} columns={columns}"]
    lines.extend(preview or ["(空表)"])
    if total_rows > MAX_PREVIEW_ROWS:
        lines.append(
            f"[预览仅展示前 {MAX_PREVIEW_ROWS} 行 × 前 {MAX_PREVIEW_COLS} 列;"
            f"第 {MAX_PREVIEW_ROWS + 1} 起未逐行返回]"
        )
    if total_rows > MAX_ROWS_PER_SHEET:
        lines.append(
            f"[行超出 5000 行上限:第 {MAX_ROWS_PER_SHEET + 1}-{total_rows} 行未读取]"
        )
    return "\n".join(lines)


def _column_reference(reference: str) -> int:
    number = 0
    for character in reference:
        if not character.isalpha():
            break
        number = number * 26 + (ord(character.upper()) - 64)
    return number


def _xlsx_cell_value(cell: ET.Element, shared: list[str]) -> str:
    kind = cell.get("t") or ""
    value_node = cell.find(f"{_MAIN_NS}v")
    if kind == "inlineStr":
        text = "".join(node.text or "" for node in cell.iter(f"{_MAIN_NS}t"))
    elif kind == "s" and value_node is not None:
        try:
            text = shared[int(value_node.text or "-1")]
        except (ValueError, IndexError):
            text = ""
    else:
        text = value_node.text or "" if value_node is not None else ""
    table = str.maketrans({"\n": " ", "\r": " ", "\t": " "})
    return text.translate(table)[:MAX_ITEM_TEXT_CHARS]


def _xlsx_profile(
    package: zipfile.ZipFile, shared: list[str], name: str, target: str
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """Column types for sheet 1, plus a bounded style preview."""

    if not target:
        return [], None
    try:
        clean = target.lstrip("/")
        if not clean.startswith("xl/"):
            clean = "xl/" + clean
        root = ET.fromstring(package.read(clean))
    except (KeyError, OSError, ET.ParseError):
        return [], None
    matrix: list[list[str]] = []
    for row in root.iter(f"{_MAIN_NS}row"):
        if len(matrix) >= MAX_ROWS_PER_SHEET:
            break
        values = [_xlsx_cell_value(node, shared) for node in row.iter(f"{_MAIN_NS}c")]
        matrix.append(values[:MAX_PREVIEW_COLS])
    columns = _column_stats(matrix)
    preview = _style_preview(package, root, name, shared)
    return columns, preview


def _column_stats(matrix: list[list[str]]) -> list[dict[str, Any]]:
    if not matrix:
        return []
    width = max((len(row) for row in matrix), default=0)
    header = matrix[0]
    body = matrix[1:] if len(matrix) > 1 else []
    stats: list[dict[str, Any]] = []
    for index in range(min(width, MAX_PREVIEW_COLS)):
        name = header[index] if index < len(header) and header[index] else f"列{index + 1}"
        values = [row[index] for row in body if index < len(row)]
        present = [value for value in values if value]
        empty = len(values) - len(present)
        kind = _column_kind(present)
        row: dict[str, Any] = {"name": name[:128], "type": kind, "empty": empty}
        if kind == "number" and present:
            numbers = [float(value) for value in present]
            row["min"] = min(numbers)
            row["max"] = max(numbers)
            row["sum"] = sum(numbers)
            row["avg"] = sum(numbers) / len(numbers)
        stats.append(row)
    return stats


def _column_kind(values: list[str]) -> str:
    if not values:
        return "text"
    if all(re.fullmatch(r"\d{4}-\d{2}-\d{2}|\d{4}/\d{1,2}/\d{1,2}", value) for value in values):
        return "date"
    if all(_is_number(value) for value in values):
        return "number"
    return "text"


def _is_number(value: str) -> bool:
    try:
        float(value)
    except ValueError:
        return False
    return True


def _style_preview(
    package: zipfile.ZipFile, root: ET.Element, name: str, shared: list[str]
) -> dict[str, Any]:
    """Bounded desktop model: merges, font/fill/align/border, widths, theme.

    Rows past the preview window stay out of this object and set ``truncated``
    so a short model is never presented as the whole sheet.
    """

    theme = _theme_colors(package)
    styles = _cell_styles(package, theme)
    merge_refs = [node.get("ref") or "" for node in root.iter(f"{_MAIN_NS}mergeCell")]
    merge_refs = [ref for ref in merge_refs if ref]
    all_rows = list(root.iter(f"{_MAIN_NS}row"))
    truncated = len(all_rows) > MAX_PREVIEW_ROWS or len(merge_refs) > 32
    spans = _merge_spans(merge_refs)
    rows: list[dict[str, Any]] = []
    for row in all_rows[:MAX_PREVIEW_ROWS]:
        nodes = list(row.iter(f"{_MAIN_NS}c"))
        if len(nodes) > MAX_PREVIEW_COLS:
            truncated = True
        cells: list[dict[str, Any]] = []
        for node in nodes[:MAX_PREVIEW_COLS]:
            cell: dict[str, Any] = {"v": _xlsx_cell_value(node, shared)[:200]}
            style = node.get("s")
            if style and style.isdigit():
                index = int(style)
                if index < len(styles):
                    cell.update(styles[index])
            span = spans.get(str(node.get("r") or "").upper())
            if span is not None:
                row_span, col_span = span
                if row_span > 1:
                    cell["rs"] = row_span
                if col_span > 1:
                    cell["cs"] = col_span
            cells.append(cell)
        item: dict[str, Any] = {"cells": cells}
        height = row.get("ht")
        if height:
            item["height"] = height[:16]
            pixels = _row_px(height)
            if pixels is not None:
                item["height_px"] = pixels
        rows.append(item)
    widths, width_truncated = _column_widths(root)
    preview: dict[str, Any] = {
        "sheet": name[:128],
        "merges": merge_refs[:32],
        "rows": rows,
    }
    if widths:
        preview["widths"] = widths
        preview["widths_px"] = [_width_px(item) for item in widths]
    if theme:
        preview["theme"] = theme
    if truncated or width_truncated:
        preview["truncated"] = True
    return preview


def _cell_styles(package: zipfile.ZipFile, theme: list[str]) -> list[dict[str, Any]]:
    """Resolve ``c@s`` through cellXfs, not the font table."""

    try:
        root = ET.fromstring(package.read("xl/styles.xml"))
    except (KeyError, OSError, ET.ParseError):
        return []
    fonts = _font_rows(root, theme)
    fills = _fill_rows(root, theme)
    borders = _border_rows(root)
    cell_xfs = root.find(f"{_MAIN_NS}cellXfs")
    styles: list[dict[str, Any]] = []
    for xf in list(cell_xfs)[:64] if cell_xfs is not None else []:
        row: dict[str, Any] = {}
        font_id = _xml_int(xf.get("fontId"))
        if font_id is not None and 0 <= font_id < len(fonts):
            row.update(fonts[font_id])
        fill_id = _xml_int(xf.get("fillId"))
        if fill_id is not None and 0 <= fill_id < len(fills):
            row.update(fills[fill_id])
        border_id = _xml_int(xf.get("borderId"))
        if border_id is not None and 0 <= border_id < len(borders):
            row.update(borders[border_id])
        align = xf.find(f"{_MAIN_NS}alignment")
        if align is not None:
            horizontal = align.get("horizontal")
            vertical = align.get("vertical")
            if horizontal:
                row["align"] = str(horizontal)[:16]
            if vertical:
                row["valign"] = str(vertical)[:16]
            if align.get("wrapText") in {"1", "true", "True"}:
                row["wrap"] = True
        styles.append(row)
    return styles


def _font_rows(root: ET.Element, theme: list[str]) -> list[dict[str, Any]]:
    parent = root.find(f"{_MAIN_NS}fonts")
    fonts: list[dict[str, Any]] = []
    for font in list(parent)[:64] if parent is not None else []:
        row: dict[str, Any] = {}
        if font.find(f"{_MAIN_NS}b") is not None:
            row["bold"] = True
        size = font.find(f"{_MAIN_NS}sz")
        if size is not None and size.get("val"):
            row["size"] = str(size.get("val"))[:16]
        name = font.find(f"{_MAIN_NS}name")
        if name is not None and name.get("val"):
            row["name"] = str(name.get("val"))[:32]
        color = _paint(font.find(f"{_MAIN_NS}color"), theme)
        if color:
            row["color"] = color
        fonts.append(row)
    return fonts


def _fill_rows(root: ET.Element, theme: list[str]) -> list[dict[str, Any]]:
    parent = root.find(f"{_MAIN_NS}fills")
    fills: list[dict[str, Any]] = []
    for fill in list(parent)[:64] if parent is not None else []:
        pattern = fill.find(f"{_MAIN_NS}patternFill")
        kind = pattern.get("patternType") if pattern is not None else None
        if pattern is None or kind in {None, "none", "gray125"}:
            fills.append({})
            continue
        paint = _paint(pattern.find(f"{_MAIN_NS}fgColor"), theme)
        fills.append({"fill": paint} if paint else {})
    return fills


def _border_rows(root: ET.Element) -> list[dict[str, Any]]:
    parent = root.find(f"{_MAIN_NS}borders")
    borders: list[dict[str, Any]] = []
    for border in list(parent)[:64] if parent is not None else []:
        sides: list[str] = []
        for side in ("left", "right", "top", "bottom"):
            node = border.find(f"{_MAIN_NS}{side}")
            style = node.get("style") if node is not None else None
            if style:
                sides.append(f"{side[0]}:{style}")
        borders.append({"border": " ".join(sides)[:64]} if sides else {})
    return borders


def _paint(node: ET.Element | None, theme: list[str]) -> str:
    if node is None:
        return ""
    tint = node.get("tint")
    rgb = node.get("rgb")
    if rgb:
        return _apply_tint(str(rgb)[:16], tint)
    index = _xml_int(node.get("theme"))
    if index is not None and 0 <= index < len(theme) and theme[index]:
        return _apply_tint(theme[index][:16], tint)
    return ""


def _apply_tint(color: str, tint: str | None) -> str:
    """SpreadsheetML tint: negative darkens, positive lightens. No lumMod."""

    if not tint:
        return color
    try:
        value = float(tint)
    except ValueError:
        return color
    if value < -1 or value > 1:
        return color
    raw = color.strip()
    alpha = raw[:2] if len(raw) == 8 else ""
    body = raw[2:] if alpha else raw
    if len(body) != 6 or any(char not in "0123456789ABCDEFabcdef" for char in body):
        return color
    mixed: list[str] = []
    for offset in (0, 2, 4):
        channel = int(body[offset : offset + 2], 16)
        painted = (
            channel * (1 + value) if value < 0 else channel * (1 - value) + 255 * value
        )
        mixed.append(f"{max(0, min(255, round(painted))):02X}")
    return (alpha + "".join(mixed))[:16]


def _column_widths(root: ET.Element) -> tuple[list[str], bool]:
    slots = [""] * MAX_PREVIEW_COLS
    seen = False
    truncated = False
    for col in root.iter(f"{_MAIN_NS}col"):
        start = _xml_int(col.get("min"))
        end = _xml_int(col.get("max"))
        width = str(col.get("width") or "")[:16]
        if start is None or end is None or not width:
            continue
        seen = True
        if end > MAX_PREVIEW_COLS or start > MAX_PREVIEW_COLS:
            truncated = True
        for index in range(max(start, 1), min(end, MAX_PREVIEW_COLS) + 1):
            slots[index - 1] = width
    if not seen:
        return [], truncated
    while slots and not slots[-1]:
        slots.pop()
    return slots, truncated


def _theme_colors(package: zipfile.ZipFile) -> list[str]:
    try:
        root = ET.fromstring(package.read("xl/theme/theme1.xml"))
    except (KeyError, OSError, ET.ParseError):
        return []
    scheme = next((node for node in root.iter() if node.tag.endswith("clrScheme")), None)
    if scheme is None:
        return []
    colors: list[str] = []
    for child in list(scheme)[:12]:
        paint = ""
        for node in child.iter():
            if node.tag.endswith("srgbClr") and node.get("val"):
                paint = str(node.get("val"))[:8]
                break
            if node.tag.endswith("sysClr") and node.get("lastClr"):
                paint = str(node.get("lastClr"))[:8]
        colors.append(paint)
    return colors


def _width_px(raw: str) -> int:
    """SpreadsheetML character width to pixels. Empty slots stay 0."""

    if not raw:
        return 0
    try:
        value = float(raw)
    except ValueError:
        return 0
    pixels = int(((256 * value + int(128 / 7)) / 256) * 7)
    return max(0, min(pixels, 4096))


def _row_px(raw: str) -> int | None:
    """Row height is stored in points. Preview pixels use 96 dpi."""

    try:
        points = float(raw)
    except ValueError:
        return None
    if points < 0:
        return None
    return max(0, min(round(points * 96 / 72), 4096))


def _merge_spans(refs: list[str]) -> dict[str, tuple[int, int]]:
    spans: dict[str, tuple[int, int]] = {}
    for ref in refs:
        if ":" not in ref:
            continue
        start, end = ref.split(":", 1)
        left = _cell_ref(start)
        right = _cell_ref(end)
        if left is None or right is None:
            continue
        (c1, r1), (c2, r2) = left, right
        origin = _col_name(min(c1, c2)) + str(min(r1, r2))
        spans[origin] = (min(abs(r2 - r1) + 1, 5000), min(abs(c2 - c1) + 1, 64))
    return spans


def _cell_ref(raw: str) -> tuple[int, int] | None:
    match = re.fullmatch(r"([A-Z]+)([0-9]+)", raw.strip().upper())
    if match is None:
        return None
    return _col_index(match.group(1)), int(match.group(2))


def _col_index(letters: str) -> int:
    value = 0
    for char in letters:
        value = value * 26 + (ord(char) - 64)
    return value


def _col_name(index: int) -> str:
    letters = ""
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def _xml_int(raw: str | None) -> int | None:
    if raw is None or not str(raw).isdigit():
        return None
    return int(raw)


def _pdf_page(data: bytes, offset: int) -> dict[str, Any]:
    try:
        from pypdf import PdfReader  # noqa: PLC0415 -- optional text layer engine
    except ImportError as exc:
        raise OfficeIngestError(
            "pdf 文本层引擎(pypdf)未安装:明确拒绝,不返回与肉眼不符的替身文本"
        ) from exc
    try:
        reader = PdfReader(io.BytesIO(data))
    except Exception as exc:  # noqa: BLE001 -- third-party parser surface varies
        raise OfficeIngestError("pdf 已加密或损坏,文本层不可用") from exc
    total = len(reader.pages)
    texts = [_pdf_text(reader, number) for number in range(1, total + 1)]
    if total and not any(text.strip() for text in texts):
        try:
            texts = office_ocr.read_pdf_pages(data)
        except office_ocr.OfficeOcrError as exc:
            raise OfficeIngestError(str(exc)) from exc
        total = len(texts)
    pages = ((number, "", text) for number, text in enumerate(texts, start=1))
    return pack(pages, offset, total)


def _pdf_text(reader, number: int) -> str:
    try:
        text = reader.pages[number - 1].extract_text() or ""
    except Exception:  # noqa: BLE001 -- report the page honestly, never half-wrong
        return "[本页文本层提取失败]"
    return _bounded_text(text)


def _text_page(data: bytes, offset: int) -> dict[str, Any]:
    try:
        text = data.decode("utf-8")
    except UnicodeError as exc:
        raise OfficeIngestError("文件不是 UTF-8 文本(可能为旧编码或二进制):明确拒绝") from exc
    lines = text.splitlines()
    return pack(
        ((number, "", line) for number, line in enumerate(lines, start=1)), offset, len(lines)
    )


def _matter_page(data: bytes, expected: str, offset: int) -> dict[str, Any]:
    """Read one fixed matter file. This path never writes."""

    try:
        document = json.loads(data.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise OfficeIngestError("matter 文件不是 UTF-8 JSON") from exc
    if not isinstance(document, dict) or document.get("kind") != expected:
        raise OfficeIngestError("matter 文件 kind 与文件名不一致")
    if expected == "mindmap":
        return _mindmap_page(document, offset)
    label = "events" if expected == "timeline" else "entries"
    text_key = "title" if expected == "timeline" else "fact"
    rows = document.get(label)
    if not isinstance(rows, list):
        raise OfficeIngestError(f"matter {label} 必须是数组")
    units = []
    missing = 0
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            continue
        if not row.get("evidence"):
            missing += 1
        text = f"{row.get('display_date') or row.get('date') or ''} {row.get(text_key) or ''}".strip()
        marker = "待补出处" if not row.get("evidence") else ""
        units.append((index, marker, text or "(空)"))
    payload = pack(iter(units), offset, len(rows))
    if missing:
        payload["note"] = f"有 {missing} 项没有出处，请补充 evidence 后再次 upsert"[:200]
    return payload


def _mindmap_page(document: dict, offset: int) -> dict[str, Any]:
    root = document.get("root")
    if not isinstance(root, dict):
        raise OfficeIngestError("mindmap 缺少 root")
    from company_agent.office_matter import _mindmap_svg  # noqa: PLC0415 -- avoid an import cycle

    flat: list[tuple[int, str, str]] = []

    def walk(node: dict) -> None:
        label = str(node.get("label") or "")
        marker = "" if node.get("evidence") else "待补出处"
        flat.append((len(flat) + 1, marker, label or "(空)"))
        for child in node.get("children") or []:
            if isinstance(child, dict):
                walk(child)

    walk(root)
    payload = pack(iter(flat), offset, len(flat))
    svg = _mindmap_svg(root)
    notes: list[str] = []
    if svg and len(svg) <= 20_000:
        payload["svg"] = svg
    elif svg:
        notes.append("思维导图超出回执篇幅，未内嵌 SVG")
    missing = sum(1 for _index, marker, _text in flat if marker)
    if missing:
        notes.append(f"有 {missing} 项没有出处，请补充 evidence 后再次 upsert")
    if notes:
        payload["note"] = "；".join(notes)[:200]
    return payload
