"""Evidence-anchor validation gate for the WPS-suite porting (P4).

WPS-SUITE-PORTING §3.5/§4.8: ``validateFileReferences`` re-reads the files
and answers PASSED/FAILED/INCOMPLETE deterministically. The gate is what
makes "the draft is anchored" a checkable fact:

- every reference needs a workspace file, a locator (``L`` paragraph/line,
  ``P`` pdf page, ``S sheet!A1`` cell) and the quote; the quote comparison
  runs on a pinned normalization (NFKC, lower, whitespace stripped);
- missing or mismatched fingerprints, missing files, unparsable locators,
  out-of-range locators and quote mismatches are FAILED;
- locators the bounded parsers do not implement (ranges such as S!A1:B2 and
  L ranges on structured kinds, non-text kinds) and empty quotes are
  INCOMPLETE — never a guess;
- PASSED only when every reference resolves;
- docx paragraph anchors follow ``company_office_analyze`` numbering and pdf
  page anchors follow the same text-layer engine (both from the P1 ingest
  module), so validate never drifts from what the model was shown.
"""
from __future__ import annotations

import io
import re
import unicodedata
import zipfile
import xml.etree.ElementTree as ET

from company_agent import office_ingest as _ingest
from company_agent import workspace_files

_W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_MAIN_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"

MAX_REFERENCES = 128
MAX_SOURCES = 128
MAX_FILE_BYTES = _ingest.MAX_FILE_BYTES

_L_RE = re.compile(r"^L([0-9]{1,9})(?:-L([0-9]{1,9}))?$")
_P_RE = re.compile(r"^P([0-9]{1,6})$")
_S_RE = re.compile(r"^S(.{1,64})!([A-Za-z]{1,3})([0-9]{1,7})$")

STATUS_PASSED = "PASSED"


class OfficeValidateError(ValueError):
    """Refusal that names the boundary hit without hinting at external paths."""


def validate(args: dict) -> dict:
    """Contract entry point: bounded evidence-anchor gate for one project."""

    root = workspace_files.root()
    project = args.get("project")
    if not isinstance(project, str) or not project.strip() or project != project.strip():
        raise OfficeValidateError("project is invalid")
    refs = args.get("references")
    if not isinstance(refs, list) or not refs or len(refs) > MAX_REFERENCES:
        raise OfficeValidateError(f"references 必须是 1..{MAX_REFERENCES} 条的数组")
    sources = args.get("sources", [])
    if sources is None:
        sources = []
    if not isinstance(sources, list) or len(sources) > MAX_SOURCES:
        raise OfficeValidateError(f"sources 必须是 <= {MAX_SOURCES} 条的数组")
    fingerprints = _fingerprint_map(project, sources)

    issues: list[dict[str, str]] = []
    passed = failed = incomplete = 0
    for number, row in enumerate(refs, start=1):
        try:
            if not isinstance(row, dict):
                raise _Issue("unknown", "reference 未提供对象")
            ref_id = _text(row.get("id"), "id", 64)
            compound = f"{project}/{_path(row.get('path'))}"
            code, detail, state = _check(
                root, compound, str(row.get("line_ref") or ""), row.get("quote"),
                fingerprints.get(compound),
            )
        except _Issue as issue:
            fallback = (
                row.get("id")
                if isinstance(row, dict) and isinstance(row.get("id"), str) and row.get("id").strip()
                else str(number)
            )
            ref_id = issue.ref_id or str(fallback)[:64]
            code, detail, state = (issue.code, issue.detail, issue.state or "failed")
        if state == "failed":
            failed += 1
        elif state == "incomplete":
            incomplete += 1
        else:
            passed += 1
        if state != "passed":
            issues.append({"id": ref_id, "code": code, "detail": detail[:200]})
    status = (
        STATUS_PASSED
        if failed == 0 and incomplete == 0
        else ("FAILED" if failed else "INCOMPLETE")
    )
    return {
        "status": status,
        "total": len(refs),
        "passed": passed,
        "failed": failed,
        "incomplete": incomplete,
        "issues": issues,
        "trust": "untrusted_reference_data",
    }


class _Issue(ValueError):
    """Internal control flow: one per-reference verdict with named code."""

    def __init__(self, code: str, detail: str, *, state: str = "failed", ref_id: str = "") -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.state = state
        self.ref_id = ref_id


