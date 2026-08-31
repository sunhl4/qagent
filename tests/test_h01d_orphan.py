"""H-01d-peek-orphan: snapshot peeks mux when history awaits approve without rpc_id."""

from __future__ import annotations

import json
import os
import socket
import sys
import threading
import time
import traceback
from pathlib import Path

os.environ.setdefault("QAGENT_DSH_MUX", "0")

from qagent.adapters.dsh_session import DshSessionClient, fold_history


ROOT = Path(__file__).resolve().parents[1]
NOTE = ROOT / "docs" / "execution" / "H-01d_peek_orphan.md"
_TESTS = Path(__file__).resolve().parent
if str(_TESTS) not in sys.path:
    sys.path.insert(0, str(_TESTS))

from test_h01d_ws import MuxFake

PREVIOUS: dict[str, str | None] = {}

ORPHAN_FRAME = {
    "type": "server-request",
    "rpcId": "rpc-orphan",
    "method": "approval/requested",
    "payload": {
        "type": "approval/requested",
        "sessionId": "sess_exist",
        "approvalId": "appr-orphan",
        "toolName": "ionstack_twin_run",
        "reason": "shots",
        "callId": "call-orphan",
    },
}


def _ok(name: str) -> None:
    print(f"ok  {name}")


def _save_env(*keys: str) -> None:
    for key in keys:
        PREVIOUS[key] = os.environ.get(key)


def _restore_env() -> None:
    for key, value in PREVIOUS.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    PREVIOUS.clear()


def _orphan_events() -> list[dict]:
    return [
        {
            "event": {
                "type": "tool/call",
                "data": {
                    "name": "ionstack_twin_run",
                    "callId": "call-orphan",
                },
            }
        }
    ]


class _HistoryClient(DshSessionClient):
    """History is injected. Peek still uses the real mux path."""

    def __init__(self, events: list[dict], **kwargs) -> None:
        super().__init__(**kwargs)
        self._events = events

    def history(self, session_id: str) -> dict:
        return {"events": self._events, "hasMore": False}


def test_orphan_history_has_no_pending() -> None:
    snap = fold_history({"events": _orphan_events()}, session_id="sess_exist")
    assert snap["awaiting"] == "approve"
    assert snap["pending_approval"] is None
    assert "twin_id" not in json.dumps(snap)


def test_orphan_snapshot_takes_rpc_from_peek() -> None:
    fake = MuxFake(frame=ORPHAN_FRAME)
    _save_env("QAGENT_DSH_MUX", "QAGENT_DSH_MUX_S")
    os.environ["QAGENT_DSH_MUX"] = "1"
    os.environ["QAGENT_DSH_MUX_S"] = "0.8"
    try:
        client = _HistoryClient(_orphan_events(), base_url=fake.base_url)
        snap = client.snapshot("sess_exist")
        pending = snap["pending_approval"]
        assert pending is not None
        assert pending["rpc_id"] == "rpc-orphan"
        assert pending["approval_id"] == "appr-orphan"
        assert pending["tool"] == "ionstack_twin_run"
        assert pending["reason"] == "shots"
        assert pending["call_id"] == "call-orphan"
        assert snap["awaiting"] == "approve"
        assert fake.seen_upgrade
        assert not fake.got_client_message
        dumped = json.dumps(snap)
        assert "twin_id" not in dumped
        assert "rpc-orphan" in dumped
    finally:
        fake.close()
        _restore_env()


def test_empty_mux_leaves_pending_none() -> None:
    fake = MuxFake(frame=None)
    _save_env("QAGENT_DSH_MUX", "QAGENT_DSH_MUX_S")
    os.environ["QAGENT_DSH_MUX"] = "1"
    os.environ["QAGENT_DSH_MUX_S"] = "0.25"
    try:
        client = _HistoryClient(_orphan_events(), base_url=fake.base_url)
        snap = client.snapshot("sess_exist")
        assert snap["awaiting"] == "approve"
        assert snap["pending_approval"] is None
        dumped = json.dumps(snap)
        assert "rpc-orphan" not in dumped
        assert "rpcId" not in dumped
        assert "twin_id" not in dumped
    finally:
        fake.close()
        _restore_env()


