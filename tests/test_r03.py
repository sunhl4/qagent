"""R-03: signed iff twin_id + qccd-twin; receipt hash; no un-sign."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

from qagent.adapters.assignment_store import AssignmentStore
from qagent.models.assignment import (
    RECEIPT_FORBIDDEN_KEYS,
    RECEIPT_KIND,
    RECEIPT_SCHEMA,
    SOURCE_AER,
    SOURCE_LOCAL_CARD,
    SOURCE_TWIN,
    STATUS_DRAFT,
    STATUS_SIGNED,
    Assignment,
    AssignmentError,
    can_sign,
    receipt_payload,
    seal_receipt,
    validate_status,
    verify_receipt,
)
from qagent.models.handles import HANDLE_CIRCUIT, HANDLE_TWIN
from qagent.services.assignment import cancel, reject, run, verify_assignment_receipt

QROOT = Path(__file__).resolve().parents[1]
VERIFY_SCRIPT = QROOT / "scripts" / "verify_receipt.py"


def _signed_fixture(**overrides: object) -> Assignment:
    raw = {
        "assignment_id": "asg_r03_fixture",
        "room": "sign",
        "brief": "model-layer placeholder twin_id; not minted by Aer",
        "recipe": "a2_chem_pes",
        "shots": 32,
        "status": STATUS_SIGNED,
        "handles": {HANDLE_TWIN: "twin_fixture", HANDLE_CIRCUIT: "circ_fixture"},
        "sources": [SOURCE_TWIN],
        "columns": {
            "identity": {"preset": "t_junction", "n_qubits": 8, "live": False, "token": "SECRET"},
            "counts": {"00": 16, "11": 16},
            "body": {"gates": ["H"]},
            "circuit": {"body": {"gates": ["H"]}},
            "bitstrings": ["00"],
            "stages": ["qagent_pin_circuit", "ionstack_twin_run"],
        },
    }
    raw.update(overrides)
    return Assignment.from_dict(raw)


def _walk_keys(value: object) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            keys.add(str(key))
            keys |= _walk_keys(item)
    elif isinstance(value, list):
        for item in value:
            keys |= _walk_keys(item)
    return keys


def test_can_sign_needs_both_handle_and_source() -> None:
    assert can_sign({}, []) is False
    assert can_sign({HANDLE_TWIN: "twin_x"}, []) is False
    assert can_sign({}, [SOURCE_TWIN]) is False
    assert can_sign({HANDLE_TWIN: "twin_x"}, [SOURCE_AER]) is False
    assert can_sign({HANDLE_TWIN: "twin_x"}, [SOURCE_LOCAL_CARD]) is False
    assert can_sign({HANDLE_CIRCUIT: "circ_x"}, [SOURCE_TWIN]) is False
    assert can_sign({HANDLE_TWIN: "twin_x"}, [SOURCE_TWIN]) is True


def test_validate_status_signed_without_twin_raises() -> None:
    try:
        validate_status(STATUS_SIGNED, {}, [])
    except AssignmentError as exc:
        assert "unsigned" in str(exc)
    else:
        raise AssertionError("signed without twin must raise")
    try:
        validate_status(STATUS_SIGNED, {HANDLE_TWIN: "twin_x"}, [SOURCE_AER])
    except AssignmentError as exc:
        assert "unsigned" in str(exc)
    else:
        raise AssertionError("aer provenance must not look signed")
    assert validate_status(STATUS_DRAFT, {}, []) == STATUS_DRAFT
    assert validate_status(STATUS_SIGNED, {HANDLE_TWIN: "twin_x"}, [SOURCE_TWIN]) == STATUS_SIGNED
    try:
        Assignment(
            assignment_id="asg_bad",
            room="lab",
            brief="",
            recipe="a2_chem_pes",
            shots=8,
            status=STATUS_SIGNED,
            handles={},
            sources=[SOURCE_LOCAL_CARD],
        )
    except AssignmentError as exc:
        assert "unsigned" in str(exc)
    else:
        raise AssertionError("constructor must refuse signed without twin")


def test_cancel_signed_raises() -> None:
    handle, name = tempfile.mkstemp(prefix="r03-asg-", suffix=".jsonl")
    os.close(handle)
    path = Path(name)
    previous = os.environ.get("QAGENT_ASSIGNMENTS_FILE")
    os.environ["QAGENT_ASSIGNMENTS_FILE"] = str(path)
    try:
        row = _signed_fixture()
        AssignmentStore().put(row)
        try:
            cancel(row.assignment_id)
        except AssignmentError as exc:
            assert "cannot be cancelled" in str(exc)
        else:
            raise AssertionError("signed assignment must not cancel")
        still = AssignmentStore().get(row.assignment_id)
        assert still.status == STATUS_SIGNED
        assert still.handles.get(HANDLE_TWIN) == "twin_fixture"
        try:
            reject(row.assignment_id)
        except AssignmentError as exc:
            assert "cannot be cancelled" in str(exc)
        else:
            raise AssertionError("signed assignment must not reject")
        try:
            run(row.assignment_id)
        except AssignmentError as exc:
            assert "cannot be rerun" in str(exc)
        else:
            raise AssertionError("signed assignment must not rerun")
        still = AssignmentStore().get(row.assignment_id)
        assert still.status == STATUS_SIGNED
    finally:
        if previous is None:
            os.environ.pop("QAGENT_ASSIGNMENTS_FILE", None)
        else:
            os.environ["QAGENT_ASSIGNMENTS_FILE"] = previous
        path.unlink(missing_ok=True)


def test_seal_mutate_shots_verify_fails() -> None:
    sealed = seal_receipt(receipt_payload(_signed_fixture()))
    assert verify_receipt(sealed)["ok"] is True
    assert verify_assignment_receipt(sealed)["ok"] is True
    mutated = dict(sealed)
    mutated["shots"] = 1
    assert verify_receipt(mutated)["ok"] is False
    assert verify_assignment_receipt(mutated)["ok"] is False
    tampered = dict(sealed)
    tampered["receipt_hash"] = "sha256:" + ("ab" * 32)
    assert verify_receipt(tampered)["ok"] is False
    assert verify_assignment_receipt(tampered)["ok"] is False


def test_receipt_kind_and_no_secrets() -> None:
    sealed = seal_receipt(receipt_payload(_signed_fixture()))
    assert sealed["kind"] == RECEIPT_KIND
    assert sealed["kind"] == "qagent/receipt"
    assert sealed["schema"] == RECEIPT_SCHEMA
    assert sealed["schema"] == "qagent.receipt/v1"
    assert sealed["receipt_hash"].startswith("sha256:")
    assert sealed["signed"] is True
    assert sealed["handles"].get(HANDLE_TWIN) == "twin_fixture"
    assert SOURCE_TWIN in sealed["sources"]
    keys = _walk_keys(sealed)
    leaked = RECEIPT_FORBIDDEN_KEYS & keys
    assert not leaked, leaked
    dumped = json.dumps(sealed)
    assert "SECRET" not in dumped
    assert "pauli" not in dumped.lower()
    assert "bitstring" not in dumped.lower()
    assert '"body"' not in dumped
    assert '"circuit"' not in dumped


def test_verify_receipt_script_rejects_tamper() -> None:
    sealed = seal_receipt(receipt_payload(_signed_fixture()))
    handle, name = tempfile.mkstemp(prefix="r03-rec-", suffix=".json")
    os.close(handle)
    path = Path(name)
    try:
        path.write_text(json.dumps(sealed), encoding="utf-8")
        good = subprocess.run(
            [sys.executable, str(VERIFY_SCRIPT), str(path)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert good.returncode == 0, good.stdout + good.stderr
        mutated = dict(sealed)
        mutated["shots"] = 1
        path.write_text(json.dumps(mutated), encoding="utf-8")
        bad = subprocess.run(
            [sys.executable, str(VERIFY_SCRIPT), str(path)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert bad.returncode == 1
        assert "FAIL" in bad.stdout
    finally:
        path.unlink(missing_ok=True)


def main() -> int:
    failed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
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
