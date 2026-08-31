"""I-03: ELN kinds (five + claim_blocked), short payloads, replay field set, fork drops twin_id."""

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
sys.path.insert(0, str(ROOT / "src"))

from qagent.adapters.eln import eln_path
from qagent.models.eln import (
    ELN_EVENT_KINDS,
    EVENT_ASSIGNMENT,
    EVENT_CLAIM_BLOCKED,
    EVENT_RECIPE_PIN,
    FIELD_ASSIGNMENT_ID,
    FIELD_PARENT_ASSIGNMENT_ID,
    FORBIDDEN_ELN_KEYS,
    SECRET_ELN_KEYS,
    drop_twin,
    short_payload,
)
from qagent.models.handles import HANDLE_TWIN
from qagent.services.eln import (
    append_assignment,
    append_b3,
    append_claim_blocked,
    append_estimate,
    append_event,
    append_recipe_pin,
    append_twin_signoff,
    fork,
    read_eln,
    replay,
)

_ENV_KEYS = ("QAGENT_ELN_FILE",)
_AID = "asg_i03_src"
_FORK = "asg_i03_fork"
_OTHER = "asg_i03_other"
_SECRET = "sk-i03-n3v3r-eln-7k2p"
_HPC = "i03-hpc-n3v3r-eln-4m9q"
_QTM = "i03-qtm-n3v3r-eln-1w8r"
_PLANTED = (_SECRET, _HPC, _QTM)
_TWIN = "twin_from_qccd_rest"


@contextmanager
def isolated_eln() -> Iterator[Path]:
    previous = {key: os.environ.get(key) for key in _ENV_KEYS}
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


def _nested_keys(value: object) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, Mapping):
        for key, inner in value.items():
            keys.add(str(key))
            keys.update(_nested_keys(inner))
    return keys


def _append_kinds(assignment_id: str) -> list[Any]:
    return [
        append_recipe_pin(recipe="a2_chem_pes", params={"shots": 8}, assignment_id=assignment_id),
        append_estimate(makespan_ns=12.5, assignment_id=assignment_id),
        append_twin_signoff(twin_id=_TWIN, shots_actual=32, assignment_id=assignment_id),
        append_b3(verdict="inconclusive", assignment_id=assignment_id),
        append_assignment(assignment_id=assignment_id, status="signed", room="lab"),
        append_claim_blocked(reason="aer_claim_twin_id", assignment_id=assignment_id),
    ]


def _append_five(assignment_id: str) -> list[Any]:
    return _append_kinds(assignment_id)


def test_short_payload_strips_nested() -> None:
    cleaned = short_payload(
        {
            "recipe": "a2_chem_pes",
            "pauli_terms": [{"Z": 1}],
            "params": {"shots": 8, "bitstrings": ["00"], "llm_api_key": _SECRET},
        }
    )
    assert cleaned["recipe"] == "a2_chem_pes"
    assert cleaned["params"] == {"shots": 8}
    assert not FORBIDDEN_ELN_KEYS & _nested_keys(cleaned)
    assert not SECRET_ELN_KEYS & _nested_keys(cleaned)
    assert HANDLE_TWIN not in drop_twin({"shots_actual": 32, HANDLE_TWIN: _TWIN})


def test_append_five_kinds() -> None:
    with isolated_eln() as path:
        assert eln_path() == path
        written = _append_kinds(_AID)
        append_recipe_pin(recipe="a2_chem_pes", assignment_id=_OTHER)
        rows = replay(_AID)
        assert [row["type"] for row in rows] == list(ELN_EVENT_KINDS)
        assert [event.type for event in written] == list(ELN_EVENT_KINDS)
        assert all(row.get(FIELD_ASSIGNMENT_ID) == _AID for row in rows)
        assert [row["type"] for row in replay(_OTHER)] == [EVENT_RECIPE_PIN]


def test_forbidden_keys_stripped() -> None:
    with isolated_eln():
        append_event(
            EVENT_RECIPE_PIN,
            {
                FIELD_ASSIGNMENT_ID: _AID,
                "recipe": "a2_chem_pes",
                "pauli_terms": [{"Z": 1}],
                "bitstrings": ["00"],
                "rows": [1],
                "counts_full": {"00": 1},
                "qasm3": "OPENQASM 3;",
                "body": "secret-circuit",
                "params": {"shots": 8, "cal": {}, "shuttle": 1, "ms_matrix": []},
            },
        )
        row = replay(_AID)[-1]
        assert row["recipe"] == "a2_chem_pes"
        assert row["params"] == {"shots": 8}
        assert not FORBIDDEN_ELN_KEYS & _nested_keys(row)


def test_replay_same_field_set() -> None:
    with isolated_eln():
        written = _append_kinds(_AID)
        first = replay(_AID)
        second = replay(_AID)
        expected = [{"type", *event.payload} for event in written]
        assert [set(row) for row in first] == expected
        assert [set(row) for row in second] == expected
        assert first == second
        assert read_eln(assignment_id=_AID) == first


def test_no_secret_values() -> None:
    with isolated_eln():
        append_event(
            EVENT_RECIPE_PIN,
            {
                FIELD_ASSIGNMENT_ID: _AID,
                "recipe": "a2_chem_pes",
                "llm_api_key": _SECRET,
                "hpc_secret": _HPC,
                "quantum_secret": _QTM,
                "params": {"shots": 8, "llm_api_key": _SECRET},
            },
        )
        rows = replay(_AID)
        blob = json.dumps(rows, ensure_ascii=False)
        for planted in _PLANTED:
            assert planted not in blob
        assert not SECRET_ELN_KEYS & _nested_keys(rows[-1])


def test_fork_drops_twin_and_records_parent() -> None:
    with isolated_eln():
        _append_kinds(_AID)
        before = [set(row) for row in replay(_AID)]
        recorded = fork(_AID, _FORK, room="lab")
        assert HANDLE_TWIN not in recorded.payload
        assert recorded.payload[FIELD_PARENT_ASSIGNMENT_ID] == _AID
        assert recorded.payload[FIELD_ASSIGNMENT_ID] == _FORK
        assert recorded.payload["status"] == "draft"
        original = replay(_AID)
        assert [set(row) for row in original] == before
        assert any(row.get(HANDLE_TWIN) == _TWIN for row in original)
        forked = replay(_FORK)
        assert HANDLE_TWIN not in _nested_keys(forked)
        assert any(
            row.get("type") == EVENT_ASSIGNMENT
            and row.get(FIELD_PARENT_ASSIGNMENT_ID) == _AID
            for row in forked
        )
        blob = json.dumps(forked, ensure_ascii=False)
        assert _TWIN not in blob
        for planted in _PLANTED:
            assert planted not in blob


def test_claim_blocked_jsonl_stays_flat() -> None:
    with isolated_eln():
        append_claim_blocked(reason="aer_claim_twin_id")
        rows = [row for row in read_eln() if row.get("type") == EVENT_CLAIM_BLOCKED]
        assert rows[-1]["reason"] == "aer_claim_twin_id"
        assert "payload" not in rows[-1]


def main() -> int:
    failed = 0
    for name, fn in (
        ("short_payload_strips_nested", test_short_payload_strips_nested),
        ("append_five_kinds", test_append_five_kinds),
        ("forbidden_keys_stripped", test_forbidden_keys_stripped),
        ("replay_same_field_set", test_replay_same_field_set),
        ("no_secret_values", test_no_secret_values),
        ("fork_drops_twin_and_records_parent", test_fork_drops_twin_and_records_parent),
        ("claim_blocked_jsonl_stays_flat", test_claim_blocked_jsonl_stays_flat),
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
