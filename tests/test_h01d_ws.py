"""H-01d-ws: mux peek over WebSocket. GET 426 is not success. No minted twin_id."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import socket
import struct
import threading
import time
import traceback
import urllib.error
import urllib.request
from pathlib import Path

os.environ.setdefault("QAGENT_DSH_MUX", "0")

from qagent.adapters.dsh_session import (
    DshSessionClient,
    DshSessionError,
    dsh_base_url,
    parse_mux_json,
)


ROOT = Path(__file__).resolve().parents[1]
NOTE = ROOT / "docs" / "execution" / "H-01d_ws_mux.md"
_WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
PREVIOUS: dict[str, str | None] = {}

FRAME = {
    "type": "server-request",
    "rpcId": "rpc-ws",
    "method": "approval/requested",
    "payload": {
        "type": "approval/requested",
        "sessionId": "sess_exist",
        "approvalId": "appr-ws",
        "toolName": "ionstack_twin_run",
        "reason": "shots",
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


def _ws_accept(key: str) -> str:
    digest = hashlib.sha1((key + _WS_GUID).encode("ascii")).digest()
    return base64.b64encode(digest).decode("ascii")


def _ws_text_frame(text: str) -> bytes:
    payload = text.encode("utf-8")
    header = bytearray([0x81])
    n = len(payload)
    if n < 126:
        header.append(n)
    elif n < 65536:
        header.append(126)
        header.extend(struct.pack("!H", n))
    else:
        header.append(127)
        header.extend(struct.pack("!Q", n))
    return bytes(header) + payload


class MuxFake:
    """Loopback mux: GET → 426; Upgrade → 101 + optional JSON text frame."""

    def __init__(self, frame: dict | None = None) -> None:
        self.frame = frame
        self.seen_host = ""
        self.seen_upgrade = False
        self.got_client_message = False
        self._closed = False
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(4)
        self.port = int(self._sock.getsockname()[1])
        self.base_url = f"http://127.0.0.1:{self.port}"
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._closed = True
        try:
            self._sock.close()
        except OSError:
            pass
        self._thread.join(timeout=1.5)

    def _run(self) -> None:
        self._sock.settimeout(0.25)
        end = time.monotonic() + 3.0
        while not self._closed and time.monotonic() < end:
            try:
                conn, _ = self._sock.accept()
            except TimeoutError:
                continue
            except OSError:
                break
            try:
                self._handle(conn)
            finally:
                try:
                    conn.close()
                except OSError:
                    pass

    def _handle(self, conn: socket.socket) -> None:
        conn.settimeout(1.5)
        buf = b""
        while b"\r\n\r\n" not in buf:
            chunk = conn.recv(4096)
            if not chunk:
                return
            buf += chunk
        head = buf.split(b"\r\n\r\n", 1)[0].decode("iso-8859-1")
        headers: dict[str, str] = {}
        for line in head.split("\r\n")[1:]:
            if ":" not in line:
                continue
            name, value = line.split(":", 1)
            headers[name.strip().lower()] = value.strip()
        self.seen_host = headers.get("host", "")
        if headers.get("upgrade", "").lower() == "websocket":
            self.seen_upgrade = True
            accept = _ws_accept(headers.get("sec-websocket-key", ""))
            resp = (
                "HTTP/1.1 101 Switching Protocols\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n"
                f"Sec-WebSocket-Accept: {accept}\r\n"
                "\r\n"
            )
            conn.sendall(resp.encode("ascii"))
            if self.frame is not None:
                conn.sendall(_ws_text_frame(json.dumps(self.frame)))
            time.sleep(0.2)
            conn.settimeout(0.15)
            try:
                extra = conn.recv(8)
            except (TimeoutError, OSError):
                extra = b""
            if extra:
                self.got_client_message = True
            return
        body = b"upgrade required"
        resp = (
            "HTTP/1.1 426 Upgrade Required\r\n"
            "Connection: Upgrade\r\n"
            "Upgrade: websocket\r\n"
            "Content-Type: text/plain\r\n"
            f"Content-Length: {len(body)}\r\n"
            "\r\n"
        )
        conn.sendall(resp.encode("ascii") + body)


def test_parse_json_server_request() -> None:
    pending = parse_mux_json(json.dumps(FRAME), session_id="sess_exist")
    assert pending is not None
    assert pending["rpc_id"] == "rpc-ws"
    assert pending["approval_id"] == "appr-ws"
    assert pending["tool"] == "ionstack_twin_run"
    assert parse_mux_json(json.dumps(FRAME), session_id="other") is None
    assert "twin_id" not in pending
    assert "twin_id" not in json.dumps(pending)


def test_get_426_not_success() -> None:
    fake = MuxFake(frame=None)
    _save_env("QAGENT_DSH_MUX", "QAGENT_DSH_MUX_S")
    os.environ["QAGENT_DSH_MUX"] = "1"
    os.environ["QAGENT_DSH_MUX_S"] = "0.25"
    try:
        client = DshSessionClient(base_url=fake.base_url)
        try:
            client._http_mux()
            raise AssertionError("GET 426 treated as success")
        except DshSessionError as exc:
            assert exc.code == "http-426"
        assert parse_mux_json("upgrade required") is None
        pending = client.peek_mux_approval("sess_exist")
        assert pending is None
        dumped = json.dumps({"pending": pending})
        assert "twin_id" not in dumped
        assert "rpc-ws" not in dumped
    finally:
        fake.close()
        _restore_env()


def test_mux_disabled_returns_none() -> None:
    _save_env("QAGENT_DSH_MUX")
    os.environ["QAGENT_DSH_MUX"] = "0"
    try:
        client = DshSessionClient(base_url="http://127.0.0.1:3081")
        assert client.peek_mux_approval("sess_exist") is None
        assert client.peek_mux_approval("sess_exist") is None
    finally:
        _restore_env()


def test_ws_peek_rpc_id() -> None:
    fake = MuxFake(frame=FRAME)
    _save_env("QAGENT_DSH_MUX", "QAGENT_DSH_MUX_S")
    os.environ["QAGENT_DSH_MUX"] = "1"
    os.environ["QAGENT_DSH_MUX_S"] = "0.8"
    try:
        client = DshSessionClient(base_url=fake.base_url)
        pending = client.peek_mux_approval("sess_exist")
        assert pending is not None
        assert pending["rpc_id"] == "rpc-ws"
        assert pending["approval_id"] == "appr-ws"
        assert fake.seen_host == f"127.0.0.1:{fake.port}"
        assert fake.seen_upgrade
        assert not fake.got_client_message
        assert "twin_id" not in pending
        assert "twin_id" not in json.dumps(pending)
    finally:
        fake.close()
        _restore_env()


def test_no_twin_id_minted() -> None:
    pending = parse_mux_json(json.dumps(FRAME), session_id="sess_exist")
    assert pending is not None
    assert "twin_id" not in pending
    _save_env("QAGENT_DSH_MUX")
    os.environ["QAGENT_DSH_MUX"] = "0"
    try:
        client = DshSessionClient(transport=lambda method, payload: {"result": {"ok": True, "value": {}}})
        assert client.peek_mux_approval("sess_exist") is None
    finally:
        _restore_env()


def test_note_cites_websocket_downlink() -> None:
    assert NOTE.exists(), f"missing {NOTE}"
    text = NOTE.read_text(encoding="utf-8")
    assert "websocket-downlink" in text
    assert "426" in text
    assert "accepted:true" not in text.replace(" ", "") or "没有" in text or "不" in text


def test_optional_live_3081() -> None:
    base = dsh_base_url()
    request = urllib.request.Request(base.rstrip("/") + "/api/events.mux", method="GET")
    try:
        with urllib.request.urlopen(request, timeout=1.0):
            status = 200
    except urllib.error.HTTPError as exc:
        status = int(exc.code)
    except (urllib.error.URLError, TimeoutError, OSError):
        print("skip live 3081 down")
        return
    assert status != 500, f"mux GET was HTTP {status}"
    _save_env("QAGENT_DSH_MUX", "QAGENT_DSH_MUX_S")
    os.environ["QAGENT_DSH_MUX"] = "1"
    os.environ["QAGENT_DSH_MUX_S"] = "0.4"
    try:
        client = DshSessionClient(base_url=base)
        try:
            raw = client._ws_mux()
        except DshSessionError as exc:
            assert exc.code != "http-500", "mux WS upgrade was HTTP 500"
            raw = ""
        pending = parse_mux_json(raw, session_id="") if raw else client.peek_mux_approval("")
        if pending:
            assert pending.get("rpc_id")
            assert "twin_id" not in json.dumps(pending)
    finally:
        _restore_env()


def main() -> int:
    failed = 0
    for name, fn in [
        ("parse_json_server_request", test_parse_json_server_request),
        ("get_426_not_success", test_get_426_not_success),
        ("mux_disabled_returns_none", test_mux_disabled_returns_none),
        ("ws_peek_rpc_id", test_ws_peek_rpc_id),
        ("no_twin_id_minted", test_no_twin_id_minted),
        ("note_cites_websocket_downlink", test_note_cites_websocket_downlink),
        ("optional_live_3081", test_optional_live_3081),
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
