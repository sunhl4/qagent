from __future__ import annotations

import json
import subprocess
from typing import Any

from qagent.adapters.contracts import ROOT
from qagent.adapters.homes import ionstack_python

_SCRIPT = ROOT / "wrappers" / "interop.py"


def call_interop(action: str, args: dict[str, Any], *, timeout: float = 20.0) -> dict[str, Any] | None:
    python = ionstack_python()
    if not python or not _SCRIPT.is_file():
        return None
    try:
        proc = subprocess.run(
            [python, str(_SCRIPT)],
            input=json.dumps({"action": action, "args": args}),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    text = (proc.stdout or "").strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict) or parsed.get("error"):
        return None
    return parsed
