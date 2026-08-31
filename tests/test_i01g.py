"""I-01g: POST assignment mutations return face_payload. No columns / circuit body."""

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

_NOTE = ROOT / "docs" / "execution" / "I-01g_face_mutate.md"
_HANDLES = frozenset({HANDLE_CIRCUIT, HANDLE_ASSET, HANDLE_TWIN})
_ALLOWED_IDS = _HANDLES | {"assignment_id"}
_ID_RE = re.compile(r"\b[a-z]+_id\b")
_FAT_KEYS = frozenset(
    {
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
        "brief",
        "recipe",
        "args",
    }
)
_CLAIM_PASS = ("G0 已通过", "G2 已通过", "G0 passed", "G2 passed")


@contextmanager
def isolated_assignments() -> Iterator[Path]:
    previous = {
        "QAGENT_ASSIGNMENTS_FILE": os.environ.get("QAGENT_ASSIGNMENTS_FILE"),
        "QAGENT_ELN_FILE": os.environ.get("QAGENT_ELN_FILE"),
        "QAGENT_TWIN_URL": os.environ.get("QAGENT_TWIN_URL"),
    }
    handle, name = tempfile.mkstemp(prefix="i01g-asg-", suffix=".jsonl")
    os.close(handle)
    path = Path(name)
    eln_handle, eln_name = tempfile.mkstemp(prefix="i01g-eln-", suffix=".jsonl")
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


def _assert_mutate_face(payload: dict[str, Any]) -> None:
    assert isinstance(payload, dict)
    keys = _walk_keys(payload)
    for name in _FAT_KEYS:
        assert name not in keys, name
    assert payload.get("assignment_id")
    assert payload.get("status")
    if "ask" in payload:
        assert set(payload["ask"]) == {"tool"}
    if "handles" in payload:
        assert set(payload["handles"]) <= _HANDLES
    extra = set(_ID_RE.findall(json.dumps(payload))) - _ALLOWED_IDS
    assert not extra, extra


def test_post_create_cancel_reject_are_face() -> None:
    with isolated_assignments():
        code, created = dispatch(
            "POST",
            "/api/assignments",
            {"room": "lab", "brief": "i01g-create", "shots": 8},
        )
        assert code == 200
        _assert_mutate_face(created)
        assert created["status"] == "draft"
        assignment_id = created["assignment_id"]
        code, cancelled = dispatch("POST", f"/api/assignments/{assignment_id}/cancel", {})
        assert code == 200
        _assert_mutate_face(cancelled)
        assert cancelled["assignment_id"] == assignment_id
        assert cancelled["status"] == "rejected"
        code, other = dispatch(
            "POST",
            "/api/assignments",
            {"room": "lab", "brief": "i01g-reject", "shots": 8},
        )
        assert code == 200
        _assert_mutate_face(other)
        code, rejected = dispatch("POST", f"/api/assignments/{other['assignment_id']}/reject", {})
        assert code == 200
        _assert_mutate_face(rejected)
        assert rejected["assignment_id"] == other["assignment_id"]
        assert rejected["status"] == "rejected"
        blob = json.dumps([created, cancelled, rejected], ensure_ascii=False)
        assert "OPENQASM" not in blob
        assert "identity" not in blob


def test_post_run_approved_without_token_is_403() -> None:
    with isolated_assignments():
        code, created = dispatch(
            "POST",
            "/api/assignments",
            {"room": "lab", "brief": "i01g-run-gate", "shots": 8},
        )
        assert code == 200
        assignment_id = created["assignment_id"]
        code, forbidden = dispatch(
            "POST",
            f"/api/assignments/{assignment_id}/run",
            {"approved": True},
        )
        assert code == 403
        assert forbidden == {"error": "approval requires QAGENT_SHELL_TOKEN"}
        code, approve_forbidden = dispatch(
            "POST",
            f"/api/assignments/{assignment_id}/approve",
            {},
        )
        assert code == 403
        assert approve_forbidden == {"error": "approval requires QAGENT_SHELL_TOKEN"}
        code, missing = dispatch("POST", "/api/assignments/asg_missing/cancel", {})
        assert code == 404
        assert "error" in missing


def test_get_list_still_thin() -> None:
    with isolated_assignments():
        code, created = dispatch(
            "POST",
            "/api/assignments",
            {"room": "lab", "brief": "i01g-list", "shots": 8},
        )
        assert code == 200
        code, listed = dispatch("GET", "/api/assignments")
        assert code == 200
        rows = listed["assignments"]
        assert len(rows) == 1
        _assert_mutate_face(rows[0])
        assert rows[0]["assignment_id"] == created["assignment_id"]
        code, one = dispatch("GET", f"/api/assignments/{created['assignment_id']}")
        assert code == 200
        _assert_mutate_face(one)
        code, forked = dispatch(
            "POST",
            f"/api/assignments/{created['assignment_id']}/fork",
            {},
        )
        assert code == 200
        _assert_mutate_face(forked)
        assert forked["assignment_id"] != created["assignment_id"]
        assert forked["status"] == "draft"


def test_note_exists() -> None:
    assert _NOTE.is_file(), _NOTE
    text = _NOTE.read_text(encoding="utf-8")
    assert "face_payload" in text
    assert "不回" in text or "无" in text
    hits = [phrase for phrase in _CLAIM_PASS if phrase in text]
    assert not hits, hits
    extra = set(_ID_RE.findall(text)) - _ALLOWED_IDS
    assert not extra, extra


def main() -> int:
    failed = 0
    for name, fn in (
        ("post_create_cancel_reject_are_face", test_post_create_cancel_reject_are_face),
        ("post_run_approved_without_token_is_403", test_post_run_approved_without_token_is_403),
        ("get_list_still_thin", test_get_list_still_thin),
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
