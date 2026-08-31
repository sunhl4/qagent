from __future__ import annotations

from qagent.adapters.engines import load_engine_packs, load_reserved_packs
from qagent.models.engine import EnginePack


def list_engines() -> list[EnginePack]:
    return load_engine_packs()


def list_reserved_engines() -> list[EnginePack]:
    return load_reserved_packs()


def require_engine(engine_id: str) -> EnginePack:
    for pack in list_engines():
        if pack.id == engine_id:
            return pack
    raise KeyError(f"unknown engine pack {engine_id!r}; add it in contracts/engines/catalog.json")
