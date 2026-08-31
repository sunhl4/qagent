"""I-01e: preflight returns checks only. No identity echo. No minted twin_id."""

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
sys.path.insert(0, str(ROOT / "src"))

from qagent.entrypoints.shell_http import dispatch
from qagent.models.eln import SECRET_ELN_KEYS
from qagent.models.handles import HANDLE_ASSET, HANDLE_CIRCUIT, HANDLE_TWIN
from qagent.services.assignment import create, preflight, run

_NOTE = ROOT / "docs" / "execution" / "I-01e_preflight.md"
_HANDLES = frozenset({HANDLE_CIRCUIT, HANDLE_ASSET, HANDLE_TWIN})
_ID_RE = re.compile(r"\b[a-z]+_id\b")
_SECRET_KEYS = frozenset(SECRET_ELN_KEYS) | {
    "identity",
    "token",
    "secret",
    "api_key",
    "password",
    "preset",
    "n_qubits",
}
_CLAIM_PASS = ("G0 已通过", "G2 已通过", "G0 passed", "G2 passed")
_BOOL_CHECKS = ("twin_live", "has_circuit", "has_asset")
_PLANTED = ("sk-i01e-n3v3r-preflight-7k2p", "i01e-hpc-n3v3r-4m9q")


@contextmanager
def isolated_assignments() -> Iterator[Path]:
    previous = {
        "QAGENT_ASSIGNMENTS_FILE": os.environ.get("QAGENT_ASSIGNMENTS_FILE"),
        "QAGENT_ELN_FILE": os.environ.get("QAGENT_ELN_FILE"),
        "QAGENT_TWIN_URL": os.environ.get("QAGENT_TWIN_URL"),
    }
    handle, name = tempfile.mkstemp(prefix="i01e-asg-", suffix=".jsonl")
    os.close(handle)
    path = Path(name)
    eln_handle, eln_name = tempfile.mkstemp(prefix="i01e-eln-", suffix=".jsonl")
    os.close(eln_handle)
    eln_path = Path(eln_name)
    os.environ["QAGENT_ASSIGNMENTS_FILE"] = str(path)
    os.environ["QAGENT_ELN_FILE"] = str(eln_path)
    os.environ["QAGENT_TWIN_URL"] = "http://127.0.0.1:1"
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
    if isinstance(value, Mapping):
        for key, item in value.items():
            keys.add(str(key))
            keys |= _walk_keys(item)
    elif isinstance(value, list):
        for item in value:
            keys |= _walk_keys(item)
    return keys


def _needs_ask_row():
    created = create(room="lab", brief="i01e-preflight", shots=32)
    ran = run(created.assignment_id)
    assert ran.status == "needs_ask"
    return ran


def _assert_preflight_shape(payload: dict[str, Any], *, status: str) -> None:
    assert isinstance(payload, dict)
    keys = _walk_keys(payload)
    assert "identity" not in payload
    assert "identity" not in keys
    assert "token" not in keys
    for name in _SECRET_KEYS:
        assert name not in keys, name
    assert "ok" in payload
    assert "checks" in payload
    checks = payload["checks"]
    assert isinstance(checks, dict)
    for name in _BOOL_CHECKS:
        assert name in checks
        assert isinstance(checks[name], bool)
    assert payload["ok"] == (
        bool(checks["twin_live"]) and bool(checks["has_circuit"]) and status == "needs_ask"
    )
    blob = json.dumps(payload, ensure_ascii=False)
    assert HANDLE_TWIN not in blob
    assert "twin_id" not in blob
    extra = set(_ID_RE.findall(blob)) - _HANDLES
    assert not extra, extra
    for planted in _PLANTED:
        assert planted not in blob
    for name in ("preset", "n_qubits", "t_junction"):
        assert name not in blob


def test_preflight_and_http_omit_identity() -> None:
    with isolated_assignments():
        row = _needs_ask_row()
        payload = preflight(row.assignment_id)
        _assert_preflight_shape(payload, status=row.status)
        code, http_payload = dispatch("GET", f"/api/assignments/{row.assignment_id}/preflight")
        assert code == 200
        assert isinstance(http_payload, dict)
        _assert_preflight_shape(http_payload, status=row.status)
        assert http_payload == payload


def test_note_exists() -> None:
    assert _NOTE.is_file(), _NOTE
    text = _NOTE.read_text(encoding="utf-8")
    assert "不回显 identity" in text
    assert "preflight" in text
    hits = [phrase for phrase in _CLAIM_PASS if phrase in text]
    assert not hits, hits
    extra = set(_ID_RE.findall(text)) - _HANDLES
    assert not extra, extra


def test_no_fourth_handle_in_payload() -> None:
    with isolated_assignments():
        row = _needs_ask_row()
        for payload in (preflight(row.assignment_id),):
            extra = set(_ID_RE.findall(json.dumps(payload))) - _HANDLES
            assert not extra, extra
            assert HANDLE_TWIN not in _walk_keys(payload)


def main() -> int:
    failed = 0
    for name, fn in (
        ("preflight_and_http_omit_identity", test_preflight_and_http_omit_identity),
        ("note_exists", test_note_exists),
        ("no_fourth_handle_in_payload", test_no_fourth_handle_in_payload),
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
