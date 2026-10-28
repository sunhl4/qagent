"""Development access gateway lifecycle around DSH, the only Agent runtime.

Opt-in via COMPANY_AGENT_MANAGED_ACCESS=1. Credentials stay in the host and are
never passed as arguments. Each gateway binds an ephemeral loopback port and
requires a fresh shared bearer token. Existing explicit provider URLs win.
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import signal
import subprocess
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

from company_agent.gateway import handler


def access_environment(environment: dict[str, str]) -> dict[str, str]:
    env = dict(environment)
    if env.get("COMPANY_AGENT_DEPLOYMENT_MODE") != "development":
        raise ValueError("managed local access is development-only")
    config = Path(env.get("UQC_WORKSPACE_CONFIG", str(Path.home() / ".config/unitqc/workspace.json")))
    saved = {}
    if config.is_file():
        if config.is_symlink() or config.stat().st_size > 32_000:
            raise ValueError("invalid workspace access configuration")
        saved = json.loads(config.read_text())
        if not isinstance(saved, dict):
            raise ValueError("invalid workspace access configuration")
    for field, name in {"hpcUser": "HPC_USER", "hpcHost": "HPC_HOST",
                        "cloudKey": "UQC_CLOUD_API_KEY", "cloudApi": "UQC_CLOUD_API_BASE_URL"}.items():
        if saved.get(field):
            if not isinstance(saved[field], str):
                raise ValueError("invalid workspace access configuration")
            env[name] = saved[field]
    for name in ("USER", "HOST"):
        env.setdefault(f"COMPANY_AGENT_HPC_{name}", env.get(f"HPC_{name}", ""))
    return env


def start_gateways(env: dict[str, str]):
    from company_agent import cloud, hpc_ssh

    servers = []
    callbacks = [
        ("HPC", lambda body, auth, workspace: hpc_ssh.handle_request(body, auth, workspace),
         bool(env.get("COMPANY_AGENT_HPC_USER") and env.get("COMPANY_AGENT_HPC_HOST"))),
        ("CLOUD", cloud.handle_request,
         bool(env.get("UQC_CLOUD_API_KEY") and env.get("UQC_CLOUD_API_BASE_URL")
              and env.get("UQC_CLOUD_PROBE_PYTHON"))),
    ]
    try:
        for kind, callback, available in callbacks:
            url_name = f"COMPANY_AGENT_{kind}_INVOKE_URL"
            if env.get(url_name) or not available:
                continue
            token_name = f"COMPANY_AGENT_{kind}_TOKEN"
            env[token_name] = secrets.token_urlsafe(32)
            server = ThreadingHTTPServer(("127.0.0.1", 0), handler(callback))
            server.daemon_threads = True
            env[url_name] = f"http://127.0.0.1:{server.server_port}/invoke"
            os.environ.update(env)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            servers.append((server, thread))
        return servers
    except BaseException:
        stop_gateways(servers)
        raise


def stop_gateways(servers):
    for server, thread in servers:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = args.command
    if command[:1] == ["--"]:
        command = command[1:]
    if not command or not Path(command[0]).is_absolute():
        parser.error("expected absolute DSH executable")
    env = access_environment(dict(os.environ))
    os.environ.update(env)
    servers = start_gateways(env)
    process = None

    def forward(signum, _frame):
        if process is not None and process.poll() is None:
            process.send_signal(signum)

    signal.signal(signal.SIGTERM, forward)
    signal.signal(signal.SIGINT, forward)
    try:
        process = subprocess.Popen(command, env=env)
        return process.wait()
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        stop_gateways(servers)


if __name__ == "__main__":
    raise SystemExit(main())
