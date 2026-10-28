#!/usr/bin/env python3
"""Verify Company Agent DSH profiles in isolated homes.

The verifier first checks each expanded configuration, then starts it and
creates a real session through the authenticated Web API. It reports one of
four stable outcomes: ok, config_error, plugin_error, or credential_error.
No model call is made.
"""

from __future__ import annotations

import argparse
import contextlib
import http.cookiejar
import json
import math
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from verify_skills import _mounts_for  # noqa: E402

from company_agent.catalog import load_skills  # noqa: E402

PROFILES = ("company-agent", "company-agent-minimal")
PROFILE_PRESETS = {"company-agent": "lab", "company-agent-minimal": "boot"}
PROFILE_MATRIX = {"company-agent": ("boot", "lab", "algo", "sign"),
                  "company-agent-minimal": ("boot", "algo")}


def selected_preset(home: Path, profile: str) -> str:
    path = home / "verification-preset"
    return path.read_text().strip() if path.is_file() else PROFILE_PRESETS[profile]


VERIFY_PROBE = "verify-session-probe.mjs"
VERIFY_PATCH = "verify-session-probe.patch.yml"
VERIFY_REPORT = "verify-session-report.json"
REQUIRED = {
    "company-agent": (
        "company-agent-policy",
        "company-agent-core",
        "company-agent-quantum",
        "company-agent-device",
        "subagent-codex",
        "permissionMode: never",
        "inheritsParentContext: false",
        "company-local",
        "deepseek-chat",
        "readMaxBytes: 51200",
        "fetch: false",
    ),
    "company-agent-minimal": (
        "company-agent-policy",
        "company-agent-core",
        "company-agent-quantum",
    ),
}
FORBIDDEN = {
    "company-agent": (
        "tool-subagent-codex",
        "toolName: subagent_codex",
        "provider: codex",
        "presets/standard",
        "presets/cordis",
        "presets/ptc",
        "presets/minimal",
    ),
    "company-agent-minimal": (
        "company-agent-device",
        "subagent-codex",
        "permissionMode: never",
        "inheritsParentContext: false",
        "company-local",
        "presets/standard",
        "presets/cordis",
        "presets/ptc",
        "presets/minimal",
    ),
}
PLUGIN_PATTERNS = (
    "plugin tree failed to load",
    "plugin(s) failed to load",
    "entry did not activate",
    "entries did not activate",
    "fatal load failure",
    "cannot resolve profile bundle",
    "could not be resolved",
    "agent-preset/invalid",
    "failed to mount",
    "composition must be a top-level list",
    "ERR_MODULE_NOT_FOUND",
    "ERR_UNKNOWN_FILE_EXTENSION",
    "ERR_UNSUPPORTED_NODE_MODULES_TYPE_STRIPPING",
)
CREDENTIAL_PATTERNS = (
    "credential",
    "api key",
    "api_key",
    "authentication",
    "unauthorized",
    "model route could not be resolved",
    "no model",
)
WEB_URL_PATTERN = re.compile(r"http://127\.0\.0\.1:\d+/\?token=[A-Za-z0-9_-]{16,512}")
SESSION_CREATE_METHOD = "session/create"


def _strict_object(pairs: list[tuple[str, object]], context: str) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"{context} has duplicate field {key!r}")
        result[key] = value
    return result


@dataclass(frozen=True)
class CheckResult:
    profile: str
    category: str
    detail: str


def runtime_paths() -> tuple[Path, Path]:
    runtime = Path(
        os.environ.get(
            "COMPANY_AGENT_RUNTIME_DIR",
            Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
            / "unitqc-company-agent"
            / "dsh-runtime",
        )
    ).expanduser()
    node = Path(os.environ.get("COMPANY_AGENT_NODE", runtime / "node_modules/node/bin/node"))
    entry = Path(
        os.environ.get(
            "COMPANY_AGENT_DSH_ENTRY",
            runtime / "node_modules/@deepseek-ai/dsh/lib/bin.js",
        )
    )
    if not node.is_absolute() or not entry.is_absolute():
        raise RuntimeError("DSH runtime paths must be absolute")
    return node.resolve(), entry.resolve()


