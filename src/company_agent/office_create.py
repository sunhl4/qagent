"""Bounded, honest office artifact creation for the WPS-suite porting (P2).

Contract: ``company_office_create`` (``company.office/2.0``, ``office.create``).
It complements the P1 read-only ingestion (``office_ingest``) with explicit
generation the agent can hand to WPS / Word / Excel / mind-map tools later:

- exactly one file is written inside the mounted workspace, addressed with the
  same ``project`` + ``path`` rail as ingestion; the P0 fences and the P0
  lexical fence are reused verbatim;
- every byte is produced by the standard library: .docx (WordprocessingML,
  opens in WPS/Word), .xlsx (SpreadsheetML), .xmind (XMind 8 ``content.xml``
  package that WPS 思维导图 and XMind open) and .mm (FreeMind XML);
  .txt/.md stay plain UTF-8 text;
- structure overshoot is refused, never silently truncated: block / sheet /
  row / node caps name the boundary like every other refusal here;
- an existing file is never overwritten without an explicit ``overwrite``
  argument; the write is a same-directory temp file replaced atomically and
  re-verified by re-read so the returned sha256 matches the bytes on disk;
- no OCR, no conversion, no template execution and no external calls.
"""
from __future__ import annotations

import errno
import hashlib
import io
import math
import os
import re
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Any

from company_agent import workspace_files

MAX_FILE_BYTES = 20_000_000
MAX_BLOCKS = 2_000
MAX_SHEETS = 32
MAX_ROWS_PER_SHEET = 5_000
MAX_COLS = 64
MAX_NODES = 512
MAX_DEPTH = 10
MAX_ITEM_TEXT_CHARS = 10_000
MAX_TEXT_CHARS = 200_000
MAX_CELL_TEXT_CHARS = 1_000
MAX_TITLE_CHARS = 200
MAX_SHEET_NAME_CHARS = 31

_PROJECT_RE = re.compile(r"^[A-Za-z0-9_](?:[A-Za-z0-9_.-]*[A-Za-z0-9_-])?$")
_KIND_BY_SUFFIX = {
    ".docx": "docx",
    ".xlsx": "xlsx",
    ".xmind": "xmind",
    ".mm": "mindmap",
    ".txt": "text",
    ".md": "text",
}

_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
_M_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_XMIND_NS = "urn:xmind:xmap:xmlns:content:2.0"
_XMIND_MANIFEST_NS = "urn:xmind:xmap:xmlns:manifest:1.0"


class OfficeCreateError(ValueError):
    """Refusal that names the boundary hit without echoing paths outside the root."""


_DOC_STYLES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    f'<w:styles xmlns:w="{_W_NS}">'
    "<w:docDefaults><w:rPrDefault><w:rPr>"
    '<w:sz w:val="21"/><w:szCs w:val="21"/></w:rPr></w:rPrDefault></w:docDefaults>'
    '<w:style w:type="paragraph" w:styleId="Normal"><w:name w:val="Normal"/></w:style>'
    '<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/>'
    '<w:basedOn w:val="Normal"/><w:qFormat/><w:pPr><w:outlineLvl w:val="0"/></w:pPr>'
    '<w:rPr><w:b/><w:sz w:val="36"/></w:rPr></w:style>'
    '<w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/>'
    '<w:basedOn w:val="Normal"/><w:qFormat/><w:pPr><w:outlineLvl w:val="1"/></w:pPr>'
    '<w:rPr><w:b/><w:sz w:val="30"/></w:rPr></w:style>'
    '<w:style w:type="paragraph" w:styleId="Heading3"><w:name w:val="heading 3"/>'
    '<w:basedOn w:val="Normal"/><w:qFormat/><w:pPr><w:outlineLvl w:val="2"/></w:pPr>'
    '<w:rPr><w:b/><w:sz w:val="26"/></w:rPr></w:style>'
    "</w:styles>"
)
_DOC_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    f'<Relationships xmlns="{_REL_NS}">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument'
    '/2006/relationships/styles" Target="styles.xml"/></Relationships>'
)