def _check(
    root, compound: str, line_ref: str, quote: object, expected_sha: str | None,
) -> tuple[str, str, str]:
    if not line_ref or not isinstance(line_ref, str) or len(line_ref) > 64:
        return ("locator_unparsable", "line_ref 缺失或超过 64 字符", "failed")
    if quote is None or (isinstance(quote, str) and not quote.strip()):
        return ("quote_empty", "quote 为空:如实记 INCOMPLETE,不算通过", "incomplete")
    if not isinstance(quote, str) or len(quote) > 4000:
        return ("locator_unparsable", "quote 必须是 <=4000 字符的字符串", "failed")
    normalized_quote = _norm(quote)
    try:
        resolved = workspace_files.resolve(root, compound)
        if not resolved.is_file():
            return ("file_missing", "被引用文件不存在", "failed")
    except (workspace_files.WorkspaceFileError, OSError) as exc:
        return ("file_missing", str(exc)[:190], "failed")
    if expected_sha is None:
        return ("fingerprint_missing", "来源指纹缺失:FAILED(不凭记忆放行)", "failed")
    try:
        fingerprint = workspace_files.fingerprint(root, compound)
    except (workspace_files.WorkspaceFileError, OSError) as exc:
        return ("file_missing", str(exc)[:190], "failed")
    if fingerprint["sha256"] != expected_sha:
        return ("fingerprint_mismatch", "内容指纹与登记不一致:FAILED", "failed")
    try:
        data = _read_bounded(root, compound)
    except (workspace_files.WorkspaceFileError, OSError) as exc:
        return ("file_missing", str(exc)[:190], "failed")

    suffix = resolved.suffix.casefold()
    parse = _S_RE.match(line_ref)
    if parse is not None:
        if suffix != ".xlsx":
            return ("kind_unsupported", f"{suffix} 不支持 S! 定位:如实 INCOMPLETE", "incomplete")
        if ":" in line_ref.split("!", 1)[1]:
            return ("locator_unsupported", "范围定位(S!A1:B2)未接入:如实 INCOMPLETE", "incomplete")
        return _xlsx_cell(data, parse.group(1).strip(), parse.group(2) + parse.group(3), normalized_quote)
    page = _P_RE.match(line_ref)
    if page is not None:
        if suffix != ".pdf":
            return ("kind_unsupported", f"{suffix} 不支持 P 定位:如实 INCOMPLETE", "incomplete")
        return _pdf_quote(data, int(page.group(1)), normalized_quote)
    lin = _L_RE.match(line_ref)
    if lin is None:
        return ("locator_unparsable", "line_ref 形态不在 L/P/S 支持面内", "failed")
    first = int(lin.group(1))
    last = int(lin.group(2)) if lin.group(2) else first
    if last < first:
        return ("locator_unparsable", "L 区间上下界倒置", "failed")
    if lin.group(2) and suffix in {".docx", ".txt", ".md"}:
        return _range_quote(data, suffix, first, last, normalized_quote)
    if lin.group(2):
        return ("locator_unsupported", f"{suffix} 的 L 区间未接入:如实 INCOMPLETE", "incomplete")
    return _single_unit(data, suffix, first, normalized_quote)


def _single_unit(data: bytes, suffix: str, number: int, quote: str) -> tuple[str, str, str]:
    units: list[str]
    if suffix == ".docx":
        try:
            stream = list(_ingest._docx_stream(data))
        except _ingest.OfficeIngestError as exc:
            return ("file_unreadable", str(exc)[:190], "failed")
        units = [text for _count, text in stream]
    elif suffix in {".txt", ".md"}:
        try:
            text = data.decode("utf-8")
        except UnicodeError as exc:
            return ("file_unreadable", "文件不是 UTF-8 文本,拒绝判读", "failed")
        units = text.splitlines()
    elif suffix == ".pdf":
        return ("locator_unsupported", "pdf 页锚请使用 P{n}:如实 INCOMPLETE", "incomplete")
    else:
        return ("kind_unsupported", f"{suffix} 不支持 L 定位:如实 INCOMPLETE", "incomplete")
    if number < 1 or number > len(units):
        return ("locator_out_of_range", f"L{number} 超出 {len(units)} 单元上限", "failed")
    if quote not in _norm(units[number - 1]):
        return ("quote_mismatch", "L 锚点处的可见文本与引文不符", "failed")
    return ("", "", "passed")


def _range_quote(
    data: bytes, suffix: str, first: int, last: int, quote: str
) -> tuple[str, str, str]:
    if suffix == ".docx":
        try:
            stream = list(_ingest._docx_stream(data))
        except _ingest.OfficeIngestError as exc:
            return ("file_unreadable", str(exc)[:190], "failed")
        units = [text for _count, text in stream]
    else:
        try:
            units = data.decode("utf-8").splitlines()
        except UnicodeError:
            return ("file_unreadable", "文件不是 UTF-8 文本,拒绝判读", "failed")
    if last > len(units) or first < 1:
        return ("locator_out_of_range", f"L{first}-L{last} 超出 {len(units)} 单元上限", "failed")
    haystack = _norm("".join(units[first - 1 : last]))
    if quote not in haystack:
        return ("quote_mismatch", "L 区间内未找到引文", "failed")
    return ("", "", "passed")


