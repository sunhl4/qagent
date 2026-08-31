"""I-01f: GET assignment list/id return face_payload. No columns / circuit body."""

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
from qagent.services.assignment import create, preflight, run

_NOTE = ROOT / "docs" / "execution" / "I-01f_face_row.md"
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
_TENANT_A = "cust-a"
_TENANT_B = "cust-b"
_HEADER_A = {"X-QAGENT-TENANT": _TENANT_A}
_HEADER_B = {"X-QAGENT-TENANT": _TENANT_B}


@contextmanager
def isolated_assignments() -> Iterator[Path]:
    previous = {
        "QAGENT_ASSIGNMENTS_FILE": os.environ.get("QAGENT_ASSIGNMENTS_FILE"),
        "QAGENT_ELN_FILE": os.environ.get("QAGENT_ELN_FILE"),
        "QAGENT_TWIN_URL": os.environ.get("QAGENT_TWIN_URL"),
    }
    handle, name = tempfile.mkstemp(prefix="i01f-asg-", suffix=".jsonl")
    os.close(handle)
    path = Path(name)
    eln_handle, eln_name = tempfile.mkstemp(prefix="i01f-eln-", suffix=".jsonl")
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


def _needs_ask_row(*, tenant_id: str = "", brief: str = "i01f-face"):
    created = create(room="lab", brief=brief, shots=32, tenant_id=tenant_id)
    ran = run(created.assignment_id, tenant_id=tenant_id)
    assert ran.status == "needs_ask"
    return ran


def _assert_face(payload: dict[str, Any]) -> None:
    assert isinstance(payload, dict)
    keys = _walk_keys(payload)
    for name in _FAT_KEYS:
        assert name not in keys, name
    assert payload.get("assignment_id")
    assert payload.get("status")
    ask_tool = payload.get("ask_tool")
    ask = payload.get("ask") if isinstance(payload.get("ask"), Mapping) else {}
    assert ask_tool or ask.get("tool")
    if "ask" in payload:
        assert set(payload["ask"]) == {"tool"}
    if "handles" in payload:
        assert set(payload["handles"]) <= _HANDLES
    extra = set(_ID_RE.findall(json.dumps(payload))) - _ALLOWED_IDS
    assert not extra, extra


def test_get_list_and_id_are_face_only() -> None:
    with isolated_assignments():
        row = _needs_ask_row()
        fat = row.to_dict()
        assert "columns" in fat
        assert isinstance(fat.get("ask"), dict) and "args" in (fat.get("ask") or {})
        code, listed = dispatch("GET", "/api/assignments")
        assert code == 200
        rows = listed["assignments"]
        assert len(rows) == 1
        _assert_face(rows[0])
        assert rows[0]["assignment_id"] == row.assignment_id
        assert rows[0]["status"] == "needs_ask"
        code, one = dispatch("GET", f"/api/assignments/{row.assignment_id}")
        assert code == 200
        _assert_face(one)
        assert one["assignment_id"] == row.assignment_id
        assert one["status"] == "needs_ask"
        blob = json.dumps([listed, one], ensure_ascii=False)
        assert "OPENQASM" not in blob
        assert "identity" not in blob
        code, posted = dispatch("POST", f"/api/assignments/{row.assignment_id}/cancel", {})
        assert code == 200
        assert "columns" not in posted
        assert "columns" not in _walk_keys(posted)
        assert posted.get("assignment_id") == row.assignment_id
        assert posted.get("status")


def test_tenant_lists_isolated() -> None:
    with isolated_assignments():
        row_a = _needs_ask_row(tenant_id=_TENANT_A, brief="i01f-a")
        row_b = _needs_ask_row(tenant_id=_TENANT_B, brief="i01f-b")
        code, from_a = dispatch("GET", "/api/assignments", {}, _HEADER_A)
        assert code == 200
        ids_a = {item["assignment_id"] for item in from_a["assignments"]}
        assert row_a.assignment_id in ids_a
        assert row_b.assignment_id not in ids_a
        for item in from_a["assignments"]:
            _assert_face(item)
        code, from_b = dispatch("GET", "/api/assignments", {}, _HEADER_B)
        assert code == 200
        ids_b = {item["assignment_id"] for item in from_b["assignments"]}
        assert row_b.assignment_id in ids_b
        assert row_a.assignment_id not in ids_b
        code, peek = dispatch(
            "GET",
            f"/api/assignments/{row_b.assignment_id}",
            {},
            _HEADER_A,
        )
        assert peek.get("error")


def test_preflight_still_omits_identity() -> None:
    with isolated_assignments():
        row = _needs_ask_row()
        payload = preflight(row.assignment_id)
        assert "identity" not in payload
        assert "identity" not in _walk_keys(payload)
        assert "ok" in payload
        assert "checks" in payload
        code, http_payload = dispatch("GET", f"/api/assignments/{row.assignment_id}/preflight")
        assert code == 200
        assert "identity" not in _walk_keys(http_payload)
        assert http_payload == payload


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
        ("get_list_and_id_are_face_only", test_get_list_and_id_are_face_only),
        ("tenant_lists_isolated", test_tenant_lists_isolated),
        ("preflight_still_omits_identity", test_preflight_still_omits_identity),
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
