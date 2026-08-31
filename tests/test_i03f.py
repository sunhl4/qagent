"""I-03f: GET /api/eln filters by caller tenant. Empty tenant still sees all."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import traceback
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Mapping

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from qagent.entrypoints.shell_http import dispatch
from qagent.models.eln import (
    EVENT_ASSIGNMENT,
    EVENT_ESTIMATE,
    EVENT_RECIPE_PIN,
    FIELD_ASSIGNMENT_ID,
    FORBIDDEN_ELN_KEYS,
    SECRET_ELN_KEYS,
)
from qagent.models.handles import HANDLE_TWIN
from qagent.services.assignment import create
from qagent.services.eln import append_estimate, append_recipe_pin, read_eln

_ENV_KEYS = ("QAGENT_ELN_FILE", "QAGENT_ASSIGNMENTS_FILE")
_AID = "asg_i03f_src"
_TENANT_A = "cust-a"
_TENANT_B = "cust-b"
_HEADER_A = {"X-QAGENT-TENANT": _TENANT_A}
_HEADER_B = {"X-QAGENT-TENANT": _TENANT_B}
_SECRET = "sk-i03f-n3v3r-eln-7k2p"
_HPC = "i03f-hpc-n3v3r-eln-4m9q"
_QTM = "i03f-qtm-n3v3r-eln-1w8r"
_PLANTED = (_SECRET, _HPC, _QTM)
_NOTE = ROOT / "docs" / "execution" / "I-03f_eln_tenant.md"
_INTERFACES = ROOT / "INTERFACES.md"


@contextmanager
def isolated_eln() -> Iterator[Path]:
    previous = {key: os.environ.get(key) for key in ("QAGENT_ELN_FILE",)}
    tmp = tempfile.TemporaryDirectory()
    try:
        path = Path(tmp.name) / "eln.jsonl"
        os.environ["QAGENT_ELN_FILE"] = str(path)
        yield path
    finally:
        tmp.cleanup()
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


@contextmanager
def isolated_stores() -> Iterator[tuple[Path, Path]]:
    previous = {key: os.environ.get(key) for key in _ENV_KEYS}
    tmp = tempfile.TemporaryDirectory()
    try:
        eln = Path(tmp.name) / "eln.jsonl"
        assignments = Path(tmp.name) / "assignments.jsonl"
        os.environ["QAGENT_ELN_FILE"] = str(eln)
        os.environ["QAGENT_ASSIGNMENTS_FILE"] = str(assignments)
        yield eln, assignments
    finally:
        tmp.cleanup()
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _nested_keys(value: object) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, Mapping):
        for key, inner in value.items():
            keys.add(str(key))
            keys.update(_nested_keys(inner))
    elif isinstance(value, list):
        for inner in value:
            keys.update(_nested_keys(inner))
    return keys


def _get_eln(
    assignment_id: str | None = None,
    headers: Mapping[str, str] | None = None,
) -> tuple[int, dict[str, Any]]:
    path = "/api/eln"
    if assignment_id:
        path = f"/api/eln?assignment_id={assignment_id}"
    if headers is None:
        code, payload = dispatch("GET", path)
    else:
        code, payload = dispatch("GET", path, {}, headers)
    assert code == 200
    assert isinstance(payload, dict)
    assert "events" in payload
    assert isinstance(payload["events"], list)
    assert "error" not in payload
    return code, payload


def test_empty_tenant_sees_pin_and_estimate() -> None:
    with isolated_eln():
        append_recipe_pin(recipe="a2_chem_pes", params={"shots": 8}, assignment_id=_AID)
        append_estimate(makespan_ns=12.5, assignment_id=_AID)
        code, payload = _get_eln()
        assert code == 200
        types = [row.get("type") for row in payload["events"]]
        assert EVENT_RECIPE_PIN in types
        assert EVENT_ESTIMATE in types
        assert len(payload["events"]) == 2
        blob = json.dumps(payload, ensure_ascii=False)
        assert HANDLE_TWIN not in blob
        assert "hpc_secret" not in blob
        assert _HPC not in blob


def test_tenant_a_does_not_see_b() -> None:
    with isolated_stores():
        row_a = create(room="lab", brief="tenant-a-eln", tenant_id=_TENANT_A, shots=8)
        row_b = create(room="lab", brief="tenant-b-eln", tenant_id=_TENANT_B, shots=8)
        append_recipe_pin(recipe="a2_chem_pes", params={"shots": 8}, assignment_id=row_a.assignment_id)
        append_estimate(makespan_ns=12.5, assignment_id=row_b.assignment_id)
        code, from_a = _get_eln(headers=_HEADER_A)
        assert code == 200
        ids_a = {row.get(FIELD_ASSIGNMENT_ID) for row in from_a["events"]}
        assert row_a.assignment_id in ids_a
        assert row_b.assignment_id not in ids_a
        assert all(row.get(FIELD_ASSIGNMENT_ID) == row_a.assignment_id for row in from_a["events"])
        types_a = [row.get("type") for row in from_a["events"]]
        assert EVENT_RECIPE_PIN in types_a
        assert EVENT_ASSIGNMENT in types_a
        assert EVENT_ESTIMATE not in types_a
        code, from_b = _get_eln(headers=_HEADER_B)
        assert code == 200
        ids_b = {row.get(FIELD_ASSIGNMENT_ID) for row in from_b["events"]}
        assert row_b.assignment_id in ids_b
        assert row_a.assignment_id not in ids_b
        types_b = [row.get("type") for row in from_b["events"]]
        assert EVENT_ESTIMATE in types_b
        assert EVENT_RECIPE_PIN not in types_b
        code, staff = _get_eln()
        staff_ids = {row.get(FIELD_ASSIGNMENT_ID) for row in staff["events"]}
        assert row_a.assignment_id in staff_ids
        assert row_b.assignment_id in staff_ids


def test_unscoped_hidden_from_set_tenant() -> None:
    with isolated_stores():
        row_a = create(room="lab", brief="tenant-a-unscoped", tenant_id=_TENANT_A, shots=8)
        append_recipe_pin(recipe="internal-pipeline")
        append_estimate(makespan_ns=3.0, assignment_id=row_a.assignment_id)
        code, scoped = _get_eln(headers=_HEADER_A)
        assert code == 200
        assert all(row.get(FIELD_ASSIGNMENT_ID) for row in scoped["events"])
        assert not any(
            row.get("type") == EVENT_RECIPE_PIN and not row.get(FIELD_ASSIGNMENT_ID)
            for row in scoped["events"]
        )
        assert any(row.get("type") == EVENT_ESTIMATE for row in scoped["events"])
        code, staff = _get_eln()
        assert any(
            row.get("type") == EVENT_RECIPE_PIN and not row.get(FIELD_ASSIGNMENT_ID)
            for row in staff["events"]
        )


def test_foreign_assignment_query_is_empty() -> None:
    with isolated_stores():
        row_a = create(room="lab", brief="tenant-a-query", tenant_id=_TENANT_A, shots=8)
        row_b = create(room="lab", brief="tenant-b-query", tenant_id=_TENANT_B, shots=8)
        append_recipe_pin(recipe="a2_chem_pes", assignment_id=row_a.assignment_id)
        append_estimate(makespan_ns=9.0, assignment_id=row_b.assignment_id)
        code, foreign = _get_eln(row_b.assignment_id, headers=_HEADER_A)
        assert code == 200
        assert foreign == {"events": []}
        blob = json.dumps(foreign, ensure_ascii=False)
        assert HANDLE_TWIN not in blob
        assert "twin_" not in blob
        code, own = _get_eln(row_a.assignment_id, headers=_HEADER_A)
        assert code == 200
        assert own["events"]
        assert all(row.get(FIELD_ASSIGNMENT_ID) == row_a.assignment_id for row in own["events"])


def test_post_does_not_append() -> None:
    with isolated_eln() as path:
        code, payload = dispatch(
            "POST",
            "/api/eln",
            {"type": EVENT_RECIPE_PIN, "recipe": "a2_chem_pes", "hpc_secret": _HPC},
            _HEADER_A,
        )
        assert code == 404
        assert isinstance(payload, dict)
        assert not path.is_file()
        assert read_eln() == []
        code, listed = _get_eln(headers=_HEADER_A)
        assert code == 200
        assert listed["events"] == []


def test_no_secrets_circuit_or_minted_twin() -> None:
    with isolated_eln() as path:
        path.write_text(
            json.dumps(
                {
                    "type": EVENT_RECIPE_PIN,
                    FIELD_ASSIGNMENT_ID: _AID,
                    "recipe": "a2_chem_pes",
                    "llm_api_key": _SECRET,
                    "hpc_secret": _HPC,
                    "quantum_secret": _QTM,
                    "body": "OPENQASM 3; secret-circuit",
                    "qasm3": "OPENQASM 3;",
                    "params": {"shots": 8, "body": "raw-circuit", "hpc_secret": _HPC},
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        code, payload = _get_eln()
        assert code == 200
        row = payload["events"][-1]
        assert row["type"] == EVENT_RECIPE_PIN
        assert row["recipe"] == "a2_chem_pes"
        assert row["params"] == {"shots": 8}
        keys = _nested_keys(payload)
        assert not SECRET_ELN_KEYS & keys
        assert not FORBIDDEN_ELN_KEYS & keys
        assert HANDLE_TWIN not in keys
        blob = json.dumps(payload, ensure_ascii=False)
        for planted in _PLANTED:
            assert planted not in blob
        assert "secret-circuit" not in blob
        assert "OPENQASM" not in blob
        assert HANDLE_TWIN not in blob


def test_dispatch_has_no_status_local() -> None:
    text = (SRC / "qagent" / "entrypoints" / "shell_http.py").read_text(encoding="utf-8")
    body = text.split("def dispatch(", 1)[1].split("\ndef ", 1)[0]
    assert "\n        status =" not in body
    assert "status as chat_status" in text
    assert "ionstack_twin_run" not in text


def test_note_exists() -> None:
    assert _NOTE.is_file(), _NOTE
    text = _NOTE.read_text(encoding="utf-8")
    assert "GET /api/eln" in text
    assert "tenant" in text or "租户" in text
    assert "不铸" in text or "twin_id" in text
    interfaces = _INTERFACES.read_text(encoding="utf-8")
    assert "GET /api/eln" in interfaces
    assert "已设租户只见本租户交办事件" in interfaces


def main() -> int:
    failed = 0
    for name, fn in (
        ("empty_tenant_sees_pin_and_estimate", test_empty_tenant_sees_pin_and_estimate),
        ("tenant_a_does_not_see_b", test_tenant_a_does_not_see_b),
        ("unscoped_hidden_from_set_tenant", test_unscoped_hidden_from_set_tenant),
        ("foreign_assignment_query_is_empty", test_foreign_assignment_query_is_empty),
        ("post_does_not_append", test_post_does_not_append),
        ("no_secrets_circuit_or_minted_twin", test_no_secrets_circuit_or_minted_twin),
        ("dispatch_has_no_status_local", test_dispatch_has_no_status_local),
        ("note_exists", test_note_exists),
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
