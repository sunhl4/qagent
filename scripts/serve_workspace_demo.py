#!/usr/bin/env python3
"""Local presentation shell around the unmodified, authenticated DSH Web UI.

This is a development demo launcher, not an Agent runtime or production login.
It supervises the existing startup script and serves only the presentation HTML.
DSH still owns authentication, sessions, models, tools, and its complete frontend.
"""
from __future__ import annotations

import argparse
import hmac
import http.client
import json
import os
import queue
import re
import secrets
import signal
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "docs" / "quantum-agent-architecture.zh-CN.html"
NATIVE_PORT = 3081
LAUNCH_PATTERN = re.compile(r"http://127\.0\.0\.1:3081/\?token=[A-Za-z0-9_-]{16,512}")
DEMO_COOKIE = "unitqc-workspace-demo"
MAX_AGE = 8 * 60 * 60


def runtime_environment(home: Path) -> dict[str, str]:
    """Start with a small allowlist: never inherit model/science credentials."""
    env = {
        key: os.environ[key]
        for key in ("HOME", "PATH", "USER", "LOGNAME", "LANG", "LC_ALL", "SHELL", "TERM", "XDG_CACHE_HOME")
        if key in os.environ
    }
    env.update({
        "COMPANY_AGENT_DSH_HOME": str(home),
        "COMPANY_AGENT_DSH_PORT": str(NATIVE_PORT),
        "COMPANY_AGENT_PROFILE": "company-agent-minimal",
        "COMPANY_AGENT_PRESET": "boot",
        "COMPANY_AGENT_DEPLOYMENT_MODE": "development",
        "COMPANY_AGENT_DEMO_UI": "1",
    })
    return env


def exchange_launch_cookie(launch_url: str) -> str:
    """Use DSH's supported token exchange; never forge or weaken its auth."""
    if not LAUNCH_PATTERN.fullmatch(launch_url):
        raise ValueError("Invalid native launch URL")
    parsed = urlsplit(launch_url)
    conn = http.client.HTTPConnection("127.0.0.1", NATIVE_PORT, timeout=5)
    try:
        conn.request("GET", f"/?{parsed.query}")
        response = conn.getresponse()
        cookie = response.getheader("Set-Cookie", "")
        if response.status != 303 or response.getheader("Location") != "/":
            raise RuntimeError("DSH authentication exchange failed")
        if not cookie.startswith("dsh-auth-") or "HttpOnly" not in cookie or "SameSite=Strict" not in cookie:
            raise RuntimeError("DSH cookie contract changed")
        if "\r" in cookie or "\n" in cookie:
            raise RuntimeError("Invalid DSH cookie")
        response.read()
        return cookie
    finally:
        conn.close()


def register_demo_workspace(launch_url: str, directory: Path) -> None:
    """Register one empty demo folder through DSH's native Workspace API."""
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    if directory.is_symlink():
        raise RuntimeError("Demo workspace must not be a symlink")
    cookie = exchange_launch_cookie(launch_url).split(";", 1)[0]
    method = "workspace/create"
    rpc_id = "workspace-demo-init"
    body = json.dumps({"type": "client-request", "rpcId": rpc_id, "method": method,
                       "payload": {"args": {"request": {"path": str(directory)}}}})
    conn = http.client.HTTPConnection("127.0.0.1", NATIVE_PORT, timeout=10)
    try:
        conn.request("POST", f"/api/{method}", body, {"Content-Type": "application/json", "Cookie": cookie})
        response = conn.getresponse()
        raw = response.read(65537)
        if response.status != 200 or len(raw) > 65536:
            raise RuntimeError("Native workspace initialization failed")
        envelope = json.loads(raw)
        result_ok = envelope.get("result", {}).get("ok") is True
        if envelope.get("type") != "server-response" or envelope.get("rpcId") != rpc_id or not result_ok:
            raise RuntimeError("Native workspace initialization was refused")
    finally:
        conn.close()


def start_runtime(home: Path) -> tuple[subprocess.Popen, str]:
    """Capture the secret native URL in memory; stdout contains no credentials."""
    process = subprocess.Popen(
        ["bash", str(ROOT / "scripts" / "start_runtime.sh")],
        cwd=ROOT, env=runtime_environment(home), stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, text=True, bufsize=1, start_new_session=True,
    )
    output: queue.Queue[str | None] = queue.Queue()

    def consume() -> None:
        assert process.stdout is not None
        for line in process.stdout:
            # Only pass the known launch line; do not echo potentially private logs.
            match = LAUNCH_PATTERN.search(line)
            if match:
                output.put(match.group(0))
        output.put(None)

    threading.Thread(target=consume, daemon=True).start()
    try:
        launch = output.get(timeout=90)
        if launch is None:
            raise RuntimeError(f"DSH exited before startup (exit {process.poll()})")
        return process, launch
    except BaseException:
        stop_runtime(process)
        raise


