"""Authenticated UQC cloud SDK gateway; only simulators can accept submissions."""
from __future__ import annotations

import hashlib
import os
import re
import stat
import subprocess
import tempfile
import urllib.parse
from pathlib import Path

from company_agent.catalog import load_tools
from company_agent.gateway import dispatch
from company_agent.jsonutil import loads
from company_agent.schema import validate_json_schema
from company_agent.workspace_files import WorkspaceFileError, open_file, resolve as resolve_workspace

PROVIDER_ID = "uqc-cloud"
TOOLS = {"cloud.devices": "quantum_cloud_devices", "cloud.submit": "quantum_cloud_submit",
         "cloud.status": "quantum_cloud_status", "cloud.result": "quantum_cloud_result"}


def read_program(path: str, workspace: str) -> str:
    """Read a bounded regular QASM artifact through the shared workspace fence."""
    root = Path(workspace)
    if not workspace or not root.is_absolute() or root.is_symlink() or not root.is_dir():
        raise ValueError("workspace unavailable")
    try:
        root = root.resolve(strict=True)
        relative = path
        candidate = Path(path)
        if candidate.is_absolute():
            relative = candidate.relative_to(root).as_posix()
        if not relative or Path(relative).suffix.lower() not in {".qasm", ".qasm3"}:
            raise ValueError("expected program artifact")
        resolved = resolve_workspace(root, relative)
        if resolved.suffix.lower() not in {".qasm", ".qasm3"}:
            raise ValueError("expected program artifact")
        with open_file(root, relative) as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_size > 64_000:
                raise ValueError("program size")
            body = stream.read(64_001)
            after = os.fstat(stream.fileno())
            identity = lambda value: (value.st_dev, value.st_ino, value.st_size,
                                      value.st_mtime_ns, value.st_ctime_ns)
            if identity(before) != identity(after) or len(body) > 64_000:
                raise ValueError("program changed")
    except (WorkspaceFileError, ValueError, OSError) as exc:
        if isinstance(exc, ValueError) and str(exc) in {"program size", "program changed", "expected program artifact"}:
            raise
        raise ValueError("program unavailable") from exc
    text = body.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    if not text.lstrip().startswith(("OPENQASM 3.0;", "OPENQASM 3;")):
        raise ValueError("unsupported program")
    # Only the standard gate include may be consumed by the remote parser.
    import re

    includes = re.findall(r"\binclude\s+([^;]+);", text)
    if any(value.strip() not in {'"stdgates.inc"', '"qelib1.inc"'} for value in includes):
        raise ValueError("external program include")
    return text


def probe_process(script: Path) -> tuple[list[str], dict[str, str]]:
    """Build the cloud SDK interpreter command.

    The stored interpreter may be a Linux absolute path. On Windows that path
    runs through the Ubuntu WSL distro instead of being treated as missing.
    """
    python = os.environ.get("UQC_CLOUD_PROBE_PYTHON", "")
    posix = os.name == "nt" and python.startswith("/") and not python.startswith("//")
    if not python or not (posix or Path(python).is_absolute()):
        raise ValueError("cloud SDK interpreter unavailable")
    inherited = {name: os.environ[name] for name in ("HOME", "PATH", "LANG", "SSL_CERT_FILE", "SYSTEMROOT", "SystemRoot", "WINDIR")
                 if name in os.environ}
    if posix:
        distro = os.environ.get("COMPANY_AGENT_WSL_DISTRO", "Ubuntu").strip() or "Ubuntu"
        if not re.fullmatch(r"[A-Za-z0-9._-]{1,64}", distro):
            raise ValueError("cloud SDK interpreter unavailable")
        root = os.environ.get("SystemRoot") or os.environ.get("SYSTEMROOT") or r"C:\Windows"
        wsl = Path(root) / "System32" / "wsl.exe"
        if not wsl.is_file():
            raise ValueError("cloud SDK interpreter unavailable")
        script_text = str(script.resolve())
        if len(script_text) < 3 or script_text[1] != ":":
            raise ValueError("cloud SDK interpreter unavailable")
        # Copy through the distro itself. A Windows write to \\wsl$ is not the
        # byte stream that distro's Python reads back.
        destination = "/tmp/company-agent-cloud-worker.py"
        try:
            subprocess.run(
                [str(wsl), "-d", distro, "--", "dd", f"of={destination}", "status=none"],
                input=script.read_bytes(),
                check=True,
            )
        except (OSError, subprocess.CalledProcessError) as exc:
            raise ValueError("cloud SDK interpreter unavailable") from exc
        inherited["WSLENV"] = "UQC_CLOUD_API_KEY:UQC_CLOUD_HOST:UQC_CLOUD_PORT"
        return [str(wsl), "-d", distro, "--", python, "-I", destination], inherited
    if not os.access(python, os.X_OK):
        raise ValueError("cloud SDK interpreter unavailable")
    return [python, "-I", str(script)], inherited


