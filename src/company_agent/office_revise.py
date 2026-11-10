"""Save spreadsheet cells and Word text from the company window.

The document preview can change a cell or a paragraph. This module writes
those changes back into the existing file. It is not a second renderer and
it does not replace ``company_office_edit``: a model still revises a project
document through that tool. A window save names a file relative to the
mounted workspace and refuses anything outside it.
"""
from __future__ import annotations

import hashlib
import io
import json
import math
import re
import zipfile
import xml.etree.ElementTree as ET

from company_agent import office_create as _oc
from company_agent import office_edit as _edit
from company_agent import office_purpose, workspace_files

_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PKG = "http://schemas.openxmlformats.org/package/2006/relationships"
_CELL_RE = re.compile(r"^([A-Z]{1,3})([1-9][0-9]{0,6})$")
_MAX_UPDATES = 500


class OfficeReviseError(ValueError):
    """A window save that stops before replacing the file."""


def revise(payload: dict) -> str:
    """Return one JSON object for a window save, including an expected refusal."""

    try:
        if not isinstance(payload, dict):
            raise OfficeReviseError("请求必须是对象")
        kind = payload.get("kind")
        if kind == "sheet":
            result = revise_sheet(payload)
        elif kind == "docx":
            result = revise_docx(payload)
        elif kind == "docx-view":
            result = view_docx(payload)
        elif kind == "docx-write":
            result = write_docx_blocks(payload)
        else:
            raise OfficeReviseError("kind 必须是 sheet、docx、docx-view 或 docx-write")
    except (OfficeReviseError, _edit.OfficeEditError, _oc.OfficeCreateError, workspace_files.WorkspaceFileError, ValueError) as exc:
        result = {"error": str(exc)[:180]}
    return json.dumps(result, ensure_ascii=False)


def revise_sheet(payload: dict) -> dict:
    """Replace the named cells and leave every other part of the workbook in place."""

    purpose = office_purpose.take(payload)
    target, data = _open_office(payload.get("path"), ".xlsx")
    sheets = payload.get("sheets")
    if not isinstance(sheets, list) or not sheets or len(sheets) > _oc.MAX_SHEETS:
        raise OfficeReviseError(f"sheets 必须是 1..{_oc.MAX_SHEETS} 个工作表")
    updates = _sheet_updates(sheets)
    with zipfile.ZipFile(io.BytesIO(data)) as package:
        names = set(package.namelist())
        located = _sheet_parts(package)
        missing = sorted({name for name, _cells in updates} - set(located))
        if missing:
            raise OfficeReviseError(f"工作表不存在: {missing[0]}")
        styled = any(spec is not None for _name, cells in updates for _value, spec in cells.values())
        style_root = _style_root(package) if styled else None
        replaced: dict[str, bytes] = {}
        for name, cells in updates:
            part = located[name]
            if part not in names:
                raise OfficeReviseError("工作表部件缺失")
            replaced[part] = _rewrite_sheet(package.read(part), cells, style_root)
        if style_root is not None:
            replaced["xl/styles.xml"] = _styles_bytes(style_root)
    revised = _repack(data, replaced)
    _oc._write_atomic(target, revised, True)
    _oc._verify_written(target, revised)
    office_purpose.audit("office_revise_sheet", purpose, {"path": _relative(payload), "cells": sum(len(cells) for _name, cells in updates)})
    return {"saved": True, "kind": "xlsx", "cells": sum(len(cells) for _name, cells in updates), "bytes": len(revised), "sha256": hashlib.sha256(revised).hexdigest()}


def revise_docx(payload: dict) -> dict:
    """Apply one tracked text change to a workspace-relative .docx."""

    purpose = office_purpose.take(payload)
    target, data = _open_office(payload.get("path"), ".docx")
    find = payload.get("find")
    replace = payload.get("replace")
    occurrences = payload.get("occurrences")
    edit = {"find": find, "replace": replace}
    if occurrences is not None:
        edit["occurrences"] = occurrences
    edits, author, _note = _edit._edits_and_meta({
        "project": "desk",
        "path": "note.docx",
        "edits": [edit],
        "purpose": purpose,
        "author": "company-agent",
    })
    root_el = _edit._parse_document(data)
    paragraphs = list(root_el.iter(f"{_edit._W}p"))
    visible = [_edit._paragraph_text(paragraph) for paragraph in paragraphs]
    eligible = {index: _edit._plain_paragraph(paragraph) for index, paragraph in enumerate(paragraphs)}
    plans, skipped = _edit._plan_spans(edits, visible, eligible)
    if not plans:
        reason = skipped[0]["reason"] if skipped else "no_change"
        raise OfficeReviseError(f"修订没有写入: {reason}")
    after = {index: _edit._replay(visible[index], row) for index, row in plans.items()}
    for index in sorted(plans):
        _edit._apply_paragraph_changes(paragraphs[index], plans[index], author)
    _edit._repair_tracked_format(root_el)
    document_xml = _edit._serialize(root_el)
    revised = _edit._repackage(data, document_xml)
    if len(revised) > _edit.MAX_FILE_BYTES:
        raise OfficeReviseError("修订后的文件超过 20MB 上限")
    _oc._write_atomic(target, revised, True)
    _oc._verify_written(target, revised)
    disk = target.read_bytes()
    fallible = _edit._read_back_replay(_edit.document_xml_bytes(disk), after)
    if fallible:
        _restore(target, data)
        raise OfficeReviseError("写回后的正文与修订不一致,已恢复原文件")
    office_purpose.audit("office_revise_docx", purpose, {"path": _relative(payload), "edited": len(plans)})
    return {
        "saved": True,
        "kind": "docx",
        "edited": len(plans),
        "hunks": sum(len(row) for row in plans.values()),
        "skipped": skipped[:8],
        "bytes": len(revised),
        "sha256": hashlib.sha256(revised).hexdigest(),
    }


def _relative(payload: dict) -> str:
    path = payload.get("path")
    return path if isinstance(path, str) else ""


