from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import socket
import struct
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any, Callable

from qagent.adapters.contracts import ROOT
from qagent.models.circuit_pick import prefer_circuit

Transport = Callable[[str, dict[str, Any]], dict[str, Any]]


class DshSessionError(RuntimeError):
    """dsh unary RPC failed. Not a science error. Never mint twin_id here."""

    def __init__(self, message: str, *, code: str = "dsh-error") -> None:
        super().__init__(message)
        self.code = code


def dsh_base_url() -> str:
    return (os.environ.get("QAGENT_DSH_URL") or "http://127.0.0.1:3081").rstrip("/")


def default_cwd() -> str:
    raw = os.environ.get("QAGENT_DSH_CWD")
    return raw if raw else str(ROOT)


class DshSessionClient:
    """HTTP unary client for dsh session.* . Does not import science cores."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        transport: Transport | None = None,
        timeout: float = 8.0,
    ) -> None:
        self.base_url = (base_url or dsh_base_url()).rstrip("/")
        self.transport = transport
        self.timeout = timeout

    def rpc(self, method: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        body = payload if isinstance(payload, dict) else {}
        if self.transport is not None:
            return self._unwrap(method, self.transport(method, body))
        return self._unwrap(method, self._http(method, body))

    def create(self, *, cwd: str | None = None, agent_preset: str | None = None) -> str:
        payload: dict[str, Any] = {}
        chosen_cwd = cwd if cwd is not None else default_cwd()
        if chosen_cwd:
            payload["cwd"] = chosen_cwd
        if agent_preset is None:
            preset = os.environ.get("QAGENT_DSH_AGENT_PRESET", "qagent")
        else:
            preset = agent_preset
        if preset:
            payload["agentPreset"] = preset
        value = self.rpc("session.create", payload)
        session_id = str(value.get("sessionId") or "").strip()
        if not session_id:
            raise DshSessionError("运行时建了会话但没有 sessionId。不会改用自研循环。", code="missing-session")
        return session_id

    def prompt(self, session_id: str, text: str, *, mode: str = "queue") -> dict[str, Any]:
        return self.rpc(
            "session.prompt",
            {
                "sessionId": session_id,
                "mode": mode,
                "content": [{"type": "text", "text": text}],
            },
        )

    def history(self, session_id: str) -> dict[str, Any]:
        return self.rpc("session.history", {"sessionId": session_id})

    def recent_assistant_text(self, session_id: str) -> str:
        return str(self.snapshot(session_id).get("reply") or "")

    def snapshot(self, session_id: str) -> dict[str, Any]:
        snap = fold_history(self.history(session_id), session_id=session_id)
        if _needs_mux_peek(snap):
            peeked = self.peek_mux_approval(session_id)
            if peeked:
                pending = snap.get("pending_approval")
                merged = _fill_pending(
                    pending if isinstance(pending, dict) else None,
                    peeked,
                )
                if merged.get("rpc_id") or merged.get("approval_id"):
                    snap["pending_approval"] = merged
                    snap["awaiting"] = "approve"
        return snap

    def respond(self, rpc_id: str, value: dict[str, Any]) -> dict[str, Any]:
        """Answer a server-request. POST /api/respond, not unary /api/{method}."""
        echoed = str(rpc_id or "").strip()
        if not echoed:
            raise DshSessionError("没有可回的 mux rpcId。不会改用自研循环。", code="missing-rpc")
        body = {"rpcId": echoed, "value": value if isinstance(value, dict) else {}}
        if self.transport is not None:
            return self._receipt(self.transport("respond", body))
        return self._receipt(self._http_respond(echoed, body["value"]))

    def approve_once(self, session_id: str, approval_id: str, rpc_id: str) -> dict[str, Any]:
        return self.respond(
            rpc_id,
            {
                "sessionId": session_id,
                "approvalId": approval_id,
                "outcome": OUTCOME_ALLOWED_ONCE,
            },
        )

    def reject_once(self, session_id: str, approval_id: str, rpc_id: str) -> dict[str, Any]:
        return self.respond(
            rpc_id,
            {
                "sessionId": session_id,
                "approvalId": approval_id,
                "outcome": OUTCOME_REJECTED,
            },
        )

    def peek_mux_approval(self, session_id: str = "") -> dict[str, str] | None:
        """Short mux peek. GET 426 is not success; then WebSocket /api/events.mux."""
        if self.transport is not None or not _mux_enabled():
            return None
        raw = ""
        try:
            raw = self._http_mux()
        except DshSessionError as exc:
            if exc.code != "http-426":
                return None
            try:
                raw = self._ws_mux()
            except DshSessionError:
                return None
        if not (raw or "").strip():
            return None
        return parse_mux_json(raw, session_id=session_id)

    def wait_for_turn(
        self,
        session_id: str,
        *,
        timeout: float | None = None,
        since: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Wait for this prompt's turn. Do not return the previous turn's reply."""
        limit = _wait_seconds() if timeout is None else timeout
        deadline = time.monotonic() + max(0.0, limit)
        last = self.snapshot(session_id)
        seen_running = bool(last.get("running"))
        while True:
            if _turn_ready(last, since=since, seen_running=seen_running):
                return last
            if time.monotonic() >= deadline:
                if since is not None and not _newer_turn(last, since):
                    stale = dict(last)
                    stale["reply"] = ""
                    stale.pop("circuit", None)
                    stale["running"] = True
                    return stale
                return last
            time.sleep(min(0.2, max(0.05, deadline - time.monotonic())))
            last = self.snapshot(session_id)
            if last.get("running"):
                seen_running = True

    def _http(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._post_json(
            f"/api/{method}",
            {
                "type": "client-request",
                "rpcId": f"qagent-{uuid.uuid4().hex[:12]}",
                "method": method,
                "payload": payload,
            },
        )

    def _http_respond(self, rpc_id: str, value: dict[str, Any]) -> dict[str, Any]:
        return self._post_json(
            "/api/respond",
            {
                "type": "client-response",
                "rpcId": rpc_id,
                "result": {"ok": True, "value": value},
            },
        )

    def _http_mux(self) -> str:
        request = urllib.request.Request(
            f"{self.base_url}/api/events.mux",
            headers={"Accept": "text/event-stream"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=_mux_seconds()) as response:
                return response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            raise DshSessionError(f"mux HTTP {exc.code}。不会改用自研循环。", code=f"http-{exc.code}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise DshSessionError("mux 没接到。不会改用自研循环。", code="mux-skip") from exc

    def _ws_mux(self) -> str:
        """Read a short window of mux JSON text frames. Never sends on the socket."""
        host, port, host_header = _mux_ws_target(self.base_url)
        timeout = _mux_seconds()
        deadline = time.monotonic() + timeout
        try:
            sock = socket.create_connection((host, port), timeout=timeout)
        except OSError as exc:
            raise DshSessionError("mux ws 没接到。不会改用自研循环。", code="mux-skip") from exc
        try:
            leftover = _ws_upgrade(sock, host_header=host_header, timeout=max(0.05, deadline - time.monotonic()))
            remain = deadline - time.monotonic()
            if remain <= 0:
                return ""
            sock.settimeout(remain)
            texts = _ws_collect_text(sock, leftover, deadline=deadline)
            return "".join(f"data: {text}\n\n" for text in texts)
        except DshSessionError:
            raise
        except (TimeoutError, socket.timeout):
            return ""
        except OSError as exc:
            raise DshSessionError("mux ws 没接到。不会改用自研循环。", code="mux-skip") from exc
        finally:
            try:
                sock.close()
            except OSError:
                pass

    def _post_json(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
            raise DshSessionError(
                f"运行时 HTTP {exc.code}。不会改用自研循环假装已经在 vibe。{detail}",
                code=f"http-{exc.code}",
            ) from exc
        except urllib.error.URLError as exc:
            raise DshSessionError(
                "运行时没在 3081。先启动 `bash scripts/start_runtime.sh`。"
                "在接通之前我不会用自研循环假装已经在 vibe。",
                code="unreachable",
            ) from exc
        except TimeoutError as exc:
            raise DshSessionError("运行时超时。不会改用自研循环。", code="timeout") from exc
        try:
            parsed = json.loads(raw) if raw else {}
        except json.JSONDecodeError as exc:
            raise DshSessionError("运行时回了非 JSON。不会改用自研循环。", code="bad-json") from exc
        if not isinstance(parsed, dict):
            raise DshSessionError("运行时回了非对象。不会改用自研循环。", code="bad-json")
        return parsed

    def _receipt(self, raw: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(raw, dict):
            raise DshSessionError("运行时回了非对象收据。不会改用自研循环。", code="bad-receipt")
        if "accepted" in raw:
            if raw.get("accepted") is True:
                return {"accepted": True}
            reason = str(raw.get("reason") or "not-pending")
            raise DshSessionError(
                f"运行时没收下这次批准（{reason}）。不会改用自研循环。",
                code=reason,
            )
        result = raw.get("result")
        if isinstance(result, dict) and result.get("ok") is True and isinstance(result.get("value"), dict):
            return self._receipt(result["value"])
        raise DshSessionError("运行时回了看不懂的收据。不会改用自研循环。", code="bad-receipt")

    def _unwrap(self, method: str, envelope: dict[str, Any]) -> dict[str, Any]:
        if envelope.get("ok") is True and isinstance(envelope.get("value"), dict):
            return envelope["value"]
        result = envelope.get("result")
        if isinstance(result, dict):
            if result.get("ok") is True:
                value = result.get("value")
                if isinstance(value, dict):
                    return value
                raise DshSessionError(f"{method} 成功但没有对象 value。", code="bad-value")
            error = result.get("error") if isinstance(result.get("error"), dict) else {}
            code = str(error.get("code") or "dsh-error")
            raise DshSessionError(_honest(method, code, str(error.get("message") or "")), code=code)
        if envelope.get("ok") is False and isinstance(envelope.get("error"), dict):
            error = envelope["error"]
            code = str(error.get("code") or "dsh-error")
            raise DshSessionError(_honest(method, code, str(error.get("message") or "")), code=code)
        raise DshSessionError(f"{method} 回了看不懂的信封。不会改用自研循环。", code="bad-envelope")


def _honest(method: str, code: str, detail: str) -> str:
    if code in {"agent-preset-invalid", "agent-preset-not-found"}:
        return (
            "运行时活着，但建不了 session（profile 的 persona 和 stock preset 冲突）。"
            "不会退回自研循环，也不会假装已经扫完。"
        )
    if code == "model-unavailable":
        return "模型还没接通运行时。先在设置里接地址和模型名。"
    if code == "unreachable":
        return "运行时没在 3081。先启动 `bash scripts/start_runtime.sh`。"
    snippet = detail.strip().splitlines()[0][:180] if detail else code
    return f"运行时拒绝了 {method}（{code}）。{snippet} 不会改用自研循环。"


OUTCOME_ALLOWED_ONCE = "allowed-once"
OUTCOME_REJECTED = "rejected"
_ASK_KINDS = frozenset({"approval/asked", "approval/requested"})
_RESOLVE_KINDS = frozenset({"approval/decided", "approval/resolved"})


def _wait_seconds() -> float:
    raw = os.environ.get("QAGENT_DSH_WAIT_S")
    if raw is None or raw == "":
        return 2.0
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 2.0


def _mux_enabled() -> bool:
    return (os.environ.get("QAGENT_DSH_MUX") or "1").strip().lower() not in {"0", "false", "no"}


def _mux_seconds() -> float:
    raw = os.environ.get("QAGENT_DSH_MUX_S")
    if raw is None or raw == "":
        return 0.4
    try:
        return max(0.05, min(2.0, float(raw)))
    except ValueError:
        return 0.4


def _needs_mux_peek(snap: dict[str, Any]) -> bool:
    """History is waiting on approve but has no mux rpcId yet."""
    if snap.get("awaiting") != "approve":
        return False
    pending = snap.get("pending_approval")
    if not isinstance(pending, dict):
        return True
    return not str(pending.get("rpc_id") or "").strip()


def _fill_pending(pending: dict[str, str] | None, peeked: dict[str, str]) -> dict[str, str]:
    """Copy mux fields that already exist. Never invent rpc_id / approval_id."""
    merged = dict(pending) if pending else {}
    for key in ("rpc_id", "approval_id", "tool", "reason", "call_id"):
        if peeked.get(key) and not merged.get(key):
            merged[key] = peeked[key]
    return merged


def _pending_key(snap: dict[str, Any] | None) -> str:
    if not isinstance(snap, dict):
        return ""
    pending = snap.get("pending_approval")
    if not isinstance(pending, dict):
        return ""
    return str(pending.get("approval_id") or pending.get("rpc_id") or "").strip()


def _newer_turn(last: dict[str, Any], since: dict[str, Any]) -> bool:
    for key in ("event_count", "assistant_index", "turn_index"):
        if int(last.get(key) or 0) > int(since.get(key) or 0):
            return True
    if str(last.get("reply") or "") != str(since.get("reply") or ""):
        return True
    if _pending_key(last) and _pending_key(last) != _pending_key(since):
        return True
    return False


def _turn_ready(
    last: dict[str, Any],
    *,
    since: dict[str, Any] | None,
    seen_running: bool,
) -> bool:
    reply = str(last.get("reply") or "").strip()
    awaiting = last.get("awaiting") == "approve"
    running = bool(last.get("running"))
    if since is None:
        return bool(reply or awaiting or not running)
    if not _newer_turn(last, since):
        return False
    if awaiting and _pending_key(last) != _pending_key(since):
        return True
    if reply and reply != str(since.get("reply") or "").strip():
        return True
    if seen_running and not running:
        return True
    return False


def fold_history(page: dict[str, Any], *, session_id: str = "") -> dict[str, Any]:
    """Turn dsh history events into 3080 bubbles. No science imports."""
    texts: list[str] = []
    tools: list[str] = []
    pending_calls: set[str] = set()
    running = False
    awaiting: str | None = None
    pending: dict[str, str] | None = None
    circuit: dict[str, Any] | None = None
    event_count = 0
    assistant_index = 0
    turn_index = 0
    for entry in page.get("events") or []:
        event = entry.get("event") if isinstance(entry, dict) else None
        if not isinstance(event, dict):
            continue
        event_count += 1
        etype = _event_kind(event)
        data = event.get("data") if isinstance(event.get("data"), dict) else {}
        if etype == "turn/start":
            running = True
            turn_index += 1
            texts = []
            tools = []
            circuit = None
        if etype in {"turn/end", "turn/error"}:
            running = False
        if etype == "assistant/message":
            message = data.get("message") if isinstance(data.get("message"), dict) else data
            texts.extend(_text_blocks(message))
            assistant_index = event_count
        if etype == "tool/call":
            name = str(data.get("name") or "")
            if name:
                tools.append(name)
            call_id = str(data.get("callId") or name or "")
            if call_id:
                pending_calls.add(call_id)
            if name == "ionstack_twin_run":
                awaiting = "approve"
        if etype == "tool/result":
            call_id = str(data.get("callId") or "")
            pending_calls.discard(call_id)
            message = data.get("message") if isinstance(data.get("message"), dict) else {}
            name = str(message.get("name") or data.get("name") or "")
            found_circuit = _circuit_from_tool_result(event)
            if found_circuit:
                circuit = prefer_circuit(circuit, found_circuit)
            if pending and call_id and call_id == pending.get("call_id"):
                pending = None
                if awaiting == "approve":
                    awaiting = None
            if name == "ionstack_twin_run" and awaiting == "approve" and pending is None:
                awaiting = None
        if etype in _ASK_KINDS:
            found = _pending_from_event(event)
            if found:
                pending = found
            awaiting = "approve"
        elif etype in _RESOLVE_KINDS:
            resolved_id = _approval_id(event)
            if pending is None or not resolved_id or resolved_id == pending.get("approval_id"):
                pending = None
                if awaiting == "approve":
                    awaiting = None
        elif etype.endswith("/ask") or etype == "user-question":
            awaiting = "approve"
    if "ionstack_twin_run" in tools and pending_calls and pending is None:
        awaiting = awaiting or "approve"
    if pending is not None:
        awaiting = "approve"
    reply = "\n".join(part for part in texts if part).strip()
    cards = [{"kind": "tool", "name": name} for name in tools[-8:]]
    out = {
        "session_id": session_id,
        "reply": reply,
        "used_tools": list(tools),
        "cards": cards,
        "running": running,
        "awaiting": awaiting,
        "pending_approval": pending,
        "event_count": event_count,
        "assistant_index": assistant_index,
        "turn_index": turn_index,
    }
    if circuit:
        out["circuit"] = circuit
    return out


def parse_mux_sse(raw: str, *, session_id: str = "") -> dict[str, str] | None:
    """Pull one approval/requested server-request out of an SSE buffer."""
    for block in (raw or "").split("\n\n"):
        lines = [
            line[5:].lstrip()
            for line in block.splitlines()
            if line.startswith("data:")
        ]
        if not lines:
            continue
        try:
            frame = json.loads("".join(lines))
        except json.JSONDecodeError:
            continue
        if not isinstance(frame, dict):
            continue
        pending = _pending_from_mux(frame, session_id=session_id)
        if pending:
            return pending
    return None


def parse_mux_json(raw: str, *, session_id: str = "") -> dict[str, str] | None:
    """Parse one JSON server-request or an SSE buffer. Never invents rpcId."""
    text = (raw or "").strip()
    if not text:
        return None
    if text.startswith("{"):
        try:
            frame = json.loads(text)
        except json.JSONDecodeError:
            frame = None
        if isinstance(frame, dict):
            pending = _pending_from_mux(frame, session_id=session_id)
            if pending:
                return pending
    return parse_mux_sse(raw, session_id=session_id)


def _circuit_from_tool_result(event: dict[str, Any]) -> dict[str, Any] | None:
    found: dict[str, Any] | None = None

    def walk(obj: object) -> None:
        nonlocal found
        if isinstance(obj, dict):
            cid = str(obj.get("circuit_id") or "")
            if re.fullmatch(r"circ_[0-9a-f]{12}", cid):
                found = obj
            for value in obj.values():
                walk(value)
            return
        if isinstance(obj, list):
            for item in obj:
                walk(item)
            return
        if isinstance(obj, str):
            text = obj.strip()
            if text.startswith("{") or text.startswith("["):
                try:
                    walk(json.loads(text))
                except json.JSONDecodeError:
                    return

    walk(event)
    if found is None:
        blob = json.dumps(event, ensure_ascii=False)
        match = re.search(r"circ_[0-9a-f]{12}", blob)
        if not match:
            return None
        return {"circuit_id": match.group(0)}
    circuit_id = str(found["circuit_id"])
    summary = found.get("summary") if isinstance(found.get("summary"), dict) else {}
    n_qubits = int(found.get("n_qubits") or summary.get("n_qubits") or 0)
    n_instructions = int(found.get("n_instructions") or summary.get("n_instructions") or 0)
    ansatz = str(found.get("ansatz") or summary.get("ansatz") or "")
    face = {"circuit_id": circuit_id}
    if n_qubits:
        face["n_qubits"] = n_qubits
    if n_instructions:
        face["n_instructions"] = n_instructions
    if ansatz:
        face["ansatz"] = ansatz
    return face


def _event_kind(event: dict[str, Any]) -> str:
    etype = str(event.get("type") or "")
    if etype == "server-request":
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        return str(event.get("method") or payload.get("type") or "")
    return etype


def _pending_from_event(event: dict[str, Any]) -> dict[str, str] | None:
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    data = event.get("data") if isinstance(event.get("data"), dict) else {}
    src: dict[str, Any] = {}
    src.update(payload)
    src.update(event)
    src.update(data)
    approval_id = str(src.get("approvalId") or src.get("approval_id") or src.get("id") or "").strip()
    rpc_id = str(src.get("rpcId") or src.get("rpc_id") or "").strip()
    tool = str(src.get("toolName") or src.get("tool") or src.get("name") or "").strip()
    reason = str(src.get("reason") or "").strip()
    call_id = str(src.get("callId") or src.get("call_id") or "").strip()
    if not approval_id and not rpc_id:
        return None
    pending = {
        "rpc_id": rpc_id,
        "approval_id": approval_id,
        "tool": tool,
        "reason": reason,
    }
    if call_id:
        pending["call_id"] = call_id
    return pending


def _pending_from_mux(frame: dict[str, Any], *, session_id: str = "") -> dict[str, str] | None:
    payload = frame.get("payload") if isinstance(frame.get("payload"), dict) else {}
    kind = str(frame.get("method") or payload.get("type") or frame.get("type") or "")
    if kind != "approval/requested":
        return None
    blob = dict(payload) if payload else dict(frame)
    if session_id:
        got = str(blob.get("sessionId") or blob.get("session_id") or "").strip()
        if got and got != session_id:
            return None
    pending = _pending_from_event({**blob, "rpcId": frame.get("rpcId") or blob.get("rpcId")})
    return pending


def _approval_id(event: dict[str, Any]) -> str:
    data = event.get("data") if isinstance(event.get("data"), dict) else {}
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    return str(
        data.get("approvalId")
        or data.get("id")
        or payload.get("approvalId")
        or event.get("approvalId")
        or ""
    ).strip()


def _text_blocks(message: Any) -> list[str]:
    if not isinstance(message, dict):
        return []
    content = message.get("content")
    if isinstance(content, str) and content.strip():
        return [content.strip()]
    texts: list[str] = []
    if isinstance(content, list):
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                text = str(part.get("text") or "").strip()
                if text:
                    texts.append(text)
            elif isinstance(part, str) and part.strip():
                texts.append(part.strip())
    return texts


_MUX_PATH = "/api/events.mux"
_WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
_WS_MAX_FRAME = 1 << 20
_WS_MAX_FRAMES = 16


def _mux_ws_target(base_url: str) -> tuple[str, int, str]:
    parsed = urllib.parse.urlparse(base_url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    return host, port, f"{host}:{port}"


def _ws_accept(key: str) -> str:
    digest = hashlib.sha1((key + _WS_GUID).encode("ascii")).digest()
    return base64.b64encode(digest).decode("ascii")


def _ws_upgrade(sock: socket.socket, *, host_header: str, timeout: float) -> bytes:
    sock.settimeout(timeout)
    key = base64.b64encode(os.urandom(16)).decode("ascii")
    request = (
        f"GET {_MUX_PATH} HTTP/1.1\r\n"
        f"Host: {host_header}\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        "Sec-WebSocket-Version: 13\r\n"
        "\r\n"
    )
    sock.sendall(request.encode("ascii"))
    header, leftover = _recv_http_head(sock)
    status, headers = _parse_http_head(header)
    if status != 101:
        raise DshSessionError(f"mux WS HTTP {status}。不会改用自研循环。", code=f"http-{status}")
    if headers.get("sec-websocket-accept") != _ws_accept(key):
        raise DshSessionError("mux WS accept 对不上。不会改用自研循环。", code="ws-accept")
    return leftover


def _recv_http_head(sock: socket.socket) -> tuple[bytes, bytes]:
    buf = b""
    while b"\r\n\r\n" not in buf:
        chunk = sock.recv(4096)
        if not chunk:
            raise OSError("eof during ws handshake")
        buf += chunk
        if len(buf) > 65536:
            raise OSError("ws handshake too large")
    head, rest = buf.split(b"\r\n\r\n", 1)
    return head, rest


def _parse_http_head(header: bytes) -> tuple[int, dict[str, str]]:
    text = header.decode("iso-8859-1")
    lines = text.split("\r\n")
    parts = lines[0].split() if lines else []
    if len(parts) < 2 or not parts[1].isdigit():
        raise DshSessionError("mux WS 握手坏了。不会改用自研循环。", code="ws-handshake")
    headers: dict[str, str] = {}
    for line in lines[1:]:
        if ":" not in line:
            continue
        name, value = line.split(":", 1)
        headers[name.strip().lower()] = value.strip()
    return int(parts[1]), headers


class _SockBuf:
    __slots__ = ("sock", "buf")

    def __init__(self, sock: socket.socket, leftover: bytes = b"") -> None:
        self.sock = sock
        self.buf = leftover

    def read(self, n: int) -> bytes:
        if n <= 0:
            return b""
        while len(self.buf) < n:
            chunk = self.sock.recv(max(4096, n - len(self.buf)))
            if not chunk:
                raise OSError("mux ws eof")
            self.buf += chunk
        out = self.buf[:n]
        self.buf = self.buf[n:]
        return out


def _ws_read_frame(reader: _SockBuf) -> tuple[int, int, bytes]:
    header = reader.read(2)
    b0, b1 = header[0], header[1]
    fin = (b0 >> 7) & 1
    opcode = b0 & 0x0F
    masked = (b1 >> 7) & 1
    length = b1 & 0x7F
    if length == 126:
        length = struct.unpack("!H", reader.read(2))[0]
    elif length == 127:
        length = struct.unpack("!Q", reader.read(8))[0]
    if length > _WS_MAX_FRAME:
        raise OSError("ws frame too large")
    mask = reader.read(4) if masked else b""
    payload = reader.read(length) if length else b""
    if masked and payload:
        payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
    return fin, opcode, payload


def _mux_frame_is_ask(text: str) -> bool:
    try:
        frame = json.loads(text)
    except json.JSONDecodeError:
        return False
    if not isinstance(frame, dict):
        return False
    payload = frame.get("payload") if isinstance(frame.get("payload"), dict) else {}
    kind = str(frame.get("method") or payload.get("type") or frame.get("type") or "")
    return kind == "approval/requested"


def _ws_collect_text(sock: socket.socket, leftover: bytes, *, deadline: float) -> list[str]:
    reader = _SockBuf(sock, leftover)
    texts: list[str] = []
    pending = bytearray()
    text_mode = False
    while len(texts) < _WS_MAX_FRAMES:
        remain = deadline - time.monotonic()
        if remain <= 0:
            break
        sock.settimeout(remain)
        try:
            fin, opcode, payload = _ws_read_frame(reader)
        except (TimeoutError, socket.timeout, OSError):
            break
        if opcode == 0x8:
            break
        if opcode in {0x9, 0xA}:
            continue
        if opcode == 0x1:
            pending = bytearray(payload)
            text_mode = True
        elif opcode == 0x0 and text_mode:
            pending.extend(payload)
        else:
            continue
        if not (fin and text_mode):
            continue
        text = pending.decode("utf-8", errors="replace")
        pending = bytearray()
        text_mode = False
        if not text:
            continue
        texts.append(text)
        if _mux_frame_is_ask(text):
            break
    return texts
