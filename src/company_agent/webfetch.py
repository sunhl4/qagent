"""company.knowledge managed web fetch: allowlist-gated, fail-closed page reader.

P3-A1/A2 of the 2000 person-day plan (受管网页检索). The tool is disabled by
construction: ``COMPANY_AGENT_FETCH_ALLOWLIST`` is the only way to name
destinations; it is bounded, operator controlled, and matched as an exact
host or a single leading ``*.`` wildcard suffix. A missing, empty or invalid
allowlist fails closed before any network access, so nothing is fetched
implicitly.

Each call performs a single HTTP(S) request made directly to one pinned
destination address: the host is resolved exactly once, every resolved
address must be global (the sole exception is an explicitly allowlisted
literal loopback address kept for offline tests and development), and the
connection opens on that address while certificate identity is still
verified against the requested hostname, so DNS rebinding cannot move the
flow after validation. Redirects are never followed, environment proxies are
disabled, only ``text/plain`` and ``text/html`` are accepted, ``http`` is
allowed only for loopback destinations, and ``localhost`` names plus private
ranges stay refused.

Fetched pages are untrusted reference data, never instructions or
authorization. The extracted ``<title>`` is returned separately for citation,
the bounded, byte-clipped body text carries budget-completeness markers, and
deterministic injection-signal detectors (bounded pattern match on the
returned excerpt only) report override language, tool-invocation directives,
credential-disclosure directives and role-identity claims; a clean report is
not a safety verdict, the trust marker stays constant. Error messages stay
free of URLs, page contents, endpoints and credentials. This module never
imports the contract kernel and creates no model, session or tool loops.
"""
from __future__ import annotations

import http.client
import ipaddress
import os
import re
import socket
import ssl
import urllib.parse
from collections.abc import Mapping
from html.parser import HTMLParser
from typing import Any

MAX_URL_BYTES = 2048
MAX_ALLOWLIST = 16
MAX_BODY_BYTES = 1_000_000
MAX_TEXT_BYTES = 20_000
MAX_TITLE_BYTES = 256
HTTP_TIMEOUT_SECONDS = 10

ALLOWLIST_ENV = "COMPANY_AGENT_FETCH_ALLOWLIST"
USER_AGENT = "company-agent-fetch/1.0"

_ALLOWED_CONTENT_TYPES = {"text/plain", "text/html"}
_CONTROL_PATTERN = re.compile(r"[\x00-\x1f\x7f]")
_SPACE_PATTERN = re.compile(r"\s+")
_LABEL_PATTERN = re.compile(r"[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?")

# Deterministic bounded injection-signal patterns (contract signals.reasons).
# Signals are evidence, not safety verdicts: web text stays untrusted data.
_OVERRIDE_LANGUAGE = re.compile(
    r"(?:ignore|disregard|forget|bypass|override)[^.\n]{0,80}"
    r"\b(?:previous(?:ly)?|prior|earlier|above|all)\b[^.\n]{0,40}\binstructions?",
    re.IGNORECASE,
)
_TOOL_INVOCATION_DIRECTIVE = re.compile(
    r"(?:调用|执行|运行|invoke|call|use|run)\s*(?:该|那个|the\s+)?"
    r"(?:工具|hpc_[a-z0-9_]+|company_[a-z0-9_]+|quantum_[a-z0-9_]+|tools?\b)",
    re.IGNORECASE,
)
_CREDENTIAL_DISCLOSURE = re.compile(
    r"(?:导出|泄露|输出|reveal|show|print|export|send|read)[^.\n]{0,60}"
    r"(?:api\s?key|(?:access|api)\s?token|password|credential|secret|private\s?key|ssh\s?key"
    r"|密钥|凭据|口令)",
    re.IGNORECASE,
)
_ROLE_IDENTITY_CLAIM = re.compile(
    r"\bsystem\s*prompt\b|you\s+are\s+(?:now|actually|really)\b"
    r"|从现在起[^.\n]{0,20}(?:你是|身份)",
    re.IGNORECASE,
)
_SIGNAL_PATTERNS = (
    ("override_language", _OVERRIDE_LANGUAGE),
    ("tool_invocation_directive", _TOOL_INVOCATION_DIRECTIVE),
    ("credential_disclosure", _CREDENTIAL_DISCLOSURE),
    ("role_identity_claim", _ROLE_IDENTITY_CLAIM),
)


class FetchError(ValueError):
    """Bounded fetch failure; messages stay free of URLs, pages and endpoints."""


_TLS_CONTEXT = ssl.create_default_context()


def _allowlist() -> tuple[str, ...]:
    raw = _CONTROL_PATTERN.sub("", os.environ.get(ALLOWLIST_ENV, "")).strip()
    if not raw:
        return ()
    entries: list[str] = []
    seen: set[str] = set()
    for chunk in raw.split(","):
        entry = chunk.strip().casefold().removesuffix(".")
        body = entry[2:] if entry.startswith("*.") else entry
        if (
            not body
            or "*" in body
            or ":" in entry
            or len(entry) > 253
            or entry in seen
            or any(not _LABEL_PATTERN.fullmatch(label) for label in body.split("."))
        ):
            raise FetchError("managed fetch allowlist entry is invalid")
        if len(entries) >= MAX_ALLOWLIST:
            raise FetchError("managed fetch allowlist exceeds the bounded size")
        seen.add(entry)
        entries.append(entry)
    return tuple(entries)