def worker(operation: str, payload: dict) -> dict:
    import json

    command, env = probe_process(Path(__file__).with_name("cloud_worker.py"))
    endpoint = urllib.parse.urlsplit(os.environ.get("UQC_CLOUD_API_BASE_URL", ""))
    if (endpoint.scheme not in {"http", "https"} or not endpoint.hostname
        or endpoint.scheme != "http"
        or endpoint.path not in {"", "/"}
        or endpoint.username or endpoint.password or endpoint.query or endpoint.fragment):
        raise ValueError("cloud endpoint unavailable")
    key = os.environ.get("UQC_CLOUD_API_KEY", "").strip()
    if not key:
        raise ValueError("cloud authentication unavailable")
    env.update({"UQC_CLOUD_API_KEY": key, "UQC_CLOUD_HOST": endpoint.hostname,
                "UQC_CLOUD_PORT": str(endpoint.port or (443 if endpoint.scheme == "https" else 8003))})
    with tempfile.TemporaryDirectory(prefix="company-cloud-worker-") as temporary:
        operation_timeout = 95 if operation == "cloud.submit" else 27
        completed = subprocess.run(
            command,
            input=json.dumps({"operation": operation, "payload": payload}),
            text=True, capture_output=True, timeout=operation_timeout, check=False, env=env,
            cwd=None if command[0].lower().endswith("wsl.exe") else temporary)
    value = loads(completed.stdout)
    if (completed.returncode != 0 or not isinstance(value, dict)
        or set(value) != {"ok", "result"} or value["ok"] is not True
        or not isinstance(value["result"], dict)):
        raise ValueError("cloud SDK operation failed")
    return value["result"]


def operation_result(operation: str, payload: dict, workspace: str = "") -> dict:
    tool = TOOLS[operation]
    row = load_tools()[tool]
    validate_json_schema(payload, row["parameters"], path="arguments")
    actual = dict(payload)
    if operation == "cloud.submit":
        if actual["shots"] % 100:
            raise ValueError("shots must be a multiple of 100")
        program = read_program(actual.pop("program_path"), workspace)
        actual["program"] = program
        program_sha256 = hashlib.sha256(program.encode("utf-8")).hexdigest()
    result = worker(operation, actual)
    if operation == "cloud.submit":
        result["program_sha256"] = program_sha256
    if operation == "cloud.result":
        from company_agent.cloud_results import limit_of, store_table
        summary = result.get("summary") if isinstance(result.get("summary"), dict) else {}
        metrics = summary.get("metrics") if isinstance(summary.get("metrics"), dict) else {}
        items = list(metrics.get("items") or [])
        shots = summary.get("shots")
        shot_count = shots if isinstance(shots, int) and not isinstance(shots, bool) else 0
        page_limit = limit_of(actual.get("limit"))
        task = str(result.get("cloud_task") or "")
        summary["artifact_path"] = store_table(workspace, task, shot_count, items)
        if workspace and not summary["artifact_path"]:
            raise ValueError("result artifact unavailable")
        summary["omitted_states"] = max(0, len(items) - page_limit)
        metrics["items"] = items[:page_limit]
        summary["metrics"] = metrics
        result["summary"] = summary
    validate_json_schema(result, row["output"], path="result")
    return result


def handle_request(body: bytes, authorization: str | None, workspace: str = ""):
    import base64

    try:
        workspace = base64.b64decode(workspace, altchars=b"-_", validate=True).decode("utf-8")
    except (ValueError, UnicodeError):
        workspace = ""
    return dispatch(body, authorization, provider=PROVIDER_ID, token_env="COMPANY_AGENT_CLOUD_TOKEN",
                    operations=set(TOOLS), execute=operation_result, workspace=workspace)