def create(args: dict) -> dict:
    """Contract entry point: bounded single-file artifact creation."""

    root = workspace_files.root()
    compound = _compound(args)
    # The P0 lexical fence stays the single source of truth; reuse it.
    workspace_files._lexical(compound)
    kind = _kind_of(compound)
    data = _render(kind, _content(args))
    if len(data) > MAX_FILE_BYTES:
        raise OfficeCreateError("生成的文件超过 20MB 上限:请拆分内容后重试")
    existed, target = _resolve_target(root, compound, _overwrite(args))
    _write_atomic(target, data, existed)
    _verify_written(target, data)
    return {
        "created": True,
        "kind": kind,
        "path": compound,
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "overwrote": existed,
    }


def _compound(args: dict) -> str:
    project = args.get("project")
    path = args.get("path")
    if not isinstance(project, str) or not _PROJECT_RE.fullmatch(project):
        raise OfficeCreateError("project 名称不符合合同模式")
    if not isinstance(path, str) or not path.strip() or path.strip() != path:
        raise OfficeCreateError("workspace 路径无效")
    compound = f"{project}/{path}"
    if len(compound.encode("utf-8")) > workspace_files.MAX_PATH_BYTES:
        raise OfficeCreateError("workspace 路径超过长度上限")
    return compound


def _kind_of(compound: str) -> str:
    suffix = Path(compound).suffix.casefold()
    kind = _KIND_BY_SUFFIX.get(suffix)
    if kind is None:
        raise OfficeCreateError(
            f"{suffix or '(无后缀)'} 不支持的生成类型;支持 .docx .xlsx .xmind .mm .txt .md"
        )
    return kind


def _content(args: dict) -> dict:
    content = args.get("content")
    if not isinstance(content, dict):
        raise OfficeCreateError("content 必须是对象")
    return content


def _overwrite(args: dict) -> bool:
    raw = args.get("overwrite")
    if raw is None:
        return False
    if not isinstance(raw, bool):
        raise OfficeCreateError("overwrite 必须是布尔值")
    return raw


def _check_text(text: Any, label: str, limit: int) -> str:
    if not isinstance(text, str):
        raise OfficeCreateError(f"{label} 必须是字符串")
    if any(ord(ch) < 32 and ch not in "\t\n" for ch in text):
        raise OfficeCreateError(f"{label} 含控制字符,拒绝")
    if len(text) > limit:
        raise OfficeCreateError(f"{label} 长度 {len(text)} 超过上限 {limit},拒绝")
    return text


