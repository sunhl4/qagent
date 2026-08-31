from __future__ import annotations

from typing import Any

from qagent.models.handles import HANDLE_ASSET, HANDLE_CIRCUIT, HANDLE_TWIN
from qagent.models.life import life_from_assignment
from qagent.services.assignment import list_assignments
from qagent.services.cards import pes_card, signoff_card
from qagent.services.doctor import probe
from qagent.services.health import health_lamps
from qagent.services.notify import asks_face
from qagent.services.savepoint import safe_mode_on
from qagent.services.usage import usage_face


def gov_face(tenant_id: str = "") -> dict[str, Any]:
    """Short 3080 face. Booleans and verdicts only. No raw third-handle value."""
    rows = list_assignments(tenant_id=tenant_id)
    latest = rows[-1] if rows else None
    handles = dict(latest.handles) if latest else {}
    b3 = signoff_card().get("b3") or {}
    recipe = pes_card().get("recipe") or {}
    aer = ""
    if latest and isinstance(latest.columns.get("aer_provenance"), str):
        aer = str(latest.columns.get("aer_provenance") or "")
    return {
        "has_circuit": bool(handles.get(HANDLE_CIRCUIT)),
        "has_asset": bool(handles.get(HANDLE_ASSET) or recipe.get("recipe")),
        "has_twin": bool(handles.get(HANDLE_TWIN)),
        "b3_verdict": b3.get("verdict") or "",
        "provenance": aer,
        "doctor_ok": bool(probe()["ok"]),
        "safe_mode": safe_mode_on(),
        "asks": asks_face(),
        "usage": usage_face(),
        "lamps": health_lamps(),
        "life": life_from_assignment(latest.columns if latest else {}, handles),
    }
