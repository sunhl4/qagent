from __future__ import annotations

import os
from pathlib import Path

from qagent.adapters.contracts import ROOT

PRESET_BOOT = "boot"
PRESETS = ("lab", "algo", "sign", PRESET_BOOT)
DEFAULT_PRESET = "lab"


def preset_path() -> Path:
    raw = os.environ.get("QAGENT_PRESET_FILE")
    if raw:
        return Path(raw)
    return ROOT / ".qagent" / "active_preset"


def _clean(raw: str | None) -> str | None:
    if raw is None:
        return None
    name = raw.strip()
    if name in PRESETS:
        return name
    return None


def active_preset(explicit: str | None = None) -> str:
    """File wins, then QAGENT_PRESET, then lab. File is how a session switches."""
    picked = _clean(explicit)
    if picked:
        return picked
    try:
        picked = _clean(preset_path().read_text(encoding="utf-8"))
        if picked:
            return picked
    except OSError:
        pass
    return _clean(os.environ.get("QAGENT_PRESET")) or DEFAULT_PRESET


def set_active_preset(name: str) -> str:
    picked = _clean(name)
    if not picked:
        raise ValueError(f"preset must be one of {list(PRESETS)}")
    path = preset_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(picked + "\n", encoding="utf-8")
    os.environ["QAGENT_PRESET"] = picked
    return picked
