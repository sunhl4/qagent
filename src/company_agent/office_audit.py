"""Read-only docx format audit for the WPS-suite porting (§4.12, L4 companion).

``WPS-SUITE-PORTING`` L4 names the format gray zone a first-class surface: the
audit tells the truth about a Word document's formatting instead of guessing.
Three scopes behind two call modes:

- ``baseline`` = the ``from-scratch`` *and* ``retemplate`` scope: check the
  document against the GB/T 9704-2012 *draft* rule table (A4 with 37/35/28/26
  mm margins, body 仿宋 16pt, first-line indent 2 chars, 26.5-30pt line band,
  title 小标宋 22pt centered, heading1 黑体 / heading2 楷体 / heading3 仿宋).
  The table is explicitly a draft pending the firm's confirmation and a
  replaceable constant;
- ``imported`` = the ``imported`` scope: never applies a template. It records
  the file's own dominant format as bounded facts and flags only structural
  anomalies such as several sections.

The bounded honesty rules carried over from the P1-P4 slices:

- paragraph locators reuse the ``company_office_analyze`` L{n} numbering
  (every ``w:p`` of ``word/document.xml`` in document order, tables counted),
  so the audit never drifts from what the model was shown;
- what the bounded parser cannot verify (headers, tables, character spacing,
  deep style chains, an unknown font, an automatic line rule) is *listed* in
  ``unchecked`` and is never claimed as passing;
- 5000 checked paragraphs is a cited cap with an explicit ``truncated`` flag,
  not a stand-in; the 20MB ingest cap and the corrupt-package refusal match
  ingestion behavior;
- read-only tool: nothing is written, nothing is fixed, no external calls.
"""
from __future__ import annotations

import hashlib
import io
import re
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter
from itertools import islice
from typing import Any

from company_agent import office_ingest as _ingest
from company_agent import workspace_files

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
MAX_FILE_BYTES = _ingest.MAX_FILE_BYTES
MAX_PARAGRAPHS = 5_000
MAX_FACTS = 16
MAX_UNCHECKED = 16

_MM_PER_TWIP = 25.4 / 1440
_TWIP_PER_PT = 20

PAGE_WIDTH_MM = 210.0
PAGE_HEIGHT_MM = 297.0
PAGE_TOLERANCE_MM = 1.0
MARGIN_TOP_MM = 37.0
MARGIN_BOTTOM_MM = 35.0
MARGIN_LEFT_MM = 28.0
MARGIN_RIGHT_MM = 26.0
MARGIN_TOLERANCE_MM = 1.0

BODY_PT = 16.0
TITLE_PT = 22.0
LINE_BAND_PT = (26.5, 30.0)
INDENT_CHARS = 2.0
INDENT_TOLERANCE = 0.25

FONT_BODY = ("仿宋", "fangsong")
FONT_HEADING1 = ("黑", "hei")
FONT_HEADING2 = ("楷", "kai")
FONT_TITLE = ("小标宋", "xiaobiaosong")
FONT_LABEL = {1: "黑体", 2: "楷体", 3: "仿宋"}

RULE_SET = {
    "id": "gbt-9704-2012-draft",
    "title": "GB/T 9704-2012 公文格式(草)",
    "status": "draft-pending-confirmation",
}

_HEADING_NAME_RE = re.compile(r"(?i)^(?:heading|标题)\D*(\d{1,2})(?:\D|$)")

_BASE_UNCHECKED: tuple[tuple[str, str], ...] = (
    ("page_furniture", "页眉、页脚、页码与版心内浮动元素未检查"),
    ("tables", "表格三线体等专用口径未检查:表内段落仅参与 L{n} 段号计数"),
    ("char_details", "字符间距、加粗、下划线等字符细节未检查"),
    ("style_depth", "样式继承链超过 4 层或 lang/font hint 类取值未核查"),
)


class OfficeAuditError(ValueError):
    """Refusal that names the boundary hit without echoing paths outside the root."""


