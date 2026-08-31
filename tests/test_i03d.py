"""I-03d: read-only GET /api/eln. No client append. No minted twin_id."""

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
    EVENT_ESTIMATE,
    EVENT_RECIPE_PIN,
    FIELD_ASSIGNMENT_ID,
    FORBIDDEN_ELN_KEYS,
    SECRET_ELN_KEYS,
)
from qagent.models.handles import HANDLE_TWIN
from qagent.services.eln import (
    append_estimate,
    append_recipe_pin,
    append_twin_signoff,
    fork,
    read_eln,
)

_ENV_KEYS = ("QAGENT_ELN_FILE",)
_AID = "asg_i03d_src"
_OTHER = "asg_i03d_other"
_FORK = "asg_i03d_fork"
_SECRET = "sk-i03d-n3v3r-eln-7k2p"
_HPC = "i03d-hpc-n3v3r-eln-4m9q"
_QTM = "i03d-qtm-n3v3r-eln-1w8r"
_PLANTED = (_SECRET, _HPC, _QTM)
_TWIN = "twin_from_qccd_rest"
_NOTE = ROOT / "docs" / "execution" / "I-03d_eln_http.md"


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
    elif isinstance(value, list):
        for inner in value:
            keys.update(_nested_keys(inner))
    return keys


def _get_eln(assignment_id: str | None = None) -> tuple[int, dict[str, Any]]:
    path = "/api/eln"
    if assignment_id:
        path = f"/api/eln?assignment_id={assignment_id}"
    code, payload = dispatch("GET", path)
    assert code == 200
    assert isinstance(payload, dict)
    assert "events" in payload
    assert isinstance(payload["events"], list)
    return code, payload


def test_get_empty_list() -> None:
    with isolated_eln() as path:
        assert not path.is_file()
        code, payload = _get_eln()
        assert code == 200
        assert payload == {"events": []}
        assert read_eln() == []


def test_get_sees_pin_and_estimate() -> None:
    with isolated_eln():
        append_recipe_pin(recipe="a2_chem_pes", params={"shots": 8}, assignment_id=_AID)
        append_estimate(makespan_ns=12.5, assignment_id=_AID)
        code, payload = _get_eln()
        assert code == 200
        types = [row.get("type") for row in payload["events"]]
        assert EVENT_RECIPE_PIN in types
        assert EVENT_ESTIMATE in types
        blob = json.dumps(payload, ensure_ascii=False)
        assert HANDLE_TWIN not in blob
        assert "hpc_secret" not in blob
        assert _HPC not in blob
        keys = _nested_keys(payload)
        assert HANDLE_TWIN not in keys
        assert "hpc_secret" not in keys
        assert not SECRET_ELN_KEYS & keys


def test_assignment_id_filter() -> None:
    with isolated_eln():
        append_recipe_pin(recipe="a2_chem_pes", params={"shots": 8}, assignment_id=_AID)
        append_estimate(makespan_ns=12.5, assignment_id=_OTHER)
        code, filtered = _get_eln(_AID)
        assert code == 200
        assert [row.get("type") for row in filtered["events"]] == [EVENT_RECIPE_PIN]
        assert all(row.get(FIELD_ASSIGNMENT_ID) == _AID for row in filtered["events"])
        code, other = _get_eln(_OTHER)
        assert code == 200
        assert [row.get("type") for row in other["events"]] == [EVENT_ESTIMATE]
        code, all_rows = _get_eln()
        assert code == 200
        assert len(all_rows["events"]) == 2


def test_get_strips_secrets_and_body() -> None:
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
        blob = json.dumps(payload, ensure_ascii=False)
        for planted in _PLANTED:
            assert planted not in blob
        assert "secret-circuit" not in blob
        assert "OPENQASM" not in blob


def test_post_does_not_append() -> None:
    with isolated_eln() as path:
        code, payload = dispatch(
            "POST",
            "/api/eln",
            {"type": EVENT_RECIPE_PIN, "recipe": "a2_chem_pes", "hpc_secret": _HPC},
        )
        assert code == 404
        assert isinstance(payload, dict)
        assert not path.is_file()
        assert read_eln() == []
        code, listed = _get_eln()
        assert code == 200
        assert listed["events"] == []


def test_fork_still_drops_twin_id() -> None:
    with isolated_eln():
        append_recipe_pin(recipe="a2_chem_pes", assignment_id=_AID)
        append_estimate(makespan_ns=4.0, assignment_id=_AID)
        append_twin_signoff(twin_id=_TWIN, shots_actual=32, assignment_id=_AID)
        fork(_AID, _FORK, room="lab")
        code, payload = _get_eln(_FORK)
        assert code == 200
        keys = _nested_keys(payload)
        assert HANDLE_TWIN not in keys
        blob = json.dumps(payload, ensure_ascii=False)
        assert _TWIN not in blob
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
    assert "assignment_id" in text
    assert "不铸" in text or "twin_id" in text


def main() -> int:
    failed = 0
    for name, fn in (
        ("get_empty_list", test_get_empty_list),
        ("get_sees_pin_and_estimate", test_get_sees_pin_and_estimate),
        ("assignment_id_filter", test_assignment_id_filter),
        ("get_strips_secrets_and_body", test_get_strips_secrets_and_body),
        ("post_does_not_append", test_post_does_not_append),
        ("fork_still_drops_twin_id", test_fork_still_drops_twin_id),
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