def _open_office(path: object, suffix: str) -> tuple:
    root = workspace_files.root()
    if not isinstance(path, str):
        raise OfficeReviseError("文件路径无效")
    relative = workspace_files._lexical(path)
    if not relative.casefold().endswith(suffix):
        raise OfficeReviseError(f"只接受 {suffix} 文件")
    target = workspace_files.resolve(root, relative)
    data = target.read_bytes()
    if len(data) > _oc.MAX_FILE_BYTES:
        raise OfficeReviseError("文件超过 20MB 上限")
    return target, data


def _restore(target, data: bytes) -> None:
    _oc._write_atomic(target, data, True)


def _sheet_updates(sheets: list) -> list[tuple[str, dict[str, object]]]:
    updates = []
    seen = set()
    total = 0
    for sheet in sheets:
        if not isinstance(sheet, dict):
            raise OfficeReviseError("每个工作表必须是对象")
        name = sheet.get("name")
        if not isinstance(name, str) or not name or len(name) > _oc.MAX_SHEET_NAME_CHARS:
            raise OfficeReviseError("工作表名称无效")
        if any(mark in name for mark in "[]:*?/\\"):
            raise OfficeReviseError("工作表名称无效")
        if name in seen:
            raise OfficeReviseError("工作表名称重复")
        seen.add(name)
        cells = sheet.get("cells")
        if not isinstance(cells, list) or not cells:
            raise OfficeReviseError("cells 必须是非空数组")
        mapped: dict[str, tuple[object, dict | None]] = {}
        for cell in cells:
            if not isinstance(cell, dict):
                raise OfficeReviseError("每个单元格必须是对象")
            ref = cell.get("cell")
            if not isinstance(ref, str) or _CELL_RE.fullmatch(ref) is None:
                raise OfficeReviseError("单元格地址无效")
            column, row = _CELL_RE.fullmatch(ref).groups()
            if _column_index(column) > _oc.MAX_COLS or int(row) > _oc.MAX_ROWS_PER_SHEET:
                raise OfficeReviseError("单元格超出表格上限")
            value = cell.get("value")
            if isinstance(value, bool) or value is None:
                stored = value
            elif isinstance(value, int):
                stored = value
            elif isinstance(value, float):
                if not math.isfinite(value):
                    raise OfficeReviseError("单元格必须是有限数")
                stored = value
            elif isinstance(value, str):
                if len(value) > _oc.MAX_CELL_TEXT_CHARS:
                    raise OfficeReviseError("单元格文本超过上限")
                stored = value
            else:
                raise OfficeReviseError("单元格只支持字符串、数字或空值")
            extra = set(cell) - {"cell", "value", "style"}
            if extra:
                raise OfficeReviseError("单元格含未知字段")
            mapped[ref] = (stored, _style_spec(cell))
            total += 1
            if total > _MAX_UPDATES:
                raise OfficeReviseError(f"一次最多修改 {_MAX_UPDATES} 个单元格")
        updates.append((name, mapped))
    return updates


def _column_index(letters: str) -> int:
    index = 0
    for letter in letters:
        index = index * 26 + ord(letter) - 64
    return index


def _sheet_parts(package: zipfile.ZipFile) -> dict[str, str]:
    try:
        workbook = ET.fromstring(package.read("xl/workbook.xml"))
        relations = ET.fromstring(package.read("xl/_rels/workbook.xml.rels"))
    except (KeyError, ET.ParseError) as exc:
        raise OfficeReviseError("工作簿结构无法读取") from exc
    targets = {}
    for relation in relations.iter(f"{{{_PKG}}}Relationship"):
        identity = relation.get("Id")
        target = relation.get("Target")
        if identity and target:
            targets[identity] = target
    found = {}
    for sheet in workbook.iter(f"{{{_MAIN}}}sheet"):
        name = sheet.get("name")
        target = targets.get(sheet.get(f"{{{_REL}}}id") or "")
        if not name or not target:
            continue
        part = target.replace("\\", "/").lstrip("/")
        if not part.startswith("xl/"):
            part = "xl/" + part
        if ".." in part.split("/"):
            raise OfficeReviseError("工作表路径无效")
        found[name] = part
    return found


def _rewrite_sheet(xml: bytes, cells: dict[str, tuple[object, dict | None]], style_root: ET.Element | None) -> bytes:
    try:
        text = xml.decode("utf-8")
    except UnicodeError as exc:
        raise OfficeReviseError("工作表 XML 无法解析") from exc
    prefix = _markup_prefix(text, "worksheet") or _markup_prefix(text, "sheetData")
    for ref, _payload in cells.items():
        span = _marked_span(text, "c", ref)
        if span is not None and _formula_span(text[span[0]:span[1]]):
            raise OfficeReviseError(f"{ref} 含公式,窗口保存不改公式")
    for ref, (value, spec) in cells.items():
        text = _splice_cell(text, ref, value, spec, style_root, prefix)
    return text.encode("utf-8")


_MARKUP_OPEN = re.compile(
    r"<(?P<qname>(?P<prefix>[A-Za-z_][\w.-]*:)?(?P<tag>sheetData|row|c))\b(?P<attrs>[^>]*?)(?P<slash>/?)>"
)


def _markup_prefix(text: str, tag: str) -> str:
    for match in _MARKUP_OPEN.finditer(text):
        if match.group("tag") == tag:
            return match.group("prefix") or ""
    return ""


def _marked_span(text: str, tag: str, ref: str | None = None, within: tuple[int, int] | None = None) -> tuple[int, int] | None:
    start_at = 0 if within is None else within[0]
    end_at = len(text) if within is None else within[1]
    for match in _MARKUP_OPEN.finditer(text, start_at, end_at):
        if match.group("tag") != tag:
            continue
        if ref is not None and _markup_attr(match.group("attrs"), "r") != ref:
            continue
        if match.start() < start_at or match.end() > end_at:
            continue
        if match.group("slash"):
            return match.start(), match.end()
        close = f"</{match.group('qname')}>"
        finish = text.find(close, match.end(), end_at)
        if finish < 0:
            raise OfficeReviseError("工作表 XML 无法解析")
        return match.start(), finish + len(close)
    return None