class _Counter:
    """Aggregate repeated paragraph violations into one receipt-short issue."""

    def __init__(self, code: str) -> None:
        self.code = code
        self.count = 0
        self.samples: list[str] = []
        self.notes: list[str] = []

    def hit(self, locator: str, note: str | None = None) -> None:
        self.count += 1
        if len(self.samples) < 3:
            self.samples.append(locator)
        if note and note not in self.notes:
            self.notes.append(note)

    def issue(self, base: str) -> tuple[str, str, str]:
        head = f"共 {self.count} 段{base}"
        if self.notes:
            head += f"({'、'.join(self.notes[:2])})"
        if self.samples:
            head += f";首处 {self.samples[0]}"
        return (self.code, self.samples[0], head)


class _Issues:
    """Bounded issue list that keeps the receipt inside the schema cap."""

    def __init__(self) -> None:
        self._rows: list[dict[str, str]] = []
        self._full = False

    def add(self, code: str, locator: str, detail: str) -> None:
        if self._full:
            return
        row = {"code": code, "locator": locator, "detail": detail[:200]}
        if len(self._rows) >= 128:
            self._rows[127] = {
                "code": "issues_truncated",
                "locator": "document",
                "detail": "更多问题被 128 条上限截断",
            }
            self._full = True
            return
        self._rows.append(row)

    def add_counter(self, counter: _Counter, base: str) -> None:
        code, locator, detail = counter.issue(base)
        self.add(code, locator, detail)

    def rows(self) -> list[dict[str, str]]:
        return list(self._rows)


class _Unchecked:
    """Honesty ledger: every unverifiable aspect lands here, at most once."""

    def __init__(self) -> None:
        self._rows: list[tuple[str, str]] = list(_BASE_UNCHECKED)
        self._codes = {code for code, _row in self._rows}

    def add(self, code: str, detail: str) -> None:
        if code in self._codes or len(self._rows) >= MAX_UNCHECKED:
            return
        self._codes.add(code)
        self._rows.append((code, detail))

    def rows(self) -> list[dict[str, str]]:
        return [{"code": code, "detail": detail} for code, detail in self._rows]


def audit(args: dict) -> dict:
    """Contract entry point: bounded read-only document format audit."""

    root = workspace_files.root()
    compound = _compound(args)
    resolved = workspace_files.resolve(root, compound)
    if not resolved.is_file():
        raise OfficeAuditError("workspace path is not a file")
    if resolved.suffix.casefold() != ".docx":
        raise OfficeAuditError("格式体检只支持 .docx:旧二进制请先在 Word/WPS 另存为 .docx")
    mode = _mode(args)
    rules = _rules(mode)
    data = _read_bounded(root, compound)

    styles, run_defaults, para_defaults = _style_tables(data)
    body, sections, last_sect = _document(data)
    paragraphs = list(islice(_iter_paragraphs(body), MAX_PARAGRAPHS))
    total = sum(1 for _node in body.iter(f"{_W}p"))

    facts: list[dict[str, str]] = []
    issues = _Issues()
    unchecked = _Unchecked()
    _page_facts(last_sect, sections, facts)
    if sections > 1:
        issues.add(
            "section_multiple", "sect", f"正文包含 {sections} 个分节(sectPr);多节间版面差异(页眉/页码)未检查"
        )
    if sections == 0 and rules == "baseline":
        facts.append({"key": "page_size", "value": "(正文无 sectPr,页面几何不可得)", "source": "none"})
        issues.add(
            "sect_missing",
            "document",
            "正文没有 sectPr:页面与页边距基线不判定,如实记录不通过;仅 structural 事实照常输出",
        )
    if rules == "baseline" and sections > 0:
        _baseline_page_checks(last_sect, issues)
    _walk_checks(rules, paragraphs, styles, run_defaults, para_defaults, facts, issues, unchecked)
    if total > MAX_PARAGRAPHS:
        unchecked.add(
            "paragraph_tail",
            f"第 {MAX_PARAGRAPHS + 1}-{total} 段超过检查上限:{total - MAX_PARAGRAPHS} 段未检查",
        )
    if rules == "imported":
        unchecked.add("rule_table", "imported 口径不套 GB/T 9704 基线:facts 即该文件自身主流格式")
    return {
        "mode": mode,
        "path": compound,
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
        "sections": sections,
        "paragraphs_total": total,
        "paragraphs_checked": len(paragraphs),
        "truncated": total > MAX_PARAGRAPHS,
        "rule_set": dict(RULE_SET),
        "facts": facts[:MAX_FACTS],
        "issues": issues.rows(),
        "unchecked": unchecked.rows(),
        "trust": "untrusted_reference_data",
    }


