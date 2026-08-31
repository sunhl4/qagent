"""I-face: INTERFACES list_engines row aligns Pennylane reserved. Not wired."""

from __future__ import annotations

import re
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT
sys.path.insert(0, str(ROOT / "src"))

from qagent.services.invoke import invoke

_INTERFACES = ROOT / "INTERFACES.md"
_NOTE = REPO / "docs" / "execution" / "I-face_pennylane.md"
_HANDLES = frozenset({"circuit_id", "asset_id", "twin_id"})
_ID_RE = re.compile(r"\b[a-z]+_id\b")
_FIVE = ("qdata", "qchem", "ionstack", "route", "qiskit")
_STALE = (
    "Pennylane 已接线",
    "Cirq reserved",
    "Cirq 是 reserved",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _list_engines_row(text: str) -> str:
    for line in text.splitlines():
        if line.startswith("|") and '`invoke("qagent_list_engines")`' in line:
            return line
    raise AssertionError("missing invoke(\"qagent_list_engines\") row")


def test_list_engines_row_reserved_not_ids() -> None:
    row = _list_engines_row(_read(_INTERFACES))
    assert "五包打头" in row
    assert "wired" in row
    assert "Cirq" in row
    assert "kind=interop" in row
    assert "provenance=cirq" in row
    assert "不发" in row and "twin_id" in row
    assert "reserved_engines" in row
    assert "Pennylane" in row
    assert "不在 ids" in row
    assert "不算接线" in row
    for phrase in _STALE:
        assert phrase not in row, phrase


def test_pennylane_only_on_list_engines_row() -> None:
    hits = [line for line in _read(_INTERFACES).splitlines() if "pennylane" in line.lower()]
    assert len(hits) == 1, hits
    assert '`invoke("qagent_list_engines")`' in hits[0]


def test_invoke_ids_omit_pennylane() -> None:
    invoked = invoke("qagent_list_engines", "lab", {})
    ids = [row["id"] for row in (invoked.payload or {}).get("engines") or []]
    assert ids[:5] == list(_FIVE)
    assert "cirq" in ids
    assert "pennylane" not in ids
    for row in (invoked.payload or {}).get("engines") or []:
        if row.get("id") == "cirq":
            assert row.get("kind") == "interop"
            assert "twin_id" not in row


def test_note_exists() -> None:
    assert _NOTE.is_file(), _NOTE
    text = _read(_NOTE)
    assert "I-face" in text
    assert "reserved_engines" in text
    assert "不在 ids" in text
    assert "不算接线" in text
    assert "五包打头" in text
    assert "kind=interop" in text
    assert "不发" in text and "twin_id" in text
    assert "circuit_id" in text
    assert "asset_id" in text
    assert "twin_id" in text
    assert "INTERFACES.md" in text
    assert '`invoke("qagent_list_engines")`' in text
    assert "不要把 Pennylane 写成已接线" in text
    assert "不要把 Cirq 写回 reserved" in text


def test_no_stale_claims() -> None:
    blob = _read(_INTERFACES) + _read(_NOTE)
    hits = [phrase for phrase in _STALE if phrase in blob]
    assert not hits, hits


def test_no_fourth_handle() -> None:
    row = _list_engines_row(_read(_INTERFACES))
    extra_row = set(_ID_RE.findall(row)) - _HANDLES
    assert not extra_row, extra_row
    note = _read(_NOTE)
    found = set(_ID_RE.findall(note))
    extra = found - _HANDLES
    assert not extra, f"note invented handles: {sorted(extra)}"
    assert _HANDLES <= found


def main() -> int:
    failed = 0
    for name, fn in (
        ("list_engines_row", test_list_engines_row_reserved_not_ids),
        ("pennylane_only_that_row", test_pennylane_only_on_list_engines_row),
        ("invoke_ids", test_invoke_ids_omit_pennylane),
        ("note_exists", test_note_exists),
        ("no_stale", test_no_stale_claims),
        ("no_fourth_handle", test_no_fourth_handle),
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
