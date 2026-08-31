from __future__ import annotations

from qagent.services.slots import empty_slots, load_slots


def main() -> int:
    slots = load_slots()
    empty = empty_slots()
    print(f"{len(empty)}/{len(slots)} empty")
    for slot in empty:
        print(f"{slot.id}\t{slot.phase}\t{slot.fill}\t{slot.title}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