def _pdf_quote(data: bytes, number: int, quote: str) -> tuple[str, str, str]:
    try:
        from pypdf import PdfReader  # noqa: PLC0415 -- optional text layer engine
    except ImportError as exc:
        raise OfficeValidateError(
            "pdf 文本层引擎(pypdf)未安装:如实验收需先配置环境"
        ) from exc
    try:
        reader = PdfReader(io.BytesIO(data))
    except Exception as exc:  # noqa: BLE001 -- third-party parser surface varies
        return ("file_unreadable", "pdf 已加密或损坏,文本层不可用", "failed")
    total = len(reader.pages)
    if number < 1 or number > total:
        return ("locator_out_of_range", f"P{number} 超出 {total} 页上限", "failed")
    try:
        page_text = reader.pages[number - 1].extract_text() or ""
    except Exception:  # noqa: BLE001 -- report honestly
        page_text = ""
    if quote not in _norm(page_text):
        return ("quote_mismatch", "P 锚点页的文本层与引文不符", "failed")
    return ("", "", "passed")


def _xlsx_cell(data: bytes, sheet: str, address: str, quote: str) -> tuple[str, str, str]:
    try:
        package, _shared, entries = _ingest._xlsx_book(data)
    except (_ingest.OfficeIngestError, ET.ParseError, zipfile.BadZipFile):
        return ("file_unreadable", "xlsx 数据包损坏或缺实体,拒绝判读", "failed")
    try:
        raw_target = next(path for _count, name, path in entries if name == sheet)
    except StopIteration:
        return ("locator_out_of_range", f"工作表 {sheet[:32]!r} 不存在", "failed")
    clean = raw_target.lstrip("/")
    if not clean.startswith("xl/"):
        clean = "xl/" + clean
    try:
        xml_root = ET.fromstring(package.read(clean))
    except (KeyError, ET.ParseError):
        return ("file_unreadable", "工作表定义无法解析", "failed")
    match = re.fullmatch(r"([A-Za-z]{1,3})([0-9]{1,7})", address or "")
    if match is None:
        return ("locator_unparsable", "单元格地址无法解析", "failed")
    col = _column_index(match.group(1).upper())
    row_number = int(match.group(2))
    if col < 1 or col > 16384:
        return ("locator_unparsable", "列地址超出 A1 记法上限", "failed")
    for position, row in enumerate(xml_root.iter(f"{_MAIN_NS}row"), start=1):
        attr = row.get("r") or ""
        row_number_seen = int(attr) if attr.isascii() and attr.isdigit() else position
        if row_number_seen != row_number:
            continue
        col_cursor = 0
        for cell in row:
            reference = cell.get("r") or ""
            if reference:
                prefix = re.match(r"([A-Za-z]+)", reference)
                col_cursor = (
                    _column_index(prefix.group(1).upper()) if prefix else col_cursor + 1
                )
            else:
                col_cursor += 1
            if col_cursor == col:
                value = _ingest._xlsx_cell_value(cell, _shared)
                if quote in _norm(str(value)):
                    return ("", "", "passed")
                return ("quote_mismatch", "S! 单元格内容与引文不符", "failed")
    return ("quote_mismatch", "S! 单元格不存在或为空", "failed")


def _column_index(letters: str) -> int:
    number = 0
    for ch in letters:
        number = number * 26 + (ord(ch) - ord("A") + 1)
    return number


def _fingerprint_map(project: str, sources: list) -> dict[str, str]:
    fingerprints: dict[str, str] = {}
    for row in sources:
        if not isinstance(row, dict):
            raise OfficeValidateError("sources 条目必须是对象")
        compound = f"{project}/{_path(row.get('path'))}"
        sha = str(row.get("sha256") or "")
        if not re.fullmatch(r"[0-9a-f]{64}", sha):
            raise OfficeValidateError(f"sources 条目 {compound[:32]} 的指纹不是 64 位小写 hex")
        fingerprints[compound] = sha
    return fingerprints


def _text(value: object, label: str, limit: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise _Issue("locator_unparsable", f"{label} 必须是 1..{limit} 字符", ref_id=str(value)[:32])
    return value


def _path(value: object) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise _Issue("locator_unparsable", "path 无效")
    if "\\" in value or value.startswith("/") or ".." in value.split("/"):
        raise _Issue("locator_unparsable", "path 含绝对或逃逸形态,拒绝")
    compound = value
    if len(compound.encode("utf-8")) > workspace_files.MAX_PATH_BYTES:
        raise _Issue("locator_unparsable", "path 超出工作区路径上限")
    return compound


def _norm(text: str) -> str:
    folded = unicodedata.normalize("NFKC", text).casefold()
    return re.sub(r"\s+", "", folded)


def _read_bounded(root, relative: str) -> bytes:
    oversized = workspace_files.resolve(root, relative).stat().st_size > MAX_FILE_BYTES
    if oversized:
        raise _Issue("kind_unsupported", "文件超过 20MB 验收上限", state="failed")
    with workspace_files.open_file(root, relative) as stream:
        data = stream.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES:
        raise _Issue("kind_unsupported", "文件超过 20MB 验收上限", state="failed")
    return data