# ---------------------------------------------------------------- entry helpers


def _compound(args: dict) -> str:
    project = args.get("project")
    path = args.get("path")
    if not isinstance(project, str) or not project.strip() or project != project.strip():
        raise OfficeAuditError("project is invalid")
    if not isinstance(path, str) or not path.strip() or path != path.strip():
        raise OfficeAuditError("workspace path is invalid")
    compound = f"{project}/{path}"
    if len(compound.encode("utf-8")) > workspace_files.MAX_PATH_BYTES:
        raise OfficeAuditError("workspace path exceeds the bound")
    return compound


def _mode(args: dict) -> str:
    mode = args.get("mode")
    if mode not in {"baseline", "imported", "retemplate"}:
        raise OfficeAuditError("mode 必须是 baseline、imported 或 retemplate")
    return str(mode)


def _rules(mode: str) -> str:
    return "baseline" if mode == "retemplate" else mode


def _read_bounded(root, relative: str) -> bytes:
    try:
        oversized = workspace_files.resolve(root, relative).stat().st_size > MAX_FILE_BYTES
    except OSError as exc:
        raise OfficeAuditError("workspace file is not available") from exc
    if oversized:
        raise OfficeAuditError("文件超过 20MB 体检上限:该文件被拒绝(明示拒收,不出替身)")
    with workspace_files.open_file(root, relative) as stream:
        data = stream.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES:
        raise OfficeAuditError("文件超过 20MB 体检上限:该文件被拒绝(明示拒收,不出替身)")
    return data


def _document(data: bytes) -> tuple[ET.Element, int, ET.Element | None]:
    try:
        package = zipfile.ZipFile(io.BytesIO(data))
        root = ET.fromstring(package.read("word/document.xml"))
        brief: ET.Element | None = None
        for node in root.iter(f"{_W}sectPr"):
            brief = node  # keep the last section: the body-end geometry
    except (zipfile.BadZipFile, KeyError, OSError) as exc:
        raise OfficeAuditError("docx 数据包损坏或缺少 word/document.xml") from exc
    except ET.ParseError as exc:
        raise OfficeAuditError("docx 正文 XML 无法解析") from exc
    sections = sum(1 for _node in root.iter(f"{_W}sectPr"))
    body = root.find(f"{_W}body")
    if body is None:
        raise OfficeAuditError("docx 正文缺失 w:body:拒绝判读")
    return body, sections, brief


def _style_tables(data: bytes) -> tuple[dict[str, dict[str, Any]], dict[str, Any], dict[str, Any]]:
    """Parse ``word/styles.xml`` into (styles, run defaults, paragraph defaults).

    Absent or unparsable styles are tolerated as empty tables: every lookup
    that needed them stays unknown and lands in ``unchecked`` instead.
    """

    run_defaults: dict[str, Any] = {}
    para_defaults: dict[str, Any] = {}
    styles: dict[str, dict[str, Any]] = {}
    try:
        package = zipfile.ZipFile(io.BytesIO(data))
        root = ET.fromstring(package.read("word/styles.xml"))
    except (zipfile.BadZipFile, KeyError, OSError, ET.ParseError):
        return styles, run_defaults, para_defaults
    defaults = root.find(f"{_W}docDefaults")
    if defaults is not None:
        r_default = defaults.find(f"{_W}rPrDefault/{_W}rPr")
        if r_default is not None:
            run_defaults |= _rpr_row(r_default)
        p_default = defaults.find(f"{_W}pPrDefault/{_W}pPr")
        if p_default is not None:
            para_defaults |= _ppr_row(p_default)
    for style in root.iter(f"{_W}style"):
        style_id = style.get(f"{_W}styleId") or ""
        if not style_id or style_id in styles:
            continue
        row: dict[str, Any] = {}
        based = style.find(f"{_W}basedOn")
        if based is not None and based.get(f"{_W}val"):
            row["based_on"] = str(based.get(f"{_W}val"))
        name = style.find(f"{_W}name")
        if name is not None and name.get(f"{_W}val"):
            row["name"] = str(name.get(f"{_W}val"))
        style_rpr = style.find(f"{_W}rPr")
        if style_rpr is not None:
            row |= _rpr_row(style_rpr)
        style_ppr = style.find(f"{_W}pPr")
        if style_ppr is not None:
            row |= _ppr_row(style_ppr)
        styles[style_id] = row
    return styles, run_defaults, para_defaults


