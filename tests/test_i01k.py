"""I-01k: POST /api/eval requires token. Chat HTTP omits used_tools."""

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
from qagent.services.eval_run import EvalResult
from qagent.services.workplace import save_workplace

_NOTE = ROOT / "docs" / "execution" / "I-01k_eval_http.md"
_HANDLES = frozenset({HANDLE_CIRCUIT, HANDLE_ASSET, HANDLE_TWIN})
_NOTE_IDS = _HANDLES | {"session_id"}
_ID_RE = re.compile(r"\b[a-z]+_id\b")
_CLAIM_PASS = ("G0 已通过", "G2 已通过", "G0 passed", "G2 passed")
_FORBIDDEN = {"error": "approval requires QAGENT_SHELL_TOKEN"}
_TOKEN = "i01k-secret"
_FAT_KEYS = frozenset(
    {
        "detail",
        "body",
        "qasm",
        "qasm3",
        "token",
        "secret",
        "api_key",
        "password",
        "used_tools",
        "session_id",
    }
)
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
_CHAT_STUB = {
    "reply": "已经看见公司软件包。",
    "awaiting": None,
    "cards": [],
    "ready": True,
    "open_settings": False,
    "running": False,
    "via": "dsh-session",
    "used_tools": ["qagent_list_engines"],
    "session_id": "sess_i01k",
}


@contextmanager
def isolated(*, ready: bool = False, token: str | None = None) -> Iterator[Path]:
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
        if token is None:
            os.environ.pop("QAGENT_SHELL_TOKEN", None)
        else:
            os.environ["QAGENT_SHELL_TOKEN"] = token
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


def _assert_eval_face(payload: dict[str, Any]) -> None:
    assert isinstance(payload, dict)
    assert set(payload) == {"passed", "results"}
    assert isinstance(payload["passed"], bool)
    assert isinstance(payload["results"], list)
    for row in payload["results"]:
        assert set(row) == {"id", "ok"}
    keys = _walk_keys(payload)
    for name in _FAT_KEYS:
        assert name not in keys, name
    extra = set(_ID_RE.findall(json.dumps(payload)))
    assert not extra, extra
    blob = json.dumps(payload, ensure_ascii=False)
    assert "OPENQASM" not in blob
    assert "twin_id" not in blob


class Fake:
    def __init__(self) -> None:
        self.created = 0

    def __call__(self, method: str, payload: dict) -> dict:
        if method == "session.create":
            self.created += 1
            return {"result": {"ok": True, "value": {"sessionId": f"sess_i01k_{self.created}"}}}
        if method == "session.prompt":
            return {"result": {"ok": True, "value": {"accepted": True}}}
        if method == "session.history":
            return {
                "result": {
                    "ok": True,
                    "value": {
                        "events": [
                            {
                                "event": {
                                    "type": "tool/call",
                                    "data": {"name": "qagent_list_engines", "callId": "c1"},
                                }
                            },
                            {
                                "event": {
                                    "type": "assistant/message",
                                    "data": {
                                        "message": {
                                            "content": [{"type": "text", "text": "已经看见公司软件包。"}]
                                        }
                                    },
                                }
                            },
                        ],
                        "hasMore": False,
                    },
                }
            }
        raise AssertionError(method)


def test_eval_without_token_is_403() -> None:
    with isolated():
        with patch("qagent.entrypoints.shell_http.run_evals") as mocked:
            code, forbidden = dispatch("POST", "/api/eval", {"ids": ["E01"]})
        assert code == 403
        assert forbidden == _FORBIDDEN
        mocked.assert_not_called()


def test_eval_token_mismatch_is_403() -> None:
    with isolated(token=_TOKEN):
        with patch("qagent.entrypoints.shell_http.run_evals") as mocked:
            code, forbidden = dispatch(
                "POST",
                "/api/eval",
                {"ids": ["E01"]},
                {"X-QAGENT-DEBUG-TOKEN": "nope"},
            )
        assert code == 403
        assert forbidden == _FORBIDDEN
        mocked.assert_not_called()


def test_eval_with_matching_token_is_thin() -> None:
    fat = [
        EvalResult(id="E01", ok=True, detail="OPENQASM secret body"),
        EvalResult(id="E05", ok=False, detail="twin_id leaked"),
    ]
    with isolated(token=_TOKEN):
        with patch("qagent.entrypoints.shell_http.run_evals", return_value=fat) as mocked:
            code, payload = dispatch(
                "POST",
                "/api/eval",
                {"ids": ["E01", "E05"]},
                {"X-QAGENT-DEBUG-TOKEN": _TOKEN},
            )
        assert code == 200
        mocked.assert_called_once_with("E01", "E05")
        assert payload["passed"] is False
        assert payload["results"] == [{"id": "E01", "ok": True}, {"id": "E05", "ok": False}]
        _assert_eval_face(payload)


def test_http_chat_omits_used_tools_and_session_id() -> None:
    with isolated():
        with patch("qagent.entrypoints.shell_http.turn", return_value=dict(_CHAT_STUB)):
            code, posted = dispatch("POST", "/api/chat", {"message": "看看引擎"})
        with patch("qagent.entrypoints.shell_http.chat_status", return_value=dict(_CHAT_STUB)):
            code_st, status = dispatch("GET", "/api/chat/status")
            code_get, get_chat = dispatch("GET", "/api/chat")
        assert code == 200
        assert "used_tools" not in posted
        assert "session_id" not in _walk_keys(posted)
        assert posted.get("reply")
        assert code_st == 200
        assert "used_tools" not in status
        assert "session_id" not in _walk_keys(status)
        assert "session_id" not in _walk_keys(get_chat)


def test_turn_still_has_used_tools() -> None:
    with isolated(ready=True):
        out = turn(message="看看引擎", client=DshSessionClient(transport=Fake()))
        assert out.get("reply")
        assert "qagent_list_engines" in out["used_tools"]
        assert out.get("session_id")


def test_note_exists() -> None:
    assert _NOTE.is_file(), _NOTE
    text = _NOTE.read_text(encoding="utf-8")
    assert "不算接线" in text
    assert "eval 无 token 403" in text
    assert "不回 detail" in text
    hits = [phrase for phrase in _CLAIM_PASS if phrase in text]
    assert not hits, hits
    extra = set(_ID_RE.findall(text)) - _NOTE_IDS
    assert not extra, extra


def main() -> int:
    failed = 0
    for name, fn in (
        ("eval_without_token_is_403", test_eval_without_token_is_403),
        ("eval_token_mismatch_is_403", test_eval_token_mismatch_is_403),
        ("eval_with_matching_token_is_thin", test_eval_with_matching_token_is_thin),
        ("http_chat_omits_used_tools_and_session_id", test_http_chat_omits_used_tools_and_session_id),
        ("turn_still_has_used_tools", test_turn_still_has_used_tools),
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
