"""DingTalk connector for the company Super DSH control plane.

Addressed robot messages become source events. This module does not start a
model loop, open a ticket, or keep a second session. A DSH session reads the
ledger and sends a short reply through the DingTalk OpenAPI.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import http.client
import ipaddress
import json
import os
import re
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from company_agent.jsonutil import loads as strict_json_loads
from company_agent.work_items import WorkItemError, WorkItemStore

APP_KEY_ENV = "COMPANY_DINGTALK_APP_KEY"
APP_SECRET_ENV = "COMPANY_DINGTALK_APP_SECRET"
ROBOT_CODE_ENV = "COMPANY_DINGTALK_ROBOT_CODE"
_API_HOST = "api.dingtalk.com"
_CALLBACK_PATH = "/dingtalk/robot"
_MAX_BODY_BYTES = 65_536
_MAX_TEXT_CHARS = 2000
_SIGNATURE_WINDOW_MS = 3_600_000
_HTTP_TIMEOUT_SECONDS = 20
_MAX_RESPONSE_BYTES = 65_536
_THREAD_ID = re.compile(r"^[A-Za-z0-9$:+/=_.-]{1,128}$")
_STAFF_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_MESSAGE_ID = re.compile(r"^[A-Za-z0-9$:+/=_.@-]{1,200}$")
_TRIGGER_ID = re.compile(r"^trg_[0-9a-f]{32}$")
_WEBHOOK = re.compile(r"https://oapi\.dingtalk\.com/\S+", re.IGNORECASE)
_SCIENCE = re.compile(r"OPENQASM\s+[23](?:\.\d+)?|-----BEGIN [A-Z ]*PRIVATE KEY-----", re.IGNORECASE)
_OMITTED = "dingtalk message omitted"
_UNIDENTIFIED = "dingtalk:unidentified"
_TOKEN_CACHE: dict[str, float | str] = {"value": "", "until": 0.0}
_SERVER: ThreadingHTTPServer | None = None


class DingtalkError(ValueError):
    """A DingTalk callback or reply could not be accepted."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        del req, fp, code, msg, headers, newurl
        return None


_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect)


def configuration() -> dict[str, object]:
    """Report whether reply credentials exist. Values stay out of the result."""
    return {
        "configured": _configured(),
        "app_key_env": APP_KEY_ENV,
        "app_secret_env": APP_SECRET_ENV,
        "robot_code_env": ROBOT_CODE_ENV,
    }


def accept_callback(headers: Mapping[str, str], body: bytes, *, tenant_id: str) -> dict[str, str]:
    """Verify one robot callback and record it when the bot was addressed."""
    if not isinstance(body, bytes) or len(body) > _MAX_BODY_BYTES:
        raise DingtalkError("dingtalk message is invalid")
    timestamp = _header(headers, "timestamp")
    sign = _header(headers, "sign")
    _verify_signature(timestamp, sign)
    try:
        payload = strict_json_loads(body.decode("utf-8"))
    except (UnicodeError, ValueError, TypeError) as exc:
        raise DingtalkError("dingtalk message is invalid") from exc
    if not isinstance(payload, dict):
        raise DingtalkError("dingtalk message is invalid")
    _reject_encrypted(payload)
    return ingest_message(payload, tenant_id=tenant_id)


def ingest_message(payload: Mapping[str, Any], *, tenant_id: str) -> dict[str, str]:
    """Record one already-verified robot message. Unsigned tool input cannot call this."""
    addressed = _addressed(payload)
    if addressed is None:
        return {
            "recorded": "false", "reason": "not_addressed", "trigger_id": "",
            "thread_key": "", "ticket_id": "",
        }
    thread_id = payload.get("conversationId")
    message_id = payload.get("msgId")
    if not isinstance(thread_id, str) or _THREAD_ID.fullmatch(thread_id) is None:
        return {"recorded": "false", "reason": "invalid", "trigger_id": "", "thread_key": "", "ticket_id": ""}
    if not isinstance(message_id, str) or _MESSAGE_ID.fullmatch(message_id) is None:
        return {"recorded": "false", "reason": "invalid", "trigger_id": "", "thread_key": "", "ticket_id": ""}
    actor = payload.get("senderStaffId")
    actor_id = actor if isinstance(actor, str) and _STAFF_ID.fullmatch(actor) else _UNIDENTIFIED
    text = _public_text(_message_text(payload))
    try:
        with WorkItemStore() as store:
            row = store.receive(
                "dingtalk", thread_id, actor_id, text, human=True, addressed=addressed,
                tenant_id=tenant_id, idempotency_key=message_id, subject_id=actor_id,
            )
    except WorkItemError as exc:
        raise _ledger_error(exc) from exc
    except (sqlite3.Error, OSError) as exc:
        raise DingtalkError("dingtalk ledger is unavailable") from exc
    return {
        "recorded": "true",
        "reason": "candidate",
        "trigger_id": str(row["trigger_id"]),
        "thread_key": str(row["thread_key"]),
        "ticket_id": "",
    }


