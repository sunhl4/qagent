"""L1-03-pl: Pennylane pack reserved. Not listed. No kernel import. No third handle."""

from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from qagent.adapters.contracts import load_engine_catalog, load_eval_cases, load_policy, load_port_catalog, load_tool_catalog
from qagent.adapters.reserved import ReservedPennylane
from qagent.models.fill import FillSlotError
from qagent.models.handles import HANDLE_TWIN
from qagent.models.invoke import STATUS_DENIED
from qagent.models.ports import PennylanePort
from qagent.services.boundaries import scan_forbidden_imports
from qagent.services.engines import list_engines
from qagent.services.invoke import invoke
from qagent.services.policy import decide
from qagent.services.ports import forbidden_import_roots, method_for_tool
from qagent.services.registry import default_registry

_HANDLE = "twin" + "_id"
_SRC = ROOT / "src"
_PKG = ROOT / "packages" / "qagent-pennylane"
_NOTE = ROOT / "docs" / "execution" / "L1-03_pennylane.md"
_FIVE = ("qdata", "qchem", "ionstack", "route", "qiskit")
_PL_TOOLS = (
    "pennylane_import_circuit",
    "pennylane_export_circuit",
    "pennylane_simulator_run",
)


def _src_and_pack_text() -> str:
    blobs: list[str] = []
    for root in (_SRC / "qagent", _PKG):
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file() and path.suffix in {".py", ".ts"}:
                blobs.append(path.read_text(encoding="utf-8"))
    return "\n".join(blobs)


def test_pack_reserved_not_listed() -> None:
    raw = load_engine_catalog()
    listed = [pack.id for pack in list_engines()]
    assert listed[:5] == list(_FIVE)
    assert set(_FIVE) <= set(listed)
    assert "pennylane" not in listed
    engines = [row for row in raw.get("engines") or [] if row.get("id") == "pennylane"]
    assert not engines, "pennylane must not enter catalog engines[]"
    reserved = [row for row in raw.get("reserved_engines") or [] if row.get("id") == "pennylane"]
    assert reserved, "pennylane pack missing from catalog reserved_engines"
    pack = reserved[0]
    assert pack["status"] == "reserved"
    assert pack["kind"] == "interop"
    assert HANDLE_TWIN not in pack.get("identity_fields", [])
    assert _HANDLE not in pack.get("identity_fields", [])
    assert "circuit_id" in pack.get("identity_fields", [])
    assert "provenance" in pack.get("identity_fields", [])
    for name in _PL_TOOLS:
        assert name in pack["tools"]
    cirq_reserved = [row for row in raw.get("reserved_engines") or [] if row.get("id") == "cirq"]
    assert not cirq_reserved, "cirq must stay wired; do not put cirq back in reserved_engines"
    assert "cirq" in listed
    cirq = next(pack for pack in list_engines() if pack.id == "cirq")
    assert cirq.status == "wired"
    future = list(raw.get("future_examples") or [])
    assert "cirq" not in future
    invoked = invoke("qagent_list_engines", "lab", {})
    ids = [row["id"] for row in (invoked.payload or {}).get("engines") or []]
    assert "pennylane" not in ids
    assert "cirq" in ids


def test_no_pennylane_import_in_src() -> None:
    assert "pennylane" in forbidden_import_roots()
    hits = scan_forbidden_imports()
    assert hits == [], hits
    text = _src_and_pack_text()
    assert "import pennylane" not in text
    assert "from pennylane " not in text
    assert "from pennylane." not in text


def test_no_third_handle() -> None:
    for spec in load_tool_catalog():
        if spec.name not in _PL_TOOLS:
            continue
        keys = spec.schema.get("forbidden_output_keys") or []
        assert HANDLE_TWIN in keys, spec.name
        blob = json.dumps(spec.schema, sort_keys=True)
        assert "qccd-twin" not in blob
        assert spec.schema.get("status") == "reserved"
        if spec.name == "pennylane_simulator_run":
            assert spec.schema["output"]["properties"]["provenance"]["const"] == "pennylane"
    ports = load_port_catalog()
    row = next(item for item in ports["ports"] if item["id"] == "pennylane")
    assert row["status"] == "reserved"
    assert row["engine"] == "pennylane"
    for name in _PL_TOOLS:
        binding = method_for_tool(name)
        assert binding.port_id == "pennylane"
        assert binding.status == "reserved"


