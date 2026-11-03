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
- no OCR, no conversion, no execution and no external calls: ``.doc``,
  ``.xls``, ``.ppt``, images and unknown suffixes are refused honestly.
"""
from __future__ import annotations

import hashlib
import io
import re
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Iterator
from typing import Any

from company_agent import workspace_files

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
    suffix = resolved.suffix.casefold()
    kind = _KIND_BY_SUFFIX.get(suffix)
    if kind is None:
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
    return _text_page(data, offset)


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
    if suffix in {".doc", ".xls", ".wps", ".et", ".dps"}:
        return f"{suffix} 旧二进制格式未接入:请在 Word/WPS 中另存为 .docx/.xlsx/.pptx 后重试"
    if suffix in {".ppt"}:
        return f"{suffix} 旧二进制格式未接入:请在 PowerPoint/WPS 中另存为 .pptx 后重试"
    if suffix in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif", ".tiff"}:
        return f"{suffix} 图片 OCR 未接入:当前明确拒绝,不返回空文本"
    return f"{suffix} 是不支持的摄取类型;支持 .docx .xlsx .pptx .pdf .txt .md"


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
    pages = ((number, "", _pdf_text(reader, number)) for number in range(1, total + 1))
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
