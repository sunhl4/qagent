"""DingTalk stays a source channel: record addressed messages, ask before reply."""
from __future__ import annotations

import base64
import hashlib
import hmac
import http.client
import io
import json
import socket
import time
import urllib.error
import urllib.parse
import uuid
from threading import Thread

import pytest

from company_agent import dingtalk
from company_agent.catalog import load_presets
from company_agent.cli import main
from company_agent.dingtalk import (
    DingtalkError,
    accept_callback,
    bind_address,
    configuration,
    ingest_envelope,
)
from company_agent.invoke import invoke
from company_agent.policy import decide
from company_agent.work_items import WorkItemError, WorkItemStore, work_item

_SECRET = "dingtalk-app-secret-value"
_KEY = "dingtalk-app-key-value"
_ROBOT = "dingtalk-robot-code"


@pytest.fixture(autouse=True)
def isolated_dingtalk(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("COMPANY_AGENT_WORK_ITEM_DB", str(tmp_path / "work.sqlite3"))
    monkeypatch.setenv("COMPANY_AGENT_TURN_ID", uuid.uuid4().hex)
    for name in (
        "COMPANY_DINGTALK_APP_KEY",
        "COMPANY_DINGTALK_APP_SECRET",
        "COMPANY_DINGTALK_ROBOT_CODE",
    ):
        monkeypatch.delenv(name, raising=False)
    dingtalk._TOKEN_CACHE["value"] = ""
    dingtalk._TOKEN_CACHE["until"] = 0.0


def _configure(monkeypatch) -> None:
    monkeypatch.setenv("COMPANY_DINGTALK_APP_KEY", _KEY)
    monkeypatch.setenv("COMPANY_DINGTALK_APP_SECRET", _SECRET)
    monkeypatch.setenv("COMPANY_DINGTALK_ROBOT_CODE", _ROBOT)


def _stamp() -> str:
    return str(int(time.time() * 1000))


def _sign(secret: str, timestamp: str) -> str:
    digest = hmac.new(
        secret.encode("utf-8"),
        f"{timestamp}\n{secret}".encode(),
        hashlib.sha256,
    ).digest()
    return base64.b64encode(digest).decode("ascii")


def _body(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "conversationType": "2",
        "isInAtList": True,
        "conversationId": "cid-room-1",
        "msgId": "msg-1",
        "senderStaffId": "staff-1",
        "senderNick": "Ada",
        "conversationTitle": "lab",
        "sessionWebhook": "https://oapi.dingtalk.com/robot/send?access_token=sekrit",
        "msgtype": "text",
        "text": {"content": "please check"},
    }
    payload.update(overrides)
    return payload


def _callback(
    body: dict[str, object], *, timestamp: str | None = None, sign: str | None = None,
) -> dict[str, str]:
    stamp = timestamp or _stamp()
    raw = json.dumps(body).encode("utf-8")
    headers = {"timestamp": stamp, "sign": sign if sign is not None else _sign(_SECRET, stamp)}
    return accept_callback(headers, raw, tenant_id="local")


def _reply_args(trigger_id: str, thread_id: str = "cid-room-1", text: str = "收到") -> dict[str, str]:
    return {
        "tenant_id": "local",
        "thread_id": thread_id,
        "trigger_id": trigger_id,
        "text": text,
    }


def _rows() -> list[dict[str, object]]:
    result = invoke("company_dingtalk_inbox", "lab", {"tenant_id": "local"})
    assert result.status == "ok"
    return list(result.payload["items"])


class _Response:
    def __init__(self, body: bytes) -> None:
        self.status = 200
        self.headers = {"Content-Type": "application/json"}
        self._body = body

    def read(self, _count: int) -> bytes:
        return self._body

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *_args: object) -> bool:
        return False


