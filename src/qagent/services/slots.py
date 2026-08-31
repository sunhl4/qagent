from __future__ import annotations

from qagent.adapters.contracts import load_slots as _load
from qagent.models.types import Slot


def load_slots() -> list[Slot]:
    return _load()


def empty_slots(*, phase: str | None = None) -> list[Slot]:
    slots = load_slots()
    if phase:
        slots = [s for s in slots if s.phase == phase]
    return [s for s in slots if s.status == "empty"]
