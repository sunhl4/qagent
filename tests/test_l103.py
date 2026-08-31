"""L1-03: Cirq pack may be listed. No kernel import. No third handle. Five packs still lead list_engines."""

from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from qagent.adapters.contracts import load_engine_catalog, load_port_catalog, load_tool_catalog
from qagent.adapters.reserved import ReservedCirq
from qagent.models.fill import FillSlotError
from qagent.models.handles import HANDLE_TWIN
from qagent.models.ports import CirqPort
from qagent.services.boundaries import scan_forbidden_imports
from qagent.services.engines import list_engines
from qagent.services.eval_run import run_evals
from qagent.services.invoke import invoke
from qagent.services.ports import forbidden_import_roots, method_for_tool

_HANDLE = "twin" + "_id"
_SRC = ROOT / "src"
_PKG = ROOT / "packages" / "qagent-cirq"
_NOTE = ROOT / "docs" / "execution" / "L1-03_add_pack.md"
_FIVE = ("qdata", "qchem", "ionstack", "route", "qiskit")
_CIRQ_TOOLS = (
    "cirq_import_circuit",
    "cirq_export_circuit",
    "cirq_simulator_run",
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


def test_pack_exists_reserved() -> None:
    raw = load_engine_catalog()
    listed = [pack.id for pack in list_engines()]
    assert listed[:5] == list(_FIVE)
    assert set(_FIVE) <= set(listed)
    reserved = [row for row in raw.get("reserved_engines") or [] if row.get("id") == "cirq"]
    engines = [row for row in raw.get("engines") or [] if row.get("id") == "cirq"]
    if "cirq" not in listed:
        assert reserved, "cirq pack missing from catalog reserved_engines"
        pack = reserved[0]
        assert pack["status"] == "reserved"
    else:
        assert not reserved, "cirq must not stay reserved after it is listed"
        assert engines, "cirq listed but missing from catalog engines[]"
        pack = engines[0]
        assert pack["status"] == "wired"
        assert listed[5] == "cirq"
    if "cirq" in listed or reserved:
        pack = (engines or reserved)[0]
        assert pack["kind"] == "interop"
        assert HANDLE_TWIN not in pack.get("identity_fields", [])
        assert _HANDLE not in pack.get("identity_fields", [])
        for name in _CIRQ_TOOLS:
            assert name in pack["tools"]


def test_no_cirq_import_in_src() -> None:
    assert "cirq" in forbidden_import_roots()
    hits = scan_forbidden_imports()
    assert hits == [], hits
    text = _src_and_pack_text()
    assert "import cirq" not in text
    assert "from cirq " not in text
    assert "from cirq." not in text


def test_no_third_handle() -> None:
    for spec in load_tool_catalog():
        if spec.name not in _CIRQ_TOOLS:
            continue
        keys = spec.schema.get("forbidden_output_keys") or []
        assert HANDLE_TWIN in keys, spec.name
        blob = json.dumps(spec.schema, sort_keys=True)
        assert "qccd-twin" not in blob
        if spec.name == "cirq_simulator_run":
            assert spec.schema["output"]["properties"]["provenance"]["const"] == "cirq"
    ports = load_port_catalog()
    cirq = next(row for row in ports["ports"] if row["id"] == "cirq")
    assert cirq["status"] == "wired"
    assert cirq["engine"] == "cirq"
    for name in _CIRQ_TOOLS:
        row = method_for_tool(name)
        assert row.port_id == "cirq"
        assert row.status == "wired"


def test_reserved_fill_and_invoke_deny() -> None:
    _: type[CirqPort] = ReservedCirq
    port = ReservedCirq()
    assert hasattr(port, "import_circuit")
    assert hasattr(port, "export_circuit")
    assert hasattr(port, "simulator_run")
    try:
        ReservedCirq().import_circuit({})
    except FillSlotError as exc:
        assert exc.slot_id == "S-CIRQ-01"
    else:
        raise AssertionError("expected FillSlotError")
    try:
        ReservedCirq().simulator_run({"circuit_id": "c1", "shots": 8})
    except FillSlotError as exc:
        assert exc.slot_id == "S-CIRQ-03"
    else:
        raise AssertionError("expected FillSlotError")
    for name in _CIRQ_TOOLS:
        result = invoke(name, "lab", {"circuit_id": "c1", "shots": 8})
        payload = dict(result.payload or {})
        assert HANDLE_TWIN not in payload
        assert _HANDLE not in json.dumps(payload)


def test_package_execute_is_invoke() -> None:
    index = (_PKG / "src" / "index.ts").read_text(encoding="utf-8")
    adapter = (_PKG / "src" / "adapter.ts").read_text(encoding="utf-8")
    assert "registerInvokeTool" in index
    assert "executeTool" in adapter
    assert "import cirq" not in index
    assert "import cirq" not in adapter
    assert HANDLE_TWIN not in index
    assert HANDLE_TWIN not in adapter


def test_e22_handles_only() -> None:
    rows = {row.id: row for row in run_evals("E22")}
    assert "E22" in rows
    assert rows["E22"].ok, rows["E22"].detail


def test_note_exists() -> None:
    assert _NOTE.exists()
    text = _NOTE.read_text(encoding="utf-8")
    assert "test_engines" in text
    assert "reserved" in text


def main() -> int:
    failed = 0
    for name, fn in (
        ("pack_reserved", test_pack_exists_reserved),
        ("no_cirq_import", test_no_cirq_import_in_src),
        ("no_third_handle", test_no_third_handle),
        ("fill_and_invoke", test_reserved_fill_and_invoke_deny),
        ("package_invoke", test_package_execute_is_invoke),
        ("e22", test_e22_handles_only),
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
