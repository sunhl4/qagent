from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping

from qagent.adapters.contracts import ROOT
from qagent.models.assignment import normalize_tenant

_FORBIDDEN = frozenset(
    {
        "qasm3",
        "qasm",
        "qasm2",
        "body",
        "twin_id",
        "token",
        "secret",
        "password",
        "pauli_terms",
        "bitstrings",
        "counts_full",
        "cal",
        "calibration",
    }
)


def ingest_path() -> Path:
    raw = os.environ.get("QAGENT_INGEST_FILE")
    return Path(raw) if raw else ROOT / ".qagent" / "ingest.json"


def _key(tenant_id: str) -> str:
    return normalize_tenant(tenant_id) or "_"


def _load() -> dict[str, Any]:
    path = ingest_path()
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8") or "{}")
    except json.JSONDecodeError:
        return {}
    return raw if isinstance(raw, dict) else {}


def _save(data: dict[str, Any]) -> None:
    path = ingest_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _strip(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _strip(item) for key, item in value.items() if key not in _FORBIDDEN}
    if isinstance(value, list):
        return [_strip(item) for item in value[:32]]
    if isinstance(value, str) and value.lstrip().startswith("OPENQASM"):
        return ""
    return value


def save_ingest(tenant_id: str, row: Mapping[str, Any]) -> None:
    data = _load()
    data[_key(tenant_id)] = {
        "algorithm_id": str(row.get("algorithm_id") or ""),
        "origin": str(row.get("origin") or ""),
        "from_kind": str(row.get("from_kind") or ""),
        "brief": str(row.get("brief") or ""),
        "circuit_id": str(row.get("circuit_id") or ""),
        "config": _strip(row.get("config") if isinstance(row.get("config"), dict) else {}),
    }
    _save(data)


def load_ingest(tenant_id: str) -> dict[str, Any]:
    row = _load().get(_key(tenant_id))
    return dict(row) if isinstance(row, dict) else {}


def clear_ingest(tenant_id: str) -> None:
    data = _load()
    data.pop(_key(tenant_id), None)
    path = ingest_path()
    if data:
        _save(data)
    elif path.is_file():
        path.unlink()