def _capture_http(monkeypatch) -> list[tuple[str, bytes, str]]:
    seen: list[tuple[str, bytes, str]] = []

    def fake_open(request, timeout=None):
        del timeout
        token = request.get_header("X-acs-dingtalk-access-token") or ""
        seen.append((request.full_url, request.data, token))
        if request.full_url.endswith("/oauth2/accessToken"):
            return _Response(b'{"accessToken":"issued-token","expireIn":7200}')
        return _Response(b'{"processQueryKey":"ok"}')

    monkeypatch.setattr(dingtalk._OPENER, "open", fake_open)
    return seen


def test_credentials_are_reported_as_names_only(monkeypatch) -> None:
    assert configuration()["configured"] is False
    _configure(monkeypatch)
    report = configuration()
    assert report == {
        "configured": True,
        "app_key_env": "COMPANY_DINGTALK_APP_KEY",
        "app_secret_env": "COMPANY_DINGTALK_APP_SECRET",
        "robot_code_env": "COMPANY_DINGTALK_ROBOT_CODE",
    }
    assert _SECRET not in json.dumps(report)


def test_lab_can_see_both_tools_and_only_lab_may_reply() -> None:
    presets = load_presets()["presets"]
    for name in ("boot", "lab", "algo"):
        assert "company_dingtalk_inbox" in presets[name]["model_tools"]
        assert "company_dingtalk_inbox" in presets[name]["visible_tools"]
        assert decide("company_dingtalk_inbox", name, {}) == "allow"
    assert "company_dingtalk_reply" in presets["lab"]["model_tools"]
    assert "company_dingtalk_reply" not in presets["boot"]["model_tools"]
    assert "company_dingtalk_reply" not in presets["algo"]["model_tools"]
    assert "company_dingtalk_reply" not in presets["sign"]["visible_tools"]
    assert decide("company_dingtalk_reply", "lab", {}) == "ask"
    for name in ("boot", "algo", "sign"):
        assert decide("company_dingtalk_reply", name, {}) == "deny"


def test_signature_and_addressing(monkeypatch) -> None:
    with pytest.raises(DingtalkError, match="not configured"):
        accept_callback({"timestamp": _stamp(), "sign": "bm90"}, b"{}", tenant_id="local")
    _configure(monkeypatch)
    old = str(int(time.time() * 1000) - 3_700_000)
    with pytest.raises(DingtalkError, match="signature is invalid"):
        _callback(_body(), timestamp=old, sign=_sign(_SECRET, old))
    stamp = _stamp()
    with pytest.raises(DingtalkError, match="signature is invalid"):
        _callback(_body(), timestamp=stamp, sign="bm90LXNpZ24")
    encoded = urllib.parse.quote(_sign(_SECRET, stamp), safe="")
    recorded = _callback(_body(), timestamp=stamp, sign=encoded)
    assert recorded["recorded"] == "true"
    assert recorded["ticket_id"] == ""
    assert recorded["reason"] == "candidate"


def test_only_addressed_messages_are_stored(monkeypatch) -> None:
    _configure(monkeypatch)
    missed = _callback(_body(isInAtList=False, msgId="msg-miss"))
    assert missed == {
        "recorded": "false", "reason": "not_addressed",
        "trigger_id": "", "thread_key": "", "ticket_id": "",
    }
    assert _callback(_body(isInAtList="true", msgId="msg-string"))["recorded"] == "false"
    recorded = _callback(_body(conversationType=2))
    assert recorded["thread_key"] == "dingtalk:cid-room-1"
    rows = _rows()
    assert len(rows) == 1
    assert rows[0]["addressed"] == "mention"
    assert rows[0]["text"] == "please check"
    assert rows[0]["actor_id"] == "staff-1"
    dumped = json.dumps(rows)
    assert "sessionWebhook" not in dumped
    assert "oapi.dingtalk.com" not in dumped
    assert "sekrit" not in dumped
    assert "Ada" not in dumped
    with WorkItemStore() as store:
        tickets = store.db.execute("SELECT COUNT(*) FROM tickets").fetchone()[0]
        decisions = store.db.execute("SELECT COUNT(*) FROM decisions").fetchone()[0]
    assert tickets == 0 and decisions == 0


