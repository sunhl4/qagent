"""H-01e: not-ready chat JSON tells the face to open settings. No twin_id."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import traceback
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ.setdefault("QAGENT_DSH_MUX", "0")

from qagent.adapters.dsh_session import DshSessionClient
from qagent.services.chat import classify, reset_chat, turn
from qagent.services.workplace import save_workplace

_ENV_KEYS = (
    "QAGENT_WORKPLACE_FILE",
    "QAGENT_SECRETS_FILE",
    "QAGENT_DSH_SESSION_FILE",
    "QAGENT_DSH_URL",
    "QAGENT_DSH_MUX",
    "QAGENT_DSH_WAIT_S",
)
_SETTINGS_REPLY = "先在设置里接上你们的本地大模型（地址和模型名）。接好之前我不会假装已经在 vibe。"
_EMPTY_REPLY = "说你要做什么。模型会自己选公司工具，没有写死的配方流程。"
_PENDING_KEYS = frozenset({"approval_id", "rpc_id", "tool", "reason"})
_CHAT_SRC = ROOT / "src" / "qagent" / "services" / "chat.py"


def _ok(name: str) -> None:
    print(f"ok  {name}")


def _no_twin(payload: object) -> None:
    dumped = json.dumps(payload, ensure_ascii=False)
    assert "twin_id" not in dumped


@contextmanager
def _temp_workplace(*, ready: bool):
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


class Boom:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def __call__(self, method: str, payload: dict) -> dict:
        self.calls.append(method)
        raise AssertionError(f"must not talk to dsh when not ready: {method}")


class Fake:
    def __init__(self, events: list[dict] | None = None) -> None:
        self.calls: list[str] = []
        self.events = list(events or _plain_events())

    def __call__(self, method: str, payload: dict) -> dict:
        self.calls.append(method)
        if method == "session.create":
            return {"result": {"ok": True, "value": {"sessionId": "sess_h01e"}}}
        if method == "session.prompt":
            return {"result": {"ok": True, "value": {"accepted": True}}}
        if method == "session.history":
            return {"result": {"ok": True, "value": {"events": self.events, "hasMore": False}}}
        raise AssertionError(method)


def _plain_events() -> list[dict]:
    return [
        {
            "event": {
                "type": "assistant/message",
                "data": {"message": {"content": [{"type": "text", "text": "已进 session"}]}},
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
                    "sessionId": "sess_h01e",
                    "approvalId": "appr-1",
                    "toolName": "ionstack_twin_run",
                    "reason": "shots",
                    "callId": "call-1",
                    "twin_id": "must-not-copy",
                },
            }
        }
    ]


def test_not_ready_opens_settings() -> None:
    with _temp_workplace(ready=False):
        boom = Boom()
        out = turn(message="扫氢分子", client=DshSessionClient(transport=boom))
        assert boom.calls == []
        assert out["open_settings"] is True
        assert out["ready"] is False
        assert out["via"] == "dsh-session"
        assert out["reply"] == _SETTINGS_REPLY
        assert "pending_approval" not in out
        assert out.get("session_id") == ""
        _no_twin(out)


def test_ready_does_not_open_settings() -> None:
    with _temp_workplace(ready=True):
        fake = Fake()
        out = turn(message="看看我们接了哪些软件", client=DshSessionClient(transport=fake))
        assert "session.create" in fake.calls
        assert out["open_settings"] is False
        assert out["ready"] is True
        assert out["via"] == "dsh-session"
        assert "pending_approval" not in out
        _no_twin(out)


def test_classify_empty_still_works() -> None:
    assert classify("") == "empty"
    assert classify("批准") == "approve"
    assert classify("先估计氢分子，先不上机") == "run"
    with _temp_workplace(ready=False):
        boom = Boom()
        out = turn(message="   ", client=DshSessionClient(transport=boom))
        assert boom.calls == []
        assert out["reply"] == _EMPTY_REPLY
        assert out["open_settings"] is True
        assert out["via"] == "dsh-session"
        _no_twin(out)
    with _temp_workplace(ready=True):
        boom = Boom()
        out = turn(message="", client=DshSessionClient(transport=boom))
        assert boom.calls == []
        assert out["reply"] == _EMPTY_REPLY
        assert out["open_settings"] is False
        assert "pending_approval" not in out
        _no_twin(out)


def test_pending_approval_from_snapshot_only() -> None:
    with _temp_workplace(ready=True):
        fake = Fake(events=_pending_events())
        out = turn(message="扫氢分子", client=DshSessionClient(transport=fake))
        pending = out.get("pending_approval")
        assert isinstance(pending, dict)
        assert set(pending) <= _PENDING_KEYS
        assert pending["approval_id"] == "appr-1"
        assert pending["rpc_id"] == "rpc-live"
        assert pending["tool"] == "ionstack_twin_run"
        assert pending["reason"] == "shots"
        assert "call_id" not in pending
        assert out["open_settings"] is False
        _no_twin(out)
        _no_twin(pending)


def test_chat_source_no_twin_mint() -> None:
    text = _CHAT_SRC.read_text(encoding="utf-8")
    assert "twin_id" not in text
    assert "from qagent.services.agent import" not in text
    assert "def _loop" not in text


def main() -> int:
    failed = 0
    for name, fn in [
        ("not_ready_opens_settings", test_not_ready_opens_settings),
        ("ready_does_not_open_settings", test_ready_does_not_open_settings),
        ("classify_empty_still_works", test_classify_empty_still_works),
        ("pending_approval_from_snapshot_only", test_pending_approval_from_snapshot_only),
        ("chat_source_no_twin_mint", test_chat_source_no_twin_mint),
    ]:
        try:
            fn()
            _ok(name)
        except Exception:
            failed += 1
            print(f"FAIL {name}")
            traceback.print_exc()
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