def available_port() -> int:
    try:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            return int(sock.getsockname()[1])
    except OSError as exc:
        raise RuntimeError("no loopback verification port is available") from exc


def _copy_managed_profile_packages(profile_root: Path, destination: Path) -> None:
    """Materialize repository-owned packages without pnpm links."""
    try:
        manifest = json.loads((profile_root / "package.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("profile package manifest is unavailable") from exc
    pending = [
        str(name) for name in (manifest.get("dependencies") or {})
        if isinstance(name, str) and name.startswith("@unitqc/")
    ]
    seen: set[str] = set()
    while pending:
        name = pending.pop(0)
        if name in seen:
            continue
        seen.add(name)
        if "/" not in name:
            raise RuntimeError("profile package name is invalid")
        package_source = ROOT / "packages" / name.split("/", 1)[1]
        package_target = destination / "node_modules" / name.split("/", 1)[0] / name.split("/", 1)[1]
        if not package_source.is_dir():
            raise RuntimeError("managed profile package is unavailable")
        shutil.copytree(
            package_source,
            package_target,
            symlinks=False,
            ignore=shutil.ignore_patterns("node_modules", "__pycache__"),
        )
        try:
            package_manifest = json.loads(
                (package_source / "package.json").read_text(encoding="utf-8")
            )
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise RuntimeError("managed package manifest is invalid") from exc
        pending.extend(
            str(dependency) for dependency in (package_manifest.get("dependencies") or {})
            if isinstance(dependency, str) and dependency.startswith("@unitqc/")
        )


def profile_home(profile: str, preset: str | None = None) -> tempfile.TemporaryDirectory[str]:
    if profile not in PROFILES:
        raise ValueError(f"unknown profile {profile!r}")
    parent = os.environ.get("COMPANY_AGENT_VERIFY_TMPDIR")
    temporary = tempfile.TemporaryDirectory(prefix=f"{profile}-verify-", dir=parent)
    home = Path(temporary.name)
    preset = preset or PROFILE_PRESETS[profile]
    if preset not in PROFILE_MATRIX[profile]:
        temporary.cleanup()
        raise ValueError("illegal profile/preset combination")
    (home / "verification-preset").write_text(preset)
    profiles = home / "profiles"
    profiles.mkdir()
    presets = home / ".agent-presets"
    shutil.copytree(
        ROOT / "profiles" / profile / "agent-presets" / "company-agent",
        presets / "company-agent",
    )
    skills = home / "skills"
    from verify_skills import sync as sync_skills

    if sync_skills(root=skills, profile=profile, preset=preset) != 0:
        shutil.rmtree(temporary, ignore_errors=True)
        raise RuntimeError("skill registry sync failed for the verification runtime")
    # Materialize repository-owned plugins without copying pnpm junctions.
    # This keeps Node resolution deterministic on Windows and avoids copying
    # installation state from a developer profile into the isolated home.
    shutil.copytree(
        ROOT / "profiles" / profile,
        profiles / profile,
        symlinks=False,
        ignore=shutil.ignore_patterns("node_modules", ".dsh-home"),
    )
    _copy_managed_profile_packages(ROOT / "profiles" / profile, profiles / profile)
    if profile == "company-agent-minimal":
        shutil.rmtree(
            profiles / profile / "node_modules" / "@unitqc" / "company-agent-device",
            ignore_errors=True,
        )
    return temporary


def dsh_command(node: Path, entry: Path, profile: str, *args: str) -> list[str]:
    return [
        str(node),
        str(ROOT / "scripts/dsh-cli.mjs"),
        "--profile",
        profile,
        *args,
    ]


def base_environment(home: Path, entry: Path, profile: str) -> dict[str, str]:
    if profile not in PROFILES:
        raise ValueError(f"unknown profile {profile!r}")
    env = os.environ.copy()
    for name in (
        "COMPANY_AGENT_APPROVAL_CONTEXT",
        "COMPANY_AGENT_ENABLE_CONFIGURED_KNOWLEDGE",
        "COMPANY_AGENT_KNOWLEDGE_PATH",
        "COMPANY_AGENT_DEMO_UI",
    ):
        env.pop(name, None)
    # Verification must be independent of the developer's provider/model secrets.
    for name in (
        "COMPANY_QUANTUM_PLATFORM_INVOKE_URL", "COMPANY_QUANTUM_PLATFORM_TOKEN",
        "COMPANY_AGENT_SIMULATOR_INVOKE_URL", "COMPANY_AGENT_SIMULATOR_TOKEN",
        "COMPANY_AGENT_COMPILER_INVOKE_URL", "COMPANY_AGENT_COMPILER_TOKEN",
        "COMPANY_AGENT_DEVICE_INVOKE_URL", "COMPANY_AGENT_DEVICE_TOKEN", "DEEPSEEK_API_KEY",
        "COMPANY_AGENT_HPC_INVOKE_URL", "COMPANY_AGENT_HPC_TOKEN",
        "COMPANY_AGENT_HPC_USER", "COMPANY_AGENT_HPC_HOST", "COMPANY_AGENT_MANAGED_ACCESS",
        "COMPANY_AGENT_CLOUD_INVOKE_URL", "COMPANY_AGENT_CLOUD_TOKEN",
        "COMPANY_AGENT_TOOL_WORKSPACE", "UQC_CLOUD_API_KEY", "UQC_CLOUD_PROBE_PYTHON",
        "COMPANY_RELAY_API_KEY",
    ):
        env.pop(name, None)
    env.update(
        {
            "DSH_HOME": str(home),
            "DSH_TELEMETRY_MODE": "DISABLED",
            "COMPANY_AGENT_DSH_ENTRY": str(entry),
            "COMPANY_AGENT_PYTHON": sys.executable,
            "COMPANY_AGENT_PYTHONPATH": str(ROOT / "src"),
            "COMPANY_AGENT_CONTRACTS_DIR": str(ROOT / "contracts"),
            "COMPANY_AGENT_PRESET_ROOT": str(home / ".agent-presets"),
            "COMPANY_AGENT_SKILL_ROOT": str(home / "skills"),
            "COMPANY_AGENT_PRESET": selected_preset(home, profile),
            "COMPANY_AGENT_PROFILE": profile,
        }
    )
    return env


def compact_detail(output: str) -> str:
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    for marker in (*PLUGIN_PATTERNS, *CREDENTIAL_PATTERNS):
        for line in lines:
            if marker.casefold() in line.casefold():
                return re.sub(r"\s+", " ", line)[:240]
    return re.sub(r"\s+", " ", lines[-1])[:240] if lines else "process exited without diagnostics"


def classify_failure(output: str) -> str:
    folded = output.casefold()
    if any(pattern.casefold() in folded for pattern in PLUGIN_PATTERNS):
        return "plugin_error"
    if any(pattern.casefold() in folded for pattern in CREDENTIAL_PATTERNS):
        return "credential_error"
    return "startup_error"


def check_config(node: Path, entry: Path, profile: str, home: Path) -> CheckResult | None:
    write_session_probe(home, profile)
    try:
        result = subprocess.run(
            dsh_command(node, entry, profile, "--dump-config"),
            cwd=ROOT,
            env=base_environment(home, entry, profile),
            text=True,
            capture_output=True,
            timeout=60,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return CheckResult(profile, "config_error", "configuration expansion timed out")
    output = result.stdout + result.stderr
    if result.returncode != 0:
        return CheckResult(profile, "config_error", compact_detail(output))
    missing = [value for value in REQUIRED[profile] if value not in result.stdout]
    leaked = [value for value in FORBIDDEN[profile] if value in result.stdout]
    if missing or leaked:
        detail = "; ".join(
            part
            for part in (
                f"missing: {', '.join(missing)}" if missing else "",
                f"forbidden: {', '.join(leaked)}" if leaked else "",
            )
            if part
        )
        return CheckResult(profile, "config_error", detail)
    return None


def write_session_probe(home: Path, profile: str) -> None:
    if profile not in PROFILES:
        raise ValueError(f"unknown profile {profile!r}")
    sys.path.insert(0, str(ROOT / "src"))
    from company_agent.catalog import builtin_tools_for_preset, load_tools_for_preset

    preset = selected_preset(home, profile)
    builtins = tuple(builtin_tools_for_preset(preset)) if profile == "company-agent" else ()
    expected = [*load_tools_for_preset(preset), *builtins, "skill"]
    source = """import { writeFileSync } from \"node:fs\";

export const name = \"company-agent-verify-session-probe\";
export const inject = [\"tools\", \"agentPresets\"];

export function apply(ctx, config) {
  const expected = [...config.expected].sort();
  const output = config.output;
  ctx.on(\"agent/created\", ({ agent }) => {
    if (!agent?.id || !agent.session || !agent.ctx) {
      throw new Error("session probe did not receive a live agent");
    }
    const actual = ctx.tools.schemas(agent).map((row) => row.name).sort();
    const extra = actual.filter((name) => !expected.includes(name));
    const missing = expected.filter((name) => !actual.includes(name));
    writeFileSync(
      output,
      JSON.stringify({ actual, expected, extra, missing }),
      { encoding: \"utf8\", mode: 0o600 },
    );
    void (async () => {
      const roster = await ctx.agentPresets.list();
      let copyError = null;
      let switchError = null;
      try { await ctx.agentPresets.copy('company-agent', 'unmanaged-fixture'); }
      catch (error) { copyError = error?.code ?? 'unexpected_error'; }
      try { await ctx.agentPresets.select(agent, 'standard'); }
      catch (error) { switchError = error?.code ?? 'unexpected_error'; }
      writeFileSync(output + '.presets', JSON.stringify({
        roster: roster.map(row => ({id: row.id, trust: row.trust})),
        authorable: ctx.agentPresets.authorable, copyError, switchError,
        selected: ctx.agentPresets.composedPreset(agent.ctx),
        toolsUnchanged: JSON.stringify(actual) === JSON.stringify(
          ctx.tools.schemas(agent).map(row => row.name).sort()),
      }), {encoding: 'utf8', mode: 0o600});
    })().catch(() => {});
  }, { global: true });
}
"""
    (home / VERIFY_PROBE).write_text(source, encoding="utf-8")
    expected_json = json.dumps(expected, ensure_ascii=False)
    patch = (
        "- insert:\n"
        "    - id: company-agent-verify-session-probe\n"
        f"      name: {home / VERIFY_PROBE}\n"
        "      config:\n"
        f"        output: {home / VERIFY_REPORT}\n"
        f"        expected: {expected_json}\n"
    )
    (home / VERIFY_PATCH).write_text(patch, encoding="utf-8")


def check_tool_report(home: Path) -> None:
    path = home / VERIFY_REPORT
    try:
        payload = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=lambda pairs: _strict_object(pairs, "session tool catalog report"),
            parse_constant=lambda value: (_ for _ in ()).throw(
                ValueError(f"non-finite JSON number {value!r}")
            ),
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise RuntimeError("session tool catalog probe produced no valid report") from exc
    if not isinstance(payload, dict) or set(payload) != {"actual", "expected", "extra", "missing"}:
        raise RuntimeError("session tool catalog probe returned an invalid report shape")
    actual = payload.get("actual")
    expected = payload.get("expected")
    extra = payload.get("extra") if isinstance(payload, dict) else None
    missing = payload.get("missing") if isinstance(payload, dict) else None
    if not all(isinstance(value, list) for value in (actual, expected, extra, missing)):
        raise RuntimeError("session tool catalog probe returned an invalid report shape")
    if len(actual) != len(set(actual)):
        raise RuntimeError("session tool catalog probe returned duplicate tools")
    if any(not isinstance(name, str) or not name for name in (*actual, *expected, *extra, *missing)):
        raise RuntimeError("session tool catalog probe returned invalid tool names")
    if extra != [] or missing != [] or actual != expected:
        raise RuntimeError(
            "session tool catalog mismatch: "
            f"extra {extra}, missing {missing}; actual {actual}, expected {expected}"
        )


def check_preset_report(home: Path) -> None:
    expected = {
        "roster": [{"id": "company-agent", "trust": "system"}],
        "authorable": False,
        "copyError": "agent-preset/read-only",
        "switchError": "agent-preset/not-found",
        "selected": "company-agent",
        "toolsUnchanged": True,
    }
    try:
        report = json.loads(
            (home / (VERIFY_REPORT + ".presets")).read_text(encoding="utf-8"),
            object_pairs_hook=lambda pairs: _strict_object(pairs, "preset containment report"),
        )
    except (OSError, ValueError) as exc:
        raise RuntimeError("preset containment probe produced no valid report") from exc
    if json.dumps(report, sort_keys=True) != json.dumps(expected, sort_keys=True):
        raise RuntimeError("preset containment behavior did not pass")


def _rpc_request(opener: urllib.request.OpenerDirector, base_url: str, method: str, args: dict) -> dict:
    if not re.fullmatch(r"http://127\.0\.0\.1:[0-9]+", base_url):
        raise RuntimeError("DSH RPC base URL must be loopback HTTP")
    rpc_id = f"verify-{uuid.uuid4().hex}"
    try:
        raw = json.dumps(
            {
                "type": "client-request",
                "rpcId": rpc_id,
                "method": method,
                "payload": {"args": args},
            },
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise RuntimeError("DSH RPC request is not valid JSON") from exc
    body = raw.encode("utf-8")
    if len(body) > 1_000_000:
        raise RuntimeError("DSH RPC request exceeds maximum size")
    if method not in {SESSION_CREATE_METHOD, "skills/list", "session/modelCatalog"}:
        raise RuntimeError("DSH RPC method is not allowed")
    request = urllib.request.Request(
        f"{base_url}/api/{method}",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with opener.open(request, timeout=5) as response:
        status = getattr(response, "status", None)
        if status is not None and status != 200:
            raise RuntimeError("DSH RPC returned unexpected HTTP status")
        content_type = str(response.headers.get("Content-Type") or "").split(";", 1)[0].strip().casefold()
        if content_type and content_type != "application/json":
            raise RuntimeError("DSH RPC returned a non-JSON content type")
        content_length = response.headers.get("Content-Length")
        if content_length is not None:
            try:
                declared = int(content_length)
            except ValueError as exc:
                raise RuntimeError("DSH RPC response has invalid Content-Length") from exc
            if declared < 0 or declared > 1_000_000:
                raise RuntimeError("DSH RPC response exceeds maximum size")
        raw = response.read(1_000_001)
    if len(raw) > 1_000_000:
        raise RuntimeError("DSH RPC response exceeds maximum size")
    try:
        text = raw.decode("utf-8")
        payload = json.loads(
            text,
            object_pairs_hook=lambda pairs: _strict_object(pairs, "DSH RPC response"),
            parse_constant=lambda value: (_ for _ in ()).throw(
                ValueError(f"non-finite JSON number {value!r}")
            ),
        )
    except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise RuntimeError("DSH returned invalid JSON") from exc
    if not isinstance(payload, dict) or payload.get("type") != "server-response":
        raise RuntimeError("DSH returned an invalid RPC response")
    if set(payload) != {"type", "rpcId", "result"}:
        raise RuntimeError("DSH returned unknown RPC response fields")
    if payload.get("rpcId") != rpc_id:
        raise RuntimeError("DSH returned an RPC correlation mismatch")
    result = payload.get("result")
    if not isinstance(result, dict):
        raise RuntimeError("DSH returned an invalid RPC result")
    return result


def check_model_catalog(result: dict, profile: str) -> None:
    """Check the same live catalog the native picker reads, without model calls."""
    value = result.get("value")
    if result.get("ok") is not True or not isinstance(value, dict):
        raise RuntimeError("native model catalog could not be read")
    groups = value.get("groups")
    providers = value.get("routableProviders")
    failures = value.get("failures")
    if not isinstance(groups, list) or not isinstance(providers, list) or not isinstance(failures, list):
        raise RuntimeError("native model catalog has an invalid shape")
    expected = {"deepseek-official"}
    if profile == "company-agent":
        expected.update(("company-local", "company-relay"))
    elif profile != "company-agent-minimal":
        raise ValueError("unknown profile")
    advertised = {}
    for group in groups:
        if not isinstance(group, dict) or not isinstance(group.get("id"), str):
            raise RuntimeError("native model catalog has an invalid provider")
        models = group.get("models")
        if not isinstance(models, list) or any(
            not isinstance(model, dict) or not isinstance(model.get("id"), str) or not model["id"]
            for model in models
        ):
            raise RuntimeError("native model catalog has invalid model rows")
        if group["id"] in advertised:
            raise RuntimeError("native model catalog has duplicate providers")
        advertised[group["id"]] = {model["id"] for model in models}
    if not expected.issubset(advertised) or not expected.issubset(providers):
        raise RuntimeError("native model catalog is missing a managed provider")
    if any(not advertised[provider] for provider in expected):
        raise RuntimeError("native model catalog has an empty managed provider")
    if any(not isinstance(row, dict) or row.get("id") in expected for row in failures):
        raise RuntimeError("native model catalog reports a managed provider failure")
    if profile == "company-agent" and "deepseek-chat" not in advertised["company-local"]:
        raise RuntimeError("native model catalog is missing the managed default model")
    if profile == "company-agent-minimal" and {"company-local", "company-relay"}.intersection(advertised):
        raise RuntimeError("minimal model catalog includes a full-profile provider")


def check_session(port: int, launch_url: str, profile: str, home: Path) -> str:
    parsed_launch = urllib.parse.urlsplit(launch_url)
    valid_launch = (
        parsed_launch.scheme == "http"
        and parsed_launch.hostname == "127.0.0.1"
        and parsed_launch.port == port
        and parsed_launch.query.startswith("token=")
        and "&" not in parsed_launch.query
        and bool(parsed_launch.query.removeprefix("token="))
    )
    if not valid_launch:
        raise RuntimeError("DSH launch URL is invalid")
    token = parsed_launch.query.removeprefix("token=")
    if not re.fullmatch(r"[A-Za-z0-9_-]{16,512}", token):
        raise RuntimeError("DSH launch token is invalid")
    cookies = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}), urllib.request.HTTPCookieProcessor(cookies)
    )
    with opener.open(launch_url, timeout=5):
        pass
    result = _rpc_request(
        opener,
        f"http://127.0.0.1:{port}",
        SESSION_CREATE_METHOD,
        {"request": {"cwd": str(ROOT), "agentPreset": "company-agent"}},
    )
    if set(result) - {"ok", "value", "error"}:
        raise RuntimeError("session creation returned unknown result fields")
    if result.get("ok") is not True:
        error = result.get("error")
        if isinstance(error, dict):
            code = str(error.get("code") or "gateway/internal")
            message = str(error.get("message") or "session creation failed")
            raise RuntimeError(f"{code}: {message}")
        raise RuntimeError("session creation failed")
    value = result.get("value")
    if not isinstance(value, dict) or value.get("agentPreset") != "company-agent":
        raise RuntimeError("session did not assemble the company-agent preset")
    if set(value) - {"sessionId", "agentPreset"}:
        raise RuntimeError("session creation returned unknown value fields")
    session_id = value.get("sessionId")
    if not isinstance(session_id, str) or not session_id or len(session_id) > 256:
        raise RuntimeError("session creation returned no valid session id")
    if not re.fullmatch(r"session-[0-9a-f-]+", session_id):
        raise RuntimeError("session creation returned an invalid session id format")
    check_tool_report(home)
    check_model_catalog(
        _rpc_request(opener, f"http://127.0.0.1:{port}", "session/modelCatalog", {}),
        profile,
    )
    skill_result = _rpc_request(
        opener,
        f"http://127.0.0.1:{port}",
        "skills/list",
        {"request": {"sessionId": session_id}},
    )
    if set(skill_result) - {"ok", "value", "error"}:
        raise RuntimeError("session skill catalog returned unknown result fields")
    if skill_result.get("ok") is not True:
        error = skill_result.get("error")
        if isinstance(error, dict):
            code = str(error.get("code") or "gateway/internal")
            message = str(error.get("message") or "session skill catalog failed")
            raise RuntimeError(f"{code}: {message}")
        raise RuntimeError("session skill catalog failed")
    skill_value = skill_result.get("value")
    if not isinstance(skill_value, dict) or set(skill_value) != {"skills"}:
        raise RuntimeError("session skill catalog returned an invalid value")
    rows = skill_value.get("skills")
    if not isinstance(rows, list):
        raise RuntimeError("session skill catalog returned an invalid skills list")
    if any(not isinstance(row, dict) or not isinstance(row.get("name"), str) for row in rows):
        raise RuntimeError("session skill catalog returned an invalid skill entry")
    names_list = [str(row["name"]) for row in rows]
    if any(not name or len(name) > 128 for name in names_list):
        raise RuntimeError("session skill catalog returned an invalid skill name")
    if len(names_list) != len(set(names_list)):
        raise RuntimeError("session skill catalog returned duplicate skills")
    names = set(names_list)
    # Registry-driven expectation: the mounted skill set equals the admitted,
    # non-revoked entries whose (profile, preset) when-clause matches.

    registry_skills = load_skills()
    expected_skills = {
        name
        for name, entry in registry_skills.items()
        if not entry["revoked"] and _mounts_for(entry, profile, selected_preset(home, profile))
    }
    if names != expected_skills:
        raise RuntimeError(
            f"session skill catalog mismatch: expected {sorted(expected_skills)}, got {sorted(names)}"
        )
    return session_id


def wait_for_session(
    process: subprocess.Popen[str],
    port: int,
    launch_url: str,
    profile: str,
    home: Path,
    deadline: float,
) -> tuple[str | None, str | None]:
    session_error: str | None = None
    while time.monotonic() < deadline:
        try:
            return check_session(port, launch_url, profile, home), None
        except urllib.error.HTTPError as exc:
            return None, str(exc)
        except (OSError, urllib.error.URLError) as exc:
            session_error = str(exc)
            if process.poll() is not None:
                break
            time.sleep(0.1)
        except (RuntimeError, ValueError) as exc:
            return None, str(exc)
    return None, session_error


def check_startup(
    node: Path,
    entry: Path,
    profile: str,
    home: Path,
    startup_seconds: float,
) -> CheckResult:
    try:
        port = available_port()
    except RuntimeError as exc:
        return CheckResult(profile, "startup_error", str(exc))
    try:
        process = subprocess.Popen(
            dsh_command(
                node,
                entry,
                profile,
                "--patch",
                str(home / VERIFY_PATCH),
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--no-open",
            ),
            cwd=ROOT,
            env=base_environment(home, entry, profile),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
    except OSError as exc:
        return CheckResult(profile, "startup_error", f"runtime could not start: {type(exc).__name__}")
    output_parts: list[str] = []
    output_lock = threading.Lock()
    launch_url: str | None = None
    launch_url_ready = threading.Event()

    def collect_output() -> None:
        nonlocal launch_url
        assert process.stdout is not None
        for line in process.stdout:
            with output_lock:
                output_parts.append(line)
            match = WEB_URL_PATTERN.search(line)
            if match is not None and launch_url is None:
                launch_url = match.group(0)
                launch_url_ready.set()

    reader = threading.Thread(target=collect_output, daemon=True)
    reader.start()
    deadline = time.monotonic() + startup_seconds
    listening = False
    session_id: str | None = None
    session_error: str | None = None
    try:
        while time.monotonic() < deadline:
            if process.poll() is not None:
                break
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                    listening = True
                    break
            except OSError:
                time.sleep(0.1)

        if listening:
            remaining = max(0.0, deadline - time.monotonic())
            launch_url_ready.wait(timeout=remaining)
            if launch_url is None:
                session_error = "authenticated Web URL was not reported before the startup deadline"
            else:
                session_id, session_error = wait_for_session(
                    process,
                    port,
                    launch_url,
                    profile,
                    home,
                    deadline,
                )

        if session_id is not None:
            # Keep observing briefly: DSH may accept the session before all
            # asynchronous plugin diagnostics have been emitted.
            observation_deadline = min(deadline, time.monotonic() + 1.0)
            while process.poll() is None and time.monotonic() < deadline:
                if time.monotonic() >= observation_deadline and (
                    home / (VERIFY_REPORT + ".presets")
                ).is_file():
                    break
                time.sleep(0.1)
    finally:
        if process.poll() is None:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGINT)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)
        reader.join(timeout=5)

    if session_id is not None:
        try:
            check_preset_report(home)
        except RuntimeError as exc:
            return CheckResult(profile, "plugin_error", str(exc))
    with output_lock:
        output = "".join(output_parts)
    abnormal_exit = process.returncode not in {None, 0, -signal.SIGINT, 130}
    if session_id is not None and not abnormal_exit:
        return CheckResult(
            profile,
            "ok",
            f"configuration expanded and session {session_id} assembled on 127.0.0.1:{port}",
        )
    if abnormal_exit:
        return CheckResult(profile, classify_failure(output), compact_detail(output))
    if not listening:
        return CheckResult(profile, "startup_error", "listener did not open before the startup deadline")
    detail = session_error or "session assembly did not complete before the startup deadline"
    return CheckResult(profile, classify_failure(detail), compact_detail(detail))


def verify(
    profile: str, node: Path, entry: Path, startup_seconds: float, preset: str | None = None,
) -> CheckResult:
    with profile_home(profile, preset) as temporary:
        home = Path(temporary)
        config_failure = check_config(node, entry, profile, home)
        if config_failure is not None:
            return config_failure
        return check_startup(node, entry, profile, home, startup_seconds)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=(*PROFILES, "all"), default="all")
    parser.add_argument("--startup-seconds", type=float, default=30.0)
    args = parser.parse_args(argv)
    if not math.isfinite(args.startup_seconds) or args.startup_seconds <= 0 or args.startup_seconds > 300:
        parser.error("--startup-seconds must be greater than 0 and at most 300")

    node, entry = runtime_paths()
    if not node.is_file() or not os.access(node, os.X_OK):
        print(f"runtime_error: pinned Node executable is missing: {node}", file=sys.stderr)
        print("run: bash scripts/bootstrap_dsh.sh", file=sys.stderr)
        return 2
    if not entry.is_file():
        print(f"runtime_error: DSH entry is missing: {entry}", file=sys.stderr)
        print("run: bash scripts/bootstrap_dsh.sh", file=sys.stderr)
        return 2

    selected = PROFILES if args.profile == "all" else (args.profile,)
    results = []
    for profile in selected:
        for preset in PROFILE_MATRIX[profile]:
            result = verify(profile, node, entry, args.startup_seconds, preset)
            results.append(CheckResult(f"{profile}/{preset}", result.category, result.detail))
    for preset in ("lab", "sign"):
        env = os.environ.copy()
        env.update(COMPANY_AGENT_PROFILE="company-agent-minimal", COMPANY_AGENT_PRESET=preset)
        rejected = subprocess.run(["bash", str(ROOT / "scripts/start_runtime.sh")],
                                  env=env, capture_output=True, text=True, timeout=15)
        valid_rejection = rejected.returncode == 2 and "only supports boot or algo" in rejected.stderr
        results.append(CheckResult(f"company-agent-minimal/{preset}",
                                   "ok" if valid_rejection else "config_error",
                                   "illegal combination rejected" if valid_rejection
                                   else "illegal combination was not rejected"))
    model_credential_configured = bool(os.environ.get("DEEPSEEK_API_KEY", "").strip())
    provider_envs = {
        "COMPANY_QUANTUM_PLATFORM_INVOKE_URL": "COMPANY_QUANTUM_PLATFORM_TOKEN",
        "COMPANY_AGENT_SIMULATOR_INVOKE_URL": "COMPANY_AGENT_SIMULATOR_TOKEN",
        "COMPANY_AGENT_COMPILER_INVOKE_URL": "COMPANY_AGENT_COMPILER_TOKEN",
        "COMPANY_AGENT_DEVICE_INVOKE_URL": "COMPANY_AGENT_DEVICE_TOKEN",
    }
    configured_providers = sorted(
        url_env
        for url_env, token_env in provider_envs.items()
        if os.environ.get(url_env, "").strip() and os.environ.get(token_env, "").strip()
    )
    for result in results:
        print(f"{result.profile}: {result.category}: {result.detail}")
    if all(result.category == "ok" for result in results):
        print(
            "verification_scope: configuration, session assembly, tool and skill catalogs, "
            "and managed preset containment, including the native model catalog; no model calls"
        )
        if model_credential_configured:
            print("model_credentials: configured: DEEPSEEK_API_KEY is present")
        else:
            print(
                "model_credentials: environment_missing: model calls were not tested; "
                "configure DEEPSEEK_API_KEY or a provider credential through the DSH Models UI"
            )
        if configured_providers:
            print(f"science_providers: configured: {', '.join(configured_providers)}")
        else:
            print(
                "science_providers: missing: scientific calls were not tested; "
                "configure provider URLs and tokens"
            )
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