def _esc(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _resolve_target(root: Path, compound: str, overwrite: bool) -> tuple[bool, Path]:
    project, _, relative = compound.partition("/")
    project_path = root / project
    if project_path.is_symlink():
        raise OfficeCreateError("项目路径指向链接,拒绝")
    if not project_path.is_dir():
        project_path.mkdir(parents=True, exist_ok=True)
    project_dir = project_path.resolve(strict=True)
    if not (project_dir.is_relative_to(root) and project_dir != root):
        raise OfficeCreateError("项目路径逃逸 workspace 根,拒绝")
    candidate = project_dir / Path(*relative.split("/"))
    if candidate.is_dir():
        raise OfficeCreateError("目标路径是目录,拒绝")
    existed = candidate.exists() or candidate.is_symlink()
    if existed and not overwrite:
        raise OfficeCreateError("目标文件已存在;如需覆盖请显式设置 overwrite=true")
    name = Path(relative).name
    parent = candidate.parent
    parent.mkdir(parents=True, exist_ok=True)
    parent_resolved = parent.resolve(strict=True)
    if not parent_resolved.is_relative_to(project_dir):
        raise OfficeCreateError("文件路径逃逸项目目录,拒绝")
    return existed, parent_resolved / name


def _write_atomic(target: Path, data: bytes, existed: bool) -> None:
    fd, stamp = tempfile.mkstemp(dir=target.parent, prefix=".office-", suffix=".part")
    try:
        with os.fdopen(fd, "wb", closefd=True) as stream:
            stream.write(data)
        try:
            os.replace(stamp, target)
        except OSError as exc:
            # Windows filter/file driver shells refuse rename/replace with
            # ERROR_NOT_SAME_DEVICE (mapped to errno.EXDEV) even inside one
            # directory; fall back to a same-name write copy and rely on the
            # re-read verification below for the honesty guarantee.
            if exc.errno != errno.EXDEV:
                raise
            if existed and target.is_symlink():
                raise OfficeCreateError("目标路径是链接,拒绝覆盖") from exc
            flags = os.O_WRONLY | os.O_CREAT | getattr(os, "O_BINARY", 0)
            if existed:
                flags |= os.O_TRUNC
            else:
                flags |= os.O_EXCL
            handle = os.open(target, flags)
            try:
                os.write(handle, data)
            finally:
                os.close(handle)
    finally:
        Path(stamp).unlink(missing_ok=True)


def _verify_written(target: Path, data: bytes) -> None:
    with open(target, "rb") as stream:
        if stream.read() != data:
            raise OfficeCreateError("写回校验失败:磁盘字节与生成字节不一致")


def _render(kind: str, content: dict) -> bytes:
    builder = {
        "docx": _docx_package,
        "xlsx": _xlsx_package,
        "xmind": _xmind_package,
        "mindmap": _mm_package,
        "text": _text_package,
    }[kind]
    return builder(content)


def _docx_package(content: dict) -> bytes:
    blocks = content.get("blocks")
    if not isinstance(blocks, list):
        raise OfficeCreateError("docx content 需要 blocks 数组")
    if len(blocks) > MAX_BLOCKS:
        raise OfficeCreateError(f"block 数 {len(blocks)} 超过上限 {MAX_BLOCKS},拒绝")
    body = []
    for block in blocks:
        if not isinstance(block, dict):
            raise OfficeCreateError("每个 block 必须是对象")
        block_kind = block.get("kind")
        text = _check_text(block.get("text"), "block.text", MAX_ITEM_TEXT_CHARS)
        if block_kind == "heading":
            level = block.get("level", 1)
            if not isinstance(level, int) or not 1 <= level <= 6:
                raise OfficeCreateError("heading.level 必须是 1..6")
            if not text:
                raise OfficeCreateError("heading.text 不能为空")
            body.append(
                f'<w:p><w:pPr><w:pStyle w:val="Heading{level}"/></w:pPr>'
                f"<w:r><w:t>{_esc(text)}</w:t></w:r></w:p>"
            )
        elif block_kind == "paragraph":
            if not text:
                body.append("<w:p/>")
                continue
            runs = []
            for position, line in enumerate(text.split("\n")):
                if position == 0:
                    runs.append(f"<w:r><w:t>{_esc(line)}</w:t></w:r>")
                else:
                    runs.append(f"<w:r><w:br/><w:t>{_esc(line)}</w:t></w:r>")
            body.append(f"<w:p>{''.join(runs)}</w:p>")
        else:
            raise OfficeCreateError("block.kind 只支持 heading / paragraph")
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:document xmlns:w="{_W_NS}"><w:body>{"".join(body)}</w:body></w:document>'
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<Types xmlns="{_CT_NS}">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats'
        '-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" ContentType="application/vnd'
        '.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        '<Override PartName="/word/styles.xml" ContentType="application/vnd'
        '.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
        "</Types>"
    )
    root_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<Relationships xmlns="{_REL_NS}">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org'
        '/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
        "</Relationships>"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as package:
        package.writestr("[Content_Types].xml", content_types)
        package.writestr("_rels/.rels", root_rels)
        package.writestr("word/document.xml", document)
        package.writestr("word/styles.xml", _DOC_STYLES)
        package.writestr("word/_rels/document.xml.rels", _DOC_RELS)
    return buffer.getvalue()


def _col_ref(index: int) -> str:
    letters = ""
    while index:
        index, rest = divmod(index - 1, 26)
        letters = chr(65 + rest) + letters
    return letters


