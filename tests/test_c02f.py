"""C-02f: chat / dsh session split by tenant. Empty tenant stays the staff file."""

from __future__ import annotations

import json
import os
import stat
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

from qagent.adapters.dsh_session import DshSessionClient
from qagent.adapters.dsh_session_store import (
    clear_session_id,
    load_session_id,
    save_session_id,
    session_path,
    tenants_path,
)
from qagent.entrypoints.shell_http import dispatch
from qagent.services.chat import reset_chat, status, turn
from qagent.services.workplace import save_workplace

_ENV_KEYS = (
    "QAGENT_WORKPLACE_FILE",
    "QAGENT_SECRETS_FILE",
    "QAGENT_DSH_SESSION_FILE",
    "QAGENT_DSH_URL",
    "QAGENT_DSH_MUX",
    "QAGENT_DSH_WAIT_S",
    "QAGENT_AGENT_THREAD",
)
_TENANT_A = "cust-a"
_TENANT_B = "cust-b"
_HEADER_A = {"X-QAGENT-TENANT": _TENANT_A}
_HEADER_B = {"X-QAGENT-TENANT": _TENANT_B}
_NOTE = ROOT / "docs" / "execution" / "C-02f_chat_tenant.md"
_INTERFACES = ROOT / "INTERFACES.md"
_STORE = SRC / "qagent" / "adapters" / "dsh_session_store.py"
_CHAT = SRC / "qagent" / "services" / "chat.py"
_HTTP = SRC / "qagent" / "entrypoints" / "shell_http.py"
_BANNED = ("qdata", "ionstack", "qchem", "qiskit")


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


def _ok(name: str) -> None:
    print(f"ok  {name}")


def _no_twin(payload: object) -> None:
    dumped = json.dumps(payload, ensure_ascii=False)
    assert "twin_id" not in dumped


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def _plain_events(text: str = "已进 session") -> list[dict]:
    return [
        {
            "event": {
                "type": "assistant/message",
                "data": {"message": {"content": [{"type": "text", "text": text}]}},
            }
        }
    ]


def _pending_events(session_id: str = "sess_exist") -> list[dict]:
    return [
        {
            "event": {
                "type": "approval/requested",
                "rpcId": "rpc-live",
                "data": {
                    "sessionId": session_id,
                    "approvalId": "appr-1",
                    "toolName": "ionstack_twin_run",
                    "reason": "shots",
                    "callId": "call-1",
                },
            }
        }
    ]