def _markup_attr(attrs: str, name: str) -> str | None:
    found = re.search(rf"(?:^|\s){name}\s*=\s*([\"'])(.*?)\1", attrs)
    return found.group(2) if found is not None else None


def _formula_span(fragment: str) -> bool:
    return re.search(r"<(?:[A-Za-z_][\w.-]*:)?f[\s>/]", fragment) is not None


def _splice_cell(text: str, ref: str, value: object, spec: dict | None, style_root: ET.Element | None, prefix: str) -> str:
    column, row_text = _CELL_RE.fullmatch(ref).groups()
    span = _marked_span(text, "c", ref)
    old_style = None
    cell_prefix = prefix
    if span is not None:
        opening = _MARKUP_OPEN.match(text, span[0])
        if opening is not None:
            old_style = _markup_attr(opening.group("attrs"), "s")
            cell_prefix = opening.group("prefix") or ""
    style = _style_index(style_root, old_style, spec) if spec is not None and style_root is not None else old_style
    built = _cell_markup(cell_prefix or prefix, ref, "" if value is None else value, style, spec)
    if span is not None:
        updated = text[:span[0]] + (built or "") + text[span[1]:]
        if built is None:
            updated = _drop_empty_row(updated, row_text)
        return updated
    if built is None:
        return text
    return _insert_cell(text, built, row_text, _column_index(column), prefix)


def _cell_markup(prefix: str, ref: str, value: object, style: str | None, spec: dict | None) -> str | None:
    if (value is None or value == "") and spec is None:
        return None
    if value is None:
        value = ""
    attrs = f' r="{ref}"'
    if style:
        attrs += f' s="{style}"'
    name = f"{prefix}c"
    if isinstance(value, bool):
        body = f"<{prefix}is><{prefix}t>{'TRUE' if value else 'FALSE'}</{prefix}t></{prefix}is>"
        return f'<{name} t="inlineStr"{attrs}>{body}</{name}>'
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        stored = str(value) if isinstance(value, int) else repr(value)
        return f"<{name}{attrs}><{prefix}v>{stored}</{prefix}v></{name}>"
    escaped = str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    space = ' xml:space="preserve"' if str(value)[:1].isspace() or str(value)[-1:].isspace() or "\n" in str(value) else ""
    return f'<{name} t="inlineStr"{attrs}><{prefix}is><{prefix}t{space}>{escaped}</{prefix}t></{prefix}is></{name}>'


def _drop_empty_row(text: str, row_text: str) -> str:
    span = _marked_span(text, "row", row_text)
    if span is None or _marked_span(text, "c", within=span) is not None:
        return text
    return text[:span[0]] + text[span[1]:]


def _insert_cell(text: str, cell: str, row_text: str, column: int, prefix: str) -> str:
    row = _marked_span(text, "row", row_text)
    if row is None:
        return _insert_row(text, f'<{prefix}row r="{row_text}">{cell}</{prefix}row>', int(row_text), prefix)
    opening = _MARKUP_OPEN.match(text, row[0])
    if opening is not None and opening.group("slash"):
        name = opening.group("qname")
        expanded = text[row[0]:opening.end() - 2] + f">{cell}</{name}>"
        return text[:row[0]] + expanded + text[row[1]:]
    cells = []
    cursor = opening.end() if opening is not None else row[0]
    while True:
        found = _marked_span(text, "c", within=(cursor, row[1]))
        if found is None:
            break
        cells.append(found)
        cursor = found[1]
    for start, finish in cells:
        match = _MARKUP_OPEN.match(text, start)
        ref = _markup_attr(match.group("attrs"), "r") if match is not None else None
        parsed = _CELL_RE.fullmatch(ref or "")
        if parsed and _column_index(parsed.group(1)) > column:
            return text[:start] + cell + text[start:]
    close = text.rfind("<", row[0], row[1])
    return text[:close] + cell + text[close:]


def _insert_row(text: str, row_xml: str, row_number: int, prefix: str) -> str:
    data = _marked_span(text, "sheetData")
    if data is None:
        raise OfficeReviseError("工作表缺少数据区")
    opening = _MARKUP_OPEN.match(text, data[0])
    if opening is not None and opening.group("slash"):
        name = opening.group("qname")
        expanded = text[data[0]:opening.end() - 2] + f">{row_xml}</{name}>"
        return text[:data[0]] + expanded + text[data[1]:]
    cursor = opening.end() if opening is not None else data[0]
    while True:
        found = _marked_span(text, "row", within=(cursor, data[1]))
        if found is None:
            break
        match = _MARKUP_OPEN.match(text, found[0])
        current = _markup_attr(match.group("attrs"), "r") if match is not None else None
        if current is not None and current.isdigit() and int(current) > row_number:
            return text[:found[0]] + row_xml + text[found[0]:]
        cursor = found[1]
    close = text.rfind("<", data[0], data[1])
    return text[:close] + row_xml + text[close:]