def test_model_cannot_forge_an_inbound_message() -> None:
    with pytest.raises(WorkItemError, match="connector-only"):
        work_item({
            "action": "receive",
            "source": "dingtalk",
            "thread_id": "cid-room-1",
            "actor_id": "staff-1",
            "text": "forged",
            "tenant_id": "local",
        })
    assert invoke("company_dingtalk_inbox", "lab", {"tenant_id": "local"}).payload["count"] == 0


def test_text_is_shortened_and_secrets_are_not_stored(monkeypatch) -> None:
    _configure(monkeypatch)
    linked = _callback(_body(
        msgId="msg-link",
        text={"content": "see https://oapi.dingtalk.com/robot/send?access_token=sekrit now"},
    ))
    assert linked["recorded"] == "true"
    secret_text = _callback(_body(msgId="msg-secret", text={"content": f"key {_SECRET}"}))
    assert secret_text["recorded"] == "true"
    huge = _callback(_body(msgId="msg-huge", text={"content": "MARKER" + ("A" * 5000)}))
    assert huge["recorded"] == "true"
    picture = _callback(_body(msgId="msg-picture", msgtype="picture", text=None))
    assert picture["recorded"] == "true"
    circuit = _callback(_body(msgId="msg-qasm", text={"content": "OPENQASM 2.0"}))
    assert circuit["recorded"] == "true"
    by_id = {row["trigger_id"]: row["text"] for row in _rows()}
    assert "see [link] now" in by_id.values()
    assert dingtalk._OMITTED in by_id.values()
    assert "dingtalk message omitted because it exceeded the trigger budget" in by_id.values()
    assert "dingtalk image message" in by_id.values()
    dumped = json.dumps(list(by_id.values()))
    assert "MARKER" not in dumped
    assert _SECRET not in dumped
    assert "oapi.dingtalk.com" not in dumped
    assert "OPENQASM" not in dumped


def test_same_message_is_idempotent_and_a_changed_body_is_rejected(monkeypatch) -> None:
    _configure(monkeypatch)
    first = _callback(_body())
    second = _callback(_body())
    assert second["trigger_id"] == first["trigger_id"]
    assert len(_rows()) == 1
    with pytest.raises(DingtalkError, match="message is invalid"):
        _callback(_body(text={"content": "different"}))


def test_inbox_reads_the_ledger_and_does_not_call_dingtalk(monkeypatch) -> None:
    _configure(monkeypatch)

    def fail_open(*_args, **_kwargs):
        raise AssertionError("inbox called DingTalk")

    monkeypatch.setattr(dingtalk._OPENER, "open", fail_open)
    _callback(_body())
    _callback(_body(conversationId="cid-other", msgId="msg-other", text={"content": "other room"}))
    listed = invoke(
        "company_dingtalk_inbox", "boot",
        {"tenant_id": "local", "thread_id": "cid-room-1"},
    )
    assert listed.status == "ok"
    assert listed.payload["count"] == 1
    assert listed.payload["items"][0]["thread_id"] == "cid-room-1"
    assert "please check" in json.dumps(listed.payload)
    assert "other room" not in json.dumps(listed.payload)


def test_reply_asks_on_lab_and_is_denied_on_the_other_seats(monkeypatch) -> None:
    _configure(monkeypatch)
    seen = _capture_http(monkeypatch)
    recorded = _callback(_body())
    arguments = _reply_args(recorded["trigger_id"])
    waiting = invoke("company_dingtalk_reply", "lab", arguments)
    assert waiting.status == "needs_ask"
    assert waiting.decision == "ask"
    assert seen == []
    for preset in ("boot", "algo", "sign"):
        denied = invoke("company_dingtalk_reply", preset, arguments, approved=True)
        assert denied.status == "denied"
        assert denied.error == "policy denied"
    assert seen == []