def ingest_envelope(envelope: Mapping[str, Any], *, tenant_id: str) -> dict[str, str]:
    """Verify the callback signature on a CLI envelope, then record the body."""
    timestamp = envelope.get("timestamp")
    sign = envelope.get("sign")
    body = envelope.get("body")
    if not isinstance(timestamp, str) or not isinstance(sign, str) or not isinstance(body, dict):
        raise DingtalkError("dingtalk message is invalid")
    if set(envelope) - {"timestamp", "sign", "body"}:
        raise DingtalkError("dingtalk message is invalid")
    _verify_signature(timestamp, sign)
    _reject_encrypted(body)
    return ingest_message(body, tenant_id=tenant_id)


def inbox(arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Return short rows already recorded for this tenant. Does not call DingTalk."""
    tenant_id = _tenant(arguments.get("tenant_id"))
    thread_id = arguments.get("thread_id")
    if thread_id is not None and (not isinstance(thread_id, str) or _THREAD_ID.fullmatch(thread_id) is None):
        raise DingtalkError("dingtalk thread is invalid")
    try:
        with WorkItemStore() as store:
            rows = store.list_source_triggers("dingtalk", tenant_id, thread_id=thread_id, limit=20)
    except WorkItemError as exc:
        raise DingtalkError("dingtalk thread is invalid") from exc
    items = []
    for row in rows:
        addressed = row.get("addressed")
        thread_key = str(row.get("thread_key") or "")
        if addressed not in {"mention", "direct"} or not thread_key.startswith("dingtalk:"):
            continue
        identity = thread_key.removeprefix("dingtalk:")
        if _THREAD_ID.fullmatch(identity) is None:
            continue
        items.append({
            "trigger_id": str(row["trigger_id"]),
            "thread_id": identity,
            "actor_id": str(row["actor_id"]),
            "addressed": addressed,
            "text": str(row["text"]),
            "created_at": str(row["created_at"]),
        })
    return {"tenant_id": tenant_id, "count": len(items), "items": items}


def reply(arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Send one short text for one recorded, addressed Source event."""
    if not _configured():
        raise DingtalkError("dingtalk is not configured")
    tenant_id = _tenant(arguments.get("tenant_id"))
    thread_id = arguments.get("thread_id")
    trigger_id = arguments.get("trigger_id")
    text = arguments.get("text")
    if not isinstance(thread_id, str) or _THREAD_ID.fullmatch(thread_id) is None:
        raise DingtalkError("dingtalk thread is invalid")
    if not isinstance(trigger_id, str) or _TRIGGER_ID.fullmatch(trigger_id) is None:
        raise DingtalkError("dingtalk trigger is invalid")
    if not isinstance(text, str) or not text.strip():
        raise DingtalkError("dingtalk reply is invalid")
    cleaned = _WEBHOOK.sub("[link]", text.strip())
    if _SCIENCE.search(cleaned) or len(cleaned.encode("utf-8")) > _MAX_TEXT_CHARS:
        raise DingtalkError("dingtalk reply is invalid")
    try:
        with WorkItemStore() as store:
            row = store.source_trigger("dingtalk", tenant_id, trigger_id)
    except WorkItemError as exc:
        raise DingtalkError("dingtalk thread is invalid") from exc
    except (sqlite3.Error, OSError) as exc:
        raise DingtalkError("dingtalk ledger is unavailable") from exc
    if (
        row is None
        or row.get("addressed") not in {"mention", "direct"}
        or row.get("thread_key") != f"dingtalk:{thread_id}"
    ):
        raise DingtalkError("dingtalk thread has no addressed message")
    addressed = str(row["addressed"])
    actor = str(row.get("actor_id") or "")
    if addressed == "direct":
        if _STAFF_ID.fullmatch(actor) is None:
            raise DingtalkError("dingtalk sender is missing")
        _post(
            "/v1.0/robot/oToMessages/batchSend",
            {
                "robotCode": _env(ROBOT_CODE_ENV),
                "userIds": [actor],
                "msgKey": "sampleText",
                "msgParam": json.dumps({"content": cleaned}, ensure_ascii=False, separators=(",", ":")),
            },
            token=_access_token(),
        )
    else:
        _post(
            "/v1.0/robot/groupMessages/send",
            {
                "robotCode": _env(ROBOT_CODE_ENV),
                "openConversationId": thread_id,
                "msgKey": "sampleText",
                "msgParam": json.dumps({"content": cleaned}, ensure_ascii=False, separators=(",", ":")),
            },
            token=_access_token(),
        )
    return {
        "status": "sent",
        "thread_key": f"dingtalk:{thread_id}",
        "addressed": addressed,
        "bytes": len(cleaned.encode("utf-8")),
    }


def serve(host: str, port: int, tenant_id: str) -> None:
    """Accept robot callbacks on one address. The process only writes source events."""
    global _SERVER
    bound_host, bound_port = bind_address(host, port)
    tenant = _tenant(tenant_id)

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 - stdlib handler name
            path = urllib.parse.urlsplit(self.path).path
            if path != _CALLBACK_PATH:
                self._empty(404)
                return
            length = self.headers.get("Content-Length")
            try:
                size = int(length) if length is not None else 0
            except ValueError:
                self._empty(400)
                return
            if size < 0 or size > _MAX_BODY_BYTES:
                self._empty(413)
                return
            body = self.rfile.read(size)
            header_map = {key: value for key, value in self.headers.items()}
            try:
                accept_callback(header_map, body, tenant_id=tenant)
            except DingtalkError as exc:
                # Signature failures are rejected. A verified body that is not
                # for the bot is acknowledged. A ledger failure stays non-2xx
                # so DingTalk can retry a message that was not recorded.
                reason = str(exc)
                if reason in {"dingtalk signature is invalid", "dingtalk is not configured"}:
                    self._empty(401)
                    return
                if reason == "dingtalk ledger is unavailable":
                    self._empty(503)
                    return
                if reason == "dingtalk callback is encrypted":
                    self._empty(400)
                    return
            self._empty(200)

        def log_message(self, fmt: str, *args: object) -> None:
            del fmt, args

        def _empty(self, status: int) -> None:
            encoded = b'{"msgtype":"empty"}'
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

    server = ThreadingHTTPServer((bound_host, bound_port), Handler)
    _SERVER = server
    try:
        server.serve_forever()
    finally:
        server.server_close()
        _SERVER = None


def bind_address(host: object, port: object) -> tuple[str, int]:
    if not isinstance(host, str) or not host or host != host.strip():
        raise DingtalkError("dingtalk listen address is invalid")
    try:
        parsed = ipaddress.ip_address(host)
    except ValueError as exc:
        raise DingtalkError("dingtalk listen address is invalid") from exc
    if parsed.is_unspecified or parsed.is_multicast or parsed.is_reserved:
        raise DingtalkError("dingtalk listen address is invalid")
    if isinstance(port, bool) or not isinstance(port, int) or port < 1 or port > 65535:
        raise DingtalkError("dingtalk listen address is invalid")
    return host, port


def _header(headers: Mapping[str, str], name: str) -> str:
    for key, value in headers.items():
        if str(key).casefold() == name and isinstance(value, str):
            return value.strip()
    return ""


def _verify_signature(timestamp: str, sign: str, *, now: float | None = None) -> None:
    secret = _env(APP_SECRET_ENV)
    if not secret:
        raise DingtalkError("dingtalk is not configured")
    if not timestamp.isdigit() or len(timestamp) > 16 or not sign or len(sign) > 512:
        raise DingtalkError("dingtalk signature is invalid")
    current = int((time.time() if now is None else now) * 1000)
    if abs(current - int(timestamp)) > _SIGNATURE_WINDOW_MS:
        raise DingtalkError("dingtalk signature is invalid")
    expected = base64.b64encode(
        hmac.new(secret.encode(), f"{timestamp}\n{secret}".encode(), hashlib.sha256).digest()
    ).decode("ascii")
    provided = urllib.parse.unquote(sign)
    if not _same(expected, provided) and not _same(expected, sign):
        raise DingtalkError("dingtalk signature is invalid")


def _same(left: str, right: str) -> bool:
    if len(left) != len(right):
        return False
    return hmac.compare_digest(left, right)


def _reject_encrypted(payload: Mapping[str, Any]) -> None:
    token = payload.get("encrypt")
    if isinstance(token, str) and token.strip():
        raise DingtalkError("dingtalk callback is encrypted")


def _ledger_error(exc: WorkItemError) -> DingtalkError:
    message = str(exc)
    if message == "idempotency conflict" or message.endswith((" is invalid", " is too long")):
        return DingtalkError("dingtalk message is invalid")
    return DingtalkError("dingtalk ledger is unavailable")


def _addressed(payload: Mapping[str, Any]) -> str | None:
    raw = payload.get("conversationType")
    if isinstance(raw, bool) or not isinstance(raw, str | int):
        return None
    kind = str(raw)
    if kind == "1":
        return "direct"
    if kind == "2" and payload.get("isInAtList") is True:
        return "mention"
    return None


def _message_text(payload: Mapping[str, Any]) -> str:
    kind = payload.get("msgtype")
    if kind == "text" and isinstance(payload.get("text"), dict):
        content = payload["text"].get("content")
        if isinstance(content, str):
            return content
    if kind == "markdown" and isinstance(payload.get("markdown"), dict):
        content = payload["markdown"].get("text")
        if isinstance(content, str):
            return content
    if kind in {"picture", "image"}:
        return "dingtalk image message"
    if kind in {"file", "audio", "video", "richText"}:
        return "dingtalk attachment message"
    return "dingtalk message"


def _public_text(value: str) -> str:
    text = _WEBHOOK.sub("[link]", value.replace("\x00", "")).strip()
    secrets = [_env(name) for name in (APP_KEY_ENV, APP_SECRET_ENV, ROBOT_CODE_ENV)]
    if not text or any(secret and secret in text for secret in secrets) or _SCIENCE.search(text):
        return _OMITTED
    limit = 4000
    if len(text.encode("utf-8")) > limit:
        return "dingtalk message omitted because it exceeded the trigger budget"
    return text


def _tenant(value: object) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.encode("utf-8")) > 80:
        raise DingtalkError("dingtalk tenant is invalid")
    return value.strip()


