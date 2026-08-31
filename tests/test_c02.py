"""C-02: tenant isolation + outbound receipt. Isolates QAGENT_ASSIGNMENTS_FILE."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import traceback
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from qagent.entrypoints.shell_http import dispatch
from qagent.models.assignment import (
    RECEIPT_FORBIDDEN_KEYS,
    AssignmentError,
    receipt_payload,
    seal_receipt,
    verify_receipt,
)
from qagent.services.assignment import (
    create,
    get_assignment,
    list_assignments,
    receipt,
    verify_assignment_receipt,
)

VERIFY_SCRIPT = ROOT / "scripts" / "verify_receipt.py"
_TENANT_A = "cust-a"
_TENANT_B = "cust-b"
_HEADER_A = {"X-QAGENT-TENANT": _TENANT_A}
_HEADER_B = {"X-QAGENT-TENANT": _TENANT_B}


@contextmanager
def isolated_assignments() -> Iterator[Path]:
    previous = {
        "QAGENT_ASSIGNMENTS_FILE": os.environ.get("QAGENT_ASSIGNMENTS_FILE"),
        "QAGENT_ELN_FILE": os.environ.get("QAGENT_ELN_FILE"),
    }
    handle, name = tempfile.mkstemp(prefix="c02-asg-", suffix=".jsonl")
    os.close(handle)
    path = Path(name)
    eln_handle, eln_name = tempfile.mkstemp(prefix="c02-eln-", suffix=".jsonl")
    os.close(eln_handle)
    eln_path = Path(eln_name)
    os.environ["QAGENT_ASSIGNMENTS_FILE"] = str(path)
    os.environ["QAGENT_ELN_FILE"] = str(eln_path)
    try:
        yield path
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        path.unlink(missing_ok=True)
        eln_path.unlink(missing_ok=True)


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


def _seed_pair() -> tuple[object, object]:
    row_a = create(room="lab", brief="tenant-a-brief", tenant_id=_TENANT_A, shots=8)
    row_b = create(room="lab", brief="tenant-b-brief", tenant_id=_TENANT_B, shots=8)
    return row_a, row_b


def test_tenant_a_cannot_get_b() -> None:
    with isolated_assignments():
        _row_a, row_b = _seed_pair()
        try:
            get_assignment(row_b.assignment_id, tenant_id=_TENANT_A)
        except AssignmentError as exc:
            assert "unknown assignment_id" in str(exc)
        else:
            raise AssertionError("tenant A must not get tenant B")
        code, payload = dispatch(
            "GET",
            f"/api/assignments/{row_b.assignment_id}",
            {},
            _HEADER_A,
        )
        assert code in {404, 400}
        assert "error" in payload
        code, rec = dispatch(
            "GET",
            f"/api/assignments/{row_b.assignment_id}/receipt",
            {},
            _HEADER_A,
        )
        assert code in {404, 400}
        assert "error" in rec


def test_tenant_a_list_excludes_b() -> None:
    with isolated_assignments():
        row_a, row_b = _seed_pair()
        listed = list_assignments(tenant_id=_TENANT_A)
        ids = {row.assignment_id for row in listed}
        assert row_a.assignment_id in ids
        assert row_b.assignment_id not in ids
        code, payload = dispatch("GET", "/api/assignments", {}, _HEADER_A)
        assert code == 200
        http_ids = {row["assignment_id"] for row in payload["assignments"]}
        assert row_a.assignment_id in http_ids
        assert row_b.assignment_id not in http_ids
        code, from_b = dispatch("GET", "/api/assignments", {}, _HEADER_B)
        assert code == 200
        b_ids = {row["assignment_id"] for row in from_b["assignments"]}
        assert row_b.assignment_id in b_ids
        assert row_a.assignment_id not in b_ids


def test_empty_tenant_sees_unscoped() -> None:
    with isolated_assignments():
        unscoped = create(room="lab", brief="扫 PES", shots=32)
        assert unscoped.tenant_id == ""
        row_a, row_b = _seed_pair()
        listed = list_assignments()
        ids = {row.assignment_id for row in listed}
        assert unscoped.assignment_id in ids
        assert row_a.assignment_id in ids
        assert row_b.assignment_id in ids
        fetched = get_assignment(unscoped.assignment_id)
        assert fetched.assignment_id == unscoped.assignment_id
        code, payload = dispatch("GET", "/api/assignments")
        assert code == 200
        http_ids = {row["assignment_id"] for row in payload["assignments"]}
        assert unscoped.assignment_id in http_ids
        tenant_listed = list_assignments(tenant_id=_TENANT_A)
        tenant_ids = {row.assignment_id for row in tenant_listed}
        assert unscoped.assignment_id not in tenant_ids


def test_receipt_has_no_body_or_secrets() -> None:
    with isolated_assignments():
        row = create(
            room="lab",
            brief="receipt-scrub",
            tenant_id=_TENANT_A,
            shots=16,
            columns={
                "body": {"gates": ["H"]},
                "circuit": {"body": {"gates": ["H"]}, "qasm3": "OPENQASM 3;"},
                "token": "SECRET",
                "secret": "leak-me",
                "api_key": "sk-test",
                "password": "pw",
                "counts": {"00": 8},
                "bitstrings": ["00"],
                "identity": {
                    "preset": "t_junction",
                    "n_qubits": 8,
                    "live": False,
                    "token": "SECRET",
                },
            },
        )
        sealed = receipt(row.assignment_id, tenant_id=_TENANT_A)
        assert sealed["kind"] == "qagent/receipt"
        assert sealed["schema"] == "qagent.receipt/v1"
        assert sealed["tenant_id"] == _TENANT_A
        assert sealed["receipt_hash"].startswith("sha256:")
        keys = _walk_keys(sealed)
        leaked = RECEIPT_FORBIDDEN_KEYS & keys
        assert not leaked, leaked
        dumped = json.dumps(sealed)
        assert "SECRET" not in dumped
        assert "leak-me" not in dumped
        assert "sk-test" not in dumped
        assert '"body"' not in dumped
        assert '"circuit"' not in dumped
        assert "qasm3" not in dumped
        assert verify_receipt(sealed)["ok"] is True
        assert verify_assignment_receipt(sealed)["ok"] is True
        unscoped = create(room="lab", brief="staff-receipt", shots=8)
        staff = receipt(unscoped.assignment_id)
        assert "tenant_id" not in staff
        staff_keys = _walk_keys(staff)
        assert not (RECEIPT_FORBIDDEN_KEYS & staff_keys)


def test_verify_receipt_script_still_works() -> None:
    with isolated_assignments():
        row = create(room="lab", brief="verify-script", tenant_id=_TENANT_A, shots=8)
        sealed = seal_receipt(receipt_payload(get_assignment(row.assignment_id, tenant_id=_TENANT_A)))
        handle, name = tempfile.mkstemp(prefix="c02-rec-", suffix=".json")
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
            assert "PASS" in good.stdout
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


def test_create_body_or_header_stamps_tenant() -> None:
    with isolated_assignments():
        code, via_header = dispatch(
            "POST",
            "/api/assignments",
            {"room": "lab", "brief": "from-header", "shots": 8},
            _HEADER_A,
        )
        assert code == 200
        assert "tenant_id" not in via_header
        code, via_body = dispatch(
            "POST",
            "/api/assignments",
            {"room": "lab", "brief": "from-body", "shots": 8, "tenant_id": _TENANT_B},
            {},
        )
        assert code == 200
        assert "tenant_id" not in via_body
        code, listed_a = dispatch("GET", "/api/assignments", {}, _HEADER_A)
        ids_a = {row["assignment_id"] for row in listed_a["assignments"]}
        assert via_header["assignment_id"] in ids_a
        assert via_body["assignment_id"] not in ids_a


def main() -> int:
    failed = 0
    for name, fn in (
        ("tenant_a_cannot_get_b", test_tenant_a_cannot_get_b),
        ("tenant_a_list_excludes_b", test_tenant_a_list_excludes_b),
        ("empty_tenant_sees_unscoped", test_empty_tenant_sees_unscoped),
        ("receipt_has_no_body_or_secrets", test_receipt_has_no_body_or_secrets),
        ("verify_receipt_script_still_works", test_verify_receipt_script_still_works),
        ("create_body_or_header_stamps_tenant", test_create_body_or_header_stamps_tenant),
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
