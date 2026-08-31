"""H-01d: dsh native approve/respond on the same session. No live dsh."""

from __future__ import annotations

import json
import os
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("QAGENT_DSH_MUX", "0")

from qagent.adapters.dsh_session import DshSessionClient, fold_history, parse_mux_sse
from qagent.adapters.dsh_session_store import save_session_id
from qagent.services.chat import reset_chat, turn
from qagent.services.workplace import save_workplace


FOLDER = ROOT / ".qagent" / "test-h01d"
PREVIOUS: dict[str, str | None] = {}


def _ok(name: str) -> None:
    print(f"ok  {name}")


def _history_ok(events: list[dict]) -> dict:
    return {"result": {"ok": True, "value": {"events": events, "hasMore": False}}}


def _pending_events(*, kind: str = "approval/requested") -> list[dict]:
    if kind == "approval/asked":
        data = {
            "id": "appr-1",
            "toolName": "ionstack_twin_run",
            "reason": "shots",
            "callId": "call-1",
        }
        return [{"event": {"type": "approval/asked", "data": data}}]
    return [
        {
            "event": {
                "type": "approval/requested",
                "rpcId": "rpc-live",
                "data": {
                    "sessionId": "sess_exist",
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


def _plain_events() -> list[dict]:
    return [
        {
            "event": {
                "type": "assistant/message",
                "data": {"message": {"content": [{"type": "text", "text": "已进 session"}]}},
            }
        }
    ]


class Fake:
    def __init__(self, events: list[dict] | None = None) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.events = list(events or _pending_events())

    def __call__(self, method: str, payload: dict) -> dict:
        self.calls.append((method, payload))
        if method == "session.create":
            return {"result": {"ok": True, "value": {"sessionId": "sess_new"}}}
        if method == "session.prompt":
            return {"result": {"ok": True, "value": {"accepted": True}}}
        if method == "session.history":
            return _history_ok(self.events)
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


def _setup() -> None:
    FOLDER.mkdir(parents=True, exist_ok=True)
    keys = (
        "QAGENT_WORKPLACE_FILE",
        "QAGENT_SECRETS_FILE",
        "QAGENT_DSH_SESSION_FILE",
        "QAGENT_DSH_URL",
        "QAGENT_DSH_MUX",
        "QAGENT_DSH_WAIT_S",
    )
    for key in keys:
        PREVIOUS[key] = os.environ.get(key)
    os.environ["QAGENT_WORKPLACE_FILE"] = str(FOLDER / "workplace.json")
    os.environ["QAGENT_SECRETS_FILE"] = str(FOLDER / "secrets.json")
    os.environ["QAGENT_DSH_SESSION_FILE"] = str(FOLDER / "dsh-session.json")
    os.environ["QAGENT_DSH_URL"] = "http://127.0.0.1:9"
    os.environ["QAGENT_DSH_MUX"] = "0"
    os.environ["QAGENT_DSH_WAIT_S"] = "0"
    reset_chat()
    save_workplace({"llm_base_url": "http://127.0.0.1:9/v1", "llm_model": "unitqc-local"})


def _teardown() -> None:
    reset_chat()
    for key, value in PREVIOUS.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    for name in ("workplace.json", "secrets.json", "dsh-session.json"):
        try:
            (FOLDER / name).unlink()
        except OSError:
            pass


def test_fold_asked() -> None:
    snap = fold_history({"events": _pending_events(kind="approval/asked")}, session_id="sess_exist")
    assert snap["awaiting"] == "approve"
    pending = snap["pending_approval"]
    assert pending is not None
    assert pending["approval_id"] == "appr-1"
    assert pending["tool"] == "ionstack_twin_run"
    assert pending["reason"] == "shots"


def test_fold_requested() -> None:
    snap = fold_history({"events": _pending_events()}, session_id="sess_exist")
    assert snap["awaiting"] == "approve"
    pending = snap["pending_approval"]
    assert pending is not None
    assert pending["rpc_id"] == "rpc-live"
    assert pending["approval_id"] == "appr-1"
    assert pending["tool"] == "ionstack_twin_run"


def test_fold_resolved_clears() -> None:
    events = _pending_events() + _resolved_events()
    snap = fold_history({"events": events}, session_id="sess_exist")
    assert snap["pending_approval"] is None
    assert snap["awaiting"] is None
    assert "续跑" in snap["reply"]


def test_fold_tool_result_clears() -> None:
    events = _pending_events() + [{"event": {"type": "tool/result", "data": {"callId": "call-1", "name": "ionstack_twin_run"}}}]
    snap = fold_history({"events": events}, session_id="sess_exist")
    assert snap["pending_approval"] is None
    assert snap["awaiting"] is None


def test_approve_same_session() -> None:
    _setup()
    try:
        save_session_id("sess_exist")
        fake = Fake()
        out = turn(message="批准", client=DshSessionClient(transport=fake))
        assert "session.create" not in fake.methods()
        assert "session.prompt" not in fake.methods()
        assert "respond" in fake.methods()
        body = fake.payload("respond")
        assert body["rpcId"] == "rpc-live"
        assert body["value"]["sessionId"] == "sess_exist"
        assert body["value"]["approvalId"] == "appr-1"
        assert body["value"]["outcome"] == "allowed-once"
        assert out["session_id"] == "sess_exist"
        assert "同一条 session" in out["reply"]
        assert "allowed-once" in out["reply"]
        dumped = json.dumps(out, ensure_ascii=False)
        assert "twin_id" not in dumped
    finally:
        _teardown()


def test_reject_same_session() -> None:
    _setup()
    try:
        save_session_id("sess_exist")
        fake = Fake()
        out = turn(message="先不批", client=DshSessionClient(transport=fake))
        assert "session.create" not in fake.methods()
        assert "session.prompt" not in fake.methods()
        body = fake.payload("respond")
        assert body["value"]["outcome"] == "rejected"
        assert body["value"]["sessionId"] == "sess_exist"
        assert "同一条 session" in out["reply"]
        assert "rejected" in out["reply"]
        assert "twin_id" not in json.dumps(out)
    finally:
        _teardown()


def test_approve_no_pending() -> None:
    _setup()
    try:
        save_session_id("sess_exist")
        fake = Fake(events=_plain_events())
        out = turn(message="批准", client=DshSessionClient(transport=fake))
        assert "session.create" not in fake.methods()
        assert "session.prompt" not in fake.methods()
        assert "respond" not in fake.methods()
        assert "现在没有待批准的上机" in out["reply"]
        assert "twin_id" not in out["reply"]
        assert "twin_id" not in json.dumps(out)
    finally:
        _teardown()


def test_create_prompt_history_still_work() -> None:
    def transport(method: str, payload: dict) -> dict:
        if method == "session.create":
            assert payload.get("agentPreset") == "qagent"
            return {"result": {"ok": True, "value": {"sessionId": "sess_test"}}}
        if method == "session.prompt":
            assert payload["sessionId"] == "sess_test"
            assert payload["content"][0]["text"] == "扫氢分子"
            return {"result": {"ok": True, "value": {"accepted": True}}}
        if method == "session.history":
            return _history_ok(_plain_events())
        raise AssertionError(method)

    client = DshSessionClient(transport=transport)
    session_id = client.create()
    assert session_id == "sess_test"
    client.prompt(session_id, "扫氢分子")
    snap = client.snapshot(session_id)
    assert snap["reply"] == "已进 session"
    assert snap["pending_approval"] is None
    assert client.wait_for_turn(session_id, timeout=0)["reply"] == "已进 session"


def test_chat_run_still_prompts() -> None:
    _setup()
    try:
        fake = Fake(events=_plain_events())
        out = turn(message="看看我们接了哪些软件", client=DshSessionClient(transport=fake))
        assert "session.create" in fake.methods()
        assert "session.prompt" in fake.methods()
        assert fake.payload("session.prompt")["sessionId"] == "sess_new"
        assert "已进 session" in out["reply"]
        assert out.get("via") == "dsh-session"
    finally:
        _teardown()


def test_parse_mux_sse_no_live() -> None:
    frame = {
        "type": "server-request",
        "rpcId": "rpc-mux",
        "method": "approval/requested",
        "payload": {
            "type": "approval/requested",
            "sessionId": "sess_exist",
            "approvalId": "appr-9",
            "toolName": "ionstack_twin_run",
            "reason": "shots",
        },
    }
    raw = ": connected\n\ndata: " + json.dumps(frame) + "\n\n"
    pending = parse_mux_sse(raw, session_id="sess_exist")
    assert pending is not None
    assert pending["rpc_id"] == "rpc-mux"
    assert pending["approval_id"] == "appr-9"
    assert parse_mux_sse(raw, session_id="other") is None


def main() -> int:
    failed = 0
    for name, fn in [
        ("fold_asked", test_fold_asked),
        ("fold_requested", test_fold_requested),
        ("fold_resolved_clears", test_fold_resolved_clears),
        ("fold_tool_result_clears", test_fold_tool_result_clears),
        ("approve_same_session", test_approve_same_session),
        ("reject_same_session", test_reject_same_session),
        ("approve_no_pending", test_approve_no_pending),
        ("create_prompt_history_still_work", test_create_prompt_history_still_work),
        ("chat_run_still_prompts", test_chat_run_still_prompts),
        ("parse_mux_sse_no_live", test_parse_mux_sse_no_live),
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
