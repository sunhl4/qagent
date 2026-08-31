"""I-03h: GET /api/eln returns claim_blocked with reason. No client append. No minted twin_id."""

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
    EVENT_CLAIM_BLOCKED,
    FORBIDDEN_ELN_KEYS,
    SECRET_ELN_KEYS,
)
from qagent.models.handles import HANDLE_TWIN
from qagent.services.eln import append_claim_blocked, read_eln

_ENV_KEYS = ("QAGENT_ELN_FILE",)
_REASON = "cirq_claim_twin_id"
_SECRET = "sk-i03h-n3v3r-eln-7k2p"
_HPC = "i03h-hpc-n3v3r-eln-4m9q"
_QTM = "i03h-qtm-n3v3r-eln-1w8r"
_PLANTED = (_SECRET, _HPC, _QTM)
_NOTE = ROOT / "docs" / "execution" / "I-03h_eln_reason_http.md"
_INTERFACES = ROOT / "INTERFACES.md"
_CLAIM_PASS = ("G0 已通过", "G2 已通过", "G0 passed", "G2 passed")


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


def _is_claim_blocked(row: Mapping[str, Any]) -> bool:
    event_type = str(row.get("type") or "")
    return event_type in {EVENT_CLAIM_BLOCKED, "claim_blocked"} or event_type.endswith(
        "/claim_blocked"
    )


def _event_reason(row: Mapping[str, Any]) -> object:
    if "reason" in row:
        return row["reason"]
    payload = row.get("payload")
    if isinstance(payload, Mapping) and "reason" in payload:
        return payload["reason"]
    raise AssertionError(f"missing reason: {row!r}")


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


def test_get_claim_blocked_has_reason() -> None:
    with isolated_eln():
        append_claim_blocked(reason=_REASON)
        code, payload = _get_eln()
        assert code == 200
        blocked = [row for row in payload["events"] if _is_claim_blocked(row)]
        assert blocked, payload["events"]
        row = blocked[-1]
        assert row.get("type") in {EVENT_CLAIM_BLOCKED, "claim_blocked"}
        assert _event_reason(row) == _REASON
        keys = _nested_keys(payload)
        assert HANDLE_TWIN not in keys
        blob = json.dumps(payload, ensure_ascii=False)
        assert _REASON in blob
        assert "hpc_secret" not in blob


def test_get_keeps_payload_reason() -> None:
    with isolated_eln() as path:
        path.write_text(
            json.dumps(
                {"type": EVENT_CLAIM_BLOCKED, "payload": {"reason": _REASON}},
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        code, payload = _get_eln()
        assert code == 200
        row = payload["events"][-1]
        assert _is_claim_blocked(row)
        assert _event_reason(row) == _REASON


def test_get_strips_secrets_and_keeps_reason() -> None:
    with isolated_eln() as path:
        path.write_text(
            json.dumps(
                {
                    "type": EVENT_CLAIM_BLOCKED,
                    "reason": _REASON,
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
        assert _is_claim_blocked(row)
        assert _event_reason(row) == _REASON
        keys = _nested_keys(payload)
        assert not SECRET_ELN_KEYS & keys
        assert not FORBIDDEN_ELN_KEYS & keys
        assert HANDLE_TWIN not in keys
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
            {"type": EVENT_CLAIM_BLOCKED, "reason": _REASON, "hpc_secret": _HPC},
        )
        assert code == 404
        assert isinstance(payload, dict)
        assert not path.is_file()
        assert read_eln() == []
        code, listed = _get_eln()
        assert code == 200
        assert listed["events"] == []


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
    assert "claim_blocked" in text
    assert "reason" in text
    assert _REASON in text
    assert "不铸" in text or "twin_id" in text
    assert "无 POST" in text or "没有 POST" in text
    assert "不算" in text
    assert "G2" in text
    for phrase in _CLAIM_PASS:
        assert phrase not in text, phrase
    interfaces = _INTERFACES.read_text(encoding="utf-8")
    assert "GET /api/eln" in interfaces
    assert "claim_blocked" in interfaces
    assert "reason" in interfaces


def main() -> int:
    failed = 0
    for name, fn in (
        ("get_claim_blocked_has_reason", test_get_claim_blocked_has_reason),
        ("get_keeps_payload_reason", test_get_keeps_payload_reason),
        ("get_strips_secrets_and_keeps_reason", test_get_strips_secrets_and_keeps_reason),
        ("post_does_not_append", test_post_does_not_append),
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
