"""I-01j: chat HTTP face omits session_id. turn() internals keep it."""

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
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))
os.environ.setdefault("QAGENT_DSH_MUX", "0")

from qagent.adapters.dsh_session import DshSessionClient
from qagent.entrypoints.shell_http import dispatch
from qagent.models.handles import HANDLE_ASSET, HANDLE_CIRCUIT, HANDLE_TWIN
from qagent.services.chat import reset_chat, turn
from qagent.services.workplace import save_workplace

_NOTE = ROOT / "docs" / "execution" / "I-01j_chat_http.md"
_HANDLES = frozenset({HANDLE_CIRCUIT, HANDLE_ASSET, HANDLE_TWIN})
_FACE_IDS = _HANDLES | {"approval_id", "rpc_id"}
_NOTE_IDS = _HANDLES | {"session_id"}
_ID_RE = re.compile(r"\b[a-z]+_id\b")
_FACE_KEYS = ("reply", "awaiting", "cards", "ready", "open_settings", "running", "via")
_PENDING_KEYS = frozenset({"approval_id", "rpc_id", "tool", "reason"})
_CLAIM_PASS = ("G0 已通过", "G2 已通过", "G0 passed", "G2 passed")
_FORBIDDEN = {"error": "approval requires QAGENT_SHELL_TOKEN"}
_ENV_KEYS = (
    "QAGENT_WORKPLACE_FILE",
    "QAGENT_SECRETS_FILE",
    "QAGENT_DSH_SESSION_FILE",
    "QAGENT_DSH_URL",
    "QAGENT_DSH_MUX",
    "QAGENT_DSH_WAIT_S",
    "QAGENT_AGENT_THREAD",
    "QAGENT_SHELL_TOKEN",
)


@contextmanager
def isolated(*, ready: bool = False) -> Iterator[Path]:
    previous = {key: os.environ.get(key) for key in _ENV_KEYS}
    tmp = tempfile.TemporaryDirectory()
    try:
        folder = Path(tmp.name)
        os.environ["QAGENT_WORKPLACE_FILE"] = str(folder / "workplace.json")
        os.environ["QAGENT_SECRETS_FILE"] = str(folder / "secrets.json")
        os.environ["QAGENT_DSH_SESSION_FILE"] = str(folder / "dsh-session.json")
        os.environ["QAGENT_DSH_URL"] = "http://127.0.0.1:9"
        os.environ["QAGENT_DSH_MUX"] = "0"
        os.environ["QAGENT_DSH_WAIT_S"] = "0"
        os.environ["QAGENT_AGENT_THREAD"] = str(folder / "thread.json")
        os.environ.pop("QAGENT_SHELL_TOKEN", None)
        reset_chat()
        if ready:
            save_workplace({"llm_base_url": "http://127.0.0.1:9/v1", "llm_model": "unitqc-local"})
        yield folder
    finally:
        reset_chat()
        tmp.cleanup()
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


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


def _assert_http_face(payload: dict[str, Any]) -> None:
    assert isinstance(payload, dict)
    assert "session_id" not in _walk_keys(payload)
    for name in _FACE_KEYS:
        assert name in payload, name
    pending = payload.get("pending_approval")
    if pending is not None:
        assert isinstance(pending, dict)
        assert set(pending) <= _PENDING_KEYS
    extra = set(_ID_RE.findall(json.dumps(payload))) - _FACE_IDS
    assert not extra, extra
    assert "twin_id" not in json.dumps(payload, ensure_ascii=False)


def _plain_events(text: str = "已进 session") -> list[dict]:
    return [
        {
            "event": {
                "type": "assistant/message",
                "data": {"message": {"content": [{"type": "text", "text": text}]}},
            }
        }
    ]


def _pending_events() -> list[dict]:
    return [
        {
            "event": {
                "type": "approval/requested",
                "rpcId": "rpc-live",
                "data": {
                    "sessionId": "sess_i01j",
                    "approvalId": "appr-1",
                    "toolName": "ionstack_twin_run",
                    "reason": "shots",
                    "callId": "call-1",
                },
            }
        }
    ]


class Fake:
    def __init__(self, events: list[dict] | None = None) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.events = list(events or _plain_events())
        self.created = 0

    def __call__(self, method: str, payload: dict) -> dict:
        self.calls.append((method, payload))
        if method == "session.create":
            self.created += 1
            return {"result": {"ok": True, "value": {"sessionId": f"sess_i01j_{self.created}"}}}
        if method == "session.prompt":
            return {"result": {"ok": True, "value": {"accepted": True}}}
        if method == "session.history":
            return {"result": {"ok": True, "value": {"events": self.events, "hasMore": False}}}
        raise AssertionError(method)


def _bind(fake: Fake):
    def factory(*args, **kwargs):
        kwargs["transport"] = fake
        return DshSessionClient(*args, **kwargs)

    return factory


def test_http_chat_omits_session_id() -> None:
    with isolated(ready=True):
        fake = Fake()
        with patch("qagent.services.chat.DshSessionClient", side_effect=_bind(fake)):
            code, posted = dispatch("POST", "/api/chat", {"message": "办一下"})
            code_st, status = dispatch("GET", "/api/chat/status")
        assert code == 200
        assert posted.get("reply")
        _assert_http_face(posted)
        assert code_st == 200
        _assert_http_face(status)


def test_http_pending_stays_slim() -> None:
    with isolated(ready=True):
        fake = Fake(events=_pending_events())
        with patch("qagent.services.chat.DshSessionClient", side_effect=_bind(fake)):
            code, posted = dispatch("POST", "/api/chat", {"message": "扫氢分子"})
        assert code == 200
        _assert_http_face(posted)
        pending = posted.get("pending_approval")
        assert isinstance(pending, dict)
        assert set(pending) <= _PENDING_KEYS
        assert "session_id" not in pending


def test_approve_without_token_is_403() -> None:
    with isolated(ready=True):
        code, forbidden = dispatch("POST", "/api/chat", {"message": "批准"}, {})
        assert code == 403
        assert forbidden == _FORBIDDEN
        assert "session_id" not in forbidden


def test_turn_still_has_session_id() -> None:
    with isolated(ready=True):
        fake = Fake()
        out = turn(message="办一下", client=DshSessionClient(transport=fake))
        assert out.get("reply")
        assert out.get("session_id")
        assert out.get("via") == "dsh-session"


def test_note_exists() -> None:
    assert _NOTE.is_file(), _NOTE
    text = _NOTE.read_text(encoding="utf-8")
    assert "不算接线" in text
    assert "HTTP 无 session_id" in text
    hits = [phrase for phrase in _CLAIM_PASS if phrase in text]
    assert not hits, hits
    extra = set(_ID_RE.findall(text)) - _NOTE_IDS
    assert not extra, extra


def main() -> int:
    failed = 0
    for name, fn in (
        ("http_chat_omits_session_id", test_http_chat_omits_session_id),
        ("http_pending_stays_slim", test_http_pending_stays_slim),
        ("approve_without_token_is_403", test_approve_without_token_is_403),
        ("turn_still_has_session_id", test_turn_still_has_session_id),
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
