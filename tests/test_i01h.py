"""I-01h: POST invoke/vibe HTTP faces are thin. Internals stay full."""

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
from qagent.models.handles import HANDLE_ASSET, HANDLE_CIRCUIT, HANDLE_TWIN
from qagent.services.vibe_path import run_vibe_path

_NOTE = ROOT / "docs" / "execution" / "I-01h_invoke_http.md"
_HANDLES = frozenset({HANDLE_CIRCUIT, HANDLE_ASSET, HANDLE_TWIN})
_ALLOWED_IDS = _HANDLES | {"assignment_id", "slot_id"}
_ID_RE = re.compile(r"\b[a-z]+_id\b")
_INVOKE_KEYS = frozenset({"tool", "decision", "status", "slot_id"})
_VIBE_KEYS = frozenset({"status", "tool", "summary", "handles"})
_FAT_KEYS = frozenset(
    {
        "payload",
        "steps",
        "args",
        "columns",
        "identity",
        "counts",
        "circuit",
        "body",
        "qasm",
        "qasm3",
        "token",
        "secret",
        "api_key",
        "password",
        "aer_leaked_twin_id",
        "makespan_ns",
        "b3",
        "aer_provenance",
    }
)
_CLAIM_PASS = ("G0 已通过", "G2 已通过", "G0 passed", "G2 passed")
_FORBIDDEN = {"error": "approval requires QAGENT_SHELL_TOKEN"}


@contextmanager
def isolated_assignments() -> Iterator[Path]:
    previous = {
        "QAGENT_ASSIGNMENTS_FILE": os.environ.get("QAGENT_ASSIGNMENTS_FILE"),
        "QAGENT_ELN_FILE": os.environ.get("QAGENT_ELN_FILE"),
        "QAGENT_TWIN_URL": os.environ.get("QAGENT_TWIN_URL"),
    }
    handle, name = tempfile.mkstemp(prefix="i01h-asg-", suffix=".jsonl")
    os.close(handle)
    path = Path(name)
    eln_handle, eln_name = tempfile.mkstemp(prefix="i01h-eln-", suffix=".jsonl")
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


def _assert_no_fat(payload: dict[str, Any]) -> None:
    keys = _walk_keys(payload)
    for name in _FAT_KEYS:
        assert name not in keys, name
    extra = set(_ID_RE.findall(json.dumps(payload))) - _ALLOWED_IDS
    assert not extra, extra


def test_invoke_list_engines_is_thin() -> None:
    with isolated_assignments():
        code, payload = dispatch(
            "POST",
            "/api/invoke",
            {"tool": "qagent_list_engines", "preset": "lab"},
        )
        assert code == 200
        assert payload["tool"] == "qagent_list_engines"
        assert payload["status"]
        assert payload["decision"]
        assert set(payload) <= _INVOKE_KEYS
        assert "payload" not in payload
        assert "body" not in payload
        assert "twin_id" not in payload
        _assert_no_fat(payload)
        blob = json.dumps(payload, ensure_ascii=False)
        assert "OPENQASM" not in blob
        assert "counts" not in blob


def test_invoke_twin_run_approved_without_token_is_403() -> None:
    with isolated_assignments():
        code, forbidden = dispatch(
            "POST",
            "/api/invoke",
            {
                "tool": "ionstack_twin_run",
                "approved": True,
                "args": {"shots": 8, "mode": "signoff"},
            },
        )
        assert code == 403
        assert forbidden == _FORBIDDEN


def test_invoke_needs_ask_omits_args() -> None:
    with isolated_assignments():
        code, payload = dispatch(
            "POST",
            "/api/invoke",
            {
                "tool": "ionstack_twin_run",
                "approved": False,
                "args": {"shots": 8, "mode": "signoff"},
            },
        )
        assert code == 200
        assert payload["status"] == "needs_ask"
        assert payload["tool"] == "ionstack_twin_run"
        assert "args" not in payload
        assert "payload" not in payload
        assert "twin_id" not in payload
        _assert_no_fat(payload)


def test_vibe_unapproved_is_thin() -> None:
    with isolated_assignments():
        code, payload = dispatch(
            "POST",
            "/api/vibe",
            {"approved": False, "shots": 8},
        )
        assert code == 200
        assert payload.get("status")
        assert "tool" in payload
        assert payload.get("summary")
        assert set(payload) <= _VIBE_KEYS
        assert "steps" not in payload
        assert "body" not in _walk_keys(payload)
        if "handles" in payload:
            assert set(payload["handles"]) <= _HANDLES
        _assert_no_fat(payload)
        blob = json.dumps(payload, ensure_ascii=False)
        assert "OPENQASM" not in blob
        assert "steps" not in blob


def test_vibe_approved_without_token_is_403() -> None:
    with isolated_assignments():
        code, forbidden = dispatch(
            "POST",
            "/api/vibe",
            {"approved": True, "shots": 8},
        )
        assert code == 403
        assert forbidden == _FORBIDDEN


def test_assignments_still_face_and_vibe_path_still_full() -> None:
    with isolated_assignments():
        code, created = dispatch(
            "POST",
            "/api/assignments",
            {"room": "lab", "brief": "i01h-face", "shots": 8},
        )
        assert code == 200
        assert "columns" not in created
        assert "brief" not in created
        code, listed = dispatch("GET", "/api/assignments")
        assert code == 200
        rows = listed["assignments"]
        assert rows
        assert "columns" not in rows[0]
        assert rows[0]["assignment_id"] == created["assignment_id"]
        path = run_vibe_path("lab", shots=8, approved=False)
        assert path["steps"]
        assert any(isinstance(step, Mapping) and "payload" in step for step in path["steps"])


def test_note_exists() -> None:
    assert _NOTE.is_file(), _NOTE
    text = _NOTE.read_text(encoding="utf-8")
    assert "不算接线" in text
    assert "不回 payload/steps" in text
    hits = [phrase for phrase in _CLAIM_PASS if phrase in text]
    assert not hits, hits
    extra = set(_ID_RE.findall(text)) - _ALLOWED_IDS
    assert not extra, extra


def main() -> int:
    failed = 0
    for name, fn in (
        ("invoke_list_engines_is_thin", test_invoke_list_engines_is_thin),
        ("invoke_twin_run_approved_without_token_is_403", test_invoke_twin_run_approved_without_token_is_403),
        ("invoke_needs_ask_omits_args", test_invoke_needs_ask_omits_args),
        ("vibe_unapproved_is_thin", test_vibe_unapproved_is_thin),
        ("vibe_approved_without_token_is_403", test_vibe_approved_without_token_is_403),
        ("assignments_still_face_and_vibe_path_still_full", test_assignments_still_face_and_vibe_path_still_full),
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
