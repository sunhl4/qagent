"""Read-only line-level comparison for the WPS-suite porting (P3).

WPS-SUITE-PORTING L2 / §4.10: ``compare_documents`` must never change a
document; it answers "what differs" over the same units a human sees:

- .txt/.md lines or .docx visible paragraphs (the ``company_office_analyze``
  L{n} anchors, byte-identical enumeration via the ingestion module);
- 4000 units per side is a refusal boundary, not a stand-in: longer inputs
  name the cap and stop;
- the receipt carries exact added/removed counts and at most 40 hunk
  samples with an explicit ``truncated`` flag, 200 characters per line;
- mixed kinds, unsupported kinds, non-UTF-8 text and corrupt packages fail
  closed; no conversion, no OCR, no external calls.
"""
from __future__ import annotations

import difflib
import hashlib
from typing import Any

from company_agent import office_ingest as _ingest
from company_agent import workspace_files

MAX_COMPARE_UNITS = 4_000
MAX_HUNKS = 40
MAX_PER_HUNK_LINES = 8
MAX_SHOWN_CHARS = 200
MAX_FILE_BYTES = _ingest.MAX_FILE_BYTES

_KINDS = {".txt": "text", ".md": "text", ".docx": "docx"}

_CL_MARKER = "…[截]"


class OfficeCompareError(ValueError):
    """Refusal that names the boundary hit without echoing paths outside the root."""


def compare(args: dict) -> dict:
    """Contract entry point: bounded read-only comparison of two files."""

    root = workspace_files.root()
    compound_a = _compound(args, "file_a")
    compound_b = _compound(args, "file_b")
    kind_a, data_a = _load(root, compound_a)
    kind_b, data_b = _load(root, compound_b)
    if kind_a != kind_b:
        raise OfficeCompareError(
            f"混合类型比对未接入:A 是 {kind_a}、B 是 {kind_b};当前支持两侧同为 text 或同为 docx"
        )
    units_a = _units(kind_a, data_a, compound_a)
    units_b = _units(kind_b, data_b, compound_b)

    matcher = difflib.SequenceMatcher(None, units_a, units_b, autojunk=False)
    added = 0
    removed = 0
    hunks: list[dict[str, Any]] = []
    truncated = False
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        if tag in ("insert", "replace"):
            added += j2 - j1
        if tag in ("delete", "replace"):
            removed += i2 - i1
        if len(hunks) >= MAX_HUNKS:
            truncated = True
            break
        hunks.append(
            {
                "index": len(hunks) + 1,
                "kind": {"replace": "changed", "insert": "added", "delete": "removed"}[tag],
                "at_a": (i1 + 1) if i2 > i1 else 0,
                "at_b": (j1 + 1) if j2 > j1 else 0,
                "before": [_clip(text) for text in units_a[i1:i2][:MAX_PER_HUNK_LINES]],
                "after": [_clip(text) for text in units_b[j1:j2][:MAX_PER_HUNK_LINES]],
            }
        )
    if truncated:
        hunks = hunks[:MAX_HUNKS]
    return {
        "kind": kind_a,
        "file_a": compound_a,
        "file_b": compound_b,
        "sha256_a": hashlib.sha256(data_a).hexdigest(),
        "sha256_b": hashlib.sha256(data_b).hexdigest(),
        "identical": added == 0 and removed == 0 and not truncated,
        "added": added,
        "removed": removed,
        "hunks": hunks,
        "truncated": truncated,
        "trust": "untrusted_reference_data",
    }


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
            "仅支持两侧同为 .txt/.md 行或同为 .docx 段落"
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


def _units(kind: str, data: bytes, compound: str) -> list[str]:
    if kind == "docx":
        try:
            units = [text for _, text in _ingest._docx_stream(data)]
        except _ingest.OfficeIngestError as exc:
            raise OfficeCompareError(str(exc)) from exc
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
