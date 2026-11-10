"""Short run index that outlives the receipt ring."""
from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from company_agent.receipts import ReceiptError, _root

_TOOLS = {
    "quantum_algorithm_run",
    "quantum_circuit_export",
    "quantum_simulate",
    "quantum_cloud_submit",
    "quantum_device_run",
}
_FIELDS = (
    "catalog_version", "component_id", "asset_id", "circuit_id",
    "twin_id", "cloud_task", "unknown", "page",
)


def _path():
    return _root() / "dossier.jsonl"


def _text(value: object, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    return value[:limit]


def remember(tool: str, arguments: Mapping[str, Any], payload: Mapping[str, Any]) -> None:
    if tool not in _TOOLS:
        return
    row = {
        "catalog_version": _text(arguments.get("catalog_version") or payload.get("catalog_version"), 64),
        "component_id": _text(arguments.get("algorithm") or payload.get("component_id") or payload.get("id"), 128),
        "asset_id": _text(arguments.get("asset_id") or payload.get("asset_id"), 256),
        "circuit_id": _text(arguments.get("circuit_id") or payload.get("circuit_id"), 256),
        "twin_id": _text(payload.get("twin_id"), 256),
        "cloud_task": _text(payload.get("cloud_task"), 128),
        "unknown": False,
        "page": _text(
            payload.get("artifact_path")
            or (payload.get("summary") or {}).get("artifact_path")
            if isinstance(payload.get("summary"), dict) else "",
            180,
        ),
        "metrics": _metrics(payload),
    }
    if not any(row[key] for key in ("asset_id", "circuit_id", "cloud_task", "twin_id")):
        return
    try:
        path = _path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    except (OSError, ReceiptError, TypeError, ValueError):
        return


def _metrics(payload: Mapping[str, Any]) -> list[dict[str, float]]:
    summary = payload.get("summary")
    metrics = summary.get("metrics") if isinstance(summary, dict) else None
    items = metrics.get("items") if isinstance(metrics, dict) else None
    if not isinstance(items, list):
        return []
    kept: list[dict[str, float]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        value = item.get("value")
        if not isinstance(name, str) or not name or len(name) > 64:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        kept.append({"name": name, "value": float(value)})
        if len(kept) == 8:
            break
    return kept


def read(arguments: Mapping[str, Any]) -> dict[str, Any]:
    circuit_id = arguments.get("circuit_id")
    asset_id = arguments.get("asset_id")
    cloud_task = arguments.get("cloud_task")
    chosen = [key for key, value in (
        ("circuit_id", circuit_id), ("asset_id", asset_id), ("cloud_task", cloud_task),
    ) if isinstance(value, str) and value]
    if len(chosen) != 1:
        raise ValueError("dossier query must name one identifier")
    key = chosen[0]
    wanted = arguments[key]
    matched: list[dict[str, Any]] = []
    try:
        path = _path()
        lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    except (OSError, ReceiptError, UnicodeError):
        lines = []
    for raw in reversed(lines):
        try:
            row = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(row, dict) or row.get(key) != wanted:
            continue
        matched.append({field: row.get(field) if field != "unknown" else bool(row.get("unknown")) for field in _FIELDS})
        for field in _FIELDS:
            if field == "unknown":
                continue
            if not isinstance(matched[-1][field], str):
                matched[-1][field] = ""
        if len(matched) == 8:
            break
    return {"ok": True, "count": len(matched), "items": matched}


def previous_metric(circuit_id: str, name: str) -> float | None:
    try:
        path = _path()
        lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    except (OSError, ReceiptError, UnicodeError):
        return None
    for raw in reversed(lines):
        try:
            row = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(row, dict) or row.get("circuit_id") != circuit_id:
            continue
        metrics = row.get("metrics")
        if not isinstance(metrics, list):
            return None
        for item in metrics:
            if isinstance(item, dict) and item.get("name") == name and isinstance(item.get("value"), (int, float)):
                return float(item["value"])
        return None
    return None
