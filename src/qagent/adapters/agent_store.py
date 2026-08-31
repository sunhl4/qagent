from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from qagent.adapters.contracts import ROOT


def thread_path() -> Path:
    raw = os.environ.get("QAGENT_AGENT_THREAD")
    return Path(raw) if raw else ROOT / ".qagent" / "agent-thread.json"


def load_thread() -> dict[str, Any]:
    path = thread_path()
    if not path.is_file():
        return {"messages": [], "pending": None}
    raw = json.loads(path.read_text(encoding="utf-8") or "{}")
    if not isinstance(raw, dict):
        return {"messages": [], "pending": None}
    return {
        "messages": list(raw.get("messages") or []),
        "pending": raw.get("pending"),
    }


def save_thread(payload: dict[str, Any]) -> None:
    path = thread_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.chmod(path, 0o600)


def clear_thread() -> None:
    save_thread({"messages": [], "pending": None})