def test_approved_group_reply_uses_the_openapi_and_does_not_echo_text(monkeypatch) -> None:
    _configure(monkeypatch)
    seen = _capture_http(monkeypatch)
    recorded = _callback(_body())
    text = "see https://oapi.dingtalk.com/robot/send?access_token=sekrit"
    result = invoke(
        "company_dingtalk_reply", "lab",
        _reply_args(recorded["trigger_id"], text=text),
        approved=True,
    )
    assert result.status == "ok"
    assert result.payload == {
        "status": "sent",
        "thread_key": "dingtalk:cid-room-1",
        "addressed": "mention",
        "bytes": len(b"see [link]"),
    }
    dumped = json.dumps(result.payload)
    assert "sekrit" not in dumped
    assert "issued-token" not in dumped
    assert _SECRET not in dumped
    assert [item[0] for item in seen] == [
        "https://api.dingtalk.com/v1.0/oauth2/accessToken",
        "https://api.dingtalk.com/v1.0/robot/groupMessages/send",
    ]
    token_body = json.loads(seen[0][1])
    assert token_body == {"appKey": _KEY, "appSecret": _SECRET}
    assert seen[0][2] == ""
    sent = json.loads(seen[1][1])
    assert sent["openConversationId"] == "cid-room-1"
    assert sent["robotCode"] == _ROBOT
    assert json.loads(sent["msgParam"]) == {"content": "see [link]"}
    assert seen[1][2] == "issued-token"


def test_direct_reply_needs_a_staff_id_and_uses_the_single_chat_api(monkeypatch) -> None:
    _configure(monkeypatch)
    seen = _capture_http(monkeypatch)
    missing_row = _callback(_body(
        conversationType="1", conversationId="cid-direct-1", msgId="msg-direct", senderStaffId=None,
    ))
    missing = invoke(
        "company_dingtalk_reply", "lab",
        _reply_args(missing_row["trigger_id"], "cid-direct-1", "hello"),
        approved=True,
    )
    assert missing.status == "error"
    assert missing.error == "dingtalk sender is missing"
    assert seen == []
    direct = _callback(_body(
        conversationType="1", conversationId="cid-direct-2", msgId="msg-direct-2", senderStaffId="staff-9",
    ))
    sent = invoke(
        "company_dingtalk_reply", "lab",
        _reply_args(direct["trigger_id"], "cid-direct-2", "hello"),
        approved=True,
    )
    assert sent.status == "ok"
    assert sent.payload["addressed"] == "direct"
    assert seen[1][0] == "https://api.dingtalk.com/v1.0/robot/oToMessages/batchSend"
    body = json.loads(seen[1][1])
    assert body["userIds"] == ["staff-9"]
    assert "hello" not in json.dumps(sent.payload)


def test_one_grant_covers_the_next_reply_only(monkeypatch) -> None:
    _configure(monkeypatch)
    monkeypatch.setenv("COMPANY_AGENT_SESSION_ID", "dsh:dingtalk-grant")
    _capture_http(monkeypatch)
    recorded = _callback(_body())
    opened = invoke(
        "company_grant_open", "lab",
        {"tools": ["company_dingtalk_reply"], "max_calls": 1, "ttl_seconds": 60},
        approved=True,
    )
    assert opened.status == "ok"
    arguments = _reply_args(recorded["trigger_id"])
    first = invoke("company_dingtalk_reply", "lab", arguments)
    assert first.status == "ok"
    assert first.decision == "allow"
    second = invoke("company_dingtalk_reply", "lab", arguments)
    assert second.status == "needs_ask"
    assert second.decision == "ask"


