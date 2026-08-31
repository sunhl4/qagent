"""Q-h06 offline: pin → unapproved ask → approved swap-body refused. No twin_id."""

from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from qagent.adapters.contracts import load_product_eval_cases
from qagent.models.handles import HANDLE_CIRCUIT, HANDLE_TWIN
from qagent.services.eval_run import DEFAULT_CIRCUIT
from qagent.services.invoke import invoke
from qagent.services.product_eval import isolate_product_eval, run_product_case

_DEAD_URL = "http://127.0.0.1:1"
_SWAPPED = {
    "n_qubits": 2,
    "n_instructions": 1,
    "body": {
        "schema_version": "3",
        "ir_kind": "logical",
        "n_qubits": 2,
        "instructions": [
            {"kind": "gate", "name": "X", "qubits": [0], "params": []},
        ],
    },
}
_NOTE = ROOT / "docs" / "execution" / "Q-h06_offline.md"
_CLAIM_PASS = (
    "G3 已通过",
    "G3 passed",
    "G3 验收通过",
    "G3 通过",
    "G3通过",
)


def _case():
    return next(item for item in load_product_eval_cases() if item.id == "Q-h06")


def _no_twin_id(payload: object) -> None:
    if isinstance(payload, dict):
        assert HANDLE_TWIN not in payload


def test_qh06_product_case_ok() -> None:
    row = run_product_case(_case())
    assert row.ok and not row.skipped, row.detail
    assert row.detail != "needs live"


def test_qh06_pin_ask_swap_refused() -> None:
    with isolate_product_eval():
        assert os.environ.get("QAGENT_TWIN_URL") == _DEAD_URL
        pinned = invoke(
            "qagent_pin_circuit",
            "lab",
            {"source": "logical", "logical": DEFAULT_CIRCUIT["body"]},
        )
        assert pinned.status == "ok"
        assert pinned.payload is not None
        circuit_id = pinned.payload[HANDLE_CIRCUIT]
        matching = {
            "mode": "signoff",
            "shots": 32,
            "circuit": DEFAULT_CIRCUIT,
            HANDLE_CIRCUIT: circuit_id,
        }
        asked = invoke("ionstack_twin_run", "lab", matching)
        assert asked.status == "needs_ask"
        assert asked.decision == "ask"
        _no_twin_id(asked.payload)

        refused = invoke(
            "ionstack_twin_run",
            "lab",
            {**matching, "circuit": _SWAPPED},
            approved=True,
        )
        assert refused.status == "error"
        _no_twin_id(refused.payload)
        assert HANDLE_TWIN not in (refused.error or "")
        assert os.environ.get("QAGENT_TWIN_URL") == _DEAD_URL
        assert "8765" not in (os.environ.get("QAGENT_TWIN_URL") or "")


def test_qh06_note() -> None:
    assert _NOTE.is_file(), _NOTE
    text = _NOTE.read_text(encoding="utf-8")
    for needle in ("Q-h06", "circuit_id", "twin_id", "needs_ask", "不算 G3"):
        assert needle in text, needle
    for phrase in _CLAIM_PASS:
        assert phrase not in text, phrase


def main() -> int:
    failed = 0
    for name, fn in (
        ("product_case_ok", test_qh06_product_case_ok),
        ("pin_ask_swap", test_qh06_pin_ask_swap_refused),
        ("note", test_qh06_note),
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