def _host_allowed(host: str, entries: tuple[str, ...]) -> bool:
    for entry in entries:
        if entry.startswith("*."):
            if host.endswith("." + entry[2:]):
                return True
        elif host == entry:
            return True
    return False


def _destination(
    raw: object,
) -> tuple[str, str, int, str]:
    if not isinstance(raw, str) or not raw:
        raise FetchError("web fetch destination is invalid")
    url = raw.strip()
    if not url or _CONTROL_PATTERN.search(url) or len(url.encode("utf-8")) > MAX_URL_BYTES:
        raise FetchError("web fetch destination is invalid")
    try:
        parsed = urllib.parse.urlsplit(url)
    except ValueError as exc:
        raise FetchError("web fetch destination is invalid") from exc
    if parsed.scheme not in {"http", "https"} or parsed.scheme != parsed.scheme.casefold():
        raise FetchError("web fetch destination scheme is not supported")
    if (
        not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        raise FetchError("web fetch destination is invalid")
    hostname = parsed.hostname.casefold().removesuffix(".")
    if not hostname.isascii():
        raise FetchError("web fetch destination is invalid")
    try:
        port = parsed.port
    except ValueError as exc:
        raise FetchError("web fetch destination is invalid") from exc
    if port is None:
        port = 443 if parsed.scheme == "https" else 80
    if not 1 <= port <= 65535:
        raise FetchError("web fetch destination is invalid")
    try:
        request_path = parsed.path or "/"
        if parsed.query:
            request_path = request_path + "?" + parsed.query
        target = urllib.parse.urlunsplit(
            (parsed.scheme, parsed.netloc, parsed.path or "/", parsed.query, "")
        )
    except ValueError as exc:
        raise FetchError("web fetch destination is invalid") from exc
    return target, hostname, int(port), parsed.scheme, request_path


def _resolve_guard(
    hostname: str, port: int, entries: tuple[str, ...]
) -> tuple[frozenset[str], bool]:
    """Fail closed unless every resolved address is global.

    The single exception is a literal loopback IP that is itself allowlisted,
    which exists for offline tests and development only; it skips resolution
    entirely so loopback replay through a resolver cannot widen the grant.
    Returns the parsed address set and the loopback-exception flag.
    """
    try:
        literal = ipaddress.ip_address(hostname)
    except ValueError:
        literal = None
    if literal is not None:
        if literal.is_loopback and hostname in entries:
            return frozenset({str(literal)}), True
        raise FetchError("web fetch destination resolved to a non-public address")
    try:
        infos = socket.getaddrinfo(hostname, port, proto=socket.IPPROTO_TCP)
    except (OSError, UnicodeError) as exc:
        raise FetchError("web fetch destination is unreachable") from exc
    addresses: set[str] = set()
    for info in infos:
        address = str(info[4][0]).split("%", 1)[0]
        try:
            addresses.add(str(ipaddress.ip_address(address)))
        except ValueError as exc:
            raise FetchError("web fetch destination address cannot be verified") from exc
    if not addresses or not all(ipaddress.ip_address(item).is_global for item in addresses):
        raise FetchError("web fetch destination resolved to a non-public address")
    return frozenset(addresses), False


def _pinned_socket(scheme: str, address: str, port: int, hostname: str) -> socket.socket:
    """Open the transport on the validated address, not on a fresh resolution.

    For HTTPS the certificate stays verified against the requested hostname,
    so the pin closes the resolution-to-connection rebinding window without
    weakening TLS.
    """
    try:
        sock = socket.create_connection((address, port), timeout=HTTP_TIMEOUT_SECONDS)
    except (OSError, ValueError) as exc:
        raise FetchError("web fetch destination is unreachable") from exc
    if scheme != "https":
        return sock
    try:
        return _TLS_CONTEXT.wrap_socket(sock, server_hostname=hostname)
    except (OSError, ValueError) as exc:
        sock.close()
        raise FetchError("web fetch transport security is not acceptable") from exc


def _request(
    scheme: str, hostname: str, port: int, request_path: str, address: str
) -> tuple[int, str, bytes, bool]:
    headers = {"Accept": "text/plain;q=1.0, text/html;q=0.9", "User-Agent": USER_AGENT}
    connection = http.client.HTTPConnection(hostname, port, timeout=HTTP_TIMEOUT_SECONDS)
    try:
        connection.sock = _pinned_socket(scheme, address, port, hostname)
        connection.request("GET", request_path, headers=headers)
        response = connection.getresponse()
        status = getattr(response, "status", None)
        if not isinstance(status, int) or not 200 <= status < 300:
            if isinstance(status, int) and 300 <= status < 400:
                raise FetchError("web fetch redirects are not followed")
            if isinstance(status, int) and 400 <= status < 500:
                raise FetchError("web fetch destination rejected the request")
            raise FetchError("web fetch returned an unexpected HTTP status")
        media_type = str(response.headers.get("Content-Type") or "").casefold().split(";", 1)[0].strip()
        if media_type not in _ALLOWED_CONTENT_TYPES:
            raise FetchError("web fetch response content type is not supported")
        # Read at most one byte past the declared body budget. Length-known
        # (will-close HTTP/1.0) responses otherwise make the extra-byte read
        # wait on a second recv that the loopback close can answer with RST.
        read_budget = MAX_BODY_BYTES + 1
        remaining = getattr(response, "length", None)
        if isinstance(remaining, int) and 0 <= remaining < read_budget:
            read_budget = remaining
        body = response.read(read_budget)
    except FetchError:
        raise
    except (OSError, ValueError, TimeoutError, http.client.HTTPException, UnicodeError) as exc:
        raise FetchError("web fetch destination is unreachable") from exc
    finally:
        connection.close()
    body_capped = len(body) > MAX_BODY_BYTES
    if body_capped:
        body = body[:MAX_BODY_BYTES]
    return status, media_type, body, body_capped


class _PageTextParser(HTMLParser):
    """Collect visible text and the ``<title>``; neither script, style nor
    title content reaches the body text."""

    _SKIP_TAGS = frozenset({"script", "style", "noscript", "template"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.pieces: list[str] = []
        self.title_parts: list[str] = []
        self._skip_depth = 0
        self._title_depth = 0

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        if tag == "title":
            self._title_depth += 1
        elif tag in self._SKIP_TAGS:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag == "title" and self._title_depth:
            self._title_depth -= 1
        elif tag in self._SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        piece = _SPACE_PATTERN.sub(" ", data).strip()
        if not piece:
            return
        if self._skip_depth:
            return
        if self._title_depth:
            self.title_parts.append(piece)
        else:
            self.pieces.append(piece)


def _clip(text: str, limit: int) -> tuple[str, bool]:
    encoded = text.encode("utf-8")
    if len(encoded) <= limit:
        return text, False
    encoded = encoded[:limit]
    while encoded:
        try:
            return encoded.decode("utf-8"), True
        except UnicodeError:
            encoded = encoded[:-1]
    return "", True


def _injection_signals(text: str) -> dict[str, Any]:
    reasons = [name for name, pattern in _SIGNAL_PATTERNS if pattern.search(text)]
    return {"fired": bool(reasons), "reasons": reasons}


def fetch(args: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(args, Mapping):
        raise TypeError("web fetch arguments must be an object")
    if not isinstance(args, dict):
        raise TypeError("web fetch arguments must be a JSON object")
    unknown = set(args) - {"url"}
    if unknown:
        raise ValueError(f"web fetch has unknown fields: {sorted(unknown)}")
    if not isinstance(args.get("url"), str):
        raise TypeError("url must be a string")
    allowlist = _allowlist()
    if not allowlist:
        raise FetchError("managed web fetch is disabled: no allowlist is configured")
    target, hostname, port, scheme, request_path = _destination(args["url"])
    if not _host_allowed(hostname, allowlist):
        raise FetchError("web fetch destination host is not in the managed allowlist")
    addresses, loopback = _resolve_guard(hostname, port, allowlist)
    if scheme == "http" and not loopback:
        raise FetchError("web fetch destination must use https outside loopback")
    address = sorted(addresses)[0]
    status, media_type, body, body_capped = _request(scheme, hostname, port, request_path, address)
    raw_text = body.decode("utf-8", errors="replace")
    title = ""
    if media_type == "text/html":
        parser = _PageTextParser()
        try:
            parser.feed(raw_text)
            parser.close()
        except Exception as exc:  # noqa: BLE001 — any parser failure fails closed
            raise FetchError("web fetch page could not be reduced to text") from exc
        title = _clip(" ".join(parser.title_parts), MAX_TITLE_BYTES)[0].strip()
        raw_text = " ".join(parser.pieces)
    text, text_capped = _clip(_SPACE_PATTERN.sub(" ", raw_text).strip(), MAX_TEXT_BYTES)
    title, _ = _clip(title, MAX_TITLE_BYTES)
    reasons: list[str] = []
    if body_capped:
        reasons.append("body_budget")
    if text_capped:
        reasons.append("byte_budget")
    truncated = bool(reasons)
    return {
        "url": target,
        "status": "fetched",
        "http_status": int(status),
        "content_type": media_type,
        "body_bytes": len(body),
        "bytes": len(text.encode("utf-8")),
        "truncated": truncated,
        "scan": {"complete": not truncated, "reasons": reasons},
        "signals": _injection_signals(text),
        "trust": "untrusted_reference_data",
        "title": title,
        "text": text,
    }