def test_mux_off_no_network_no_invented() -> None:
    hits = {"n": 0}

    def _serve(sock: socket.socket) -> None:
        sock.settimeout(0.2)
        end = time.monotonic() + 1.2
        while time.monotonic() < end:
            try:
                conn, _ = sock.accept()
            except TimeoutError:
                continue
            except OSError:
                break
            hits["n"] += 1
            try:
                conn.close()
            except OSError:
                pass

    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(2)
    port = int(listener.getsockname()[1])
    thread = threading.Thread(target=_serve, args=(listener,), daemon=True)
    thread.start()
    _save_env("QAGENT_DSH_MUX", "QAGENT_DSH_MUX_S")
    os.environ["QAGENT_DSH_MUX"] = "0"
    os.environ["QAGENT_DSH_MUX_S"] = "0.8"
    try:
        client = _HistoryClient(_orphan_events(), base_url=f"http://127.0.0.1:{port}")
        snap = client.snapshot("sess_exist")
        assert snap["awaiting"] == "approve"
        assert snap["pending_approval"] is None
        assert hits["n"] == 0
        dumped = json.dumps(snap)
        assert "twin_id" not in dumped
        assert "rpc-orphan" not in dumped
    finally:
        try:
            listener.close()
        except OSError:
            pass
        thread.join(timeout=1.0)
        _restore_env()


def test_injected_transport_no_network() -> None:
    calls: list[str] = []

    def transport(method: str, payload: dict) -> dict:
        calls.append(method)
        if method == "session.history":
            return {"result": {"ok": True, "value": {"events": _orphan_events(), "hasMore": False}}}
        raise AssertionError(method)

    _save_env("QAGENT_DSH_MUX")
    os.environ["QAGENT_DSH_MUX"] = "1"
    try:
        client = DshSessionClient(transport=transport, base_url="http://127.0.0.1:3081")
        snap = client.snapshot("sess_exist")
        assert calls == ["session.history"]
        assert snap["awaiting"] == "approve"
        assert snap["pending_approval"] is None
        assert "twin_id" not in json.dumps(snap)
    finally:
        _restore_env()


def test_no_twin_id_minted() -> None:
    snap = fold_history({"events": _orphan_events()}, session_id="sess_exist")
    assert "twin_id" not in json.dumps(snap)
    _save_env("QAGENT_DSH_MUX")
    os.environ["QAGENT_DSH_MUX"] = "0"
    try:
        client = _HistoryClient(_orphan_events(), base_url="http://127.0.0.1:9")
        out = client.snapshot("sess_exist")
        assert out["pending_approval"] is None
        assert "twin_id" not in json.dumps(out)
    finally:
        _restore_env()


def test_note_exists_no_live_accepted() -> None:
    assert NOTE.exists(), f"missing {NOTE}"
    text = NOTE.read_text(encoding="utf-8")
    compact = text.replace(" ", "")
    assert "accepted:true" not in compact or "不" in text or "没有" in text
    assert "不声称" in text or "不写" in text or "没有" in text
    assert "accepted:true" not in compact or "活" in text


def main() -> int:
    failed = 0
    for name, fn in [
        ("orphan_history_has_no_pending", test_orphan_history_has_no_pending),
        ("orphan_snapshot_takes_rpc_from_peek", test_orphan_snapshot_takes_rpc_from_peek),
        ("empty_mux_leaves_pending_none", test_empty_mux_leaves_pending_none),
        ("mux_off_no_network_no_invented", test_mux_off_no_network_no_invented),
        ("injected_transport_no_network", test_injected_transport_no_network),
        ("no_twin_id_minted", test_no_twin_id_minted),
        ("note_exists_no_live_accepted", test_note_exists_no_live_accepted),
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