def _xlsx_package(content: dict) -> bytes:
    sheets = content.get("sheets")
    if not isinstance(sheets, list) or not sheets:
        raise OfficeCreateError("xlsx content 需要 sheets 数组")
    if len(sheets) > MAX_SHEETS:
        raise OfficeCreateError(f"sheet 数 {len(sheets)} 超过上限 {MAX_SHEETS},拒绝")
    seen: set[str] = set()
    declared: list[str] = []
    sheet_xmls: list[str] = []
    for index, sheet in enumerate(sheets, 1):
        if not isinstance(sheet, dict):
            raise OfficeCreateError("每个 sheet 必须是对象")
        name = _check_text(sheet.get("name"), "sheet.name", MAX_SHEET_NAME_CHARS)
        if not name or any(ch in name for ch in "[]:*?/\\"):
            raise OfficeCreateError(f"sheet 名 {name!r} 无效")
        if name in seen:
            raise OfficeCreateError(f"sheet 名 {name!r} 重复,拒绝")
        seen.add(name)
        rows = sheet.get("rows")
        if not isinstance(rows, list):
            raise OfficeCreateError("sheet.rows 必须是数组")
        if len(rows) > MAX_ROWS_PER_SHEET:
            raise OfficeCreateError(f"sheet {name!r} 行数超过上限 {MAX_ROWS_PER_SHEET},拒绝")
        declared.append(
            f'<m:sheet name="{_esc(name)}" sheetId="{index}" r:id="rId{index}"/>'
        )
        sheet_xmls.append(f"xl/worksheets/sheet{index}.xml")
    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<m:workbook xmlns:m="{_M_NS}" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'<m:sheets>{"".join(declared)}</m:sheets></m:workbook>'
    )
    workbook_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<Relationships xmlns="{_REL_NS}">'
        + "".join(
            f'<Relationship Id="rId{index}" Type="http://schemas.openxmlformats.org'
            f'/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{index}.xml"/>'
            for index in range(1, len(sheets) + 1)
        )
        + "</Relationships>"
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<Types xmlns="{_CT_NS}">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats'
        '-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats'
        '-officedocument.spreadsheetml.sheet.main+xml"/>'
        + "".join(
            f'<Override PartName="/{element}" ContentType="application/vnd.openxmlformats'
            '-officedocument.spreadsheetml.worksheet+xml"/>'
            for element in sheet_xmls
        )
        + "</Types>"
    )
    root_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<Relationships xmlns="{_REL_NS}">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org'
        '/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        "</Relationships>"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as package:
        package.writestr("[Content_Types].xml", content_types)
        package.writestr("_rels/.rels", root_rels)
        package.writestr("xl/workbook.xml", workbook)
        package.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        for index, sheet in enumerate(sheets, 1):
            package.writestr(f"xl/worksheets/sheet{index}.xml", _sheet_xml(sheet))
    return buffer.getvalue()


def _sheet_xml(sheet: dict) -> str:
    rows = sheet["rows"]
    row_parts = []
    for row_index, row in enumerate(rows, 1):
        if row is None:
            row = []
        if not isinstance(row, list):
            raise OfficeCreateError("每一行必须是数组")
        if len(row) > MAX_COLS:
            raise OfficeCreateError(f"第 {row_index} 行列数超过上限 {MAX_COLS},拒绝")
        cells = []
        for col_index, cell in enumerate(row, 1):
            ref = f"{_col_ref(col_index)}{row_index}"
            if cell is None or (isinstance(cell, str) and not cell):
                continue
            if isinstance(cell, bool):
                rendered = "TRUE" if cell else "FALSE"
                cells.append(
                    f'<m:c r="{ref}" t="inlineStr"><m:is><m:t>{rendered}</m:t></m:is></m:c>'
                )
            elif isinstance(cell, int):
                cells.append(f'<m:c r="{ref}"><m:v>{cell}</m:v></m:c>')
            elif isinstance(cell, float):
                if not math.isfinite(cell):
                    raise OfficeCreateError("浮点单元格必须是有限数,拒绝")
                cells.append(f'<m:c r="{ref}"><m:v>{cell!r}</m:v></m:c>')
            elif isinstance(cell, str):
                text = _check_text(cell, "单元格文本", MAX_CELL_TEXT_CHARS)
                preserve = ' xml:space="preserve"' if "\n" in text else ""
                cells.append(
                    f'<m:c r="{ref}" t="inlineStr"><m:is><m:t{preserve}>{_esc(text)}</m:t></m:is></m:c>'
                )
            else:
                raise OfficeCreateError("单元格只支持 字符串/数字/布尔/None")
        if cells:
            row_parts.append(f'<m:row r="{row_index}">{"".join(cells)}</m:row>')
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<m:worksheet xmlns:m="{_M_NS}">'
        f"<m:sheetData>{''.join(row_parts)}</m:sheetData></m:worksheet>"
    )