def stop_runtime(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=5)


class DemoServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, port: int, launch_url: str):
        self.bootstrap = secrets.token_urlsafe(32)
        self.session = secrets.token_urlsafe(32)
        self.launch_url = launch_url
        self.expires_at = time.monotonic() + MAX_AGE
        super().__init__(("127.0.0.1", port), DemoHandler)

    @property
    def authority(self) -> str:
        return f"127.0.0.1:{self.server_port}"


class DemoHandler(BaseHTTPRequestHandler):
    server: DemoServer

    def log_message(self, _format: str, *args: object) -> None:
        # Neither URLs nor cookie/token values belong in demo logs.
        pass

    def respond(
        self,
        status: int,
        body: bytes = b"",
        *,
        cookies: tuple[str, ...] = (),
        location: str | None = None,
        content_type: str = "text/plain; charset=utf-8",
    ) -> None:
        self.send_response(status)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Type", content_type)
        for cookie in cookies:
            self.send_header("Set-Cookie", cookie)
        if location:
            self.send_header("Location", location)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def trusted_request(self) -> bool:
        if self.headers.get("Host") != self.server.authority:
            return False
        if self.headers.get("Sec-Fetch-Site") == "cross-site":
            return False
        origin = self.headers.get("Origin")
        return origin is None or origin == f"http://{self.server.authority}"

    def authenticated(self) -> bool:
        if time.monotonic() >= self.server.expires_at:
            return False
        for pair in self.headers.get("Cookie", "").split(";"):
            name, _, value = pair.strip().partition("=")
            if name == DEMO_COOKIE and hmac.compare_digest(value, self.server.session):
                return True
        return False

    def do_GET(self) -> None:
        if not self.trusted_request():
            self.respond(403, b"Local same-origin access only.\n")
            return
        parsed = urlsplit(self.path)
        if parsed.query:
            self.respond(400, b"Query parameters are not accepted.\n")
            return
        prefix = "/start/"
        if parsed.path.startswith(prefix):
            expired = time.monotonic() >= self.server.expires_at
            digest = hmac.compare_digest(parsed.path[len(prefix):], self.server.bootstrap)
            if self.command != "GET" or expired or not digest:
                self.respond(401, b"Reopen the local demo launch link.\n")
                return
            try:
                native_cookie = exchange_launch_cookie(self.server.launch_url)
            except (OSError, ValueError, RuntimeError, http.client.HTTPException):
                self.respond(503, b"Native DSH is unavailable. Restart the demo.\n")
                return
            # Cookies are host-scoped across ports, while the DSH signature stays
            # bound to its own authority. The parent page cannot read HttpOnly.
            demo_cookie = f"{DEMO_COOKIE}={self.server.session}; Path=/; HttpOnly;"
            demo_cookie += f" SameSite=Strict; Max-Age={MAX_AGE}"
            self.respond(303, cookies=(demo_cookie, native_cookie), location="http://127.0.0.1:3081/")
            return
        if not self.authenticated():
            self.respond(401, b"Open the launch link printed by serve_workspace_demo.py.\n")
            return
        if parsed.path in {"/", "/workspace"}:
            self.respond(303, location="http://127.0.0.1:3081/")
        elif re.fullmatch(r"/[A-Za-z0-9][A-Za-z0-9._-]*\.md", parsed.path):
            # The docs root is static design material, never a runtime state root.
            doc = ROOT / "docs" / parsed.path[1:]
            if doc.is_file() and not doc.is_symlink():
                self.respond(200, doc.read_bytes(), content_type="text/plain; charset=utf-8")
            else:
                self.respond(404)
        else:
            self.respond(404)

    def do_HEAD(self) -> None:
        self.do_GET()

    def do_POST(self) -> None:
        self.respond(405)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=17867)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535 or args.port == NATIVE_PORT:
        parser.error("Choose a non-privileged port different from 3081")
    cache = Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache")))
    home = cache / "unitqc-company-agent" / "dsh-demo-home"
    if not (home / "profiles" / "company-agent-minimal").is_dir():
        parser.error("Run bootstrap_dsh.sh with COMPANY_AGENT_DSH_HOME pointing to dsh-demo-home first")
    def interrupt(_signum: int, _frame: object) -> None:
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, interrupt)
    runtime, launch_url = start_runtime(home)
    server = None
    try:
        register_demo_workspace(launch_url, cache / "unitqc-company-agent" / "demo-workspace")
        server = DemoServer(args.port, launch_url)
        print("Native DSH ready. Local-only demo; no inherited model or science credentials.", flush=True)
        print(f"Open: http://{server.authority}/start/{server.bootstrap}", flush=True)
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        if server is not None:
            server.server_close()
        stop_runtime(runtime)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
