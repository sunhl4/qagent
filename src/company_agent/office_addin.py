"""Loopback review protocol for a Word/WPS task pane (§5.2).

The HTTP server starts only when ``COMPANY_AGENT_ADDIN=1``. Tests drive
``ReviewStore`` directly. Writes go through ``company_office_edit``. A real
Word/WPS host is not claimed accepted by this module.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ENV_ADDIN = "COMPANY_AGENT_ADDIN"
DEDUPE_SECONDS = 600
ORPHAN_SECONDS = 1800
_STATES = {"queued", "running", "ready", "failed", "stale", "superseded"}
_VIEW = Path(__file__).resolve().parents[2] / "view" / "office-addin"
_ASSETS = {
    "/word-addin/taskpane.html": (_VIEW / "taskpane.html", "text/html; charset=utf-8"),
    "/word-addin/taskpane.js": (_VIEW / "taskpane.js", "text/javascript; charset=utf-8"),
    "/word-addin/taskpane.css": (_VIEW / "taskpane.css", "text/css; charset=utf-8"),
    "/word-addin/config.js": (_VIEW / "config.js", "text/javascript; charset=utf-8"),
    "/word-addin/manifest.xml": (_VIEW / "manifest.xml", "application/xml"),
    "/word-addin/wps/host.js": (_VIEW / "wps" / "host.js", "text/javascript; charset=utf-8"),
}


class OfficeAddinError(ValueError):
    """Refusal that names the boundary hit."""


class ReviewStore:
    """In-memory review queue with the spec's state machine."""

    def __init__(self, token: str, clock=time.time) -> None:
        self._token = token
        self._clock = clock
        self._rows: dict[str, dict] = {}
        self._lock = threading.Lock()

    def submit(self, file_bytes: bytes, instruction: str) -> dict:
        if not isinstance(instruction, str) or not instruction.strip():
            raise OfficeAddinError("instruction 不能为空")
        fingerprint = _fingerprint(file_bytes)
        now = self._clock()
        with self._lock:
            self._expire(now)
            for row in self._rows.values():
                if row["fingerprint"] == fingerprint and row["instruction"] == instruction:
                    if row["state"] == "running" and now - row["updated"] < DEDUPE_SECONDS:
                        return dict(row)
                    if now - row["updated"] < DEDUPE_SECONDS and row["state"] in {"queued", "ready"}:
                        return dict(row)
            review_id = hashlib.sha256(f"{fingerprint}:{instruction}:{now}".encode()).hexdigest()[:16]
            row = {
                "id": review_id,
                "state": "queued",
                "fingerprint": fingerprint,
                "instruction": instruction.strip()[:200],
                "updated": now,
                "edits": [],
            }
            self._rows[review_id] = row
            return dict(row)

    def take(self, review_id: str, file_bytes: bytes) -> dict:
        with self._lock:
            row = self._must(review_id)
            if row["state"] == "running":
                return dict(row)
            if _fingerprint(file_bytes) != row["fingerprint"]:
                row["state"] = "stale"
                row["updated"] = self._clock()
                return dict(row)
            row["state"] = "running"
            row["updated"] = self._clock()
            return dict(row)

    def complete(self, review_id: str, edits: list) -> dict:
        with self._lock:
            row = self._must(review_id)
            if row["state"] != "running":
                raise OfficeAddinError("只有 running 的审查可以完成")
            row["edits"] = list(edits)
            row["state"] = "ready"
            row["updated"] = self._clock()
            return dict(row)

    def fail(self, review_id: str, reason: str) -> dict:
        with self._lock:
            row = self._must(review_id)
            row["state"] = "failed"
            row["reason"] = reason[:200]
            row["updated"] = self._clock()
            return dict(row)

    def get(self, review_id: str) -> dict:
        with self._lock:
            return dict(self._must(review_id))

    def _expire(self, now: float) -> None:
        for row in self._rows.values():
            if row["state"] in {"queued", "running"} and now - row["updated"] > ORPHAN_SECONDS:
                row["state"] = "failed"
                row["reason"] = "孤儿审查超过 30 分钟"
                row["updated"] = now

    def _must(self, review_id: str) -> dict:
        row = self._rows.get(review_id)
        if row is None:
            raise OfficeAddinError("审查不存在")
        if row["state"] not in _STATES:
            raise OfficeAddinError("审查状态无效")
        return row


def _fingerprint(data: bytes) -> str:
    material = (
        data[:131072] + data[-65536:] + str(len(data)).encode("ascii")
        if len(data) > 2_000_000
        else data
    )
    return hashlib.sha256(material).hexdigest()


def land(body: dict) -> dict:
    """Write a task-pane edit only through the tracked docx editor."""

    from company_agent import office_edit  # noqa: PLC0415 - keep the loopback import local

    payload = dict(body)
    payload.setdefault("purpose", "加载项审阅落盘")
    return office_edit.edit(payload)


def serve(token: str, port: int = 8765) -> ThreadingHTTPServer:
    """Bind 127.0.0.1 and ::1 on the same port. The caller starts serve_forever."""

    if os.environ.get(ENV_ADDIN) != "1":
        raise OfficeAddinError("COMPANY_AGENT_ADDIN 未开启:拒绝启动回环服务")
    store = ReviewStore(token)

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 - stdlib name
            if self.headers.get("Authorization") != f"Bearer {token}":
                self.send_error(401)
                return
            length = int(self.headers.get("Content-Length") or "0")
            if length > 1_000_000:
                self.send_error(413)
                return
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError:
                self.send_error(400)
                return
            if not isinstance(body, dict):
                self.send_error(400)
                return
            try:
                if self.path == "/api/word-addin/reviews":
                    row = store.submit(_review_bytes(body), str(body.get("instruction") or ""))
                elif self.path == "/api/word-addin/apply":
                    row = land(body)
                else:
                    self.send_error(404)
                    return
            except (OfficeAddinError, ValueError) as exc:
                message = str(exc).encode("utf-8")
                self.send_response(400)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(message)))
                self.end_headers()
                self.wfile.write(message)
                return
            payload = json.dumps(row).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self) -> None:  # noqa: N802 - stdlib name
            path = self.path.split("?", 1)[0]
            asset = _ASSETS.get(path)
            if asset is None or not asset[0].is_file():
                self.send_error(404)
                return
            payload = asset[0].read_bytes()
            self.server.visits.append(path)  # type: ignore[attr-defined]
            self.send_response(200)
            self.send_header("Content-Type", asset[1])
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, fmt: str, *args: object) -> None:
            self.server.visits.append(fmt % args)  # type: ignore[attr-defined]

    visits: list[str] = []
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.visits = visits  # type: ignore[attr-defined]
    chosen = server.server_address[1]
    try:
        twin: ThreadingHTTPServer | None = ThreadingHTTPServer(("::1", chosen), Handler)
    except OSError:
        twin = None
    server.loopback_v6 = twin  # type: ignore[attr-defined]
    if twin is not None:
        twin.visits = visits  # type: ignore[attr-defined]
    return server


def _review_bytes(body: dict) -> bytes:
    encoded = body.get("file")
    if not isinstance(encoded, str) or not encoded.strip():
        raise OfficeAddinError("reviews 需要 file 的 base64 字节")
    try:
        data = base64.b64decode(encoded, validate=True)
    except ValueError as exc:
        raise OfficeAddinError("file 必须是 base64") from exc
    if not data:
        raise OfficeAddinError("file 不能为空")
    return data