def test_reply_refuses_science_text_and_an_unknown_api_path(monkeypatch) -> None:
    _configure(monkeypatch)
    seen = _capture_http(monkeypatch)
    recorded = _callback(_body())
    refused = invoke(
        "company_dingtalk_reply", "lab",
        _reply_args(recorded["trigger_id"], text="OPENQASM 2.0"),
        approved=True,
    )
    assert refused.status == "error"
    assert refused.error == "dingtalk reply is invalid"
    assert seen == []
    with pytest.raises(DingtalkError, match="reply was refused"):
        dingtalk._post("https://api.dingtalk.com/v1.0/elsewhere", {}, token="")


def test_reply_is_bound_to_one_recorded_event(monkeypatch) -> None:
    _configure(monkeypatch)
    seen = _capture_http(monkeypatch)
    recorded = _callback(_body())
    other = _callback(_body(conversationId="cid-other", msgId="msg-other"))
    wrong_thread = invoke(
        "company_dingtalk_reply", "lab",
        _reply_args(other["trigger_id"]),
        approved=True,
    )
    missing = invoke(
        "company_dingtalk_reply", "lab",
        _reply_args("trg_" + ("ab" * 16)),
        approved=True,
    )
    assert wrong_thread.status == "error"
    assert missing.status == "error"
    assert wrong_thread.error == "dingtalk thread has no addressed message"
    assert missing.error == "dingtalk thread has no addressed message"
    assert seen == []
    assert recorded["trigger_id"] != other["trigger_id"]


def test_encrypted_callback_and_ledger_failure_are_not_success(monkeypatch) -> None:
    _configure(monkeypatch)
    stamp = _stamp()
    raw = json.dumps({"encrypt": "ciphertext"}).encode()
    with pytest.raises(DingtalkError, match="callback is encrypted"):
        accept_callback(
            {"timestamp": stamp, "sign": _sign(_SECRET, stamp)}, raw, tenant_id="local",
        )

    def fail_receive(self, *_args, **_kwargs):
        raise WorkItemError("trigger was not recorded")

    monkeypatch.setattr(WorkItemStore, "receive", fail_receive)
    with pytest.raises(DingtalkError, match="ledger is unavailable"):
        _callback(_body())


def test_http_errors_do_not_leak_the_url(monkeypatch) -> None:
    def fail_open(request, timeout=None):
        del timeout
        raise urllib.error.HTTPError(
            request.full_url, 403, "no",
            hdrs=http.client.HTTPMessage(), fp=io.BytesIO(b"https://api.dingtalk.com/secret"),
        )

    monkeypatch.setattr(dingtalk._OPENER, "open", fail_open)
    with pytest.raises(DingtalkError, match="^dingtalk rejected the call$") as caught:
        dingtalk._post("/v1.0/oauth2/accessToken", {"appKey": _KEY, "appSecret": _SECRET}, token="")
    assert "http" not in str(caught.value)
    assert "api.dingtalk.com" not in str(caught.value)


def test_listen_address_rejects_an_open_bind() -> None:
    assert bind_address("127.0.0.1", 8787) == ("127.0.0.1", 8787)
    assert bind_address("192.168.1.10", 8787) == ("192.168.1.10", 8787)
    for host in ("0.0.0.0", "::", "255.255.255.255"):
        with pytest.raises(DingtalkError, match="listen address"):
            bind_address(host, 8787)