def test_reserved_fill_and_invoke_deny() -> None:
    _: type[PennylanePort] = ReservedPennylane
    port = ReservedPennylane()
    assert hasattr(port, "import_circuit")
    assert hasattr(port, "export_circuit")
    assert hasattr(port, "simulator_run")
    try:
        ReservedPennylane().import_circuit({})
    except FillSlotError as exc:
        assert exc.slot_id == "S-PL-01"
    else:
        raise AssertionError("expected FillSlotError")
    try:
        ReservedPennylane().simulator_run({"circuit_id": "c1", "shots": 8})
    except FillSlotError as exc:
        assert exc.slot_id == "S-PL-03"
    else:
        raise AssertionError("expected FillSlotError")
    registry = default_registry()
    assert not hasattr(registry, "pennylane")
    try:
        registry.get("pennylane")
    except KeyError:
        pass
    else:
        raise AssertionError("pennylane must not be on PortRegistry")
    for name in _PL_TOOLS:
        assert decide(name, "lab", {"circuit_id": "c1", "shots": 8}) == "deny"
        result = invoke(name, "lab", {"circuit_id": "c1", "shots": 8})
        assert result.decision == "deny"
        assert result.status == STATUS_DENIED
        payload = dict(result.payload or {})
        assert HANDLE_TWIN not in payload
        assert _HANDLE not in json.dumps(payload)
    assert decide(
        "pennylane_simulator_run",
        "lab",
        {"circuit_id": "c1", "shots": 8, "claim_twin_id": True},
    ) == "deny"
    claimed = invoke(
        "pennylane_simulator_run",
        "lab",
        {"circuit_id": "c1", "shots": 8, "claim_twin_id": True},
    )
    assert claimed.decision == "deny"
    assert HANDLE_TWIN not in dict(claimed.payload or {})


def test_southbound_still_forbidden() -> None:
    policy = load_policy()
    forbidden = set(policy["forbidden_tool_names"])
    assert {"cal_edit", "shuttle_write", "qiskit_ibm_run"} <= forbidden
    assert set(_PL_TOOLS) <= forbidden
    assert decide("cal_edit", "lab", {}) == "deny"
    assert decide("shuttle_write", "lab", {}) == "deny"
    assert decide("qiskit_ibm_run", "lab", {}) == "deny"


def test_package_execute_is_invoke() -> None:
    index = (_PKG / "src" / "index.ts").read_text(encoding="utf-8")
    adapter = (_PKG / "src" / "adapter.ts").read_text(encoding="utf-8")
    assert "registerInvokeTool" in index
    assert "executeTool" in adapter
    assert "import pennylane" not in index
    assert "import pennylane" not in adapter
    assert HANDLE_TWIN not in index
    assert HANDLE_TWIN not in adapter


def test_no_e23() -> None:
    assert not (ROOT / "contracts" / "eval" / "E23.json").exists()
    assert "E23" not in {row.id for row in load_eval_cases()}


def test_note_exists() -> None:
    assert _NOTE.exists()
    text = _NOTE.read_text(encoding="utf-8")
    assert "reserved_engines" in text
    assert "engines[]" in text
    assert "pennylane" in text
    assert "不接线" in text


def main() -> int:
    failed = 0
    for name, fn in (
        ("pack_reserved", test_pack_reserved_not_listed),
        ("no_pennylane_import", test_no_pennylane_import_in_src),
        ("no_third_handle", test_no_third_handle),
        ("fill_and_invoke", test_reserved_fill_and_invoke_deny),
        ("southbound_forbid", test_southbound_still_forbidden),
        ("package_invoke", test_package_execute_is_invoke),
        ("no_e23", test_no_e23),
        ("note", test_note_exists),
    ):
        try:
            fn()
            print(f"ok  {name}")
        except Exception:
            failed += 1
            print(f"FAIL {name}")
            traceback.print_exc()
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