def _configured() -> bool:
    return all(_env(name) for name in (APP_KEY_ENV, APP_SECRET_ENV, ROBOT_CODE_ENV))


def _env(name: str) -> str:
    value = str(os.environ.get(name) or "").strip()
    if not value or len(value) > 256 or any(ord(char) < 32 or ord(char) == 127 for char in value):
        return ""
    return value


def _access_token() -> str:
    cached = str(_TOKEN_CACHE.get("value") or "")
    until = float(_TOKEN_CACHE.get("until") or 0)
    if cached and until > time.time() + 60:
        return cached
    payload = _post(
        "/v1.0/oauth2/accessToken",
        {"appKey": _env(APP_KEY_ENV), "appSecret": _env(APP_SECRET_ENV)},
        token="",
    )
    token = payload.get("accessToken")
    expire = payload.get("expireIn")
    if (
        not isinstance(token, str) or not token.strip()
        or isinstance(expire, bool) or not isinstance(expire, int)
    ):
        raise DingtalkError("dingtalk rejected the call")
    if not 60 <= expire <= 86400 or any(ord(char) < 33 or ord(char) == 127 for char in token):
        raise DingtalkError("dingtalk rejected the call")
    _TOKEN_CACHE["value"] = token
    _TOKEN_CACHE["until"] = time.time() + expire
    return token


