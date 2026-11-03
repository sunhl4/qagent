"""Delivery naming for one workspace file (§3.7/§4.3; MeWork present port).

The reference names deliverables ``标题_YYYYMMDD_NN`` and never overwrites a
delivery; the six-step output-location ladder collapses to the project
directory in a workspace-fenced adapter, so the discipline kept here is the
name itself:

- the delivery goes to ``deliverables/`` in the project directory, named
  ``<title>_<UTC YYYYMMDD>_<NN>.<ext>``;
- the title defaults to the source stem with any old stamp
  (``_20260101`` / ``_20260101_02`` / ``_20260101_02_123456``) stripped;
- NN is the next free two-digit sequence for that title and UTC date; 99
  occupied is an honest refusal;
- the copy is atomic (temp + replace) and re-verified by re-read; the source
  file is never touched, a delivered name never overwritten;
- project/relative paths in the receipt only; 20MB cap.
"""
from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from pathlib import Path

from company_agent import office_create as _oc
from company_agent import office_ingest as _ingest
from company_agent import workspace_files

DELIVERY_DIR = "deliverables"
MAX_FILE_BYTES = _ingest.MAX_FILE_BYTES
_STAMP = re.compile(r"_\d{8}(?:_\d{2})?(?:_\d{6})?$")

DELIVERABLE_SUFFIXES = (
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".ppt",
    ".pptx",
    ".wps",
    ".et",
    ".dps",
    ".pdf",
    ".txt",
    ".md",
    ".csv",
    ".json",
    ".png",
    ".jpg",
    ".jpeg",
)


class OfficeDeliverError(ValueError):
    """Refusal that names the boundary hit without echoing paths outside the root."""


def deliver(args: dict) -> dict:
    """Contract entry point: named, sequenced, never-overwriting delivery copy."""

    root = workspace_files.root()
    compound = _oc._compound(args)
    resolved = workspace_files.resolve(root, compound)
    if not resolved.is_file():
        raise OfficeDeliverError("workspace path is not a file")
    suffix = resolved.suffix.casefold()
    if suffix not in DELIVERABLE_SUFFIXES:
        raise OfficeDeliverError(
            f"{suffix or '(无后缀)'} 不是交付类型;支持 {' '.join(DELIVERABLE_SUFFIXES)}"
        )
    data = _read_bounded(root, compound)
    title = _title(args, resolved)
    project_deliverables = f"{compound.split('/', 1)[0]}/{DELIVERY_DIR}"
    sequence, target_name = _next_free(root, project_deliverables, title, suffix)

    target_compound = f"{project_deliverables}/{target_name}"
    existed, target = _oc._resolve_target(root, target_compound, False)
    _oc._write_atomic(target, data, existed)
    _oc._verify_written(target, data)
    if target.read_bytes() != data:
        raise OfficeDeliverError("交付复验失败:磁盘字节与源不一致,如实失败")
    return {
        "source": compound,
        "path": target_compound,
        "sequence": sequence,
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def _title(args: dict, resolved: Path) -> str:
    raw = args.get("title")
    if raw is None:
        candidate = _strip_stamp(resolved.stem)
    elif isinstance(raw, str) and raw.strip() and raw.strip() == raw:
        candidate = raw.strip()
    else:
        raise OfficeDeliverError("title 必须是干净的字符串,或缺省")
    if "/" in candidate or "\\" in candidate or ":" in candidate:
        raise OfficeDeliverError("title 不得包含路径分隔符,拒绝")
    candidate = candidate[:60]
    if not candidate.strip():
        raise OfficeDeliverError("title 不能为空")
    return candidate


def _next_free(root: Path, deliverables: str, title: str, suffix: str) -> tuple[int, str]:
    stamp = datetime.now(UTC).strftime("%Y%m%d")
    prefix = f"{title}_{stamp}_"
    occupied: set[int] = set()
    try:
        directory = workspace_files.resolve(root, deliverables)
    except workspace_files.WorkspaceFileError:
        directory = None
    if directory is not None and directory.is_dir():
        for entry in directory.iterdir():
            if entry.name.endswith(suffix):
                match = re.fullmatch(rf"{re.escape(prefix)}(\d{{2}})\.{re.escape(suffix[1:])}", entry.name)
                if match is not None:
                    occupied.add(int(match.group(1)))
    if len(occupied) >= 99:
        raise OfficeDeliverError(f"{title}_{stamp} 已有 99 个交付序号:请归档或清理,如实拒绝")
    sequence = next(number for number in range(1, 100) if number not in occupied)
    return sequence, f"{prefix}{sequence:02d}{suffix}"


def _strip_stamp(stem: str) -> str:
    return _STAMP.sub("", stem)


def _read_bounded(root, relative: str) -> bytes:
    try:
        oversized = workspace_files.resolve(root, relative).stat().st_size > MAX_FILE_BYTES
    except OSError as exc:
        raise OfficeDeliverError("workspace file is not available") from exc
    if oversized:
        raise OfficeDeliverError("文件超过 20MB 交付上限:该文件被拒绝(明示拒收)")
    with workspace_files.open_file(root, relative) as stream:
        data = stream.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES:
        raise OfficeDeliverError("文件超过 20MB 交付上限:该文件被拒绝(明示拒收)")
    return data
