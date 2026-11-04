"""Read-only comparison for the WPS-suite porting (P3).

WPS-SUITE-PORTING L2 / §4.10 and MeWork §3.3: sources are never modified.
Line mode is the default. ``granularity=word`` reports the five states
equal / changed / removed / added / moved. An optional ``output_path``
writes a ``.comp.json`` artifact beside those sources.

- .txt/.md lines, .docx paragraphs, .pdf pages, .xlsx rows, or .doc text;
- ``ocr_mode=on`` is the only path that OCRs an empty PDF text layer;
- 4000 units per side is a refusal boundary, not a stand-in: longer inputs
  name the cap and stop;
- the receipt carries exact added/removed/moved counts and at most 40 hunk
  samples with an explicit ``truncated`` flag, 200 characters per line;
- mixed kinds, unsupported kinds, non-UTF-8 text and corrupt packages fail
  closed; no conversion and no upload.
"""
from __future__ import annotations

import difflib
import hashlib
import io
import json
import re
import xml.etree.ElementTree as ET
from collections import Counter
from typing import Any

from company_agent import office_binary, office_ocr, workspace_files
from company_agent import office_create as _oc
from company_agent import office_ingest as _ingest

MAX_COMPARE_UNITS = 4_000
MAX_HUNKS = 40
MAX_PER_HUNK_LINES = 8
MAX_SHOWN_CHARS = 200
MAX_FILE_BYTES = _ingest.MAX_FILE_BYTES

_KINDS = {
    ".txt": "text",
    ".md": "text",
    ".docx": "docx",
    ".pdf": "pdf",
    ".xlsx": "xlsx",
    ".doc": "doc",
}
_SAME_KIND = "两侧必须同为 text、docx、pdf、xlsx 或 doc"

_CL_MARKER = "…[截]"


class OfficeCompareError(ValueError):
    """Refusal that names the boundary hit without echoing paths outside the root."""


