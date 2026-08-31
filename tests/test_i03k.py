"""I-03k: GET /api/eln washes twin_id. Disk signoff may keep it. Not G2."""

from __future__ import annotations

import json
import os
import re
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
    EVENT_CLAIM_BLOCKED,
    EVENT_RECIPE_PIN,
    EVENT_TWIN_SIGNOFF,
    FIELD_ASSIGNMENT_ID,
    FORBIDDEN_ELN_KEYS,
    SECRET_ELN_KEYS,
)
from qagent.models.handles import HANDLE_TWIN, HANDLES
from qagent.services.eln import append_claim_blocked, append_recipe_pin, append_twin_signoff

_ENV_KEYS = ("QAGENT_ELN_FILE",)
_AID = "asg_i03k_src"
_SECRET = "sk-i03k-n3v3r-eln-7k2p"
_HPC = "i03k-hpc-n3v3r-eln-4m9q"
_QTM = "i03k-qtm-n3v3r-eln-1w8r"
_PLANTED = (_SECRET, _HPC, _QTM)
_TWIN = "twin_from_qccd_rest"
_REASON = "claim_blocked_no_signoff"
_NOTE = ROOT / "docs" / "execution" / "I-03k_eln_http.md"
_SHELL = SRC / "qagent" / "entrypoints" / "shell_http.py"
_ALLOWED_IDS = frozenset({FIELD_ASSIGNMENT_ID})
_ID_RE = re.compile(r"\b[a-z]+_id\b")
_CLAIM_PASS = ("G0 已通过", "G2 已通过", "G0 passed", "G2 passed")
_SCIENCE = ("qdata", "ionstack", "qchem", "qiskit", "pennylane")


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


def _assert_clean_events(payload: Mapping[str, Any]) -> None:
    keys = _nested_keys(payload)
    assert HANDLE_TWIN not in keys
    assert not SECRET_ELN_KEYS & keys
    assert not FORBIDDEN_ELN_KEYS & keys
    assert "body" not in keys
    assert "qasm" not in keys
    assert "qasm3" not in keys
    extra = {key for key in keys if key.endswith("_id")} - _ALLOWED_IDS
    assert not extra, extra
    blob = json.dumps(payload, ensure_ascii=False)
    assert HANDLE_TWIN not in blob
    assert _TWIN not in blob
    for planted in _PLANTED:
        assert planted not in blob
    assert "secret-circuit" not in blob
    assert "OPENQASM" not in blob
    assert "raw-circuit" not in blob


def _get_eln() -> tuple[int, dict[str, Any]]:
    code, payload = dispatch("GET", "/api/eln")
    assert code == 200
    assert isinstance(payload, dict)
    assert "events" in payload
    assert isinstance(payload["events"], list)
    return code, payload


