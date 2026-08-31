"""A-05b: reserved_engines pass-through. Not wired. No pytest required."""

from __future__ import annotations

import json
import re
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT
sys.path.insert(0, str(ROOT / "src"))

from qagent.models.handles import HANDLE_ASSET, HANDLE_CIRCUIT, HANDLE_TWIN
from qagent.services.engines import list_engines, list_reserved_engines
from qagent.services.invoke import invoke
from qagent.services.workplace import workplace_status

_NOTE = REPO / "docs" / "execution" / "A-05b_reserved.md"
_SCHEMA = ROOT / "contracts" / "tools" / "qagent_list_engines.json"
_SRC = (
    ROOT / "src" / "qagent" / "adapters" / "catalog.py",
    ROOT / "src" / "qagent" / "adapters" / "engines.py",
    ROOT / "src" / "qagent" / "services" / "engines.py",
    ROOT / "src" / "qagent" / "services" / "workplace.py",
)
_FIVE = ("qdata", "qchem", "ionstack", "route", "qiskit")
_HANDLES = frozenset({HANDLE_CIRCUIT, HANDLE_ASSET, HANDLE_TWIN})
_ID_RE = re.compile(r"\b[a-z]+_id\b")
_CLAIM_PASS = (
    "G0 已通过",
    "G1 已通过",
    "G2 已通过",
    "G0 passed",
    "G1 passed",
    "G2 passed",
)
_IDENTITY_OK = frozenset({HANDLE_CIRCUIT, "provenance"})


def _ids(rows: object) -> list[str]:
    return [str(row["id"]) for row in rows or [] if isinstance(row, dict) and row.get("id")]


def _row(rows: object, engine_id: str) -> dict:
    for row in rows or []:
        if isinstance(row, dict) and row.get("id") == engine_id:
            return row
    raise AssertionError(f"missing {engine_id!r}")


def test_invoke_reserved_pennylane() -> None:
    invoked = invoke("qagent_list_engines", "lab", {})
    assert invoked.status == "ok"
    payload = invoked.payload or {}
    engine_ids = _ids(payload.get("engines"))
    reserved_ids = _ids(payload.get("reserved_engines"))
    assert engine_ids[:5] == list(_FIVE)
    assert "cirq" in engine_ids
    assert "pennylane" not in engine_ids
    assert "pennylane" in reserved_ids
    assert "cirq" not in reserved_ids
    row = _row(payload.get("reserved_engines"), "pennylane")
    assert row["status"] == "reserved"
    assert row["kind"] == "interop"
    assert HANDLE_TWIN not in row
    identity = row.get("identity_fields")
    if identity is not None:
        assert set(identity) <= _IDENTITY_OK
        assert HANDLE_CIRCUIT in identity
        assert "provenance" in identity
        assert HANDLE_TWIN not in identity
    listed = [pack.id for pack in list_engines()]
    reserved = [pack.id for pack in list_reserved_engines()]
    assert "pennylane" not in listed
    assert "pennylane" in reserved
    assert "cirq" not in reserved


def test_workplace_reserved_pennylane() -> None:
    status = workplace_status()
    engine_ids = _ids(status.get("engines"))
    reserved_ids = _ids(status.get("reserved_engines"))
    assert engine_ids[:5] == list(_FIVE)
    assert "cirq" in engine_ids
    assert "pennylane" not in engine_ids
    assert "pennylane" in reserved_ids
    assert "cirq" not in reserved_ids
    row = _row(status.get("reserved_engines"), "pennylane")
    assert row["status"] == "reserved"
    assert row["kind"] == "interop"
    assert row.get("label")
    assert HANDLE_TWIN not in row
    for key in ("id", "kind", "label", "status"):
        assert key in row


def test_schema_allows_reserved_engines() -> None:
    schema = json.loads(_SCHEMA.read_text(encoding="utf-8"))
    output = schema["output"]
    assert "engines" in output["required"]
    assert "reserved_engines" in output["properties"]
    reserved = output["properties"]["reserved_engines"]
    engines = output["properties"]["engines"]
    assert reserved["type"] == "array"
    assert reserved["items"]["required"] == engines["items"]["required"]


def test_no_fourth_handle() -> None:
    blobs = [
        _NOTE.read_text(encoding="utf-8"),
        _SCHEMA.read_text(encoding="utf-8"),
    ]
    extra = set(_ID_RE.findall("\n".join(blobs))) - _HANDLES
    assert not extra, extra
    invoked = invoke("qagent_list_engines", "lab", {})
    reserved = (invoked.payload or {}).get("reserved_engines") or []
    workplace = workplace_status().get("reserved_engines") or []
    for row in list(reserved) + list(workplace):
        extra_row = set(_ID_RE.findall(json.dumps(row))) - _HANDLES
        assert not extra_row, extra_row
        assert HANDLE_TWIN not in row


def test_note_exists() -> None:
    assert _NOTE.is_file(), _NOTE
    text = _NOTE.read_text(encoding="utf-8")
    assert "不算接线" in text
    assert "reserved_engines" in text
    hits = [phrase for phrase in _CLAIM_PASS if phrase in text]
    assert not hits, hits


def test_no_pennylane_import_or_twin_assign() -> None:
    blob = "\n".join(path.read_text(encoding="utf-8") for path in _SRC)
    assert "import pennylane" not in blob
    assert "from pennylane" not in blob
    assert f"{HANDLE_TWIN}=" not in blob
    assert "import cirq" not in blob
    assert "import qdata" not in blob
    assert "import ionstack" not in blob
    assert "import qchem" not in blob
    assert "import qiskit" not in blob


def main() -> int:
    failed = 0
    for name, fn in (
        ("invoke_reserved_pennylane", test_invoke_reserved_pennylane),
        ("workplace_reserved_pennylane", test_workplace_reserved_pennylane),
        ("schema_allows_reserved_engines", test_schema_allows_reserved_engines),
        ("no_fourth_handle", test_no_fourth_handle),
        ("note_exists", test_note_exists),
        ("no_pennylane_import_or_twin_assign", test_no_pennylane_import_or_twin_assign),
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