def _repack(data: bytes, replacements: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as source, zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as dest:
        for info in source.infolist():
            dest.writestr(info, replacements.get(info.filename, source.read(info.filename)))
    return buffer.getvalue()


_STYLE_KEYS = {"bold", "italic", "strike", "underline", "size", "color", "fill", "align", "valign", "wrap", "font"}
_STYLE_ORDER = ("numFmts", "fonts", "fills", "borders", "cellStyleXfs", "cellXfs", "cellStyles", "dxfs", "tableStyles", "colors")
_ALIGN = {"left", "center", "right"}
_VALIGN = {"top", "center", "bottom"}
_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")
_BLOCK_ID = re.compile(r"^p[0-9]{1,4}$")
_MAX_BLOCKS = 800
_MAX_BLOCK_CHARS = 1500
_DOC_ALIGN = {"left", "center", "right", "both"}


def _style_spec(cell: dict) -> dict | None:
    if "style" not in cell:
        return None
    style = cell.get("style")
    if not isinstance(style, dict) or not style or set(style) - _STYLE_KEYS:
        raise OfficeReviseError("单元格样式无效")
    spec: dict = {}
    for key in ("bold", "italic", "strike", "underline", "wrap"):
        if key in style:
            if not isinstance(style[key], bool):
                raise OfficeReviseError("单元格样式无效")
            spec[key] = style[key]
    if "size" in style:
        size = style["size"]
        if isinstance(size, bool) or not isinstance(size, (int, float)) or isinstance(size, float) and not size.is_integer() or not 8 <= float(size) <= 72:
            raise OfficeReviseError("字号无效")
        spec["size"] = int(size)
    for key in ("color", "fill"):
        if key in style:
            if not isinstance(style[key], str) or _COLOR.fullmatch(style[key]) is None:
                raise OfficeReviseError("颜色无效")
            spec[key] = style[key].upper()
    if "align" in style:
        if style["align"] not in _ALIGN:
            raise OfficeReviseError("水平对齐无效")
        spec["align"] = style["align"]
    if "valign" in style:
        if style["valign"] not in _VALIGN:
            raise OfficeReviseError("垂直对齐无效")
        spec["valign"] = style["valign"]
    if "font" in style:
        font = style["font"]
        if not isinstance(font, str) or not font.strip() or len(font) > 40 or any(mark in font for mark in "<>&"):
            raise OfficeReviseError("字体名称无效")
        spec["font"] = font.strip()
    if not spec:
        raise OfficeReviseError("单元格样式无效")
    return spec


def _style_root(package: zipfile.ZipFile) -> ET.Element:
    try:
        xml = package.read("xl/styles.xml")
        for _event, (prefix, uri) in ET.iterparse(io.BytesIO(xml), events=("start-ns",)):
            ET.register_namespace(prefix, uri)
        root = ET.fromstring(xml)
    except (KeyError, ET.ParseError, ValueError) as exc:
        raise OfficeReviseError("表格样式表无法读取") from exc
    if root.tag != f"{{{_MAIN}}}styleSheet":
        raise OfficeReviseError("表格样式表无法读取")
    _prepare_styles(root)
    return root


def _prepare_styles(root: ET.Element) -> None:
    fonts = _ensure_style(root, "fonts")
    if not list(fonts):
        font = ET.SubElement(fonts, f"{{{_MAIN}}}font")
        ET.SubElement(font, f"{{{_MAIN}}}sz").set("val", "11")
        ET.SubElement(font, f"{{{_MAIN}}}name").set("val", "Calibri")
    fills = _ensure_style(root, "fills")
    if not list(fills):
        ET.SubElement(ET.SubElement(fills, f"{{{_MAIN}}}fill"), f"{{{_MAIN}}}patternFill").set("patternType", "none")
    if len(list(fills)) == 1:
        ET.SubElement(ET.SubElement(fills, f"{{{_MAIN}}}fill"), f"{{{_MAIN}}}patternFill").set("patternType", "gray125")
    borders = _ensure_style(root, "borders")
    if not list(borders):
        border = ET.SubElement(borders, f"{{{_MAIN}}}border")
        for side in ("left", "right", "top", "bottom", "diagonal"):
            ET.SubElement(border, f"{{{_MAIN}}}{side}")
    xfs = _ensure_style(root, "cellXfs")
    if not list(xfs):
        ET.SubElement(xfs, f"{{{_MAIN}}}xf", {"numFmtId": "0", "fontId": "0", "fillId": "0", "borderId": "0", "xfId": "0"})
    for node in (fonts, fills, borders, xfs):
        node.set("count", str(len(list(node))))


def _ensure_style(root: ET.Element, tag: str) -> ET.Element:
    found = root.find(f"{{{_MAIN}}}{tag}")
    if found is not None:
        return found
    node = ET.Element(f"{{{_MAIN}}}{tag}")
    rank = _STYLE_ORDER.index(tag)
    for index, child in enumerate(list(root)):
        name = child.tag.rsplit("}", 1)[-1]
        if name in _STYLE_ORDER and _STYLE_ORDER.index(name) > rank:
            root.insert(index, node)
            return node
    root.append(node)
    return node


def _styles_bytes(root: ET.Element) -> bytes:
    ET.register_namespace("", _MAIN)
    return b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' + ET.tostring(root, encoding="utf-8")


def _style_index(root: ET.Element, base: str | None, spec: dict) -> str:
    fonts = root.find(f"{{{_MAIN}}}fonts")
    fills = root.find(f"{{{_MAIN}}}fills")
    xfs = root.find(f"{{{_MAIN}}}cellXfs")
    if fonts is None or fills is None or xfs is None:
        raise OfficeReviseError("表格样式表不完整")
    xf = _at(xfs, base)
    font_id = _font_id(fonts, _at(fonts, xf.get("fontId") if xf is not None else "0"), spec)
    fill_id = _fill_id(fills, xf.get("fillId") if xf is not None else "0", spec)
    border_id = xf.get("borderId") if xf is not None and xf.get("borderId") else "0"
    num_fmt = xf.get("numFmtId") if xf is not None and xf.get("numFmtId") else "0"
    align = _alignment(xf, spec)
    key = (font_id, fill_id, border_id, num_fmt, align)
    for index, item in enumerate(list(xfs)):
        if _xf_key(item) == key:
            return str(index)
    if len(list(xfs)) >= 128:
        raise OfficeReviseError("表格样式过多")
    created = ET.SubElement(xfs, f"{{{_MAIN}}}xf", {
        "numFmtId": num_fmt, "fontId": font_id, "fillId": fill_id, "borderId": border_id,
        "xfId": "0", "applyFont": "1", "applyFill": "1", "applyAlignment": "1",
    })
    horizontal, vertical, wrap = align
    if horizontal or vertical or wrap:
        node = ET.SubElement(created, f"{{{_MAIN}}}alignment")
        if horizontal:
            node.set("horizontal", horizontal)
        if vertical:
            node.set("vertical", vertical)
        if wrap:
            node.set("wrapText", "1")
    xfs.set("count", str(len(list(xfs))))
    return str(len(list(xfs)) - 1)


def _at(parent: ET.Element | None, index_text: str | None) -> ET.Element | None:
    if parent is None:
        return None
    children = list(parent)
    if not children:
        return None
    try:
        index = int(index_text or "0")
    except ValueError:
        index = 0
    if index < 0 or index >= len(children):
        return children[0]
    return children[index]


def _xf_key(item: ET.Element) -> tuple:
    node = item.find(f"{{{_MAIN}}}alignment")
    align = ("", "", "")
    if node is not None:
        align = (node.get("horizontal") or "", node.get("vertical") or "", "1" if node.get("wrapText") in {"1", "true"} else "")
    return (item.get("fontId") or "0", item.get("fillId") or "0", item.get("borderId") or "0", item.get("numFmtId") or "0", align)


def _alignment(xf: ET.Element | None, spec: dict) -> tuple[str, str, str]:
    node = xf.find(f"{{{_MAIN}}}alignment") if xf is not None else None
    horizontal = node.get("horizontal") if node is not None and node.get("horizontal") else ""
    vertical = node.get("vertical") if node is not None and node.get("vertical") else ""
    wrap = "1" if node is not None and node.get("wrapText") in {"1", "true"} else ""
    if "align" in spec:
        horizontal = spec["align"]
    if "valign" in spec:
        vertical = spec["valign"]
    if "wrap" in spec:
        wrap = "1" if spec["wrap"] else ""
    return (horizontal, vertical, wrap)


def _font_id(fonts: ET.Element, base: ET.Element | None, spec: dict) -> str:
    bold = _on(base, "b")
    italic = _on(base, "i")
    strike = _on(base, "strike")
    underline = _on(base, "u")
    size = _attr(base, "sz", "val") or "11"
    color = (_attr(base, "color", "rgb") or "").upper()
    name = _attr(base, "name", "val") or "Calibri"
    if "bold" in spec:
        bold = spec["bold"]
    if "italic" in spec:
        italic = spec["italic"]
    if "strike" in spec:
        strike = spec["strike"]
    if "underline" in spec:
        underline = spec["underline"]
    if "size" in spec:
        size = str(spec["size"])
    if "color" in spec:
        color = "FF" + spec["color"][1:]
    if "font" in spec:
        name = spec["font"]
    key = (bold, italic, strike, underline, size, color, name)
    for index, font in enumerate(list(fonts)):
        if _font_key(font) == key:
            return str(index)
    if len(list(fonts)) >= 64:
        raise OfficeReviseError("表格字体样式过多")
    font = ET.SubElement(fonts, f"{{{_MAIN}}}font")
    if bold:
        ET.SubElement(font, f"{{{_MAIN}}}b")
    if italic:
        ET.SubElement(font, f"{{{_MAIN}}}i")
    if strike:
        ET.SubElement(font, f"{{{_MAIN}}}strike")
    if underline:
        ET.SubElement(font, f"{{{_MAIN}}}u")
    ET.SubElement(font, f"{{{_MAIN}}}sz").set("val", size)
    if color:
        ET.SubElement(font, f"{{{_MAIN}}}color").set("rgb", color)
    ET.SubElement(font, f"{{{_MAIN}}}name").set("val", name)
    fonts.set("count", str(len(list(fonts))))
    return str(len(list(fonts)) - 1)


def _font_key(font: ET.Element) -> tuple:
    return (
        _on(font, "b"), _on(font, "i"), _on(font, "strike"), _on(font, "u"),
        _attr(font, "sz", "val") or "11", (_attr(font, "color", "rgb") or "").upper(), _attr(font, "name", "val") or "Calibri",
    )


def _on(node: ET.Element | None, tag: str) -> bool:
    if node is None:
        return False
    found = node.find(f"{{{_MAIN}}}{tag}")
    return found is not None and found.get("val") not in {"0", "false", "off"}


def _attr(node: ET.Element | None, tag: str, name: str) -> str:
    if node is None:
        return ""
    found = node.find(f"{{{_MAIN}}}{tag}")
    return found.get(name) or "" if found is not None else ""


def _fill_id(fills: ET.Element, base_id: str | None, spec: dict) -> str:
    if "fill" not in spec:
        return base_id or "0"
    rgb = "FF" + spec["fill"][1:]
    for index, fill in enumerate(list(fills)):
        pattern = fill.find(f"{{{_MAIN}}}patternFill")
        color = pattern.find(f"{{{_MAIN}}}fgColor") if pattern is not None else None
        if pattern is not None and pattern.get("patternType") == "solid" and color is not None and (color.get("rgb") or "").upper() == rgb:
            return str(index)
    if len(list(fills)) >= 64:
        raise OfficeReviseError("表格填充样式过多")
    pattern = ET.SubElement(ET.SubElement(fills, f"{{{_MAIN}}}fill"), f"{{{_MAIN}}}patternFill")
    pattern.set("patternType", "solid")
    ET.SubElement(pattern, f"{{{_MAIN}}}fgColor").set("rgb", rgb)
    ET.SubElement(pattern, f"{{{_MAIN}}}bgColor").set("indexed", "64")
    fills.set("count", str(len(list(fills))))
    return str(len(list(fills)) - 1)


def view_docx(payload: dict) -> dict:
    """Return the paragraphs and tables a person can edit on the document page."""

    purpose = office_purpose.take(payload)
    _target, data = _open_office(payload.get("path"), ".docx")
    if not data.startswith(b"PK"):
        if b"Esafenet" in data[:512]:
            raise OfficeReviseError("这份文件被亿赛通加密了，窗口只能编辑未加密的 docx。")
        raise OfficeReviseError("这个文件不是标准 docx，窗口只能编辑 docx 页面。")
    root = _edit._parse_document(data)
    body = root.find(f"{_edit._W}body")
    if body is None:
        raise OfficeReviseError("文档没有正文")
    blocks, total = _docx_blocks(body)
    office_purpose.audit("office_view_docx", purpose, {"path": _relative(payload), "blocks": len(blocks)})
    return {"kind": "docx", "blocks": blocks, "paragraphs": total}


def write_docx_blocks(payload: dict) -> dict:
    """Write edited paragraph text and basic formatting back into the .docx."""

    purpose = office_purpose.take(payload)
    target, data = _open_office(payload.get("path"), ".docx")
    incoming = _docx_edits(payload.get("blocks"))
    root = _edit._parse_document(data)
    body = root.find(f"{_edit._W}body")
    paragraphs = list(body.iter(f"{_edit._W}p")) if body is not None else []
    applied: list[tuple[int, dict, dict]] = []
    unchanged = 0
    for index, change in incoming:
        if index >= len(paragraphs):
            raise OfficeReviseError("段落不存在")
        full = _edit._paragraph_text(paragraphs[index])
        if len(full) > _MAX_BLOCK_CHARS:
            raise OfficeReviseError("这段超过 1500 字，窗口不写回。")
        current = _paragraph_block(paragraphs[index], index)
        if _same_paragraph(change, full, current):
            unchanged += 1
            continue
        applied.append((index, change, current))
    if not applied:
        raise OfficeReviseError("没有需要保存的修改" if unchanged else "没有可写回的正文")
    try:
        document = _edit.document_xml_bytes(data).decode("utf-8")
    except UnicodeError as exc:
        raise OfficeReviseError("文档正文无法解析") from exc
    if len(_word_paragraph_spans(document)) != len(paragraphs):
        raise OfficeReviseError("文档正文无法解析")
    for index, change, current in sorted(applied, key=lambda item: item[0], reverse=True):
        document = _splice_paragraph(document, index, change, current)
    revised = _edit._repackage(data, document.encode("utf-8"))
    if len(revised) > _edit.MAX_FILE_BYTES:
        raise OfficeReviseError("修订后的文件超过 20MB 上限")
    _oc._write_atomic(target, revised, True)
    _oc._verify_written(target, revised)
    saved_root = _edit._parse_document(target.read_bytes())
    saved_body = saved_root.find(f"{_edit._W}body")
    saved = list(saved_body.iter(f"{_edit._W}p")) if saved_body is not None else []
    for index, change, _current in applied:
        if _edit._paragraph_text(saved[index]) != change["text"]:
            _restore(target, data)
            raise OfficeReviseError("写回后的正文与页面不一致,已恢复原文件")
    office_purpose.audit("office_write_docx", purpose, {"path": _relative(payload), "edited": len(applied)})
    return {"saved": True, "kind": "docx", "edited": len(applied), "skipped": 0, "bytes": len(revised), "sha256": hashlib.sha256(revised).hexdigest()}


def _docx_blocks(body: ET.Element) -> tuple[list, int]:
    paragraphs = list(body.iter(f"{_edit._W}p"))
    index_of = {id(paragraph): index for index, paragraph in enumerate(paragraphs)}
    blocks: list = []

    def take(paragraph: ET.Element) -> dict:
        return _paragraph_block(paragraph, index_of[id(paragraph)])

    for child in list(body):
        if len(blocks) >= _MAX_BLOCKS:
            break
        if child.tag == f"{_edit._W}p":
            blocks.append({"kind": "paragraph", **take(child)})
        elif child.tag == f"{_edit._W}tbl":
            rows = []
            for row in child.findall(f"{_edit._W}tr"):
                cells = []
                for cell in row.findall(f"{_edit._W}tc"):
                    direct = [node for node in list(cell) if node.tag == f"{_edit._W}p"]
                    if not direct:
                        continue
                    cells.append({"paragraphs": [take(paragraph) for paragraph in direct]})
                if cells:
                    rows.append(cells)
            if rows:
                blocks.append({"kind": "table", "rows": rows})
    return blocks, len(paragraphs)


def _paragraph_block(paragraph: ET.Element, index: int) -> dict:
    full = _edit._paragraph_text(paragraph)
    return {
        "id": f"p{index}",
        "text": full[:_MAX_BLOCK_CHARS],
        "bold": _doc_flag(paragraph, "b"),
        "italic": _doc_flag(paragraph, "i"),
        "size": _doc_size(paragraph),
        "align": _doc_align(paragraph),
        "mixed": _mixed_runs(paragraph),
        "truncated": len(full) > _MAX_BLOCK_CHARS,
    }


def _same_paragraph(change: dict, full: str, current: dict) -> bool:
    return (
        change["text"] == full
        and change["bold"] == current["bold"]
        and change["italic"] == current["italic"]
        and change["size"] == current["size"]
        and change["align"] == current["align"]
    )


def _mixed_runs(paragraph: ET.Element) -> bool:
    signatures = []
    for run in paragraph.iter(f"{_edit._W}r"):
        if "".join(node.text or "" for node in run.iter(f"{_edit._W}t")) == "":
            continue
        props = run.find(f"{_edit._W}rPr")
        signatures.append((
            _run_mark(props, "b"),
            _run_mark(props, "i"),
            _run_value(props, "sz"),
            _run_value(props, "color").upper(),
        ))
    return len(signatures) > 1 and len(set(signatures)) > 1


def _run_mark(props: ET.Element | None, tag: str) -> bool:
    if props is None:
        return False
    node = props.find(f"{_edit._W}{tag}")
    return node is not None and node.get(f"{_edit._W}val") not in {"0", "false", "off"}


def _run_value(props: ET.Element | None, tag: str) -> str:
    if props is None:
        return ""
    node = props.find(f"{_edit._W}{tag}")
    return node.get(f"{_edit._W}val") or "" if node is not None else ""


def _doc_flag(paragraph: ET.Element, tag: str) -> bool:
    props = _first_props(paragraph)
    if props is None:
        return False
    node = props.find(f"{_edit._W}{tag}")
    return node is not None and node.get(f"{_edit._W}val") not in {"0", "false", "off"}


def _doc_size(paragraph: ET.Element) -> int:
    props = _first_props(paragraph)
    node = props.find(f"{_edit._W}sz") if props is not None else None
    raw = node.get(f"{_edit._W}val") if node is not None else None
    try:
        size = int(raw or "24")
    except ValueError:
        size = 24
    return min(144, max(16, size))


def _doc_align(paragraph: ET.Element) -> str:
    props = paragraph.find(f"{_edit._W}pPr")
    node = props.find(f"{_edit._W}jc") if props is not None else None
    value = node.get(f"{_edit._W}val") if node is not None else "left"
    if value == "start":
        return "left"
    if value == "end":
        return "right"
    return value if value in _DOC_ALIGN else "left"


def _first_props(paragraph: ET.Element) -> ET.Element | None:
    for run in paragraph.findall(f"{_edit._W}r"):
        props = run.find(f"{_edit._W}rPr")
        if props is not None:
            return props
    return None


def _docx_edits(blocks: object) -> list[tuple[int, dict]]:
    if not isinstance(blocks, list):
        raise OfficeReviseError("正文段落无效")
    if not blocks:
        raise OfficeReviseError("没有需要保存的修改")
    if len(blocks) > _MAX_BLOCKS:
        raise OfficeReviseError(f"这篇文档超过 {_MAX_BLOCKS} 段，窗口一次保存不下。")
    edits = []
    seen = set()
    for block in blocks:
        if not isinstance(block, dict) or set(block) - {"id", "text", "bold", "italic", "size", "align"}:
            raise OfficeReviseError("正文段落无效")
        identity = block.get("id")
        if not isinstance(identity, str) or _BLOCK_ID.fullmatch(identity) is None:
            raise OfficeReviseError("段落编号无效")
        index = int(identity[1:])
        if index in seen:
            raise OfficeReviseError("段落编号重复")
        seen.add(index)
        text = block.get("text")
        if not isinstance(text, str) or len(text) > _MAX_BLOCK_CHARS or "\x00" in text:
            raise OfficeReviseError("段落文本无效")
        if not isinstance(block.get("bold"), bool) or not isinstance(block.get("italic"), bool):
            raise OfficeReviseError("段落格式无效")
        size = block.get("size")
        if isinstance(size, bool) or not isinstance(size, int) or not 16 <= size <= 144:
            raise OfficeReviseError("字号无效")
        align = block.get("align")
        if align not in _DOC_ALIGN:
            raise OfficeReviseError("段落对齐无效")
        edits.append((index, {"text": text, "bold": block["bold"], "italic": block["italic"], "size": size, "align": align}))
    return edits


_WORD_TAG = re.compile(
    r"<(?P<close>/)?(?P<qname>(?P<prefix>[A-Za-z_][\w.-]*:)?(?P<local>[A-Za-z_][\w.-]*))(?P<attrs>[^>]*?)(?P<self>/)?>"
)


def _splice_paragraph(text: str, index: int, change: dict, current: dict) -> str:
    spans = _word_paragraph_spans(text)
    if index >= len(spans):
        raise OfficeReviseError("段落不存在")
    start, end, prefix = spans[index]
    nested = [(left - start, right - start) for left, right, _prefix in spans if start < left and right <= end]
    updated = _edit_paragraph(text[start:end], prefix, change, current, nested)
    return text[:start] + updated + text[end:]


def _word_paragraph_spans(text: str) -> list[tuple[int, int, str]]:
    """Return each word paragraph in the same order ElementTree walks them."""

    stack: list[tuple[str, dict[str, str], int | None]] = []
    spans: list[dict[str, int | str | None]] = []
    for match in _word_tags(text):
        qname = match.group("qname")
        if match.group("close"):
            while stack:
                item = stack.pop()
                if item[0] == qname:
                    if item[2] is not None:
                        spans[item[2]]["end"] = match.end()
                    break
            continue
        parent = stack[-1][1] if stack else {"": ""}
        current = dict(parent)
        for key, uri in re.findall(r'\sxmlns(?::([A-Za-z_][\w.-]*))?="([^"]*)"', match.group("attrs") or ""):
            current[key or ""] = uri
        prefix = match.group("prefix") or ""
        is_paragraph = match.group("local") == "p" and current.get(prefix[:-1], "") == _edit._W_NS
        if match.group("self"):
            if is_paragraph:
                spans.append({"start": match.start(), "end": match.end(), "prefix": prefix})
            continue
        slot = None
        if is_paragraph:
            slot = len(spans)
            spans.append({"start": match.start(), "end": None, "prefix": prefix})
        stack.append((qname, current, slot))
    if any(item["end"] is None for item in spans):
        raise OfficeReviseError("文档正文无法解析")
    return [(int(item["start"]), int(item["end"]), str(item["prefix"])) for item in spans]


def _word_tags(text: str):
    index = 0
    while index < len(text):
        if text.startswith("<!--", index):
            finish = text.find("-->", index + 4)
            index = len(text) if finish < 0 else finish + 3
            continue
        if text.startswith("<![CDATA[", index):
            finish = text.find("]]>", index + 9)
            index = len(text) if finish < 0 else finish + 3
            continue
        if text.startswith("<?", index):
            finish = text.find("?>", index + 2)
            index = len(text) if finish < 0 else finish + 2
            continue
        if text[index] != "<":
            index += 1
            continue
        match = _WORD_TAG.match(text, index)
        if match is None or match.end() <= index:
            index += 1
            continue
        yield match
        index = match.end()


def _edit_paragraph(paragraph: str, prefix: str, change: dict, current: dict, nested: list[tuple[int, int]]) -> str:
    if not paragraph.endswith(f"</{prefix}p>"):
        if not paragraph.rstrip().endswith("/>"):
            raise OfficeReviseError("文档正文无法解析")
        paragraph = paragraph.rstrip()[:-2].rstrip() + f"></{prefix}p>"
    texts = _direct_spans(paragraph, f"{prefix}t", nested)
    runs = _direct_spans(paragraph, f"{prefix}r", nested)
    props = _direct_spans(paragraph, f"{prefix}pPr", nested)
    ops: list[tuple[int, int, str]] = []
    if texts:
        for slot, span in enumerate(texts):
            ops.append((span[0], span[1], _render_text(paragraph[span[0]:span[1]], prefix, change["text"] if slot == 0 else "")))
        run_span = next((span for span in runs if span[0] <= texts[0][0] and texts[0][1] <= span[1]), None)
        if run_span is not None:
            ops.extend(_mark_ops(paragraph, prefix, change, current, run_span))
    elif change["text"]:
        close = len(paragraph) - len(f"</{prefix}p>")
        ops.append((close, close, _new_run(prefix, change, current)))
    elif runs:
        ops.extend(_mark_ops(paragraph, prefix, change, current, runs[0]))
    if change["align"] != current["align"]:
        ops.append(_align_op(paragraph, prefix, change["align"], props[0] if props else None))
    return _apply_spans(paragraph, ops)


def _mark_ops(paragraph: str, prefix: str, change: dict, current: dict, run_span: tuple[int, int]) -> list[tuple[int, int, str]]:
    if change["bold"] == current["bold"] and change["italic"] == current["italic"] and change["size"] == current["size"]:
        return []
    marks = _direct_spans(paragraph[run_span[0]:run_span[1]], f"{prefix}rPr", [])
    if marks:
        start = run_span[0] + marks[0][0]
        end = run_span[0] + marks[0][1]
        return [(start, end, _adjust_mark(paragraph[start:end], prefix, change, current))]
    fresh = _fresh_mark(prefix, change, current)
    if not fresh:
        return []
    opened = paragraph.find(">", run_span[0], run_span[1]) + 1
    return [(opened, opened, fresh)]


def _align_op(paragraph: str, prefix: str, align: str, prop: tuple[int, int] | None) -> tuple[int, int, str]:
    alignment = f'<{prefix}jc {prefix}val="{align}"/>'
    if prop is None:
        return paragraph.find(">") + 1, paragraph.find(">") + 1, f"<{prefix}pPr>{alignment}</{prefix}pPr>"
    existing = _direct_spans(paragraph[prop[0]:prop[1]], f"{prefix}jc", [])
    if existing:
        return prop[0] + existing[0][0], prop[0] + existing[0][1], alignment
    close = paragraph.rfind(f"</{prefix}pPr>", prop[0], prop[1])
    return close, close, alignment


def _direct_spans(text: str, qname: str, blocked: list[tuple[int, int]]) -> list[tuple[int, int]]:
    found = []
    for match in _word_tags(text):
        if match.start() >= len(text):
            break
        if match.group("qname") != qname or match.group("close") or _covered(match.start(), blocked):
            continue
        if match.group("self"):
            found.append((match.start(), match.end()))
            continue
        close = text.find(f"</{qname}>", match.end())
        if close < 0:
            raise OfficeReviseError("文档正文无法解析")
        found.append((match.start(), close + len(f"</{qname}>")))
    return found


def _covered(position: int, blocked: list[tuple[int, int]]) -> bool:
    return any(start <= position < end for start, end in blocked)


def _render_text(existing: str, prefix: str, value: str) -> str:
    close = f"</{prefix}t>"
    if existing.endswith("/>"):
        opening = existing[:-2].rstrip() + ">"
    else:
        opening = existing[:existing.find(">") + 1]
    if value[:1].isspace() or value[-1:].isspace() or "\n" in value:
        if "xml:space" not in opening:
            opening = opening[:-1] + ' xml:space="preserve">'
    escaped = value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return opening + escaped + close


def _adjust_mark(mark: str, prefix: str, change: dict, current: dict) -> str:
    if change["bold"] != current["bold"]:
        mark = _set_flag(mark, prefix, "b", change["bold"])
    if change["italic"] != current["italic"]:
        mark = _set_flag(mark, prefix, "i", change["italic"])
    if change["size"] != current["size"]:
        mark = _set_size(mark, prefix, "sz", change["size"])
        mark = _set_size(mark, prefix, "szCs", change["size"])
    return mark


def _fresh_mark(prefix: str, change: dict, current: dict) -> str:
    body = ""
    if change["bold"] != current["bold"] and change["bold"]:
        body += f"<{prefix}b/>"
    if change["italic"] != current["italic"] and change["italic"]:
        body += f"<{prefix}i/>"
    if change["size"] != current["size"]:
        body += f'<{prefix}sz {prefix}val="{change["size"]}"/>'
        body += f'<{prefix}szCs {prefix}val="{change["size"]}"/>'
    return f"<{prefix}rPr>{body}</{prefix}rPr>" if body else ""


def _new_run(prefix: str, change: dict, current: dict) -> str:
    return f"<{prefix}r>{_fresh_mark(prefix, change, current)}{_render_text(f'<{prefix}t/>', prefix, change['text'])}</{prefix}r>"


def _set_flag(mark: str, prefix: str, tag: str, enabled: bool) -> str:
    pattern = re.compile(
        rf"<{re.escape(prefix)}{tag}(?=[\s/>])[^>]*/>|<{re.escape(prefix)}{tag}(?=[\s/>])[^>]*>.*?</{re.escape(prefix)}{tag}>",
        re.DOTALL,
    )
    mark = pattern.sub("", mark)
    if not enabled:
        return mark
    point = mark.find(">") + 1
    return mark[:point] + f"<{prefix}{tag}/>" + mark[point:]


def _set_size(mark: str, prefix: str, tag: str, size: int) -> str:
    pattern = re.compile(
        rf"<{re.escape(prefix)}{tag}(?=[\s/>])[^>]*/>|<{re.escape(prefix)}{tag}(?=[\s/>])[^>]*>.*?</{re.escape(prefix)}{tag}>",
        re.DOTALL,
    )
    replacement = f'<{prefix}{tag} {prefix}val="{size}"/>'
    if pattern.search(mark):
        return pattern.sub(replacement, mark, count=1)
    point = mark.find(">") + 1
    return mark[:point] + replacement + mark[point:]


def _apply_spans(text: str, ops: list[tuple[int, int, str]]) -> str:
    for start, end, value in sorted(ops, key=lambda item: (item[0], item[1]), reverse=True):
        text = text[:start] + value + text[end:]
    return text
