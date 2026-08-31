from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from qagent.adapters.contracts import ROOT

_DEFAULT_DIR = ROOT / ".qagent"


def _path(env_name: str, default: Path) -> Path:
    raw = os.environ.get(env_name)
    return Path(raw) if raw else default


def usage_path() -> Path:
    return _path("QAGENT_USAGE_FILE", _DEFAULT_DIR / "usage.jsonl")


def asks_path() -> Path:
    return _path("QAGENT_ASKS_FILE", _DEFAULT_DIR / "asks.jsonl")


def handoff_dir() -> Path:
    return _path("QAGENT_HANDOFF_DIR", _DEFAULT_DIR / "handoffs")


def savepoint_dir() -> Path:
    return _path("QAGENT_SAVEPOINT_DIR", _DEFAULT_DIR / "savepoints")


def safe_mode_path() -> Path:
    return _path("QAGENT_SAFE_MODE_FILE", _DEFAULT_DIR / "safe_mode")


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def append_jsonl(path: Path, row: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(dict(row), sort_keys=True, ensure_ascii=False) + "\n")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def write_json(path: Path, row: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(row), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8") or "{}")
    return raw if isinstance(raw, dict) else {}
