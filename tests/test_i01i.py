"""I-01i: face_payload short reason on rejected/failed. No error text. No fourth handle."""

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
from qagent.models.assignment import Assignment
from qagent.models.handles import HANDLE_ASSET, HANDLE_CIRCUIT, HANDLE_TWIN
from qagent.services.assignment import create, run

_NOTE = ROOT / "docs" / "execution" / "I-01i_face_reason.md"
_HANDLES = frozenset({HANDLE_CIRCUIT, HANDLE_ASSET, HANDLE_TWIN})
_ALLOWED_IDS = _HANDLES | {"assignment_id"}
_ID_RE = re.compile(r"\b[a-z]+_id\b")
_REASONS = frozenset({"cancelled", "rejected", "failed"})
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
        "error",
    }
)
_CLAIM_PASS = ("G0 已通过", "G2 已通过", "G0 passed", "G2 passed")
_TWIN_LEAK = "TwinRun REST did not return twin_id"


@contextmanager
def isolated_assignments() -> Iterator[Path]:
    previous = {
        "QAGENT_ASSIGNMENTS_FILE": os.environ.get("QAGENT_ASSIGNMENTS_FILE"),
        "QAGENT_ELN_FILE": os.environ.get("QAGENT_ELN_FILE"),
        "QAGENT_TWIN_URL": os.environ.get("QAGENT_TWIN_URL"),
    }
    handle, name = tempfile.mkstemp(prefix="i01i-asg-", suffix=".jsonl")
    os.close(handle)
    path = Path(name)
    eln_handle, eln_name = tempfile.mkstemp(prefix="i01i-eln-", suffix=".jsonl")
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


def _assert_face(payload: dict[str, Any], *, status: str, reason: str | None) -> None:
    assert isinstance(payload, dict)
    keys = _walk_keys(payload)
    for name in _FAT_KEYS:
        assert name not in keys, name
    assert payload.get("assignment_id")
    assert payload.get("status") == status
    if reason is None:
        assert "reason" not in payload
    else:
        assert payload.get("reason") == reason
        assert reason in _REASONS
    if "ask" in payload:
        assert set(payload["ask"]) == {"tool"}
    if "handles" in payload:
        assert set(payload["handles"]) <= _HANDLES
    extra = set(_ID_RE.findall(json.dumps(payload))) - _ALLOWED_IDS
    assert not extra, extra
    blob = json.dumps(payload, ensure_ascii=False)
    assert "TwinRun" not in blob
    assert _TWIN_LEAK not in blob


def test_get_cancel_has_cancelled_reason() -> None:
    with isolated_assignments():
        code, created = dispatch(
            "POST",
            "/api/assignments",
            {"room": "lab", "brief": "i01i-cancel", "shots": 8},
        )
        assert code == 200
        _assert_face(created, status="draft", reason=None)
        assignment_id = created["assignment_id"]
        code, cancelled = dispatch("POST", f"/api/assignments/{assignment_id}/cancel", {})
        assert code == 200
        _assert_face(cancelled, status="rejected", reason="cancelled")
        code, one = dispatch("GET", f"/api/assignments/{assignment_id}")
        assert code == 200
        _assert_face(one, status="rejected", reason="cancelled")
        assert "error" not in one


def test_get_reject_has_rejected_reason() -> None:
    with isolated_assignments():
        code, created = dispatch(
            "POST",
            "/api/assignments",
            {"room": "lab", "brief": "i01i-reject", "shots": 8},
        )
        assert code == 200
        assignment_id = created["assignment_id"]
        code, rejected = dispatch("POST", f"/api/assignments/{assignment_id}/reject", {})
        assert code == 200
        _assert_face(rejected, status="rejected", reason="rejected")
        code, one = dispatch("GET", f"/api/assignments/{assignment_id}")
        assert code == 200
        _assert_face(one, status="rejected", reason="rejected")


def test_failed_reason_via_service() -> None:
    with isolated_assignments():
        row = create(room="sign", brief="i01i-fail", shots=8)
        ran = run(row.assignment_id, approved=True)
        if ran.status != "failed":
            print("skip failed HTTP: status=%s" % ran.status)
            return
        assert ran.error
        assert "TwinRun" in str(ran.error)
        face = ran.face_payload()
        _assert_face(face, status="failed", reason="failed")
        assert face["reason"] == "failed"
        code, one = dispatch("GET", f"/api/assignments/{ran.assignment_id}")
        assert code == 200
        _assert_face(one, status="failed", reason="failed")


def test_model_face_does_not_copy_error() -> None:
    long_error = "TwinRun REST did not return twin_id and counts; no local twin_id is minted"
    failed = Assignment(
        assignment_id="asg_i01i_failed",
        room="lab",
        brief="i01i-model-fail",
        recipe="a2_chem_pes",
        shots=8,
        status="failed",
        error=long_error,
    )
    face = failed.face_payload()
    _assert_face(face, status="failed", reason="failed")
    assert long_error not in json.dumps(face, ensure_ascii=False)
    draft = Assignment(
        assignment_id="asg_i01i_draft",
        room="lab",
        brief="i01i-model-draft",
        recipe="a2_chem_pes",
        shots=8,
        status="draft",
        error=long_error,
    )
    _assert_face(draft.face_payload(), status="draft", reason=None)
    running = Assignment(
        assignment_id="asg_i01i_running",
        room="lab",
        brief="i01i-model-run",
        recipe="a2_chem_pes",
        shots=8,
        status="running",
    )
    _assert_face(running.face_payload(), status="running", reason=None)


def test_note_exists() -> None:
    assert _NOTE.is_file(), _NOTE
    text = _NOTE.read_text(encoding="utf-8")
    assert "face_payload" in text
    assert "不算接线" in text
    assert "不回 error 原文" in text
    hits = [phrase for phrase in _CLAIM_PASS if phrase in text]
    assert not hits, hits
    extra = set(_ID_RE.findall(text)) - _ALLOWED_IDS
    assert not extra, extra


def main() -> int:
    failed = 0
    for name, fn in (
        ("get_cancel_has_cancelled_reason", test_get_cancel_has_cancelled_reason),
        ("get_reject_has_rejected_reason", test_get_reject_has_rejected_reason),
        ("failed_reason_via_service", test_failed_reason_via_service),
        ("model_face_does_not_copy_error", test_model_face_does_not_copy_error),
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