def _plant_fat_lines(path: Path) -> None:
    fat_pin = {
        "type": EVENT_RECIPE_PIN,
        FIELD_ASSIGNMENT_ID: _AID,
        "recipe": "a2_chem_pes",
        HANDLE_TWIN: _TWIN,
        "llm_api_key": _SECRET,
        "hpc_secret": _HPC,
        "quantum_secret": _QTM,
        "body": "OPENQASM 3; secret-circuit",
        "qasm3": "OPENQASM 3;",
        "params": {"shots": 8, "body": "raw-circuit", "hpc_secret": _HPC, HANDLE_TWIN: _TWIN},
    }
    fat_signoff = {
        "type": EVENT_TWIN_SIGNOFF,
        FIELD_ASSIGNMENT_ID: _AID,
        HANDLE_TWIN: _TWIN,
        "shots_actual": 64,
        "llm_api_key": _SECRET,
        "hpc_secret": _HPC,
        "quantum_secret": _QTM,
        "body": "OPENQASM 3; secret-circuit",
        "qasm3": "OPENQASM 3;",
    }
    fat_blocked = {
        "type": EVENT_CLAIM_BLOCKED,
        FIELD_ASSIGNMENT_ID: _AID,
        "reason": _REASON,
        HANDLE_TWIN: _TWIN,
        "body": "OPENQASM 3; secret-circuit",
        "hpc_secret": _HPC,
    }
    with path.open("a", encoding="utf-8") as handle:
        for row in (fat_pin, fat_signoff, fat_blocked):
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def test_eln_get_drops_twin_keeps_face() -> None:
    with isolated_eln() as path:
        append_twin_signoff(twin_id=_TWIN, shots_actual=32, assignment_id=_AID)
        on_disk = path.read_text(encoding="utf-8")
        assert HANDLE_TWIN in on_disk
        assert _TWIN in on_disk
        append_recipe_pin(recipe="a2_chem_pes", params={"shots": 8}, assignment_id=_AID)
        append_claim_blocked(reason=_REASON, assignment_id=_AID)
        _plant_fat_lines(path)

        code, payload = _get_eln()
        assert code == 200
        events = payload["events"]
        assert events
        types = [row.get("type") for row in events]
        assert EVENT_TWIN_SIGNOFF in types
        assert EVENT_RECIPE_PIN in types
        assert EVENT_CLAIM_BLOCKED in types
        for row in events:
            assert row.get("type")
            assert row.get(FIELD_ASSIGNMENT_ID) == _AID
            assert HANDLE_TWIN not in row
        signoff = next(row for row in events if row.get("type") == EVENT_TWIN_SIGNOFF)
        assert signoff.get(FIELD_ASSIGNMENT_ID) == _AID
        pin = next(
            row
            for row in events
            if row.get("type") == EVENT_RECIPE_PIN and row.get("params") == {"shots": 8}
        )
        assert pin.get("recipe") == "a2_chem_pes"
        assert pin.get("params") == {"shots": 8}
        blocked = next(row for row in events if row.get("type") == EVENT_CLAIM_BLOCKED)
        assert blocked.get("reason") == _REASON
        _assert_clean_events(payload)

        code, posted = dispatch(
            "POST",
            "/api/eln",
            {"type": EVENT_TWIN_SIGNOFF, HANDLE_TWIN: _TWIN, "hpc_secret": _HPC},
        )
        assert code == 404
        assert isinstance(posted, dict)
        assert HANDLE_TWIN in path.read_text(encoding="utf-8")
        code, listed = _get_eln()
        assert code == 200
        _assert_clean_events(listed)


def test_eln_http_source_has_no_fourth_handle() -> None:
    text = _SHELL.read_text(encoding="utf-8")
    body = text.split("def _eln_http(", 1)[1].split("\ndef ", 1)[0]
    assert "drop_twin" in body
    assert "short_payload" in body
    assert "short_payload(drop_twin(row))" in body
    extra = set(_ID_RE.findall(body)) - _ALLOWED_IDS - frozenset({"tenant_id"}) - set(HANDLES)
    assert not extra, extra
    for name in _SCIENCE:
        assert name not in body, name
        assert f"import {name}" not in text


def test_note_exists() -> None:
    assert _NOTE.is_file(), _NOTE
    text = _NOTE.read_text(encoding="utf-8")
    assert "不算 G2" in text
    assert "不泄 twin_id" in text
    assert "盘上可留" in text
    assert "GET /api/eln" in text
    assert "type" in text
    assert "assignment_id" in text
    assert "第四" in text
    assert "不算接线" in text
    extra = set(_ID_RE.findall(text)) - _ALLOWED_IDS - set(HANDLES)
    assert not extra, extra
    for phrase in _CLAIM_PASS:
        assert phrase not in text, phrase


def main() -> int:
    failed = 0
    for name, fn in (
        ("eln_get_drops_twin_keeps_face", test_eln_get_drops_twin_keeps_face),
        ("eln_http_source_has_no_fourth_handle", test_eln_http_source_has_no_fourth_handle),
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
