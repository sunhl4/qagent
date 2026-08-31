from __future__ import annotations

from typing import Any

from qagent.adapters.catalog import NativeCatalog
from qagent.adapters.preset import active_preset, set_active_preset

_READ_HINT = "这是只读。切换请 POST /api/preset，或 list_engines 带 preset。"
_SWITCH_HINT = "已切会话。钉住的线路句柄仍在。只读请用 GET /api/preset。"


def _engine_ids() -> set[str]:
    listed = NativeCatalog().list_engines({})
    rows = listed.get("engines") if isinstance(listed.get("engines"), list) else []
    return {str(row.get("id")) for row in rows if isinstance(row, dict) and row.get("id")}


def preset_face() -> dict[str, Any]:
    return {"active_preset": active_preset(), "hint": _READ_HINT}


def switch_preset(name: str) -> dict[str, Any]:
    previous = active_preset()
    before = _engine_ids()
    set_active_preset(name)
    after = _engine_ids()
    current = active_preset()
    return {
        "previous_preset": previous,
        "active_preset": current,
        "switched": previous != current,
        "added": sorted(after - before),
        "removed": sorted(before - after),
        "hint": _SWITCH_HINT,
    }
