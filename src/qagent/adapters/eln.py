from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping

from qagent.adapters.contracts import ROOT
from qagent.models.eln import ElnEvent

_DEFAULT = ROOT / ".qagent" / "eln.jsonl"


def eln_path() -> Path:
    raw = os.environ.get("QAGENT_ELN_FILE")
    if raw:
        return Path(raw)
    return _DEFAULT


class NativeEln:
    """Qagent-owned experiment log. Not a dsh session file, not a science store."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or eln_path()

    def append(self, event_type: str, payload: Mapping[str, Any]) -> ElnEvent:
        event = ElnEvent(type=event_type, payload=dict(payload))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps({"type": event.type, **event.payload}, sort_keys=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
        return event

    def read(self) -> list[dict[str, Any]]:
        if not self.path.is_file():
            return []
        out: list[dict[str, Any]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                out.append(json.loads(line))
        return out
