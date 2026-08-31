from __future__ import annotations

from typing import Any, Mapping

from qagent.adapters.engines import load_engine_packs, load_reserved_packs
from qagent.adapters.preset import active_preset, set_active_preset
from qagent.models.engine import EnginePack


def _listed_row(pack: EnginePack) -> dict[str, Any]:
    return {
        "id": pack.id,
        "kind": pack.kind,
        "status": pack.status,
        "tools": pack.tools,
        "identity_fields": pack.identity_fields,
    }


class NativeCatalog:
    """Qagent-owned. Does not import science packages."""

    def list_engines(self, args: Mapping[str, Any]) -> dict[str, Any]:
        previous = active_preset()
        switched = args.get("preset") is not None
        if switched:
            set_active_preset(str(args.get("preset") or ""))
        face = {
            "engines": [_listed_row(pack) for pack in load_engine_packs()],
            "reserved_engines": [_listed_row(pack) for pack in load_reserved_packs()],
            "active_preset": active_preset(),
        }
        if switched:
            face["switched"] = True
            face["previous_preset"] = previous
            face["hint"] = "带 preset 会切会话。只读请不要传 preset。"
        return face
