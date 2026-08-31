from __future__ import annotations

from typing import Any, NoReturn


class FillSlotError(NotImplementedError):
    """Raised when a reserved port has not been wired."""

    def __init__(self, slot_id: str, where: str, *, extra: Any = None) -> None:
        self.slot_id = slot_id
        self.where = where
        self.extra = extra
        super().__init__(f"empty slot {slot_id}: fill {where}")


def fill(slot_id: str, where: str, extra: Any = None) -> NoReturn:
    raise FillSlotError(slot_id, where, extra=extra)