def _rpr_row(node: ET.Element) -> dict[str, Any]:
    row: dict[str, Any] = {}
    fonts = node.find(f"{_W}rFonts")
    if fonts is not None:
        for attr in ("eastAsia", "ascii"):
            value = fonts.get(f"{_W}{attr}")
            if value:
                row["font"] = value
                break
    size = node.find(f"{_W}sz")
    if size is not None:
        raw = str(size.get(f"{_W}val") or "").strip()
        if raw.isdigit() and int(raw) > 0:
            row["size"] = int(raw) / 2
    return row


def _ppr_row(node: ET.Element) -> dict[str, Any]:
    row: dict[str, Any] = {}
    spacing = node.find(f"{_W}spacing")
    if spacing is not None:
        line = str(spacing.get(f"{_W}line") or "").strip()
        if line.isdigit() and int(line) > 0:
            row["line"] = int(line) / _TWIP_PER_PT
        rule = str(spacing.get(f"{_W}lineRule") or "").strip()
        if rule:
            row["line_rule"] = rule
    indent = node.find(f"{_W}ind")
    if indent is not None:
        chars = str(indent.get(f"{_W}firstLineChars") or "").strip()
        if chars.isdigit():
            row["first_line_chars"] = int(chars) / 100
        twips = str(indent.get(f"{_W}firstLine") or "").strip()
        if twips.isdigit() and int(twips) > 0:
            row["first_line"] = int(twips) / _TWIP_PER_PT
    justify = node.find(f"{_W}jc")
    if justify is not None and justify.get(f"{_W}val"):
        row["jc"] = str(justify.get(f"{_W}val"))
    outline = node.find(f"{_W}outlineLvl")
    if outline is not None:
        raw = str(outline.get(f"{_W}val") or "").strip()
        if raw.isdigit():
            row["outline"] = int(raw)
    return row


def _iter_paragraphs(body: ET.Element):
    """Every ``w:p`` at body scope in document order, with a table flag.

    The order matches ``office_ingest._docx_stream`` (``root.iter`` is also
    depth-first document order), so ``L{n}`` locators stay identical to what
    analyze and validate showed. Table paragraphs carry ``in_table=True`` and
    only participate in numbering, never in the rule checks.
    """

    def walk(node: ET.Element, in_table: bool):
        for child in node:
            if child.tag == f"{_W}p":
                yield child, in_table
            else:
                yield from walk(child, in_table or child.tag == f"{_W}tbl")

    yield from walk(body, False)


# ---------------------------------------------------------------- page geometry


def _page_facts(last_sect: ET.Element | None, sections: int, facts: list[dict[str, str]]) -> None:
    if last_sect is None:
        return
    pg = last_sect.find(f"{_W}pgSz")
    width = pg.get(f"{_W}w") if pg is not None else ""
    height = pg.get(f"{_W}h") if pg is not None else ""
    if width and height and width.isdigit() and height.isdigit():
        facts.append(
            {
                "key": "page_size",
                "value": f"{int(width) * _MM_PER_TWIP:.1f}x{int(height) * _MM_PER_TWIP:.1f}mm",
                "source": "sect",
            }
        )
    margins = last_sect.find(f"{_W}pgMar")
    for attr, key in (
        ("top", "margin_top"),
        ("bottom", "margin_bottom"),
        ("left", "margin_left"),
        ("right", "margin_right"),
    ):
        raw = margins.get(f"{_W}{attr}") if margins is not None else ""
        if raw and raw.isdigit():
            facts.append({"key": key, "value": f"{int(raw) * _MM_PER_TWIP:.1f}mm", "source": "sect"})
    facts.append({"key": "sections", "value": str(sections), "source": "sect"})