def _mind_tree(content: dict) -> dict:
    """Validate and clamp a mind-map tree; returns the flat-checked structure."""

    root = content.get("root")
    if not isinstance(root, dict):
        raise OfficeCreateError("思维导图 content 需要 root 对象")
    state = {"nodes": 0}

    def build(node: dict, depth: int) -> dict:
        if not isinstance(node, dict):
            raise OfficeCreateError("思维导图节点必须是对象")
        state["nodes"] += 1
        if state["nodes"] > MAX_NODES:
            raise OfficeCreateError(f"节点数超过上限 {MAX_NODES},拒绝")
        if depth > MAX_DEPTH:
            raise OfficeCreateError(f"树深度超过上限 {MAX_DEPTH},拒绝")
        title = _check_text(node.get("title"), "node.title", MAX_TITLE_CHARS)
        if not title:
            raise OfficeCreateError("node.title 不能为空")
        children = node.get("children", [])
        if not isinstance(children, list):
            raise OfficeCreateError("node.children 必须是数组")
        return {"title": title, "children": [build(child, depth + 1) for child in children]}

    return build(root, 1)


def _xmind_package(content: dict) -> bytes:
    tree = _mind_tree(content)
    ET.register_namespace("", _XMIND_NS)

    def emit_into(bucket: ET.Element, node: dict) -> None:
        item = ET.SubElement(bucket, f"{{{_XMIND_NS}}}topic")
        title = ET.SubElement(item, f"{{{_XMIND_NS}}}title")
        title.text = node["title"]
        if node["children"]:
            wrapped = ET.SubElement(item, f"{{{_XMIND_NS}}}children")
            children_bucket = ET.SubElement(
                wrapped, f"{{{_XMIND_NS}}}topics", {"type": "attached"}
            )
            for child in node["children"]:
                emit_into(children_bucket, child)

    root_element = ET.Element(f"{{{_XMIND_NS}}}xmap-content", {"version": "2.0"})
    sheet_element = ET.SubElement(root_element, f"{{{_XMIND_NS}}}sheet")
    emit_into(sheet_element, tree)
    body = (
        '<?xml version="1.0" encoding="UTF-8" standalone="no"?>\n'
        + ET.tostring(root_element, encoding="unicode")
    )
    manifest = (
        '<?xml version="1.0" encoding="UTF-8" standalone="no"?>'
        f'<manifest xmlns="{_XMIND_MANIFEST_NS}">'
        '<file-entry full-path="content.xml" media-type="text/xml"/>'
        "</manifest>"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as package:
        package.writestr("content.xml", body)
        package.writestr("META-INF/manifest.xml", manifest)
    return buffer.getvalue()


def _mm_package(content: dict) -> bytes:
    tree = _mind_tree(content)
    root_element = ET.Element("map", {"version": "1.0.1"})

    def emit_into(parent: ET.Element, node: dict) -> None:
        item = ET.SubElement(parent, "node", {"TEXT": node["title"]})
        for child in node["children"]:
            emit_into(item, child)

    emit_into(root_element, tree)
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        + ET.tostring(root_element, encoding="unicode")
    )
    return body.encode("utf-8")


def _text_package(content: dict) -> bytes:
    text = _check_text(content.get("text"), "text", MAX_TEXT_CHARS)
    return text.encode("utf-8")
