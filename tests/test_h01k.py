"""H-01k: TwinRun accepts pinned circuit_id. Skip-as-green is incomplete."""

from __future__ import annotations

import re
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from qagent.adapters.pin import NativePin
from qagent.models.handles import HANDLE_ASSET, HANDLE_CIRCUIT, HANDLE_TWIN
from qagent.services.invoke import invoke

NOTE = ROOT / "docs" / "execution" / "H-01k_twin_run_circuit_id.md"
TWIN = ROOT / "packages" / "qagent-twin" / "src" / "index.ts"
ION = ROOT / "src" / "qagent" / "adapters" / "ionstack.py"
ASSIGNMENT = ROOT / "src" / "qagent" / "services" / "assignment.py"
_HANDLES = frozenset({HANDLE_CIRCUIT, HANDLE_ASSET, HANDLE_TWIN})
_KNOWN = _HANDLES | {"rpc_id", "approval_id", "sessionId"}
_ID_RE = re.compile(r"\b[a-z]+_id\b")


def _text(path: Path) -> str:
    assert path.is_file(), f"missing {path}"
    return path.read_text(encoding="utf-8")


def test_note() -> None:
    text = _text(NOTE)
    assert "H-01k" in text
    assert "circuit_id" in text
    assert "pipeline" in text
    assert "S-TWIN-02" in text
    assert "twin_id" in text
    assert "不算 G0" in text
    print("note names circuit_id resolve")


def test_dsh_requires_pipeline_fields() -> None:
    text = _text(TWIN)
    assert "H-01k" not in text or "circuit_id" in text
    assert 'registerInvokeTool(ctx, "ionstack_twin_run"' in text
    assert '"mode"' in text or "mode:" in text
    assert "pipeline" in text
    assert "circuit_id" in text
    assert "Never call with {}" in text or "Never call with {}." in text
    print("dsh twin_run asks for mode shots circuit_id")


def test_empty_still_errors() -> None:
    empty = invoke("ionstack_twin_run", "lab", {}, approved=True)
    assert empty.status != "ok"
    assert not (empty.payload or {}).get(HANDLE_TWIN)
    print("empty args still fail, no twin_id")


def test_circuit_id_unapproved_asks() -> None:
    pinned = NativePin().pin_circuit({"source": "qdata", "asset_id": "asset_h01k"})
    circuit_id = pinned[HANDLE_CIRCUIT]
    asked = invoke(
        "ionstack_twin_run",
        "lab",
        {"mode": "pipeline", "shots": 8, HANDLE_CIRCUIT: circuit_id},
        approved=False,
    )
    assert asked.status == "needs_ask"
    assert not (asked.payload or {}).get(HANDLE_TWIN)
    print(f"unapproved circuit_id asks circuit_id={circuit_id}")


def test_circuit_id_approved_does_not_mint() -> None:
    pinned = NativePin().pin_circuit({"source": "qdata", "asset_id": "asset_h01k_live"})
    circuit_id = pinned[HANDLE_CIRCUIT]
    got = invoke(
        "ionstack_twin_run",
        "lab",
        {"mode": "pipeline", "shots": 8, HANDLE_CIRCUIT: circuit_id},
        approved=True,
    )
    twin = (got.payload or {}).get(HANDLE_TWIN)
    assert got.status != "ok"
    assert not twin
    err = (got.error or "").lower()
    assert "logical.body" in err or "fall back" in err or "h+cx" in err
    print(f"approved circuit_id without body honest {got.status} {got.error}")


def test_no_fourth_handle_or_extra_pipeline() -> None:
    for path in (NOTE, TWIN):
        for match in _ID_RE.findall(_text(path)):
            assert match in _KNOWN, (path.name, match)
    assert "circuit.body or circuit_id" in _text(ION)
    assert _text(ASSIGNMENT).count('"mode": "pipeline"') == 3
    print("still three handles; pipeline count frozen")


def main() -> int:
    failed = 0
    for name, fn in (
        ("note", test_note),
        ("dsh_requires_pipeline_fields", test_dsh_requires_pipeline_fields),
        ("empty_still_errors", test_empty_still_errors),
        ("circuit_id_unapproved_asks", test_circuit_id_unapproved_asks),
        ("circuit_id_approved_does_not_mint", test_circuit_id_approved_does_not_mint),
        ("no_fourth_handle_or_extra_pipeline", test_no_fourth_handle_or_extra_pipeline),
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
