"""Company entry to the research-layer clock.

The loop stays in research-layer. This module returns a short record and, after
a real loop, records a research candidate. It does not open a ticket or call a
device.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import statistics
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from company_agent.super_dsh import record_device_handoff
from company_agent.superagent_adapt import admit_source_event
from company_agent.work_items import WorkItemStore, work_item

_ROOT = Path(__file__).resolve().parents[2]
_CLI = _ROOT / "research-layer" / "scripts" / "research-cli.mjs"
_WORKTREE = _ROOT / "research-layer" / "scripts" / "worktree-once.mjs"
_MARKERS = ("secret", "token", "password", "prompt", "credential", "api_key")
_STOPS = {
    "kept", "exhausted", "budget_exhausted", "deadline", "stopped", "escalated",
    "blocked", "consecutive_failures", "no_candidate", "invalid_candidate", "handoff", "none",
}
_DECISIONS = {"keep", "discard", "extend", "stop", "escalate", "none"}
_DECISION_ROW = re.compile(
    r"^(?:keep|discard|extend|stop|escalate|none)"
    r"(?:,(?:keep|discard|extend|stop|escalate|none)){0,4}$"
)
_EXECUTORS = {"stub", "local", "handoff", "none"}
_NUMBER = r"-?(?:\d+(?:\.\d+)?|\.\d+)"
_METRIC_LINE = re.compile(
    rf"^(?:attempt=(?P<attempt>[1-9])\s+)?"
    rf"(?:seed=(?P<seed>\d{{1,4}})\s+)?"
    rf"val_loss=(?P<loss>{_NUMBER})"
    rf"(?:\s+train_time_seconds=(?P<time>(?:\d+(?:\.\d+)?|\.\d+)))?$"
)
_EFFECT = 0.02
_TIME_LIMIT = 0.1
_SPREAD_LIMIT = 0.5
_HANDOFF_TOOLS = {
    "hpc": "hpc_submit",
    "cloud": "quantum_cloud_submit",
}
_HANDOFF_FIELDS = {
    "hpc": "job_name,script",
    "cloud": "program_path,target,shots",
    "qpu": "circuit_id,shots",
}
_RESOURCE_TYPES = {"", "cpu", "gpu", "hpc", "qpu", "cloud"}
_NEXT_TOOL = {
    "hpc": "hpc_submit",
    "cloud": "quantum_cloud_submit",
    "qpu": "quantum_device_run",
}
_NEXT_FIELDS = {
    "kept": "hypothesis,falsifier",
    "invalid_candidate": "hypothesis,falsifier",
    "exhausted": "hypothesis,falsifier",
    "budget_exhausted": "max_cost",
    "deadline": "changed_path",
    "consecutive_failures": "changed_path",
    "stopped": "changed_path",
}
_NEEDS_DECISION = {"deadline", "consecutive_failures", "escalated", "blocked", "stopped"}
_DISCARD_STOPS = {"exhausted", "deadline", "consecutive_failures", "budget_exhausted"}


def _state_dir() -> Path:
    configured = str(os.environ.get("COMPANY_AGENT_RESEARCH_STATE") or "").strip()
    path = Path(configured).expanduser() if configured else Path.home() / ".dsh" / "research-clock"
    if not path.is_absolute():
        raise ValueError("research state path must be absolute")
    path.mkdir(parents=True, exist_ok=True)
    return path


def _load() -> dict[str, Any]:
    path = _state_dir() / "records.json"
    if not path.is_file():
        return {"runs": []}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("runs"), list):
        raise ValueError("research record is invalid")
    return payload


def _save(payload: dict[str, Any]) -> None:
    path = _state_dir() / "records.json"
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    temporary.replace(path)


def _clean(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is invalid")
    text = value.strip()
    if any(marker in text.casefold() for marker in _MARKERS):
        raise ValueError(f"{field} is invalid")
    return text


def _spec_fields(args: dict[str, Any]) -> dict[str, Any]:
    changed = _clean(args.get("changed_path"), "changed_path")
    if ".." in changed:
        raise ValueError("changed_path is invalid")
    project = args.get("project_id")
    return {
        "tenant_id": _clean(args.get("tenant_id"), "tenant_id"),
        "experiment_id": _clean(args.get("experiment_id"), "experiment_id"),
        "task_id": _clean(args.get("task_id"), "task_id"),
        "project_id": _clean(project, "project_id") if project is not None else "",
        "hypothesis": _clean(args.get("hypothesis"), "hypothesis"),
        "falsifier": _clean(args.get("falsifier"), "falsifier"),
        "baseline_name": _clean(args.get("baseline_name"), "baseline_name"),
        "baseline_source": _clean(args.get("baseline_source"), "baseline_source"),
        "baseline_metric": args.get("baseline_metric"),
        "baseline_reproduced": args.get("baseline_reproduced") is True,
        "baseline_train_time_seconds": _optional_time(args.get("baseline_train_time_seconds")),
        "min_seeds": _optional_seeds(args.get("min_seeds")),
        "changed_path": changed,
        "primary_metric": _clean(args.get("primary_metric"), "primary_metric"),
        "direction": args.get("direction"),
        "resource_type": args.get("resource_type"),
        "max_cost": args.get("max_cost"),
        "max_attempts": args.get("max_attempts"),
    }


def _node() -> str:
    found = shutil.which("node")
    if not found:
        raise ValueError("research clock runtime is unavailable")
    return found


def _call(action: str, fields: dict[str, Any]) -> dict[str, Any]:
    if not _CLI.is_file():
        raise ValueError("research clock is unavailable")
    payload = {"action": action, **fields}
    completed = subprocess.run(
        [_node(), str(_CLI)],
        input=json.dumps(payload, ensure_ascii=False),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if completed.returncode != 0 or not completed.stdout.strip():
        raise ValueError("research clock failed")
    parsed = json.loads(completed.stdout)
    if not isinstance(parsed, dict):
        raise ValueError("research clock failed")
    return parsed


def _optional_time(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("baseline_train_time_seconds is invalid")
    number = float(value)
    if not math.isfinite(number) or number <= 0 or number > 1_000_000:
        raise ValueError("baseline_train_time_seconds is invalid")
    return number


def _optional_seeds(value: object) -> int:
    if value is None:
        return 1
    if isinstance(value, bool) or not isinstance(value, int) or value not in {1, 2, 3}:
        raise ValueError("min_seeds is invalid")
    return value


def _money(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("research cost is invalid")
    number = float(value)
    if not math.isfinite(number) or number < 0 or number > 1_000_000:
        raise ValueError("research cost is invalid")
    return round(number, 4)


def _code(value: object) -> str:
    if not isinstance(value, str) or len(value) > 40:
        raise ValueError("research error code is invalid")
    if value and any(not (character.isascii() and (character.isalnum() or character == "_")) for character in value):
        raise ValueError("research error code is invalid")
    return value


def compile_spec(args: dict[str, Any]) -> dict[str, Any]:
    fields = _spec_fields(args)
    result = _call("compile", fields)
    return {
        "ok": result.get("ok") is True,
        "experiment_id": fields["experiment_id"],
        "primary_metric": fields["primary_metric"],
        "direction": fields["direction"],
        "changed_path": fields["changed_path"],
        "resource_type": fields["resource_type"],
        "max_attempts": fields["max_attempts"],
        "max_cost": fields["max_cost"],
        "currency": "CNY",
        "approval_required": result.get("approval_required") is True,
        "error_code": "" if result.get("ok") is True else _code(result.get("error_code")),
    }


def _blank_run(experiment_id: str, *, stop_reason: str = "invalid_candidate") -> dict[str, Any]:
    return {
        "ok": False,
        "executor": "none",
        "experiment_id": experiment_id,
        "stop_reason": stop_reason,
        "attempts": 0,
        "decision": "none",
        "decisions": "",
        "remaining_budget": 0,
        "total_cost": 0,
        "currency": "CNY",
        "failure_count": 0,
        "signal_type": "none",
        "authority": "none",
        "trigger_id": "",
    }


def _remember(row: dict[str, Any]) -> None:
    payload = _load()
    runs = [item for item in payload["runs"] if isinstance(item, dict)]
    runs.append(row)
    payload["runs"] = runs[-64:]
    _save(payload)


def _cached(tenant_id: str, experiment_id: str, idempotency_key: str) -> dict[str, Any] | None:
    for item in reversed(_load()["runs"]):
        if not isinstance(item, dict):
            continue
        if item.get("tenant_id") == tenant_id and item.get("idempotency_key") == idempotency_key:
            if item.get("experiment_id") != experiment_id:
                raise ValueError("idempotency_key is already used")
            return item
    return None


def _decisions(value: object, attempts: int) -> str:
    if attempts == 0:
        if value not in (None, ""):
            raise ValueError("research record is invalid")
        return ""
    if not isinstance(value, str) or _DECISION_ROW.fullmatch(value) is None:
        raise ValueError("research record is invalid")
    parts = value.split(",")
    if len(parts) != attempts:
        raise ValueError("research record is invalid")
    return value


def _public_run(row: dict[str, Any]) -> dict[str, Any]:
    stop = row.get("stop_reason")
    decision = row.get("decision")
    executor = row.get("executor")
    attempts = row.get("attempts")
    if (
        stop not in _STOPS
        or decision not in _DECISIONS
        or executor not in _EXECUTORS
        or isinstance(attempts, bool)
        or not isinstance(attempts, int)
        or attempts < 0
        or attempts > 5
    ):
        raise ValueError("research record is invalid")
    decisions = _decisions(row.get("decisions", ""), attempts)
    if attempts and decisions.split(",")[-1] != decision:
        raise ValueError("research record is invalid")
    resource_type = row.get("resource_type") or ""
    if not isinstance(resource_type, str) or resource_type not in _RESOURCE_TYPES:
        raise ValueError("research record is invalid")
    next_tool = _NEXT_TOOL.get(resource_type, "") if stop == "handoff" else ""
    next_fields = _HANDOFF_FIELDS.get(resource_type, "") if stop == "handoff" else _NEXT_FIELDS.get(stop, "")
    if stop == "handoff" and (not next_tool or not next_fields):
        raise ValueError("research record is invalid")
    return {
        "ok": row.get("ok") is True,
        "executor": executor,
        "experiment_id": row["experiment_id"],
        "stop_reason": stop,
        "attempts": attempts,
        "decision": decision,
        "decisions": decisions,
        "remaining_budget": _money(row["remaining_budget"]),
        "total_cost": _money(row["total_cost"]),
        "currency": "CNY",
        "failure_count": int(row["failure_count"]),
        "signal_type": row.get("signal_type") or "none",
        "authority": row.get("authority") or "none",
        "trigger_id": str(row.get("trigger_id") or ""),
        "resource_type": resource_type,
        "next_tool": next_tool,
        "approval_still_required": next_tool != "",
        "next_fields": next_fields,
    }


def _signal(fields: dict[str, Any], *, signal_type: str, version: int) -> dict[str, Any]:
    payload = {
        "action": "signal",
        "signal_type": signal_type,
        "tenant_id": fields["tenant_id"],
        "resource_id": fields["experiment_id"],
        "resource_version": version,
        "time": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    if fields["project_id"]:
        payload["project_id"] = fields["project_id"]
    recorded = work_item(payload)
    return {
        "authority": recorded["authority"],
        "trigger_id": recorded["trigger_id"],
        "signal_type": signal_type,
    }


def _next_version(tenant_id: str, experiment_id: str) -> int:
    versions = [
        int(item["resource_version"])
        for item in _load()["runs"]
        if isinstance(item, dict)
        and item.get("tenant_id") == tenant_id
        and item.get("experiment_id") == experiment_id
        and isinstance(item.get("resource_version"), int)
    ]
    return max(versions, default=0) + 1


def _card_fingerprint(fields: dict[str, Any]) -> str:
    raw = f"{fields['hypothesis']}\n{fields['falsifier']}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _kept_same_card(fields: dict[str, Any]) -> bool:
    fingerprint = _card_fingerprint(fields)
    for item in reversed(_load()["runs"]):
        if not isinstance(item, dict):
            continue
        if item.get("tenant_id") != fields["tenant_id"] or item.get("experiment_id") != fields["experiment_id"]:
            continue
        if item.get("stop_reason") == "kept" and item.get("card_fingerprint") == fingerprint:
            return True
    return False


def _research_root() -> Path | None:
    raw = str(os.environ.get("COMPANY_AGENT_RESEARCH_ROOT") or "").strip()
    if not raw:
        return None
    root = Path(raw)
    if not root.is_absolute() or not root.is_dir():
        raise ValueError("research clock failed")
    return root.resolve()


def _metric_file(root: Path, changed: str) -> Path | None:
    candidate = Path(changed)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError("changed_path is invalid")
    target = (root / candidate).resolve()
    if root != target and root not in target.parents:
        raise ValueError("changed_path is invalid")
    if not target.is_file():
        return None
    if target.stat().st_size > 4096:
        raise ValueError("research clock failed")
    return target


def _judge(baseline: object, direction: object, value: float) -> str:
    if isinstance(baseline, bool) or not isinstance(baseline, (int, float)):
        raise ValueError("research clock failed")
    delta = float(baseline) - value if direction == "minimize" else value - float(baseline)
    return "keep" if delta >= _EFFECT else "discard"


def _append_ledger(experiment_id: str, metric: str, status: str, note: str) -> None:
    path = _state_dir() / "ledger.tsv"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"{experiment_id}\t{metric}\t{status}\t{note}\n")


def _is_git_repo(root: Path) -> bool:
    marker = root / ".git"
    return marker.is_dir() or marker.is_file()


def _worktree(action: str, root: Path, experiment_id: str, attempt: int) -> dict[str, Any] | str | None:
    if not _WORKTREE.is_file():
        return None
    payload = json.dumps({
        "action": action,
        "repoRoot": str(root),
        "experiment_id": experiment_id,
        "attempt": attempt,
    }, ensure_ascii=False)
    try:
        completed = subprocess.run(
            [_node(), "--experimental-strip-types", str(_WORKTREE)],
            input=payload,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if not completed.stdout.strip():
        return None
    try:
        parsed = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    if parsed.get("ok") is True:
        value = parsed.get("value")
        if isinstance(value, dict) and value.get("state") in {"created", "reused", "removed", "absent"}:
            return value
        return None
    error = parsed.get("error")
    if isinstance(error, dict) and error.get("code") == "DIRTY":
        return "dirty"
    return None


def _release_worktree(root: Path, experiment_id: str, attempt: int, opened: dict[str, Any] | str | None, *, keep: bool) -> None:
    state = opened.get("state") if isinstance(opened, dict) else None
    if keep or state not in {"created", "reused"}:
        return
    removed = _worktree("remove", root, experiment_id, attempt)
    if not isinstance(removed, dict) or removed.get("state") not in {"removed", "absent"}:
        _append_ledger(experiment_id, "0", "discard", "dirty")


def _unstable(values: list[float]) -> bool:
    if len(values) < 2:
        return False
    mean = statistics.fmean(values)
    if mean == 0:
        return any(value != 0 for value in values)
    return statistics.stdev(values) / abs(mean) > _SPREAD_LIMIT


def _guard_regressed(baseline: float | None, times: list[float | None]) -> bool:
    if baseline is None:
        return False
    if not times or any(item is None for item in times):
        return True
    return statistics.fmean([float(item) for item in times]) > baseline * (1 + _TIME_LIMIT)


def _attempt_rows(lines: list[str]) -> list[dict[str, Any]]:
    parsed: list[dict[str, Any]] = []
    saw_attempt = False
    saw_plain = False
    for line in lines:
        if line in {"timeout", "crash"}:
            parsed.append({"kind": line, "text": line})
            continue
        matched = _METRIC_LINE.fullmatch(line)
        if matched is None:
            parsed.append({"kind": "crash", "text": line})
            continue
        attempt = matched.group("attempt")
        saw_attempt = saw_attempt or attempt is not None
        saw_plain = saw_plain or attempt is None
        parsed.append({
            "kind": "metric",
            "attempt": int(attempt) if attempt else None,
            "loss": float(matched.group("loss")),
            "time": None if matched.group("time") is None else float(matched.group("time")),
            "text": line,
        })
    if saw_attempt and saw_plain:
        return [{"kind": "crash", "text": "crash"}]
    if not saw_attempt:
        return [
            item if item["kind"] != "metric" else {
                "kind": "metric",
                "losses": [item["loss"]],
                "times": [item["time"]],
                "text": item["text"],
            }
            for item in parsed
        ]
    groups: list[dict[str, Any]] = []
    index: dict[int, dict[str, Any]] = {}
    for item in parsed:
        if item["kind"] != "metric":
            groups.append(item)
            continue
        bucket = index.get(item["attempt"])
        if bucket is None:
            bucket = {"kind": "metric", "losses": [], "times": [], "lines": []}
            index[item["attempt"]] = bucket
            groups.append(bucket)
        bucket["losses"].append(item["loss"])
        bucket["times"].append(item["time"])
        bucket["lines"].append(item["text"])
    for bucket in groups:
        if bucket["kind"] == "metric":
            bucket["text"] = "\n".join(bucket["lines"])
    return groups


def _pin_attempt(opened: dict[str, Any] | str | None, relative: str, text: str) -> bool:
    if not isinstance(opened, dict):
        return True
    raw = opened.get("path")
    if not isinstance(raw, str) or not raw:
        return False
    worktree = Path(raw).resolve()
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts:
        return False
    target = (worktree / candidate).resolve()
    if worktree != target and worktree not in target.parents:
        return False
    git = shutil.which("git")
    if git is None:
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text if text.endswith("\n") else f"{text}\n", encoding="utf-8")
    added = subprocess.run(
        [git, "add", "--", relative],
        cwd=worktree,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=20,
        check=False,
    )
    if added.returncode != 0:
        return False
    committed = subprocess.run(
        [git, "-c", "user.email=dev@example.com", "-c", "user.name=dev", "commit", "-m", "attempt", "--", relative],
        cwd=worktree,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=20,
        check=False,
    )
    return committed.returncode == 0


def _local_run(fields: dict[str, Any]) -> dict[str, Any] | None:
    root = _research_root()
    if root is None:
        return None
    target = _metric_file(root, fields["changed_path"])
    if target is None:
        return None
    lines = [line.strip() for line in target.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not lines:
        return None
    rows = _attempt_rows(lines)
    attempts = int(fields["max_attempts"])
    budget = int(fields["max_cost"])
    spent = 0
    decisions: list[str] = []
    failures = 0
    stop = "exhausted"
    repo = _is_git_repo(root)
    for row in rows:
        if len(decisions) >= attempts:
            break
        if spent >= budget:
            stop = "budget_exhausted"
            break
        spent += 1
        attempt = len(decisions) + 1
        opened = _worktree("create", root, fields["experiment_id"], attempt) if repo else None
        pinned = _pin_attempt(opened, fields["changed_path"], str(row["text"]))
        if repo and not pinned:
            decisions.append("discard")
            failures += 1
            stop = "consecutive_failures"
            _append_ledger(fields["experiment_id"], "0", "crash", "dirty")
            _release_worktree(root, fields["experiment_id"], attempt, opened, keep=False)
            break
        kind = row["kind"]
        if kind == "timeout":
            decisions.append("discard")
            failures += 1
            stop = "deadline"
            _append_ledger(fields["experiment_id"], "0", "crash", "timeout")
            _release_worktree(root, fields["experiment_id"], attempt, opened, keep=False)
            break
        if kind != "metric":
            decisions.append("discard")
            failures += 1
            stop = "consecutive_failures"
            _append_ledger(fields["experiment_id"], "0", "crash", "crash")
            _release_worktree(root, fields["experiment_id"], attempt, opened, keep=False)
            break
        losses = [float(item) for item in row["losses"]]
        if len(losses) < int(fields["min_seeds"]) or _unstable(losses):
            choice = "extend"
            note = "spread"
            stop = "stopped"
        elif _guard_regressed(fields.get("baseline_train_time_seconds"), row["times"]):
            choice = "discard"
            note = "guardrail"
            stop = "exhausted"
        else:
            choice = _judge(fields["baseline_metric"], fields["direction"], statistics.fmean(losses))
            note = "improve" if choice == "keep" else "no-gain"
            stop = "kept" if choice == "keep" else "exhausted"
        decisions.append(choice)
        _append_ledger(fields["experiment_id"], f"{statistics.fmean(losses):.4f}", choice, note)
        if choice == "keep":
            _release_worktree(root, fields["experiment_id"], attempt, opened, keep=True)
            break
        _release_worktree(root, fields["experiment_id"], attempt, opened, keep=False)
        if choice == "extend":
            break
    else:
        if stop not in {"kept", "stopped"}:
            stop = "exhausted"
    if not decisions:
        return None
    if stop not in {"kept", "deadline", "consecutive_failures", "budget_exhausted", "stopped"}:
        stop = "exhausted"
    return {
        "ok": True,
        "executor": "local",
        "stop_reason": stop,
        "attempts": len(decisions),
        "decision": decisions[-1],
        "decisions": ",".join(decisions),
        "remaining_budget": max(0, budget - spent),
        "total_cost": spent,
        "failure_count": failures,
    }


def _resource_handoff(fields: dict[str, Any], idempotency_key: str, tool: str) -> dict[str, Any]:
    admitted = admit_source_event({
        "schema_version": "1",
        "source": "research",
        "thread_id": fields["experiment_id"],
        "actor_id": fields["tenant_id"],
        "text": f"resource-handoff {fields['resource_type']} {tool}",
        "tenant_id": fields["tenant_id"],
        "idempotency_key": idempotency_key,
        "written_rule": False,
    })
    row = _blank_run(fields["experiment_id"], stop_reason="handoff")
    row.update({
        "ok": True,
        "executor": "handoff",
        "tenant_id": fields["tenant_id"],
        "idempotency_key": idempotency_key,
        "resource_version": _next_version(fields["tenant_id"], fields["experiment_id"]),
        "authority": admitted["authority"],
        "trigger_id": admitted["trigger_id"],
        "card_fingerprint": _card_fingerprint(fields),
        "resource_type": fields["resource_type"],
    })
    _remember(row)
    return _public_run(row)


def run_spec(args: dict[str, Any]) -> dict[str, Any]:
    fields = _spec_fields(args)
    idempotency_key = _clean(args.get("idempotency_key"), "idempotency_key")
    cached = _cached(fields["tenant_id"], fields["experiment_id"], idempotency_key)
    if cached is not None:
        return _public_run(cached)
    if _kept_same_card(fields):
        row = _blank_run(fields["experiment_id"])
        row.update({
            "tenant_id": fields["tenant_id"],
            "idempotency_key": idempotency_key,
            "resource_version": 0,
            "card_fingerprint": _card_fingerprint(fields),
            "resource_type": fields["resource_type"],
        })
        _remember(row)
        return _public_run(row)
    compiled = _call("compile", fields)
    if compiled.get("ok") is not True:
        row = _blank_run(fields["experiment_id"])
        row.update({
            "tenant_id": fields["tenant_id"],
            "idempotency_key": idempotency_key,
            "resource_version": 0,
            "resource_type": fields["resource_type"],
        })
        _remember(row)
        return _public_run(row)
    if fields["resource_type"] == "qpu":
        handoff = record_device_handoff(WorkItemStore(), {
            "tenant_id": fields["tenant_id"],
            "request_id": fields["experiment_id"],
            "idempotency_key": idempotency_key,
            "mandate": "lab",
            "tool": "quantum_device_run",
        })
        row = _blank_run(fields["experiment_id"], stop_reason="handoff")
        row.update({
            "ok": True,
            "executor": "handoff",
            "tenant_id": fields["tenant_id"],
            "idempotency_key": idempotency_key,
            "resource_version": _next_version(fields["tenant_id"], fields["experiment_id"]),
            "authority": handoff["authority"],
            "trigger_id": handoff["trigger_id"],
            "card_fingerprint": _card_fingerprint(fields),
            "resource_type": fields["resource_type"],
        })
        _remember(row)
        return _public_run(row)
    handoff_tool = _HANDOFF_TOOLS.get(fields["resource_type"])
    if handoff_tool is not None:
        return _resource_handoff(fields, idempotency_key, handoff_tool)
    local = _local_run(fields)
    result = local if local is not None else _call("run", {**fields, "idempotency_key": idempotency_key})
    if result.get("ok") is not True:
        raise ValueError("research clock failed")
    stop = result.get("stop_reason")
    if stop not in _STOPS or stop in {"handoff", "none"}:
        raise ValueError("research clock failed")
    attempts = result.get("attempts")
    failures = result.get("failure_count")
    decision = result.get("decision")
    if isinstance(attempts, bool) or not isinstance(attempts, int) or attempts < 0 or attempts > 5:
        raise ValueError("research clock failed")
    if isinstance(failures, bool) or not isinstance(failures, int) or failures < 0 or failures > 32:
        raise ValueError("research clock failed")
    if decision not in _DECISIONS:
        raise ValueError("research clock failed")
    decisions = _decisions(result.get("decisions"), attempts)
    if attempts and decisions.split(",")[-1] != decision:
        raise ValueError("research clock failed")
    version = _next_version(fields["tenant_id"], fields["experiment_id"])
    signal_type = "none"
    authority = "none"
    trigger_id = ""
    if stop == "budget_exhausted":
        signal_type = "budget.exhausted.v1"
    elif stop == "kept":
        signal_type = "experiment.completed.v1"
    if signal_type != "none":
        signal = _signal(fields, signal_type=signal_type, version=version)
        authority = signal["authority"]
        trigger_id = signal["trigger_id"]
    row = {
        "ok": True,
        "executor": result.get("executor") if result.get("executor") in _EXECUTORS else "stub",
        "tenant_id": fields["tenant_id"],
        "experiment_id": fields["experiment_id"],
        "idempotency_key": idempotency_key,
        "resource_version": version,
        "stop_reason": stop,
        "attempts": attempts,
        "decision": decision,
        "decisions": decisions,
        "remaining_budget": _money(result.get("remaining_budget")),
        "total_cost": _money(result.get("total_cost")),
        "failure_count": failures,
        "signal_type": signal_type,
        "authority": authority,
        "trigger_id": trigger_id,
        "card_fingerprint": _card_fingerprint(fields),
        "resource_type": fields["resource_type"],
    }
    _remember(row)
    return _public_run(row)


def read_digest(args: dict[str, Any]) -> dict[str, Any]:
    tenant_id = _clean(args.get("tenant_id"), "tenant_id")
    runs = [
        item for item in _load()["runs"]
        if isinstance(item, dict) and item.get("tenant_id") == tenant_id
    ]
    kept = sum(1 for item in runs if item.get("stop_reason") == "kept")
    handoffs = sum(1 for item in runs if item.get("stop_reason") == "handoff")
    discarded = sum(1 for item in runs if item.get("stop_reason") in _DISCARD_STOPS)
    rejected = sum(
        1 for item in runs
        if item.get("stop_reason") not in _DISCARD_STOPS | {"kept", "handoff"}
    )
    failures = sum(int(item.get("failure_count") or 0) for item in runs)
    cost = sum(float(item.get("total_cost") or 0) for item in runs)
    attention = sum(1 for item in runs if item.get("stop_reason") in _NEEDS_DECISION)
    return {
        "ok": True,
        "runs": min(len(runs), 64),
        "kept": min(kept, 64),
        "discarded": min(discarded, 64),
        "handoffs": min(handoffs, 64),
        "rejected": min(rejected, 64),
        "needs_decision": min(attention, 64),
        "failure_count": min(failures, 2048),
        "total_cost": min(round(cost, 4), 1_000_000),
        "currency": "CNY",
    }


def read_status(args: dict[str, Any]) -> dict[str, Any]:
    tenant_id = _clean(args.get("tenant_id"), "tenant_id")
    experiment_id = _clean(args.get("experiment_id"), "experiment_id")
    found = None
    for item in reversed(_load()["runs"]):
        if isinstance(item, dict) and item.get("tenant_id") == tenant_id and item.get("experiment_id") == experiment_id:
            found = item
            break
    if found is None:
        return {
            "ok": True,
            "recorded": False,
            "executor": "none",
            "experiment_id": experiment_id,
            "stop_reason": "none",
            "attempts": 0,
            "decision": "none",
            "decisions": "",
            "remaining_budget": 0,
            "failure_count": 0,
            "resource_type": "",
            "next_tool": "",
            "approval_still_required": False,
            "next_fields": "",
        }
    public = _public_run(found)
    return {
        "ok": True,
        "recorded": True,
        "executor": public["executor"],
        "experiment_id": experiment_id,
        "stop_reason": public["stop_reason"],
        "attempts": public["attempts"],
        "decision": public["decision"],
        "decisions": public["decisions"],
        "remaining_budget": public["remaining_budget"],
        "failure_count": public["failure_count"],
        "resource_type": public["resource_type"],
        "next_tool": public["next_tool"],
        "approval_still_required": public["approval_still_required"],
        "next_fields": public["next_fields"],
    }
