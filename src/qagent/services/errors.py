from __future__ import annotations

from typing import Any

from qagent.adapters.errors import load_error_catalog
from qagent.models.errors import (
    ErrorFace,
    classify_kind,
    code_for,
    overlay_catalog,
)


def explain_failure(
    tool: str,
    message: str,
    *,
    status: str = "",
    slot: str = "",
) -> ErrorFace:
    """Map a raw invoke failure. Slot id stays a fill id, not the reason."""
    kind = classify_kind(tool, message, status=status)
    code = code_for(tool, kind)
    face = ErrorFace(
        code=code,
        kind=kind,
        severity="error",
        phase="policy" if status == "denied" else "estimate",
        retryable=kind in {"missing", "unready", "quota"},
        hint="",
        health="estimate",
        slot=slot,
        message=message,
    )
    return overlay_catalog(face, load_error_catalog())


def lookup_error(
    *,
    slot: str = "",
    code: str = "",
    tool: str = "",
    message: str = "",
    status: str = "",
) -> dict[str, Any]:
    catalog = load_error_catalog()
    if tool or message or status:
        return {
            "entry": explain_failure(tool, message, status=status, slot=slot).to_public(),
            "note": "slot is a fill id, not the reason",
        }
    entries = [row for row in (catalog.get("entries") or []) if isinstance(row, dict)]
    if code:
        return {
            "entries": [row for row in entries if row.get("code") == code],
            "note": "slot is a fill id, not the reason",
        }
    if slot:
        return {
            "entries": [row for row in entries if row.get("slot") == slot],
            "note": "same slot can mean missing, unready, or refused",
        }
    return {"entries": entries, "kinds": catalog.get("kinds") or []}
