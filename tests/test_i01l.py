"""I-01l: POST /api/agent/reset requires token. reset_chat() stays open."""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import traceback
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))
os.environ.setdefault("QAGENT_DSH_MUX", "0")

from qagent.adapters.dsh_session_store import load_session_id, save_session_id
from qagent.entrypoints.shell_http import dispatch
from qagent.models.handles import HANDLE_ASSET, HANDLE_CIRCUIT, HANDLE_TWIN
from qagent.services.chat import reset_chat

_NOTE = ROOT / "docs" / "execution" / "I-01l_reset_http.md"
_HANDLES = frozenset({HANDLE_CIRCUIT, HANDLE_ASSET, HANDLE_TWIN})
_NOTE_IDS = _HANDLES
_ID_RE = re.compile(r"\b[a-z]+_id\b")
_CLAIM_PASS = ("G0 已通过", "G2 已通过", "G0 passed", "G2 passed")
_FORBIDDEN = {"error": "approval requires QAGENT_SHELL_TOKEN"}
_TOKEN = "i01l-secret"
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
def isolated(*, token: str | None = None) -> Iterator[Path]:
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
        yield folder
    finally:
        reset_chat()
        tmp.cleanup()
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def test_reset_without_token_is_403() -> None:
    with isolated():
        save_session_id("sess_staff")
        with patch("qagent.entrypoints.shell_http.reset_chat") as mocked_chat:
            code, forbidden = dispatch("POST", "/api/agent/reset", {}, {})
        assert code == 403
        assert forbidden == _FORBIDDEN
        mocked_chat.assert_not_called()
        assert load_session_id() == "sess_staff"


def test_reset_token_mismatch_is_403() -> None:
    with isolated(token=_TOKEN):
        save_session_id("sess_staff")
        with patch("qagent.entrypoints.shell_http.reset_chat") as mocked_chat:
            code, forbidden = dispatch(
                "POST",
                "/api/agent/reset",
                {},
                {"X-QAGENT-DEBUG-TOKEN": "nope"},
            )
        assert code == 403
        assert forbidden == _FORBIDDEN
        mocked_chat.assert_not_called()
        assert load_session_id() == "sess_staff"


def test_reset_with_matching_token_clears_staff() -> None:
    with isolated(token=_TOKEN):
        save_session_id("sess_staff")
        code, payload = dispatch(
            "POST",
            "/api/agent/reset",
            {},
            {"X-QAGENT-DEBUG-TOKEN": _TOKEN},
        )
        assert code == 200
        assert payload == {"ok": True}
        assert load_session_id() is None
        extra = set(_ID_RE.findall(json.dumps(payload)))
        assert not extra, extra
        assert "twin_id" not in json.dumps(payload)


def test_reset_chat_service_needs_no_token() -> None:
    with isolated():
        save_session_id("sess_staff")
        reset_chat()
        assert load_session_id() is None


def test_note_exists() -> None:
    assert _NOTE.is_file(), _NOTE
    text = _NOTE.read_text(encoding="utf-8")
    assert "不算接线" in text
    assert "reset 无 token 403" in text
    hits = [phrase for phrase in _CLAIM_PASS if phrase in text]
    assert not hits, hits
    extra = set(_ID_RE.findall(text)) - _NOTE_IDS
    assert not extra, extra


def main() -> int:
    failed = 0
    for name, fn in (
        ("reset_without_token_is_403", test_reset_without_token_is_403),
        ("reset_token_mismatch_is_403", test_reset_token_mismatch_is_403),
        ("reset_with_matching_token_clears_staff", test_reset_with_matching_token_clears_staff),
        ("reset_chat_service_needs_no_token", test_reset_chat_service_needs_no_token),
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