def test_callback_server_acks_without_storing_unaddressed_chat(monkeypatch) -> None:
    _configure(monkeypatch)
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = int(probe.getsockname()[1])
    thread = Thread(target=dingtalk.serve, args=("127.0.0.1", port, "local"), daemon=True)
    thread.start()
    server = None
    for _ in range(100):
        server = dingtalk._SERVER
        if server is not None:
            break
        time.sleep(0.02)
    assert server is not None
    try:
        missed = _http(port, _body(isInAtList=False, msgId="msg-http-miss"), _stamp())
        assert missed[0] == 200
        assert missed[1] == b'{"msgtype":"empty"}'
        stamp = _stamp()
        bad = _http(port, _body(), stamp, sign="bm90LXNpZ24")
        assert bad[0] == 401
        broken = _http_raw(port, b"{", {"timestamp": stamp, "sign": _sign(_SECRET, stamp)})
        assert broken[0] == 200
        stored = _http(port, _body(msgId="msg-http"), _stamp())
        assert stored[0] == 200
        clash = _http(port, _body(msgId="msg-http", text={"content": "changed"}), _stamp())
        assert clash[0] == 200
        sealed = json.dumps({"encrypt": "ciphertext"}).encode()
        sealed_stamp = _stamp()
        encrypted = _http_raw(
            port, sealed, {"timestamp": sealed_stamp, "sign": _sign(_SECRET, sealed_stamp)},
        )
        assert encrypted[0] == 400

        def fail_receive(self, *_args, **_kwargs):
            raise WorkItemError("trigger was not recorded")

        monkeypatch.setattr(WorkItemStore, "receive", fail_receive)
        dropped = _http(port, _body(msgId="msg-ledger"), _stamp())
        assert dropped[0] == 503
        wrong = _http_raw(port, b"{}", {"timestamp": stamp, "sign": _sign(_SECRET, stamp)}, path="/other")
        assert wrong[0] == 404
    finally:
        server.shutdown()
        thread.join(timeout=3)
    rows = _rows()
    assert [row["text"] for row in rows] == ["please check"]


def test_cli_ingest_verifies_the_envelope(monkeypatch, capsys) -> None:
    _configure(monkeypatch)
    stamp = _stamp()
    envelope = {
        "timestamp": stamp,
        "sign": _sign(_SECRET, stamp),
        "body": _body(),
        "sessionWebhook": "https://oapi.dingtalk.com/robot/send?access_token=sekrit",
    }
    _set_stdin(monkeypatch, envelope)
    assert main(["dingtalk", "ingest", "--tenant", "local"]) == 1
    assert json.loads(capsys.readouterr().out)["error"] == "dingtalk message is invalid"
    envelope.pop("sessionWebhook")
    _set_stdin(monkeypatch, envelope)
    assert main(["dingtalk", "ingest", "--tenant", "local"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["recorded"] == "true"
    assert payload["ticket_id"] == ""
    _set_stdin(monkeypatch, {"timestamp": stamp, "sign": "bm90", "body": _body(msgId="msg-cli")})
    assert main(["dingtalk", "ingest", "--tenant", "local"]) == 1
    assert json.loads(capsys.readouterr().out)["error"] == "dingtalk signature is invalid"
    listed = ingest_envelope(envelope, tenant_id="local")
    assert listed["trigger_id"] == payload["trigger_id"]


def _set_stdin(monkeypatch, payload: dict[str, object]) -> None:
    raw = json.dumps(payload).encode("utf-8")

    class _Input:
        def __init__(self) -> None:
            self.buffer = io.BytesIO(raw)

    monkeypatch.setattr("company_agent.cli.sys.stdin", _Input())


def _http(port: int, body: dict[str, object], stamp: str, *, sign: str | None = None) -> tuple[int, bytes]:
    raw = json.dumps(body).encode("utf-8")
    headers = {
        "timestamp": stamp,
        "sign": sign if sign is not None else _sign(_SECRET, stamp),
        "Content-Type": "application/json",
    }
    return _http_raw(port, raw, headers)


def _http_raw(
    port: int, raw: bytes, headers: dict[str, str], *, path: str = "/dingtalk/robot",
) -> tuple[int, bytes]:
    last: Exception | None = None
    for _ in range(20):
        try:
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            connection.request("POST", path, body=raw, headers=headers)
            response = connection.getresponse()
            payload = response.read()
            status = response.status
            connection.close()
            return status, payload
        except OSError as exc:
            last = exc
            time.sleep(0.05)
    raise AssertionError(f"dingtalk listen was not reachable: {last}")