def _resolved_events() -> list[dict]:
    return [
        {
            "event": {
                "type": "approval/resolved",
                "data": {"approvalId": "appr-1", "outcome": "allowed-once"},
            }
        },
        {
            "event": {
                "type": "assistant/message",
                "data": {"message": {"content": [{"type": "text", "text": "同一条 session 已续跑"}]}},
            }
        },
        {"event": {"type": "turn/end", "data": {}}},
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
            return {"result": {"ok": True, "value": {"sessionId": f"sess_t{self.created}"}}}
        if method == "session.prompt":
            return {"result": {"ok": True, "value": {"accepted": True}}}
        if method == "session.history":
            return {"result": {"ok": True, "value": {"events": self.events, "hasMore": False}}}
        if method == "respond":
            self.events = _resolved_events()
            return {"accepted": True}
        raise AssertionError(method)

    def methods(self) -> list[str]:
        return [name for name, _ in self.calls]

    def payload(self, method: str) -> dict:
        for name, body in self.calls:
            if name == method:
                return body
        raise AssertionError(f"missing {method}")


def _bind(fake: Fake):
    def factory(*args, **kwargs):
        kwargs["transport"] = fake
        return DshSessionClient(*args, **kwargs)

    return factory


def test_empty_tenant_existing_api() -> None:
    with isolated():
        save_session_id("sess_a")
        assert load_session_id() == "sess_a"
        path = session_path()
        assert path.is_file()
        raw = json.loads(path.read_text(encoding="utf-8"))
        assert raw == {"sessionId": "sess_a"}
        assert _mode(path) == 0o600
        assert not tenants_path().is_file()
        clear_session_id()
        assert load_session_id() is None
        assert not path.is_file()


def test_tenants_keep_separate_keys() -> None:
    with isolated():
        save_session_id("sess_staff")
        save_session_id("sess_a", tenant_id=_TENANT_A)
        save_session_id("sess_b", tenant_id=_TENANT_B)
        assert load_session_id() == "sess_staff"
        assert load_session_id(tenant_id=_TENANT_A) == "sess_a"
        assert load_session_id(tenant_id=_TENANT_B) == "sess_b"
        staff = json.loads(session_path().read_text(encoding="utf-8"))
        assert staff == {"sessionId": "sess_staff"}
        assert "by_tenant" not in staff
        sidecar = tenants_path()
        assert sidecar.is_file()
        assert _mode(sidecar) == 0o600
        buckets = json.loads(sidecar.read_text(encoding="utf-8"))
        assert buckets == {"by_tenant": {_TENANT_A: "sess_a", _TENANT_B: "sess_b"}}


def test_turn_status_a_cannot_see_b() -> None:
    with isolated(ready=True):
        save_session_id("sess_b", tenant_id=_TENANT_B)
        fake = Fake(events=_plain_events("只给 B"))
        out_a = turn(message="办 A", client=DshSessionClient(transport=fake), tenant_id=_TENANT_A)
        assert out_a["session_id"] != "sess_b"
        assert load_session_id(tenant_id=_TENANT_A) != "sess_b"
        assert load_session_id(tenant_id=_TENANT_B) == "sess_b"
        st_a = status(client=DshSessionClient(transport=fake), tenant_id=_TENANT_A)
        st_b = status(client=DshSessionClient(transport=fake), tenant_id=_TENANT_B)
        assert st_a["session_id"] != "sess_b"
        assert st_b["session_id"] == "sess_b"
        staff = status(client=DshSessionClient(transport=fake))
        assert staff["session_id"] == ""
        _no_twin(out_a)
        _no_twin(st_a)
        _no_twin(st_b)


def test_http_headers_split_sessions() -> None:
    with isolated(ready=True):
        fake = Fake()
        with patch("qagent.services.chat.DshSessionClient", side_effect=_bind(fake)):
            code_a, out_a = dispatch("POST", "/api/chat", {"message": "办 A"}, _HEADER_A)
            code_b, out_b = dispatch("POST", "/api/chat", {"message": "办 B"}, _HEADER_B)
            code_a2, again_a = dispatch("POST", "/api/chat", {"message": "再办 A"}, _HEADER_A)
            code_sa, st_a = dispatch("GET", "/api/chat/status", {}, _HEADER_A)
            code_sb, st_b = dispatch("GET", "/api/chat/status", {}, _HEADER_B)
            code_ss, staff = dispatch("GET", "/api/chat/status")
        assert code_a == code_b == code_a2 == code_sa == code_sb == code_ss == 200
        assert fake.created == 2
        prompts = [body["sessionId"] for name, body in fake.calls if name == "session.prompt"]
        assert len(prompts) == 3
        assert prompts[0] != prompts[1]
        assert prompts[2] == prompts[0]
        store_a = load_session_id(tenant_id=_TENANT_A)
        store_b = load_session_id(tenant_id=_TENANT_B)
        assert store_a == prompts[0]
        assert store_b == prompts[1]
        assert store_a != store_b
        assert load_session_id() is None
        assert out_a.get("reply") and out_b.get("reply") and again_a.get("reply")
        assert st_a.get("via") == "dsh-session"
        assert st_b.get("via") == "dsh-session"
        assert staff.get("via") == "dsh-session"
        _no_twin(out_a)
        _no_twin(out_b)
        _no_twin(st_a)
        _no_twin(st_b)


def test_reset_empty_unlinks_staff() -> None:
    with isolated():
        save_session_id("sess_staff")
        save_session_id("sess_a", tenant_id=_TENANT_A)
        reset_chat()
        assert load_session_id() is None
        assert not session_path().is_file()
        assert load_session_id(tenant_id=_TENANT_A) == "sess_a"
        save_session_id("sess_staff2")
        previous = os.environ.get("QAGENT_SHELL_TOKEN")
        os.environ["QAGENT_SHELL_TOKEN"] = "c02f-secret"
        try:
            code, payload = dispatch(
                "POST",
                "/api/agent/reset",
                {},
                {"X-QAGENT-DEBUG-TOKEN": "c02f-secret"},
            )
        finally:
            if previous is None:
                os.environ.pop("QAGENT_SHELL_TOKEN", None)
            else:
                os.environ["QAGENT_SHELL_TOKEN"] = previous
        assert code == 200
        assert payload == {"ok": True}
        assert load_session_id() is None
        assert not session_path().is_file()
        assert load_session_id(tenant_id=_TENANT_A) == "sess_a"


def test_reset_one_tenant_only() -> None:
    with isolated():
        save_session_id("sess_a", tenant_id=_TENANT_A)
        save_session_id("sess_b", tenant_id=_TENANT_B)
        reset_chat(tenant_id=_TENANT_A)
        assert load_session_id(tenant_id=_TENANT_A) is None
        assert load_session_id(tenant_id=_TENANT_B) == "sess_b"
        previous = os.environ.get("QAGENT_SHELL_TOKEN")
        os.environ["QAGENT_SHELL_TOKEN"] = "c02f-secret"
        try:
            code, payload = dispatch(
                "POST",
                "/api/agent/reset",
                {},
                {**_HEADER_B, "X-QAGENT-DEBUG-TOKEN": "c02f-secret"},
            )
        finally:
            if previous is None:
                os.environ.pop("QAGENT_SHELL_TOKEN", None)
            else:
                os.environ["QAGENT_SHELL_TOKEN"] = previous
        assert code == 200
        assert payload == {"ok": True}
        assert load_session_id(tenant_id=_TENANT_B) is None
        assert not tenants_path().is_file()


def test_approve_stays_on_caller_session() -> None:
    with isolated(ready=True):
        save_session_id("sess_a", tenant_id=_TENANT_A)
        save_session_id("sess_b", tenant_id=_TENANT_B)
        fake_a = Fake(events=_pending_events("sess_a"))
        out = turn(message="批准", client=DshSessionClient(transport=fake_a), tenant_id=_TENANT_A)
        assert "session.create" not in fake_a.methods()
        assert "session.prompt" not in fake_a.methods()
        body = fake_a.payload("respond")
        assert body["value"]["sessionId"] == "sess_a"
        assert body["value"]["outcome"] == "allowed-once"
        assert out["session_id"] == "sess_a"
        _no_twin(out)
        fake_empty = Fake(events=_pending_events("sess_b"))
        none = turn(message="批准", client=DshSessionClient(transport=fake_empty), tenant_id="cust-c")
        assert "session.create" not in fake_empty.methods()
        assert "respond" not in fake_empty.methods()
        assert "现在没有待批准的上机" in none["reply"]
        _no_twin(none)


def test_tenant_key_is_not_a_path() -> None:
    with isolated() as folder:
        evil = "../../tmp/qagent-c02f-pwn"
        pwn = Path("/tmp/qagent-c02f-pwn")
        existed = pwn.exists()
        save_session_id("sess_x", tenant_id=evil)
        assert load_session_id() is None
        assert load_session_id(tenant_id=evil) == "sess_x"
        assert not session_path().is_file()
        sidecar = tenants_path().resolve()
        assert sidecar.is_file()
        assert sidecar.parent == folder.resolve()
        assert ".." not in sidecar.name
        assert "/" not in json.loads(sidecar.read_text(encoding="utf-8"))["by_tenant"]
        if not existed:
            assert not pwn.exists()


def test_no_twin_or_science_import() -> None:
    for path in (_STORE, _CHAT, _HTTP):
        text = path.read_text(encoding="utf-8")
        assert "twin_id" not in text
        for name in _BANNED:
            assert f"import {name}" not in text
            assert f"from {name}" not in text
    chat = _CHAT.read_text(encoding="utf-8")
    assert "def _loop" not in chat
    assert "from qagent.services.agent import" not in chat
    http = _HTTP.read_text(encoding="utf-8")
    body = http.split("def dispatch(", 1)[1].split("\ndef ", 1)[0]
    assert "\n        status =" not in body
    assert "status as chat_status" in http


def test_note_and_interfaces() -> None:
    assert _NOTE.is_file(), _NOTE
    text = _NOTE.read_text(encoding="utf-8")
    assert "sessionId" in text
    assert "by_tenant" in text
    assert "0600" in text
    assert "空租户" in text
    assert "旁路" in text or "tenants.json" in text
    assert "不铸" in text or "twin_id" in text
    interfaces = _INTERFACES.read_text(encoding="utf-8")
    assert "已设租户各一条 session" in interfaces


def main() -> int:
    failed = 0
    for name, fn in (
        ("empty_tenant_existing_api", test_empty_tenant_existing_api),
        ("tenants_keep_separate_keys", test_tenants_keep_separate_keys),
        ("turn_status_a_cannot_see_b", test_turn_status_a_cannot_see_b),
        ("http_headers_split_sessions", test_http_headers_split_sessions),
        ("reset_empty_unlinks_staff", test_reset_empty_unlinks_staff),
        ("reset_one_tenant_only", test_reset_one_tenant_only),
        ("approve_stays_on_caller_session", test_approve_stays_on_caller_session),
        ("tenant_key_is_not_a_path", test_tenant_key_is_not_a_path),
        ("no_twin_or_science_import", test_no_twin_or_science_import),
        ("note_and_interfaces", test_note_and_interfaces),
    ):
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
