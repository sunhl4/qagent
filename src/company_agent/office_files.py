"""Move, rename and copy inside one project, with a reversible journal (§4.13).

Nothing is deleted except by ``revert``, and revert only undoes a journalled
copy or move. Bytes are never rewritten in place.
"""
from __future__ import annotations

import json

from company_agent import audit_chain, workspace_files
from company_agent import office_create as _oc
from company_agent import office_ingest as _ingest

JOURNAL = "desk-writes.jsonl"
_ACTIONS = {"copy", "move", "rename", "revert"}


class OfficeFilesError(ValueError):
    """Refusal that names the boundary hit."""


def files(args: dict) -> dict:
    root = workspace_files.root()
    project = _project(args)
    _purpose(args)
    action = args.get("action")
    if action not in _ACTIONS:
        raise OfficeFilesError("action 必须是 copy、move、rename 或 revert")
    if action == "revert":
        return _revert(root, project, args)
    ops = args.get("ops")
    if not isinstance(ops, list) or not ops or len(ops) > 32:
        raise OfficeFilesError("ops 必须是 1..32 条")
    applied: list[dict[str, str]] = []
    written: list[tuple[str, bytes | None]] = []
    try:
        for index, op in enumerate(ops, start=1):
            if not isinstance(op, dict):
                raise OfficeFilesError(f"第 {index} 条 op 必须是对象")
            source = _rel(project, op.get("source"), "source")
            target = _rel(project, op.get("target"), "target")
            if source == target:
                raise OfficeFilesError("source 与 target 相同,拒绝")
            src_path = workspace_files.resolve(root, source)
            if not src_path.is_file():
                raise OfficeFilesError("source 不是文件")
            data = _ingest._read_bounded(root, source)
            existed, dest = _oc._resolve_target(root, target, False)
            if existed:
                raise OfficeFilesError("target 已存在,拒绝覆盖")
            _oc._write_atomic(dest, data, False)
            _oc._verify_written(dest, data)
            written.append((target, None))
            if action in {"move", "rename"}:
                src_path.unlink()
                written.append((source, data))
            applied.append({"source": source, "target": target, "action": str(action)})
    except Exception:
        _rollback(root, written)
        raise
    _append_journal(root, project, {"action": action, "ops": applied, "purpose": args.get("purpose")})
    _note(args, "office_files", {"action": action, "count": len(applied)})
    return {
        "action": action,
        "applied": len(applied),
        "ops": applied,
        "trust": "untrusted_reference_data",
    }


def _revert(root, project: str, args: dict) -> dict:
    journal = workspace_files.resolve(root, f"{project}/{JOURNAL}")
    if not journal.is_file():
        raise OfficeFilesError("没有可撤销的文件操作")
    lines = [line for line in journal.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not lines:
        raise OfficeFilesError("没有可撤销的文件操作")
    last = json.loads(lines[-1])
    ops = list(reversed(last.get("ops") or []))
    for op in ops:
        source = op["source"]
        target = op["target"]
        data = _ingest._read_bounded(root, target)
        if last.get("action") in {"move", "rename"}:
            _existed, dest = _oc._resolve_target(root, source, True)
            _oc._write_atomic(dest, data, _existed)
            workspace_files.resolve(root, target).unlink()
        else:
            workspace_files.resolve(root, target).unlink()
    journal.write_text("\n".join(lines[:-1]) + ("\n" if len(lines) > 1 else ""), encoding="utf-8")
    _note(args, "office_files_revert", {"count": len(ops)})
    return {
        "action": "revert",
        "applied": len(ops),
        "ops": ops,
        "trust": "untrusted_reference_data",
    }


def _rollback(root, written: list[tuple[str, bytes | None]]) -> None:
    for compound, data in reversed(written):
        try:
            path = workspace_files.resolve(root, compound)
        except workspace_files.WorkspaceFileError:
            continue
        if data is None:
            path.unlink(missing_ok=True)
        else:
            _oc._write_atomic(path, data, True)


def _append_journal(root, project: str, row: dict) -> None:
    _existed, target = _oc._resolve_target(root, f"{project}/{JOURNAL}", True)
    previous = target.read_text(encoding="utf-8") if target.exists() else ""
    payload = previous + json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
    _oc._write_atomic(target, payload.encode("utf-8"), target.exists())


def _project(args: dict) -> str:
    project = args.get("project")
    if not isinstance(project, str) or not project.strip():
        raise OfficeFilesError("project is invalid")
    return project


def _rel(project: str, value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise OfficeFilesError(f"{label} 无效")
    compound = f"{project}/{value}"
    workspace_files._lexical(compound)
    return compound


def _purpose(args: dict) -> str:
    purpose = args.get("purpose")
    if not isinstance(purpose, str) or not purpose.strip() or len(purpose) > 80:
        raise OfficeFilesError("purpose 必须是 1..80 字的说明")
    return purpose.strip()


def _note(args: dict, event: str, detail: dict) -> None:
    detail = dict(detail)
    detail["purpose"] = _purpose(args)
    try:
        audit_chain.append(event, detail)
    except audit_chain.AuditChainError:
        return