def compare(args: dict) -> dict:
    """Contract entry point: bounded read-only comparison of two files."""

    root = workspace_files.root()
    compound_a = _compound(args, "file_a")
    compound_b = _compound(args, "file_b")
    granularity = _granularity(args)
    ocr_mode = _ocr_mode(args)
    kind_a, data_a = _load(root, compound_a)
    kind_b, data_b = _load(root, compound_b)
    if kind_a != kind_b:
        raise OfficeCompareError(
            f"混合类型比对未接入:A 是 {kind_a}、B 是 {kind_b};{_SAME_KIND}"
        )
    units_a = _units(kind_a, data_a, compound_a, ocr_mode)
    units_b = _units(kind_b, data_b, compound_b, ocr_mode)
    if granularity == "word":
        units_a = _words(units_a, compound_a)
        units_b = _words(units_b, compound_b)
    added, removed, moved, hunks, truncated, equal = _diff(units_a, units_b)
    payload = {
        "kind": kind_a,
        "file_a": compound_a,
        "file_b": compound_b,
        "sha256_a": hashlib.sha256(data_a).hexdigest(),
        "sha256_b": hashlib.sha256(data_b).hexdigest(),
        "identical": added == 0 and removed == 0 and moved == 0 and not truncated,
        "added": added,
        "removed": removed,
        "moved": moved,
        "granularity": granularity,
        "hunks": hunks,
        "truncated": truncated,
        "trust": "untrusted_reference_data",
    }
    output = args.get("output_path")
    if output is not None:
        project = compound_a.split("/", 1)[0]
        compound_out = _output_compound(project, output)
        if compound_out in {compound_a, compound_b}:
            raise OfficeCompareError("output_path 不得覆盖比对原文")
        document = {
            "schemaVersion": 1,
            "granularity": granularity,
            "file_a": compound_a,
            "file_b": compound_b,
            "identical": payload["identical"],
            "added": added,
            "removed": removed,
            "moved": moved,
            "equal": equal,
            "hunks": hunks,
        }
        raw = (json.dumps(document, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
        existed, target = _oc._resolve_target(root, compound_out, True)
        _oc._write_atomic(target, raw, existed)
        _oc._verify_written(target, raw)
        payload["comp_path"] = compound_out
    return payload


def _granularity(args: dict) -> str:
    value = args.get("granularity", "line")
    if value not in {"line", "word"}:
        raise OfficeCompareError("granularity 只接受 line 或 word")
    return value


def _ocr_mode(args: dict) -> str:
    value = args.get("ocr_mode", "off")
    if value not in {"off", "on"}:
        raise OfficeCompareError("ocr_mode 只接受 off 或 on")
    return value


def _words(lines: list[str], compound: str) -> list[str]:
    tokens: list[str] = []
    for line in lines:
        tokens.extend(re.findall(r"[\u4e00-\u9fff]+|[A-Za-z0-9_]+|[^\s]", line))
    if len(tokens) > MAX_COMPARE_UNITS:
        raise OfficeCompareError(
            f"{compound} 的词数超过 {MAX_COMPARE_UNITS} 上限:明确拒绝,不比对替身"
        )
    return tokens


def _diff(
    units_a: list[str], units_b: list[str]
) -> tuple[int, int, int, list[dict[str, Any]], bool, int]:
    matcher = difflib.SequenceMatcher(None, units_a, units_b, autojunk=False)
    opcodes = matcher.get_opcodes()
    deleted = [
        text
        for tag, i1, i2, _j1, _j2 in opcodes
        if tag in {"delete", "replace"}
        for text in units_a[i1:i2]
    ]
    inserted = [
        text
        for tag, _i1, _i2, j1, j2 in opcodes
        if tag in {"insert", "replace"}
        for text in units_b[j1:j2]
    ]
    del_counts = Counter(deleted)
    ins_counts = Counter(inserted)
    movable = {
        text
        for text, count in del_counts.items()
        if text and count == 1 and ins_counts.get(text) == 1
    }
    added = len(inserted) - len(movable)
    removed = len(deleted) - len(movable)
    equal = sum(i2 - i1 for tag, i1, i2, _j1, _j2 in opcodes if tag == "equal")
    hunks: list[dict[str, Any]] = []
    truncated = False
    for tag, i1, i2, j1, j2 in opcodes:
        if tag == "equal":
            continue
        if len(hunks) >= MAX_HUNKS:
            truncated = True
            break
        before = units_a[i1:i2]
        after = units_b[j1:j2]
        kind = {"replace": "changed", "insert": "added", "delete": "removed"}[tag]
        if before and after and Counter(before) == Counter(after) and all(text in movable for text in before):
            kind = "moved"
        hunks.append(
            {
                "index": len(hunks) + 1,
                "kind": kind,
                "at_a": (i1 + 1) if i2 > i1 else 0,
                "at_b": (j1 + 1) if j2 > j1 else 0,
                "before": [_clip(text) for text in before[:MAX_PER_HUNK_LINES]],
                "after": [_clip(text) for text in after[:MAX_PER_HUNK_LINES]],
            }
        )
    return added, removed, len(movable), hunks[:MAX_HUNKS], truncated, equal


def _output_compound(project: str, output: object) -> str:
    if not isinstance(output, str) or not output.strip() or output != output.strip():
        raise OfficeCompareError("output_path 必须是以 .comp.json 结尾的相对路径")
    if not output.endswith(".comp.json") or output.startswith(("/", "\\")):
        raise OfficeCompareError("output_path 必须是以 .comp.json 结尾的相对路径")
    compound = f"{project}/{output}"
    if len(compound.encode("utf-8")) > workspace_files.MAX_PATH_BYTES:
        raise OfficeCompareError("output_path exceeds the workspace path bound")
    try:
        workspace_files._lexical(compound)
    except workspace_files.WorkspaceFileError as exc:
        raise OfficeCompareError(str(exc)) from exc
    return compound


def _clip(text: str, limit: int = MAX_SHOWN_CHARS) -> str:
    if len(text) <= limit:
        return text
    keep = limit - len(_CL_MARKER)
    return text[:keep] + _CL_MARKER


def _compound(args: dict, key: str) -> str:
    project = args.get("project")
    path = args.get(key)
    if not isinstance(project, str) or not project.strip() or project != project.strip():
        raise OfficeCompareError("project is invalid")
    if not isinstance(path, str) or not path.strip() or path != path.strip():
        raise OfficeCompareError(f"{key} is invalid")
    compound = f"{project}/{path}"
    if len(compound.encode("utf-8")) > workspace_files.MAX_PATH_BYTES:
        raise OfficeCompareError(f"{key} exceeds the workspace path bound")
    return compound


def _load(root, compound: str) -> tuple[str, bytes]:
    try:
        resolved = workspace_files.resolve(root, compound)
    except workspace_files.WorkspaceFileError as exc:
        raise OfficeCompareError(str(exc)) from exc
    if not resolved.is_file():
        raise OfficeCompareError("workspace path is not a file")
    kind = _KINDS.get(resolved.suffix.casefold())
    if kind is None:
        raise OfficeCompareError(
            f"{resolved.suffix.casefold() or '(无后缀)'} 是不支持的比对类型;"
            "仅支持 .txt/.md、.docx、.pdf、.xlsx 或 .doc"
        )
    try:
        oversized = resolved.stat().st_size > MAX_FILE_BYTES
    except OSError as exc:
        raise OfficeCompareError("workspace file is not available") from exc
    if oversized:
        raise OfficeCompareError("文件超过 20MB 比对上限:明确拒绝,不出替身")
    with workspace_files.open_file(root, compound) as stream:
        data = stream.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES:
        raise OfficeCompareError("文件超过 20MB 比对上限:明确拒绝,不出替身")
    return kind, data


def _units(kind: str, data: bytes, compound: str, ocr_mode: str) -> list[str]:
    if kind == "docx":
        try:
            units = [text for _, text in _ingest._docx_stream(data)]
        except _ingest.OfficeIngestError as exc:
            raise OfficeCompareError(str(exc)) from exc
    elif kind == "pdf":
        units = _pdf_units(data, ocr_mode)
    elif kind == "xlsx":
        units = _xlsx_units(data)
    elif kind == "doc":
        units = _doc_units(data)
    else:
        try:
            text = data.decode("utf-8")
        except UnicodeError as exc:
            raise OfficeCompareError("文件不是 UTF-8 文本(可能为旧编码或二进制):明确拒绝") from exc
        units = text.splitlines()
    if len(units) > MAX_COMPARE_UNITS:
        raise OfficeCompareError(
            f"{compound} 的比对单元数超过 {MAX_COMPARE_UNITS} 行上限:明确拒绝,不比对替身"
        )
    return units


def _pdf_units(data: bytes, ocr_mode: str) -> list[str]:
    try:
        from pypdf import PdfReader  # noqa: PLC0415 -- optional text layer
    except ImportError as exc:
        raise OfficeCompareError("pdf 文本层引擎(pypdf)未安装:明确拒绝") from exc
    try:
        reader = PdfReader(io.BytesIO(data))
        texts = [page.extract_text() or "" for page in reader.pages]
    except Exception as exc:  # noqa: BLE001 -- parser failures stay a refusal
        raise OfficeCompareError("pdf 已加密或损坏,文本层不可用") from exc
    if not any(text.strip() for text in texts):
        if ocr_mode != "on":
            raise OfficeCompareError("pdf 文本层为空且 ocr_mode=off:拒绝,不出替身")
        try:
            texts = office_ocr.read_pdf_pages(data)
        except office_ocr.OfficeOcrError as exc:
            raise OfficeCompareError(str(exc)) from exc
    units: list[str] = []
    for text in texts:
        units.extend(text.splitlines() or [text])
    return units


def _xlsx_units(data: bytes) -> list[str]:
    try:
        package, shared, entries = _ingest._xlsx_book(data)
    except _ingest.OfficeIngestError as exc:
        raise OfficeCompareError(str(exc)) from exc
    lines: list[str] = []
    try:
        for _count, name, target in entries:
            if not target:
                lines.append(f"{name}\t[未能定位该工作表的数据实体]")
                continue
            clean = target.lstrip("/")
            if not clean.startswith("xl/"):
                clean = "xl/" + clean
            root = ET.fromstring(package.read(clean))
            for row in root.iter(f"{_ingest._MAIN_NS}row"):
                values = [
                    _ingest._xlsx_cell_value(cell, shared)
                    for cell in row.iter(f"{_ingest._MAIN_NS}c")
                ]
                lines.append(name + "\t" + "\t".join(values))
    except (KeyError, ET.ParseError) as exc:
        raise OfficeCompareError("xlsx 工作表数据无法读取") from exc
    finally:
        package.close()
    return lines


def _doc_units(data: bytes) -> list[str]:
    try:
        parsed = office_binary.read_doc(data)
    except office_binary.OfficeBinaryError as exc:
        raise OfficeCompareError(str(exc)) from exc
    return str(parsed["text"]).splitlines()