def _baseline_page_checks(last_sect: ET.Element, issues: _Issues) -> None:
    pg = last_sect.find(f"{_W}pgSz")
    width = pg.get(f"{_W}w") if pg is not None else ""
    height = pg.get(f"{_W}h") if pg is not None else ""
    if width and height and width.isdigit() and height.isdigit():
        w_mm, h_mm = int(width) * _MM_PER_TWIP, int(height) * _MM_PER_TWIP
        if abs(w_mm - PAGE_WIDTH_MM) > PAGE_TOLERANCE_MM or abs(h_mm - PAGE_HEIGHT_MM) > PAGE_TOLERANCE_MM:
            issues.add(
                "page_size_mismatch",
                "sect",
                f"页面 {w_mm:.1f}x{h_mm:.1f}mm 与 A4 相差超过 ±{PAGE_TOLERANCE_MM:.0f}mm",
            )
    margins = last_sect.find(f"{_W}pgMar")
    for attr, baseline, code, zh in (
        ("top", MARGIN_TOP_MM, "margin_top_mismatch", "上边距"),
        ("bottom", MARGIN_BOTTOM_MM, "margin_bottom_mismatch", "下边距"),
        ("left", MARGIN_LEFT_MM, "margin_left_mismatch", "左页边距"),
        ("right", MARGIN_RIGHT_MM, "margin_right_mismatch", "右页边距"),
    ):
        raw = margins.get(f"{_W}{attr}") if margins is not None else ""
        if not raw or not raw.isdigit():
            issues.add(code, "sect", f"正文末节 sectPr 缺 {zh} 值,基线 {baseline:.0f}mm 不判定")
            continue
        mm = int(raw) * _MM_PER_TWIP
        if abs(mm - baseline) > MARGIN_TOLERANCE_MM:
            issues.add(
                code,
                "sect",
                f"{zh} {mm:.1f}mm 与基线 {baseline:.0f}mm 相差超过 ±{MARGIN_TOLERANCE_MM:.0f}mm",
            )


# ---------------------------------------------------------------- paragraph walk


def _walk_checks(
    mode: str,
    paragraphs: list[tuple[ET.Element, bool]],
    styles: dict[str, dict[str, Any]],
    run_defaults: dict[str, Any],
    para_defaults: dict[str, Any],
    facts: list[dict[str, str]],
    issues: _Issues,
    unchecked: _Unchecked,
) -> None:
    body_font = _Counter("body_font_mismatch")
    body_size = _Counter("body_size_mismatch")
    line_band = _Counter("line_spacing_out_of_band")
    indent_band = _Counter("first_line_indent_mismatch")
    heading_font = {level: _Counter(f"heading{level}_font_mismatch") for level in (1, 2, 3)}
    unknown_heading_font = 0
    unknown_body_font = 0
    unknown_body_size = 0
    title_seen = False

    for number, (node, in_table) in enumerate(paragraphs, start=1):
        locator = f"L{number}"
        if in_table:
            continue
        if not "".join(part.text or "" for part in node.iter(f"{_W}t")).strip():
            continue
        props = _resolve(node, styles, run_defaults, para_defaults)
        level = _heading_level(props, styles)
        if not title_seen:
            title_seen = True
            facts.append({"key": "title_font", "value": _known(props, "font"), "source": "title"})
            facts.append({"key": "title_pt", "value": _pt_value(props, "size"), "source": "title"})
            if mode == "baseline":
                _title_checks(locator, props, issues, unchecked)
            continue
        if level:
            wanted = FONT_HEADING1 if level == 1 else FONT_HEADING2 if level == 2 else FONT_BODY
            font = props.get("font")
            if font is None:
                unknown_heading_font += 1
            elif not _font_matches(font, wanted):
                heading_font[min(level, 3)].hit(locator, f"现为 {font}")
            continue
        font = props.get("font")
        size = props.get("size")
        if font is None:
            unknown_body_font += 1
        elif not _font_matches(font, FONT_BODY):
            body_font.hit(locator, f"现为 {font}")
        if size is None:
            unknown_body_size += 1
        elif abs(size - BODY_PT) > 1e-9:
            body_size.hit(locator, f"现为 {size:.1f}pt")
        _line_check(locator, props, line_band, unchecked)
        _indent_check(locator, props, indent_band, unchecked)

    if unknown_heading_font:
        unchecked.add("heading_font_unknown", f"{unknown_heading_font} 个标题段样式链无字体,标题级字体未核")
    if unknown_body_font:
        unchecked.add("body_font_unknown", f"{unknown_body_font} 个正文段样式链无字体,该部分正文口径未判")
    if unknown_body_size:
        unchecked.add("body_size_unknown", f"{unknown_body_size} 个正文段样式链无字号,该部分正文口径未判")
    for level in (1, 2, 3):
        if heading_font[level].count:
            issues.add_counter(heading_font[level], f"标题级{level}字体不是 {FONT_LABEL[level]}")
    if body_font.count:
        issues.add_counter(body_font, "正文段字体不是仿宋")
    if body_size.count:
        issues.add_counter(body_size, "正文段字号不是 16pt(三号)")
    if line_band.count:
        issues.add_counter(line_band, f"行距不在 {LINE_BAND_PT[0]}-{LINE_BAND_PT[1]}pt 带")
    if indent_band.count:
        issues.add_counter(indent_band, "首行缩进不是 2 字")
    _majority_facts(paragraphs, styles, run_defaults, para_defaults, facts)
    if not title_seen:
        issues.add(
            "title_missing",
            "document",
            "检查范围内没有可见正文:标题不判定"
            if mode == "baseline"
            else "检查范围内没有可见正文,主流格式不判定",
        )
        unchecked.add("paragraph_tail_short", "文档开头即空段/全空,标题与正文口径未实战判定")


