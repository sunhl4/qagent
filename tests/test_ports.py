from qagent.adapters.contracts import load_tool_catalog
from qagent.adapters.reserved import ReservedQData
from qagent.models.fill import FillSlotError
from qagent.models.handles import TWIN_ISSUER_ENGINE, may_emit_twin_id
from qagent.services.engines import list_engines
from qagent.services.ports import load_port_methods, method_for_tool


def test_every_tool_has_a_port() -> None:
    mapped = {row.tool for row in load_port_methods()}
    for spec in load_tool_catalog():
        assert spec.name in mapped, spec.name


def test_compile_estimate_stays_on_ionstack_port() -> None:
    row = method_for_tool("ionstack_compile_estimate")
    assert row.port_id == "ionstack"
    assert row.slot == "S-TWIN-03"


def test_only_ionstack_may_emit_twin_id() -> None:
    assert may_emit_twin_id("ionstack")
    assert not may_emit_twin_id("qiskit")
    assert not may_emit_twin_id("qdata")
    qiskit = next(e for e in list_engines() if e.id == "qiskit")
    assert TWIN_ISSUER_ENGINE not in qiskit.identity_fields
    assert "twin_id" not in qiskit.identity_fields


def test_science_packs_are_reserved() -> None:
    for pack in list_engines():
        assert pack.status == "reserved", pack.id


def test_reserved_qdata_does_not_call_home() -> None:
    try:
        ReservedQData().run_recipe({"name": "a2_chem_pes"})
    except FillSlotError as exc:
        assert exc.slot_id == "S-QDATA-04"
    else:
        raise AssertionError("expected FillSlotError")