def _post(path: str, body: Mapping[str, Any], *, token: str) -> dict[str, Any]:
    if path not in {
        "/v1.0/oauth2/accessToken",
        "/v1.0/robot/groupMessages/send",
        "/v1.0/robot/oToMessages/batchSend",
    }:
        raise DingtalkError("dingtalk reply was refused")
    encoded = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(encoded) > _MAX_RESPONSE_BYTES:
        raise DingtalkError("dingtalk reply is invalid")
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        headers["x-acs-dingtalk-access-token"] = token
    request = urllib.request.Request(
        f"https://{_API_HOST}{path}", data=encoded, headers=headers, method="POST",
    )
    try:
        with _OPENER.open(request, timeout=_HTTP_TIMEOUT_SECONDS) as response:
            status = getattr(response, "status", None)
            if status != 200:
                raise DingtalkError("dingtalk rejected the call")
            media = str(response.headers.get("Content-Type") or "").casefold().split(";", 1)[0].strip()
            if media != "application/json" and not (
                media.startswith("application/") and media.endswith("+json")
            ):
                raise DingtalkError("dingtalk rejected the call")
            raw = response.read(_MAX_RESPONSE_BYTES + 1)
    except DingtalkError:
        raise
    except urllib.error.HTTPError as exc:
        exc.close()
        raise DingtalkError("dingtalk rejected the call") from None
    except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException) as exc:
        raise DingtalkError("dingtalk is unreachable") from exc
    if len(raw) > _MAX_RESPONSE_BYTES:
        raise DingtalkError("dingtalk rejected the call")
    try:
        payload = strict_json_loads(raw.decode("utf-8"))
    except (UnicodeError, ValueError, TypeError) as exc:
        raise DingtalkError("dingtalk rejected the call") from exc
    if not isinstance(payload, dict):
        raise DingtalkError("dingtalk rejected the call")
    return payload