def _title_checks(
    locator: str, props: dict[str, Any], issues: _Issues, unchecked: _Unchecked
) -> None:
    font = props.get("font")
    size = props.get("size")
    if font is None:
        unchecked.add("title_font_unknown", "标题段样式链无 eastAsia 字体,小标宋基线未核;请核对样式表")
    elif not _font_matches(font, FONT_TITLE):
        issues.add("title_font_mismatch", locator, f"标题字体 {font} 不是小标宋(草案基线,确认后可替换)")
    if size is None:
        unchecked.add("title_size_unknown", "标题段样式链无字号,22pt 基线未核")
    elif abs(size - TITLE_PT) > 1e-9:
        issues.add("title_size_mismatch", locator, f"标题字号 {size:.1f}pt 不是 22pt")
    if props.get("jc") != "center":
        issues.add("title_not_centered", locator, f"标题对齐为 {props.get('jc') or '(继承)'},基线要求居中")


def _line_check(locator: str, props: dict[str, Any], counter: _Counter, unchecked: _Unchecked) -> None:
    line = props.get("line")
    if line is None:
        unchecked.add("line_unknown", "存在未显式设置行距的样式链,该部分行距未核")
        return
    if (props.get("line_rule") or "auto") == "auto":
        unchecked.add("line_auto", "存在按倍数(w:lineRule=auto)的行距,该部分行距未核")
        return
    if not LINE_BAND_PT[0] <= line <= LINE_BAND_PT[1]:
        counter.hit(locator, f"现为 {line:.1f}pt")


def _indent_check(locator: str, props: dict[str, Any], counter: _Counter, unchecked: _Unchecked) -> None:
    chars = props.get("first_line_chars")
    if chars is None:
        twips, size = props.get("first_line"), props.get("size")
        if twips is None or size is None:
            unchecked.add("indent_unknown", "存在样式链无首行缩进且字号不可得的段落,缩进未核")
            return
        chars = twips / size
    if abs(chars - INDENT_CHARS) > INDENT_TOLERANCE:
        counter.hit(locator, f"现为 {chars:.2f} 字")


def _majority_facts(
    paragraphs: list[tuple[ET.Element, bool]],
    styles: dict[str, dict[str, Any]],
    run_defaults: dict[str, Any],
    para_defaults: dict[str, Any],
    facts: list[dict[str, str]],
) -> None:
    if run_defaults.get("font"):
        facts.append({"key": "default_font", "value": run_defaults["font"], "source": "doc_defaults"})
    if run_defaults.get("size"):
        facts.append(
            {"key": "default_pt", "value": f"{run_defaults['size']:.1f}pt", "source": "doc_defaults"}
        )
    fonts: list[str] = []
    sizes: list[float] = []
    lines: list[float] = []
    indents: list[float] = []
    title_seen = False
    for node, in_table in paragraphs[:1_000]:
        if in_table:
            continue
        if not "".join(part.text or "" for part in node.iter(f"{_W}t")).strip():
            continue
        props = _resolve(node, styles, run_defaults, para_defaults)
        if _heading_level(props, styles):
            continue
        if not title_seen:
            title_seen = True
            continue  # 标题段不进主流口径的投票池
        if isinstance(props.get("font"), str) and props["font"]:
            fonts.append(props["font"])
        if isinstance(props.get("size"), (int, float)):
            sizes.append(props["size"])
        if props.get("line") is not None and (props.get("line_rule") or "auto") != "auto":
            lines.append(props["line"])
        if props.get("first_line_chars") is not None:
            indents.append(props["first_line_chars"])
    for key, values, fmt in (
        ("body_font", fonts, lambda value: value),
        ("body_pt", sizes, lambda value: f"{value:.1f}pt"),
        ("line_pt", lines, lambda value: f"{value:.1f}pt"),
        ("indent_chars", indents, lambda value: f"{value:.2f}字"),
    ):
        if values:
            facts.append({"key": key, "value": fmt(Counter(values).most_common(1)[0][0]), "source": "modal"})


