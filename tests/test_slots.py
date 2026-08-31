from qagent.adapters.contracts import ROOT, load_slots
from qagent.services.fill import FillSlotError, fill
from qagent.services.slots import empty_slots


def test_fill_raises() -> None:
    try:
        fill("S-QDATA-04", "qdata_run_recipe.execute")
    except FillSlotError as exc:
        assert exc.slot_id == "S-QDATA-04"
    else:
        raise AssertionError("expected FillSlotError")


def test_no_empty_slots() -> None:
    assert empty_slots() == []


def test_slot_fill_paths_are_declared() -> None:
    for slot in load_slots():
        assert slot.fill
        target = ROOT / slot.fill
        if slot.fill.endswith((".ts", ".yml", ".md", ".py")):
            assert target.exists(), slot.fill
        elif slot.fill == "pins.json":
            assert (ROOT / "pins.json").exists()
