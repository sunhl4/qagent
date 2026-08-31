from __future__ import annotations

from typing import Any, Mapping

from qagent.adapters.contracts import load_engine_catalog
from qagent.models.engine import EnginePack


def _pack_from_row(row: Mapping[str, Any]) -> EnginePack:
    return EnginePack(
        id=row["id"],
        kind=row["kind"],
        label=row["label"],
        status=row["status"],
        tools=list(row.get("tools") or []),
        identity_fields=list(row.get("identity_fields") or []),
        vibe=row.get("vibe", ""),
        home=row.get("home"),
    )


def load_engine_packs() -> list[EnginePack]:
    raw = load_engine_catalog()
    return [_pack_from_row(row) for row in raw["engines"]]


def load_reserved_packs() -> list[EnginePack]:
    raw = load_engine_catalog()
    return [_pack_from_row(row) for row in raw.get("reserved_engines") or []]