# ---------------------------------------------------------------- style resolution


def _resolve(
    paragraph: ET.Element,
    styles: dict[str, dict[str, Any]],
    run_defaults: dict[str, Any],
    para_defaults: dict[str, Any],
) -> dict[str, Any]:
    """Effective properties for one paragraph under the bounded style chain.

    Precedence: direct paragraph pPr → paragraph-mark rPr → first formatted
    run → pStyle chain (at most 4 hops, nearest wins) → docDefaults. Missing
    values stay absent; the caller treats them as unknown and records honesty
    items instead of guessing.
    """

    props: dict[str, Any] = {}
    pstyle = ""
    ppr = paragraph.find(f"{_W}pPr")
    if ppr is not None:
        props |= _ppr_row(ppr)
        para_rpr = ppr.find(f"{_W}rPr")
        if para_rpr is not None:
            props |= _rpr_row(para_rpr)
        style_ref = ppr.find(f"{_W}pStyle")
        if style_ref is not None:
            pstyle = str(style_ref.get(f"{_W}val") or "")
    if "font" not in props or "size" not in props:
        for run in paragraph.iter(f"{_W}r"):
            rpr = run.find(f"{_W}rPr")
            if rpr is None:
                continue
            run_row = _rpr_row(rpr)
            if "font" in run_row and "font" not in props:
                props["font"] = run_row["font"]
            if "size" in run_row and "size" not in props:
                props["size"] = run_row["size"]
            if "font" in props and "size" in props:
                break
    if pstyle:
        props["pstyle"] = pstyle
    for source in _style_chain(pstyle, styles):
        for key in ("font", "size", "line", "line_rule", "first_line_chars", "first_line", "jc", "outline"):
            if key in source and key not in props:
                props[key] = source[key]
    for source in (para_defaults, run_defaults):
        for key in ("font", "size", "line", "line_rule", "first_line_chars", "first_line", "jc"):
            if key in source and key not in props:
                props[key] = source[key]
    return props


def _style_chain(pstyle: str, styles: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    chain: list[dict[str, Any]] = []
    current = pstyle
    for _hop in range(4):
        row = styles.get(current)
        if row is None:
            return chain
        chain.append(row)
        current = row.get("based_on") or ""
        if not current:
            return chain
    return chain


def _heading_level(props: dict[str, Any], styles: dict[str, dict[str, Any]]) -> int:
    outline = props.get("outline")
    if isinstance(outline, int) and 0 <= outline <= 5:
        return outline + 1
    pstyle = str(props.get("pstyle") or "")
    row = styles.get(pstyle) or {}
    level = row.get("outline")
    if isinstance(level, int) and 0 <= level <= 5:
        return level + 1
    name = str(row.get("name") or "")
    heading = _HEADING_NAME_RE.match(pstyle) or _HEADING_NAME_RE.match(name)
    if heading and 1 <= int(heading.group(1)) <= 9:
        return int(heading.group(1))
    if pstyle.isdigit() and 1 <= int(pstyle) <= 9:
        return int(pstyle)
    return 0


def _font_matches(font: object, wanted: tuple[str, ...]) -> bool:
    if not isinstance(font, str):
        return False
    haystack = font.replace(" ", "").casefold()
    return any(word in haystack for word in wanted)


def _known(props: dict[str, Any], key: str) -> str:
    value = props.get(key)
    return value if isinstance(value, str) and value.strip() else "(样式链未命名字体)"


def _pt_value(props: dict[str, Any], key: str) -> str:
    value = props.get(key)
    if isinstance(value, (int, float)):
        return f"{value:.1f}pt"
    return "(样式链未命名字号)"
