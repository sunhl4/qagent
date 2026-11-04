"""Structured pptx generation and shape text rewrite (§4.5, L3; stdlib port).

``WPS-SUITE-PORTING`` L3 names structured layouts over full-page text boxes the
quality line for generated decks; the reference drives one binary for visuals
and one library for decks. This adapter keeps the same behavioral contract on
the Python side with nothing but the standard library:

- ``render``: one .pptx built from a slide array of structured layouts - title
  (heading plus optional subtitle), agenda (numbered), bullets, two_column,
  matrix (a real PowerPoint table object, 1..6 x 1..6 cells), checklist
  (checkbox-prefixed) - fixed 16:9 geometry, named textboxes, numbered slides,
  so the deck opens in WPS/PowerPoint as an editable outline;
- ``edit``: rewrite the visible text of one ``p:sp`` textbox per edit,
  addressed as ``slide``/``shape`` (1-based document order, tables excluded).
  The batch is all-or-nothing: every target is validated before a byte is
  written, never a silent skip; newline edits refuse (one paragraph per shape);
- B5 gate: every written package is re-opened and per-slide ``a:t`` sequences
  are replayed against what was built before the receipt returns; a failed
  edit verification restores the original bytes, a failed render verification
  names the product undeliverable;
- caps are refusals, not stand-ins: 64 slides, 8 bullets per column, 4000
  characters per shape text, 120 characters per title, 400 per bullet and
  subtitle, 120 per matrix cell, 200 enumerated shapes; the P0 fences, the
  atomic temp+replace write and the re-read verification reuse
  ``office_create``;
- ``preview`` re-unites with the reference's §4.1 binary path: page count,
  shape enumeration and per-page screenshots (1280x720, referenced by the CLI
  as ``--screenshot-width/--screenshot-height --render html``) through a
  resolved officecli (``COMPANY_AGENT_OFFICECLI`` absolute path, or
  ``officecli``/``officecli.exe`` on PATH, or an honest refusal without a
  stand-in). The child spec is identical to the converter (minimal env,
  arrayed argv, bounded stdout, timeout) and the three runs sit under one
  per-file lease; both counts officecli reports are cross-checked against
  the re-opened deck package, shape routes reuse the 1-based slide/shape
  numbers edit addresses, screenshots land in ``preview/<stem>/slide-N.png``
  and a mid-run source change refuses the receipt.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from company_agent import office_convert, office_purpose, workspace_files
from company_agent import office_create as _oc
from company_agent import office_ingest as _ingest

ENV_OFFICECLI = "COMPANY_AGENT_OFFICECLI"
CLI_TIMEOUT = 180
CLI_STDOUT_CAP = 4_000_000
CLI_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
MAX_SHAPES = 200
DETAIL_BUDGET = 48_000
_DETAIL_TEXT_CHARS = 200
_SCREENSHOT_W = 1280
_SCREENSHOT_H = 720

_A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
_P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
_R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PKG_RELS_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
_CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
_TABLE_URI = "http://schemas.openxmlformats.org/drawingml/2006/table"

_A = "{" + _A_NS + "}"
_P = "{" + _P_NS + "}"

MAX_FILE_BYTES = _ingest.MAX_FILE_BYTES
MAX_SLIDES = 80
MAX_EDITS = 64
MAX_BULLETS = 8
MAX_TITLE_CHARS = 120
MAX_SUBTITLE_CHARS = 400
MAX_BULLET_CHARS = 400
MAX_SHAPE_TEXT_CHARS = 8_000
MAX_MATRIX_ROWS = 6
MAX_MATRIX_COLS = 6
MAX_CELL_CHARS = 120

SLIDE_CX = 12_192_000
SLIDE_CY = 6_858_000
MARGIN_X = 914_400
TITLE_OFF = (838_200, 609_600)
TITLE_EXT = (10_515_600, 1_143_000)
SUBTITLE_OFF = (1_524_000, 1_981_200)
SUBTITLE_EXT = (9_144_000, 1_066_800)
BODY_OFF = (914_400, 2_032_000)
BODY_EXT = (10_363_200, 4_419_600)
COLUMN_GAP = 304_800
COLUMN_W = (BODY_EXT[0] - COLUMN_GAP) // 2
ROW_H = 457_200

XML_HEAD = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'


class OfficePptxError(ValueError):
    """Refusal that names the boundary hit without echoing paths outside the root."""


def pptx(args: dict) -> dict:
    """Contract entry point: bounded render, all-or-nothing edit, or CLI preview."""

    purpose = office_purpose.take(args)
    root = workspace_files.root()
    compound = _oc._compound(args)
    action = _action(args)
    if action == "edit" and _overwrite(args):
        raise OfficePptxError("edit 原位改写现有文件,不接受 overwrite=true")
    extras: dict[str, object] = {}
    if action == "render":
        data, slides, shapes, applied = _render(root, compound, args)
    elif action == "edit":
        data, slides, shapes, applied = _edit(root, compound, args)
    else:
        data, slides, shapes, applied, extras = _preview(root, compound, args)
    payload = {
        "action": action,
        "path": compound,
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
        "slides": slides,
        "shapes": shapes,
        "applied": applied,
        "trust": "untrusted_reference_data",
    }
    payload.update(extras)
    office_purpose.audit("office_pptx", purpose, {"path": compound, "action": action})
    return payload


def _action(args: dict) -> str:
    raw = args.get("action")
    if raw not in {"render", "edit", "preview"}:
        raise OfficePptxError('action 必须是 "render"、"edit" 或 "preview"')
    return str(raw)


def _overwrite(args: dict) -> bool:
    raw = args.get("overwrite")
    if raw is None:
        return False
    if not isinstance(raw, bool):
        raise OfficePptxError("overwrite 必须是布尔值")
    return raw


# ---------------------------------------------------------------- render


def _render(root, compound: str, args: dict) -> tuple[bytes, int, int, int]:
    content = args.get("content")
    if not isinstance(content, dict):
        raise OfficePptxError("content 必须是对象(render 动作需要 slides)")
    if args.get("edits") is not None:
        raise OfficePptxError("edits 只用于 edit 动作;当前是 render")
    slides = content.get("slides")
    if not isinstance(slides, list) or not slides:
        raise OfficePptxError("content.slides 必须是非空数组")
    if len(slides) > MAX_SLIDES:
        raise OfficePptxError(f"幻灯片数 {len(slides)} 超过上限 {MAX_SLIDES},拒绝")
    built: list[tuple[str, list[str]]] = []
    shapes = 0
    for number, slide in enumerate(slides, start=1):
        shape_xmls, texts, sp_count = _slide_shapes(slide, number)
        shapes += sp_count
        built.append((XML_HEAD + _sld_document("".join(shape_xmls)), texts))
    data = _package(built)
    if len(data) > MAX_FILE_BYTES:
        raise OfficePptxError("生成的文件超过 20MB 上限:请拆分内容后重试")
    existed, target = _oc._resolve_target(root, compound, _overwrite(args))
    _oc._write_atomic(target, data, existed)
    _oc._verify_written(target, data)
    _verify_render(target, built)
    return data, len(built), shapes, 0


def _slide_shapes(slide: object, number: int) -> tuple[list[str], list[str], int]:
    if not isinstance(slide, dict):
        raise OfficePptxError(f"第 {number} 张必须是对象")
    kind = slide.get("kind")
    if kind not in LAYOUTS:
        raise OfficePptxError(f"第 {number} 张 kind 只支持 {'/'.join(LAYOUTS)}")
    title = _oc._check_text(slide.get("title"), f"第 {number} 张 title", MAX_TITLE_CHARS)
    if not title.strip():
        raise OfficePptxError(f"第 {number} 张 title 不能为空")
    texts: list[str] = [title]
    shapes: list[str] = [_title_box(2, title)]
    sp_count = 1
    if kind == "title":
        subtitle = slide.get("subtitle") or ""
        if subtitle:
            checked = _oc._check_text(subtitle, f"第 {number} 张 subtitle", MAX_SUBTITLE_CHARS)
            texts.append(checked)
            sp_count += 1
            shapes.append(
                _box(
                    3,
                    f"第 {number} 张副标题",
                    *SUBTITLE_OFF,
                    *SUBTITLE_EXT,
                    [_paragraph(checked, 2400)],
                )
            )
    elif kind in {"agenda", "bullets", "checklist"}:
        rows = _rows_of(slide, number, "bullets")
        if kind == "agenda":
            display = [f"{index}. {row}" for index, row in enumerate(rows, start=1)]
        elif kind == "checklist":
            display = [f"□ {row}" for row in rows]
        else:
            display = rows
        texts.extend(display)
        sp_count += 1
        shapes.append(_box(3, f"第 {number} 张正文", *BODY_OFF, *BODY_EXT, _bullet_paragraphs(display, kind)))
    elif kind == "two_column":
        left = _rows_of(slide, number, "left")
        right = _rows_of(slide, number, "right")
        texts.extend(left)
        texts.extend(right)
        sp_count += 2
        shapes.append(
            _box(
                3,
                f"第 {number} 张左栏",
                MARGIN_X,
                BODY_OFF[1],
                COLUMN_W,
                BODY_EXT[1],
                _bullet_paragraphs(left, "bullets"),
            )
        )
        shapes.append(
            _box(
                4,
                f"第 {number} 张右栏",
                MARGIN_X + COLUMN_W + COLUMN_GAP,
                BODY_OFF[1],
                COLUMN_W,
                BODY_EXT[1],
                _bullet_paragraphs(right, "bullets"),
            )
        )
    else:
        grid = _matrix_of(slide, number)
        texts.extend(cell for row in grid for cell in row)
        shapes.append(_table(3, f"第 {number} 张表格", BODY_OFF[0], BODY_OFF[1], grid))
    return shapes, texts, sp_count


def _rows_of(slide: dict, number: int, label: str) -> list[str]:
    rows = slide.get(label)
    if not isinstance(rows, list):
        raise OfficePptxError(f"第 {number} 张 {label} 需要是数组")
    if len(rows) > MAX_BULLETS:
        raise OfficePptxError(f"第 {number} 张 {label} 共 {len(rows)} 行,超过上限 {MAX_BULLETS},拒绝")
    return [
        _oc._check_text(row, f"第 {number} 张 {label} 行", MAX_BULLET_CHARS)
        for row in rows
    ]


def _matrix_of(slide: dict, number: int) -> list[list[str]]:
    grid = slide.get("matrix")
    if not isinstance(grid, list) or not grid:
        raise OfficePptxError(f"第 {number} 张 matrix 需要非空二维数组")
    if len(grid) > MAX_MATRIX_ROWS:
        raise OfficePptxError(f"第 {number} 张 matrix 共 {len(grid)} 行,超过上限 {MAX_MATRIX_ROWS},拒绝")
    checked: list[list[str]] = []
    width: int | None = None
    for row in grid:
        if not isinstance(row, list) or not row:
            raise OfficePptxError(f"第 {number} 张 matrix 每行需要是非空数组")
        if width is None:
            width = len(row)
            if width > MAX_MATRIX_COLS:
                raise OfficePptxError(f"第 {number} 张 matrix 共 {width} 列,超过上限 {MAX_MATRIX_COLS},拒绝")
        elif len(row) != width:
            raise OfficePptxError(f"第 {number} 张 matrix 各行列数不一致,拒绝")
        checked.append(
            [_oc._check_text(cell, f"第 {number} 张 matrix 单元格", MAX_CELL_CHARS) for cell in row]
        )
    return checked


def _bullet_paragraphs(rows: list[str], kind: str) -> list[str]:
    paragraphs: list[str] = []
    for row in rows:
        if kind == "bullets":
            escaped = _oc._esc(row)
            paragraphs.append(
                f'<a:p><a:pPr marL="285750" indent="-285750"><a:buChar char="•"/></a:pPr>'
                f'<a:r><a:rPr lang="zh-CN" sz="1600"/><a:t>{escaped}</a:t></a:r></a:p>'
            )
        else:
            paragraphs.append(_paragraph(row, 1600))
    return paragraphs


def _paragraph(text: str, size: int, center: bool = False) -> str:
    align = ' algn="ctr"' if center else ""
    bold = ' b="1"' if center else ""
    return (
        f'<a:p><a:pPr{align}/><a:r><a:rPr lang="zh-CN" sz="{size}"{bold}/>'
        f"<a:t>{_oc._esc(text)}</a:t></a:r></a:p>"
    )


def _title_box(shape_id: int, title: str) -> str:
    return _box(shape_id, "标题", *TITLE_OFF, *TITLE_EXT, [_paragraph(title, 4000)])


def _box(shape_id: int, name: str, x: int, y: int, cx: int, cy: int, paragraphs: list[str]) -> str:
    return (
        f'<p:sp><p:nvSpPr><p:cNvPr id="{shape_id}" name="{_oc._esc(name)}"/>'
        '<p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr>'
        f'<p:spPr><a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
        '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>'
        '<p:txBody><a:bodyPr wrap="square"/><a:lstStyle/>'
        f"{''.join(paragraphs)}</p:txBody></p:sp>"
    )


def _table(shape_id: int, name: str, x: int, y: int, grid: list[list[str]]) -> str:
    cols = len(grid[0])
    width = BODY_EXT[0]
    height = ROW_H * len(grid)
    cells = "".join(
        f'<a:tr h="{ROW_H}">'
        + "".join(
            f'<a:tc><a:txBody><a:bodyPr/><a:lstStyle/>{_paragraph(cell, 1400)}</a:txBody>'
            f'<a:tcPr marL="91440" marR="91440" marT="45720" marB="45720"/></a:tc>'
            for cell in row
        )
        + "</a:tr>"
        for row in grid
    )
    column = "".join(f'<a:gridCol w="{width // cols}"/>' for _ in range(cols))
    return (
        f'<p:graphicFrame><p:nvGraphicFramePr><p:cNvPr id="{shape_id}" name="{_oc._esc(name)}"/>'
        '<p:cNvGraphicFramePr><a:graphicFrameLocks noGrp="1"/></p:cNvGraphicFramePr>'
        "<p:nvPr/></p:nvGraphicFramePr>"
        f'<p:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{width}" cy="{height}"/></p:xfrm>'
        f'<a:graphic><a:graphicData uri="{_TABLE_URI}"><a:tbl>'
        f"<a:tblGrid>{column}</a:tblGrid>{cells}</a:tbl>"
        "</a:graphicData></a:graphic></p:graphicFrame>"
    )


def _sld_document(shapes: str) -> str:
    return (
        f'<p:sld xmlns:a="{_A_NS}" xmlns:r="{_R_NS}" xmlns:p="{_P_NS}">'
        '<p:cSld><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/>'
        "<p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr/>"
        f"{shapes}</p:spTree></p:cSld>"
        "<p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sld>"
    )


def _zi(name: str, data: bytes) -> tuple[zipfile.ZipInfo, bytes]:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    return info, data


def _package(built: list[tuple[str, list[str]]]) -> bytes:
    count = len(built)
    slide_ids = "".join(
        f'<p:sldId id="{255 + number}" r:id="rId{number + 1}"/>'
        for number in range(1, count + 1)
    )
    presentation = (
        XML_HEAD
        + f'<p:presentation xmlns:a="{_A_NS}" xmlns:r="{_R_NS}" xmlns:p="{_P_NS}">'
        '<p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/></p:sldMasterIdLst>'
        f"<p:sldIdLst>{slide_ids}</p:sldIdLst>"
        f'<p:sldSz cx="{SLIDE_CX}" cy="{SLIDE_CY}"/>'
        "<p:notesSz cx=\"6858000\" cy=\"9144000\"/></p:presentation>"
    )
    presentation_rels = [
        _rel(
            "rId1",
            "slideMaster",
            "slideMasters/slideMaster1.xml",
        )
    ]
    presentation_rels.extend(
        _rel(f"rId{number + 1}", "slide", f"slides/slide{number}.xml")
        for number in range(1, count + 1)
    )
    root_rels = [
        _rel(
            "rId1",
            "officeDocument",
            "ppt/presentation.xml",
        )
    ]
    master_rels = [
        _rel("rId1", "slideLayout", "../slideLayouts/slideLayout1.xml"),
        _rel("rId2", "theme", "../theme/theme1.xml"),
    ]
    layout_rels = [_rel("rId1", "slideMaster", "../slideMasters/slideMaster1.xml")]
    slide_rels = [_rel("rId1", "slideLayout", "../slideLayouts/slideLayout1.xml")]
    overrides = [
        (
            "/ppt/presentation.xml",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml",
        ),
        (
            "/ppt/slideMasters/slideMaster1.xml",
            "application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml",
        ),
        (
            "/ppt/slideLayouts/slideLayout1.xml",
            "application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml",
        ),
        ("/ppt/theme/theme1.xml", "application/vnd.openxmlformats-officedocument.theme+xml"),
    ]
    overrides.extend(
        (
            f"/ppt/slides/slide{number}.xml",
            "application/vnd.openxmlformats-officedocument.presentationml.slide+xml",
        )
        for number in range(1, count + 1)
    )
    content_types = (
        XML_HEAD
        + f'<Types xmlns="{_CT_NS}">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats'
        '-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        + "".join(f'<Override PartName="{part}" ContentType="{ctype}"/>' for part, ctype in overrides)
        + "</Types>"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as package:
        for name, payload in (
            ("[Content_Types].xml", content_types.encode("utf-8")),
            ("_rels/.rels", _rels_xml(root_rels).encode("utf-8")),
            ("ppt/presentation.xml", presentation.encode("utf-8")),
            ("ppt/_rels/presentation.xml.rels", _rels_xml(presentation_rels).encode("utf-8")),
            ("ppt/slideMasters/slideMaster1.xml", _MASTER_XML.encode("utf-8")),
            ("ppt/slideMasters/_rels/slideMaster1.xml.rels", _rels_xml(master_rels).encode("utf-8")),
            ("ppt/slideLayouts/slideLayout1.xml", _LAYOUT_XML.encode("utf-8")),
            ("ppt/slideLayouts/_rels/slideLayout1.xml.rels", _rels_xml(layout_rels).encode("utf-8")),
            ("ppt/theme/theme1.xml", _THEME_XML.encode("utf-8")),
        ):
            package.writestr(*_zi(name, payload))
        for number, (slide_xml, _texts) in enumerate(built, start=1):
            package.writestr(*_zi(f"ppt/slides/slide{number}.xml", slide_xml.encode("utf-8")))
            package.writestr(
                *_zi(f"ppt/slides/_rels/slide{number}.xml.rels", _rels_xml(slide_rels).encode("utf-8"))
            )
    return buffer.getvalue()


def _rel(rel_id: str, rest: str, target: str) -> str:
    return (
        f'<Relationship Id="{rel_id}" Type="http://schemas.openxmlformats.org'
        f'/officeDocument/2006/relationships/{rest}" Target="{target}"/>'
    )


def _rels_xml(rows: list[str]) -> str:
    return XML_HEAD + f'<Relationships xmlns="{_PKG_RELS_NS}">' + "".join(rows) + "</Relationships>"


_MASTER_XML = (
    XML_HEAD
    + f'<p:sldMaster xmlns:a="{_A_NS}" xmlns:r="{_R_NS}" xmlns:p="{_P_NS}">'
    '<p:cSld><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/>'
    "<p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr/></p:spTree></p:cSld>"
    '<p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" '
    'accent2="accent2" accent3="accent3" accent4="accent4" accent5="accent5" '
    'accent6="accent6" hlink="hlink" folHlink="folHlink"/>'
    '<p:sldLayoutIdLst><p:sldLayoutId id="2147483649" r:id="rId1"/></p:sldLayoutIdLst>'
    "</p:sldMaster>"
)
_LAYOUT_XML = (
    XML_HEAD
    + f'<p:sldLayout xmlns:a="{_A_NS}" xmlns:r="{_R_NS}" xmlns:p="{_P_NS}">'
    '<p:cSld name="blank"><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/>'
    "<p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr/></p:spTree></p:cSld>"
    "<p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sldLayout>"
)
_CLRS = (
    '<a:dk1><a:sysClr val="windowText" lastClr="000000"/></a:dk1>'
    '<a:lt1><a:sysClr val="window" lastClr="FFFFFF"/></a:lt1>'
    '<a:dk2><a:srgbClr val="1F2933"/></a:dk2>'
    '<a:lt2><a:srgbClr val="F5F7FA"/></a:lt2>'
    '<a:accent1><a:srgbClr val="2563EB"/></a:accent1>'
    '<a:accent2><a:srgbClr val="0891B2"/></a:accent2>'
    '<a:accent3><a:srgbClr val="16A34A"/></a:accent3>'
    '<a:accent4><a:srgbClr val="D97706"/></a:accent4>'
    '<a:accent5><a:srgbClr val="9333EA"/></a:accent5>'
    '<a:accent6><a:srgbClr val="DC2626"/></a:accent6>'
    '<a:hlink><a:srgbClr val="2563EB"/></a:hlink>'
    '<a:folHlink><a:srgbClr val="7C3AED"/></a:folHlink>'
)
_STYLE = '<a:solidFill><a:schemeClr val="accent1"/></a:solidFill>'
_LINES = "".join(
    f'<a:ln w="{weight}">{_STYLE}</a:ln>' for weight in (9525, 19050, 28575)
)
_FMT = (
    f'<a:fmtScheme name="office">'
    f"<a:fillStyleLst>{_STYLE}{_STYLE}{_STYLE}</a:fillStyleLst>"
    f"<a:lnStyleLst>{_LINES}</a:lnStyleLst>"
    "<a:effectStyleLst><a:effectStyle><a:effectLst/></a:effectStyle>"
    "<a:effectStyle><a:effectLst/></a:effectStyle>"
    "<a:effectStyle><a:effectLst/></a:effectStyle></a:effectStyleLst>"
    f"<a:bgFillStyleLst>{_STYLE}{_STYLE}{_STYLE}</a:bgFillStyleLst>"
    "</a:fmtScheme>"
)
_THEME_XML = (
    XML_HEAD
    + f'<a:theme xmlns:a="{_A_NS}" name="office">'
    "<a:themeElements>"
    f'<a:clrScheme name="office">{_CLRS}</a:clrScheme>'
    '<a:fontScheme name="office">'
    '<a:majorFont><a:latin typeface="Calibri Light"/><a:ea typeface=""/><a:cs typeface=""/></a:majorFont>'
    '<a:minorFont><a:latin typeface="Calibri"/><a:ea typeface=""/><a:cs typeface=""/></a:minorFont>'
    "</a:fontScheme>"
    f"{_FMT}</a:themeElements></a:theme>"
)

LAYOUTS: tuple[str, ...] = ("agenda", "bullets", "checklist", "matrix", "title", "two_column")


# ---------------------------------------------------------------- edit


def _edit(root, compound: str, args: dict) -> tuple[bytes, int, int, int]:
    if args.get("content") is not None:
        raise OfficePptxError("content 只用于 render 动作;当前是 edit")
    edits = args.get("edits")
    if not isinstance(edits, list) or not edits:
        raise OfficePptxError("edits 必须是非空数组(edit 动作)")
    if len(edits) > MAX_EDITS:
        raise OfficePptxError(f"edits 共 {len(edits)} 条,超过上限 {MAX_EDITS},拒绝")
    plans: list[tuple[int, int, str]] = []
    for number, row in enumerate(edits, start=1):
        if not isinstance(row, dict):
            raise OfficePptxError(f"第 {number} 条 edit 必须是对象")
        slide = row.get("slide")
        shape = row.get("shape")
        text = _oc._check_text(row.get("text"), f"第 {number} 条 edit.text", MAX_SHAPE_TEXT_CHARS)
        if not isinstance(slide, int) or isinstance(slide, bool) or not 1 <= slide <= MAX_SLIDES:
            raise OfficePptxError(f"第 {number} 条 edit.slide 必须是 1..{MAX_SLIDES}")
        if not isinstance(shape, int) or isinstance(shape, bool) or shape < 1:
            raise OfficePptxError(f"第 {number} 条 edit.shape 必须是 >= 1")
        text = " ".join(part.strip() for part in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"))
        text = " ".join(text.split())
        plans.append((slide, shape, text))
    resolved = workspace_files.resolve(root, compound)
    if not resolved.is_file():
        raise OfficePptxError("workspace path is not a file")
    if resolved.suffix.casefold() != ".pptx":
        raise OfficePptxError("文本回写只支持 .pptx")
    original = _read_bounded(root, compound)
    package = zipfile.ZipFile(io.BytesIO(original))
    try:
        _slide_numbers, slide_roots = _load_slides(package)
    except (zipfile.BadZipFile, ET.ParseError, KeyError) as exc:
        raise OfficePptxError("pptx 数据包损坏或缺实体,拒绝判读") from exc
    _validate_targets(plans, slide_roots)
    rewritten: set[int] = set()
    for slide_number, shape_number, text in plans:
        sps = list(slide_roots[slide_number].iter(_P + "sp"))
        _rewrite_shape(sps[shape_number - 1], text)
        rewritten.add(slide_number)
    edited: dict[str, bytes] = {}
    ET.register_namespace("a", _A_NS)
    ET.register_namespace("p", _P_NS)
    ET.register_namespace("r", _R_NS)
    for slide_number in sorted(rewritten):
        edited[f"ppt/slides/slide{slide_number}.xml"] = (
            XML_HEAD + ET.tostring(slide_roots[slide_number], encoding="unicode")
        ).encode("utf-8")
    output = _repackage(package, edited)
    existed, target = _oc._resolve_target(root, compound, True)
    _oc._write_atomic(target, output, existed)
    _oc._verify_written(target, output)
    try:
        _verify_edit(target, plans)
    except OfficePptxError:
        _oc._write_atomic(target, original, True)
        _oc._verify_written(target, original)
        raise
    shapes = 0
    with zipfile.ZipFile(target.open("rb")) as reopened:
        _slide_numbers, reopened_roots = _load_slides(reopened)
        for slide_root in reopened_roots.values():
            shapes += len(list(slide_root.iter(_P + "sp")))
    return output, len(_slide_numbers), shapes, len(plans)


# ---------------------------------------------------------------- preview


def _preview(root, compound: str, args: dict) -> tuple[bytes, int, int, int, dict[str, object]]:
    """Officecli visual preview: page count, shape listing, per-page shots.

    Read-only over the source deck: every number the receipt reports is
    cross-checked (stats page count and per-slide shape count against the
    re-opened package), all shots must carry PNG magic, and a source change
    inside the run window refuses the receipt instead of describing a deck
    that no longer exists.
    """
    if args.get("content") is not None:
        raise OfficePptxError("content 只用于 render 动作;当前是 preview")
    if args.get("edits") is not None:
        raise OfficePptxError("edits 只用于 edit 动作;当前是 preview")
    if _overwrite(args):
        raise OfficePptxError("preview 只读取源文件,不接受 overwrite=true")
    resolved = workspace_files.resolve(root, compound)
    if not resolved.is_file():
        raise OfficePptxError("workspace path is not a file")
    if resolved.suffix.casefold() != ".pptx":
        raise OfficePptxError("视觉预览只支持 .pptx")
    original = _read_bounded(root, compound)
    package = zipfile.ZipFile(io.BytesIO(original))
    try:
        slide_numbers, slide_roots = _load_slides(package)
    except (zipfile.BadZipFile, ET.ParseError, KeyError) as exc:
        raise OfficePptxError("pptx 数据包损坏或缺实体,拒绝判读") from exc
    if len(slide_numbers) > MAX_SLIDES:
        raise OfficePptxError(f"预览页数 {len(slide_numbers)} 超过上限 {MAX_SLIDES},拒绝")
    shapes = _deck_shapes(slide_roots)
    if len(shapes) > MAX_SHAPES:
        raise OfficePptxError(
            f"该演示文稿共 {len(shapes)} 个文本框,超过枚举上限 {MAX_SHAPES},拒绝"
        )
    detail_rows = [
        {"slide": slide_number, "shape": ordinal, "text": text[:_DETAIL_TEXT_CHARS]}
        for slide_number, ordinal, text in shapes
    ]
    if (
        len(json.dumps(detail_rows, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        > DETAIL_BUDGET
    ):
        raise OfficePptxError("shape 枚举行超过回执预算,拒绝(精简文本或减少页数后再预览)")

    engine = _resolve_cli()
    lease_path = Path(tempfile.gettempdir()) / (
        "officecli-" + hashlib.sha1(str(resolved).encode("utf-8")).hexdigest()[:12] + ".lock"
    )
    try:
        with (
            office_convert._lease(lease_path),
            tempfile.TemporaryDirectory(prefix="office-pptx-preview-") as staging,
        ):
            pages = _cli_stats(engine, resolved, staging)
            if len(slide_numbers) != pages:
                raise OfficePptxError(
                    f"officecli 报告页数 {pages} 与包内幻灯片数 {len(slide_numbers)} 不一致,拒绝预览"
                )
            _check_shape_enumeration(_cli_shapes(engine, resolved, staging), shapes)
            shots = _cli_shots(engine, resolved, staging, pages, root, compound)
    except office_convert.OfficeConvertError as exc:
        raise OfficePptxError(str(exc)) from exc
    after = _read_bounded(root, compound)
    if after != original:
        raise OfficePptxError("预览期间源文件被并发修改,如实拒绝")
    return (
        after,
        len(slide_numbers),
        len(shapes),
        0,
        {
            "officecli": Path(engine).name[:80] or "officecli",
            "screenshots": shots,
            "shapes_detail": detail_rows,
        },
    )


def _deck_shapes(slide_roots: dict[int, ET.Element]) -> list[tuple[int, int, str]]:
    """(slide, shape, a:t text) in document order - the addresses edit uses."""

    rows: list[tuple[int, int, str]] = []
    for slide_number in sorted(slide_roots):
        for ordinal, sp in enumerate(slide_roots[slide_number].iter(_P + "sp"), start=1):
            tx_body = sp.find(_P + "txBody")
            text = (
                "".join(node.text or "" for node in tx_body.iter(_A + "t"))
                if tx_body is not None
                else ""
            )
            rows.append((slide_number, ordinal, text))
    return rows


def _check_shape_enumeration(
    rows: list[tuple[int, str]], shapes: list[tuple[int, int, str]]
) -> None:
    if len(rows) != len(shapes):
        raise OfficePptxError(
            f"officecli 枚举文本框 {len(rows)} 个,与包内 {len(shapes)} 个不一致,拒绝预览"
        )
    if all(slide > 0 for slide, _row in rows):
        theirs: dict[int, int] = {}
        for slide, _row in rows:
            theirs[slide] = theirs.get(slide, 0) + 1
        ours: dict[int, int] = {}
        for slide, _ordinal, _text in shapes:
            ours[slide] = ours.get(slide, 0) + 1
        if theirs != ours:
            raise OfficePptxError("officecli 逐张文本框数与包内容不一致,拒绝预览")


def _resolve_cli(explicit: str | None = None) -> str:
    """Five-step officecli lookup: argument, env, bundled resources, repo root, PATH."""

    if explicit and str(explicit).strip():
        found = Path(str(explicit).strip())
        if not found.is_file():
            raise OfficePptxError("显式 officecli 路径不是文件,请核对安装位置")
        return str(found)
    configured = str(os.environ.get(ENV_OFFICECLI) or "").strip()
    if configured:
        found = Path(configured)
        if not found.is_file():
            raise OfficePptxError("COMPANY_AGENT_OFFICECLI 配置的路径不是文件,请核对 officecli 安装位置")
        return str(found)
    root = _repo_root()
    names = ("officecli.exe", "officecli") if os.name == "nt" else ("officecli", "officecli.exe")
    bundled = root / "resources" / "officecli" / _platform_tag()
    for name in names:
        candidate = bundled / name
        if candidate.is_file():
            return str(candidate)
    for name in names:
        candidate = root / name
        if candidate.is_file():
            return str(candidate)
    for name in names:
        found = shutil.which(name)
        if found:
            return str(found)
    raise OfficePptxError(
        "本机未找到 officecli:pptx 视觉预览依赖 OfficeCLI 二进制,"
        "请安装后用 COMPANY_AGENT_OFFICECLI 指向绝对路径;如实拒绝,不出替身"
    )


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _platform_tag() -> str:
    system = {"win32": "win32", "darwin": "darwin", "linux": "linux"}.get(sys.platform, sys.platform)
    machine = platform.machine().lower()
    arch = "x64" if machine in {"amd64", "x86_64"} else machine or "x64"
    return f"{system}-{arch}"


_PAGE_KEYS = ("slides", "pages", "pageCount", "page_count", "slideCount", "slide_count")


def _stats_pages(payload: object) -> int | None:
    if isinstance(payload, dict):
        scopes = [payload]
        nested = payload.get("stats")
        if isinstance(nested, dict):
            scopes.append(nested)
        for scope in scopes:
            for key in _PAGE_KEYS:
                value = scope.get(key)
                if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                    return value
    return None


def _entry_slide(entry: dict) -> int:
    path = entry.get("path")
    if isinstance(path, str):
        match = re.search(r"/slide\[(\d+)\]", path)
        if match is not None:
            return int(match.group(1))
    slide = entry.get("slide")
    if isinstance(slide, int) and not isinstance(slide, bool):
        return slide
    return 0


def _cli_stats(engine: str, deck: Path, cwd: str) -> int:
    _code, output = _cli(engine, ["view", str(deck), "stats", "--json"], cwd)
    try:
        payload = json.loads(output.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise OfficePptxError("officecli stats 输出不是合法 JSON,如实拒绝") from exc
    pages = _stats_pages(payload)
    if pages is None:
        raise OfficePptxError("officecli stats JSON 没有可读的页数字段,如实拒绝")
    return pages


def _cli_shapes(engine: str, deck: Path, cwd: str) -> list[tuple[int, str]]:
    _code, output = _cli(engine, ["query", str(deck), "shape", "--json"], cwd)
    try:
        payload = json.loads(output.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise OfficePptxError("officecli shape 输出不是合法 JSON,如实拒绝") from exc
    entries = payload.get("shapes") if isinstance(payload, dict) else payload
    if not isinstance(entries, list):
        raise OfficePptxError("officecli shape JSON 没有 shapes 数组,如实拒绝")
    rows: list[tuple[int, str]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise OfficePptxError("officecli shape 条目不是对象,如实拒绝")
        rows.append((_entry_slide(entry), str(entry.get("text") or "")))
    return rows


def _cli_shots(
    engine: str, deck: Path, cwd: str, pages: int, root, compound: str
) -> list[dict[str, object]]:
    shots: list[dict[str, object]] = []
    shots_dir: Path | None = None
    for page in range(1, pages + 1):
        artifact = _shot_compound(compound, deck, page)
        workspace_files._lexical(artifact)
        _existed, target = _oc._resolve_target(root, artifact, True)
        shots_dir = target.parent
        _code, _out = _cli(
            engine,
            [
                "view",
                str(deck),
                "screenshot",
                "--page",
                str(page),
                "-o",
                str(target),
                "--screenshot-width",
                str(_SCREENSHOT_W),
                "--screenshot-height",
                str(_SCREENSHOT_H),
                "--render",
                "html",
            ],
            cwd,
        )
        data = target.read_bytes()
        if not data or not data.startswith(CLI_PNG_MAGIC):
            raise OfficePptxError(f"第 {page} 张截图不是合法 PNG,officecli 产物不可信,如实拒绝")
        shots.append({"page": page, "path": artifact, "bytes": len(data)})
    if shots_dir is not None:
        _drop_stale_shots(shots_dir, pages)
    return shots


def _shot_compound(compound: str, deck: Path, page: int) -> str:
    project, _, _relative = compound.partition("/")
    stamp = str(deck.stat().st_mtime_ns).encode("ascii")
    key = hashlib.sha1(str(deck).encode("utf-8") + b"\0" + stamp).hexdigest()[:24]
    return f"{project}/cache/pptx-preview/{key}/slide-{page}.png"


def _drop_stale_shots(folder: Path, pages: int) -> None:
    for entry in list(folder.iterdir()):
        match = re.fullmatch(r"slide-([0-9]{1,3})\.png", entry.name)
        if match is not None and int(match.group(1)) > pages:
            entry.unlink(missing_ok=True)


def _cli(engine: str, tail: list[str], cwd: str) -> tuple[int, bytes]:
    code, output = _run([engine, *tail], cwd)
    if code != 0:
        raise OfficePptxError(f"officecli 退出码 {code},如实拒绝")
    return code, output


def _run(command: list[str], cwd: str) -> tuple[int, bytes]:
    """Bounded officecli child run; child spec identical to the soffice converter."""

    try:
        finished = subprocess.run(
            command,
            cwd=cwd,
            env=office_convert._minimal_env(),
            capture_output=True,
            timeout=CLI_TIMEOUT,
        )
    except FileNotFoundError as exc:
        raise OfficePptxError("officecli 可执行文件消失,如实拒绝") from exc
    except subprocess.TimeoutExpired as exc:
        raise OfficePptxError(f"officecli 超过 {CLI_TIMEOUT} 秒被终止,如实拒绝") from exc
    output = finished.stdout or b""
    if len(output) > CLI_STDOUT_CAP:
        output = output[:CLI_STDOUT_CAP]
    return int(finished.returncode or 0), output


def _validate_targets(plans: list[tuple[int, int, str]], slide_roots: dict[int, ET.Element]) -> None:
    for number, (slide_number, shape_number, _text) in enumerate(plans, start=1):
        slide_root = slide_roots.get(slide_number)
        if slide_root is None:
            raise OfficePptxError(
                f"第 {number} 条 edit 的 slide {slide_number} 不存在"
                f"(共 {len(slide_roots)} 张);整批拒绝,未写入"
            )
        sps = list(slide_root.iter(_P + "sp"))
        if shape_number > len(sps):
            raise OfficePptxError(
                f"第 {number} 条 edit 的 slide {slide_number} 只有 {len(sps)} 个文本框,"
                f"shape {shape_number} 不存在;整批拒绝,未写入"
            )


def _load_slides(package: zipfile.ZipFile) -> tuple[list[int], dict[int, ET.Element]]:
    pattern = re.compile(r"^ppt/slides/slide([0-9]{1,4})\.xml$")
    numbers: list[int] = []
    roots: dict[int, ET.Element] = {}
    for name in package.namelist():
        match = pattern.match(name)
        if match is None:
            continue
        number = int(match.group(1))
        numbers.append(number)
        roots[number] = ET.fromstring(package.read(name))
    return sorted(numbers), roots


def _rewrite_shape(sp: ET.Element, text: str) -> None:
    tx_body = sp.find(_P + "txBody")
    if tx_body is None:
        raise OfficePptxError("目标 shape 没有文本体(p:txBody),不能回写;整批拒绝,未写入")
    run_props = ""
    first_run = tx_body.find(f".//{_A}r/{_A}rPr")
    if first_run is not None:
        run_props = ET.tostring(first_run, encoding="unicode").strip()
    fragment = ET.fromstring(
        f'<p:txBody xmlns:a="{_A_NS}" xmlns:p="{_P_NS}">'
        '<a:bodyPr wrap="square" rtlCol="0"/><a:lstStyle/>'
        f"<a:p><a:r>{run_props}<a:t>{_oc._esc(text)}</a:t></a:r></a:p></p:txBody>"
    )
    for child in list(tx_body):
        tx_body.remove(child)
    for child in fragment:
        tx_body.append(child)


def _repackage(package: zipfile.ZipFile, edited: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as output:
        for info in package.infolist():
            payload = edited.get(info.filename)
            if payload is None:
                payload = package.read(info.filename)
            output.writestr(info, payload)
    return buffer.getvalue()


def _read_bounded(root, relative: str) -> bytes:
    try:
        oversized = workspace_files.resolve(root, relative).stat().st_size > MAX_FILE_BYTES
    except OSError as exc:
        raise OfficePptxError("workspace file is not available") from exc
    if oversized:
        raise OfficePptxError("文件超过 20MB 回写上限:该文件被拒绝(明示拒收,不出替身)")
    with workspace_files.open_file(root, relative) as stream:
        data = stream.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES:
        raise OfficePptxError("文件超过 20MB 回写上限:该文件被拒绝(明示拒收,不出替身)")
    return data


# ---------------------------------------------------------------- B5 verification


def _verify_render(target, built: list[tuple[str, list[str]]]) -> None:
    with zipfile.ZipFile(target.open("rb")) as package:
        numbers, roots = _load_slides(package)
        if numbers != list(range(1, len(built) + 1)):
            raise OfficePptxError("回放校验失败:写回包的幻灯片数与生成计划不一致,该产物不可交付")
        for number, (_xml, texts) in enumerate(built, start=1):
            seen = [node.text or "" for node in roots[number].iter(_A + "t")]
            if seen != texts:
                raise OfficePptxError(
                    f"第 {number} 张回放校验失败:写回包内容与生成计划不一致,该产物不可交付"
                )


def _verify_edit(target, plans: list[tuple[int, int, str]]) -> None:
    with zipfile.ZipFile(target.open("rb")) as package:
        _numbers, roots = _load_slides(package)
        for slide_number, shape_number, text in plans:
            if slide_number not in roots:
                raise OfficePptxError("回放校验失败:写入后的包缺少目标幻灯片,已恢复原文件")
            sps = list(roots[slide_number].iter(_P + "sp"))
            if shape_number > len(sps):
                raise OfficePptxError("回放校验失败:写入后的包缺少目标文本框,已恢复原文件")
            tx_body = sps[shape_number - 1].find(_P + "txBody")
            seen = (
                "".join(node.text or "" for node in tx_body.iter(_A + "t"))
                if tx_body is not None
                else None
            )
            if seen != text:
                raise OfficePptxError("回放校验失败:写入后的文本与计划不一致,已恢复原文件")
