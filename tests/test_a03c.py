"""A-03c TwinRun ask/resume. Isolates QAGENT_TWIN_URL. No pytest required."""

from __future__ import annotations

import os
import sys
import traceback
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from qagent.adapters.ionstack import WiredIonstack
from qagent.models.handles import HANDLE_CIRCUIT, HANDLE_TWIN
from qagent.services.eval_run import DEFAULT_CIRCUIT
from qagent.services.invoke import invoke

_DEAD_URL = "http://127.0.0.1:1"
_TWIN_ARGS = {"mode": "signoff", "shots": 32, "circuit": DEFAULT_CIRCUIT}
_SWAPPED_CIRCUIT = {
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


@contextmanager
def isolated_twin_url(url: str = _DEAD_URL) -> Iterator[None]:
    previous = os.environ.get("QAGENT_TWIN_URL")
    os.environ["QAGENT_TWIN_URL"] = url
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("QAGENT_TWIN_URL", None)
        else:
            os.environ["QAGENT_TWIN_URL"] = previous


def _no_twin_id(payload: object) -> None:
    if isinstance(payload, dict):
        assert HANDLE_TWIN not in payload


def test_unapproved_twin_run_needs_ask() -> None:
    with isolated_twin_url():
        asked = invoke("ionstack_twin_run", "lab", _TWIN_ARGS)
    assert asked.status == "needs_ask"
    assert asked.decision == "ask"
    _no_twin_id(asked.payload)


def test_approved_dead_url_errors_without_twin_id() -> None:
    with isolated_twin_url():
        dead = invoke("ionstack_twin_run", "lab", _TWIN_ARGS, approved=True)
    assert dead.status == "error"
    _no_twin_id(dead.payload)
    assert "twin_id" in (dead.error or "")


def test_swap_circuit_under_same_id_refused() -> None:
    pinned = invoke(
        "qagent_pin_circuit",
        "lab",
        {"source": "logical", "logical": DEFAULT_CIRCUIT["body"]},
    )
    assert pinned.status == "ok"
    assert pinned.payload is not None
    circuit_id = pinned.payload[HANDLE_CIRCUIT]
    matching = {**_TWIN_ARGS, HANDLE_CIRCUIT: circuit_id}
    asked = invoke("ionstack_twin_run", "lab", matching)
    assert asked.status == "needs_ask"
    _no_twin_id(asked.payload)

    swapped = {**matching, "circuit": _SWAPPED_CIRCUIT}
    with isolated_twin_url():
        try:
            WiredIonstack().twin_run(swapped)
        except ValueError as exc:
            assert "circuit.body" in str(exc)
            assert "circuit_id" in str(exc)
        else:
            raise AssertionError("expected ValueError when circuit.body is swapped")
        refused = invoke("ionstack_twin_run", "lab", swapped, approved=True)
    assert refused.status == "error"
    _no_twin_id(refused.payload)
    assert HANDLE_TWIN not in (refused.error or "")

    with isolated_twin_url():
        same = invoke("ionstack_twin_run", "lab", matching, approved=True)
    assert same.status == "error"
    _no_twin_id(same.payload)
    assert "circuit.body does not match" not in (same.error or "")


def main() -> int:
    failed = 0
    for name, fn in (
        ("unapproved_needs_ask", test_unapproved_twin_run_needs_ask),
        ("approved_dead_url", test_approved_dead_url_errors_without_twin_id),
        ("swap_circuit_refused", test_swap_circuit_under_same_id_refused),
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
