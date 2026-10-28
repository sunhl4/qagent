#!/usr/bin/env python3
"""Record the fixed offline closure gates with exclusive output and stable source identities."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import signal
import stat
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

# Administrative tooling, never imported by the Agent runtime.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from release_manifest import ManifestError, contract_digest, load_json, lock_digest, sha256_file  # noqa: E402
from verify_acceptance import offline_environment  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED = {"node_modules", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
AGENT_INPUTS = (
    "src", "contracts", "packages", "profiles", "skills", "knowledge", "scripts", "tests", "runtime",
    "pyproject.toml", "README.md", "pins.json", "package.json", ".github/workflows/ci.yml",
)
PLATFORM_INPUTS = (
    "src", "tests", "scripts", "tools", "stubs", "deploy", "examples", "pyproject.toml",
    "MANIFEST.in",
)


def timestamp() -> str:
    return datetime.now(UTC).isoformat()


def write_new(path: Path, value: dict) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")


def inventory(root: Path, inputs: tuple[str, ...]) -> dict:
    """Hash enumerated implementation inputs, omitting only installed and generated caches."""
    rows = {}

    def entry(path: Path) -> None:
        info = path.lstat()
        name = path.relative_to(root).as_posix()
        if path.is_symlink():
            raise ValueError("source inventory contains a symlink")
        if not stat.S_ISREG(info.st_mode):
            raise ValueError("source inventory contains a nonregular file")
        rows[name] = {"sha256": sha256_file(path), "size": info.st_size,
                      "mode": f"{stat.S_IMODE(info.st_mode):04o}"}

    def walk_error(error: OSError) -> None:
        raise error

    for relative in inputs:
        path = root / relative
        if path.is_symlink():
            raise ValueError("source inventory contains a symlink")
        if path.is_dir():
            for base, directories, names in os.walk(path, onerror=walk_error, followlinks=False):
                directories[:] = sorted(name for name in directories
                                        if name not in EXCLUDED and not name.endswith(".egg-info"))
                if any((Path(base) / name).is_symlink() for name in directories):
                    raise ValueError("source inventory contains a linked directory")
                for name in sorted(names):
                    if not name.endswith((".pyc", ".pyo")):
                        entry(Path(base) / name)
        else:
            entry(path)
    encoded = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()
    return {"sha256": "sha256:" + hashlib.sha256(encoded).hexdigest(), "files": rows}


def run(name: str, command: list[str], cwd: Path, env: dict, output: Path) -> dict:
    """Execute one bounded offline gate, preserving failures without retries."""
    started = timestamp()
    clock = time.monotonic()
    status = "failed"
    with (output / f"{name}.log").open("x", encoding="utf-8") as log:
        try:
            process = subprocess.Popen(command, cwd=cwd, env=env, stdout=log,
                                       stderr=subprocess.STDOUT, start_new_session=True)
            try:
                code = process.wait(timeout=1200)
                status = "passed" if code == 0 else "failed"
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=10)
                code = 124
                status = "timeout"
        except OSError:
            code = 127
            status = "unavailable"
    row = {"gate": name, "command": command, "cwd": str(cwd), "started_at": started,
           "ended_at": timestamp(), "elapsed_ms": round((time.monotonic() - clock) * 1000),
           "exit_code": code, "status": status}
    log_path = output / f"{name}.log"
    row["log_sha256"] = sha256_file(log_path)
    if name in {"platform_tests", "dual_repository"}:
        counts = {key: int(value) for value, key in re.findall(
            r"(\d+) (passed|failed|skipped|deselected|subtests passed)", log_path.read_text()
        )}
        row["counts"] = counts
        if code == 0 and (
            not counts.get("passed") or counts.get("failed")
            or counts.get("skipped") or counts.get("deselected")
        ):
            row["status"] = "failed"
            row["reason"] = "incomplete_test_selection"
    if name == "agent_local" and code == 0:
        try:
            report = load_json(log_path)
            if not isinstance(report, dict) or (
                report.get("status") != "passed" or report.get("mode") != "local"
                or report.get("scope") != "agent_single_repository"
                or report.get("external_acceptance") != "blocked"
                or report.get("release_accepted") is not False
                or report.get("production_authorized") is not False
            ):
                raise ValueError("invalid local report")
            checks = report.get("checks")
            expected = ["tests", "static", "dsh_profiles", "retrieval_benchmark"]
            if not isinstance(checks, list) or len(checks) != len(expected):
                raise ValueError("missing local checks")
            if any(not isinstance(check, dict) or check.get("check") != name
                   or check.get("status") != "passed" for name, check in zip(expected, checks, strict=True)):
                raise ValueError("incomplete local checks")
            counts = checks[0].get("counts")
            if not isinstance(counts, dict) or set(counts) != {"passed", "failed", "skipped", "deselected"}:
                raise ValueError("missing local test counts")
            if any(type(value) is not int or value < 0 for value in counts.values()) or (
                not counts["passed"] or counts["failed"] or counts["skipped"]
            ):
                raise ValueError("incomplete local tests")
            row["counts"] = counts
        except (ManifestError, OSError, ValueError):
            row["status"] = "failed"
            row["reason"] = "invalid_local_acceptance_report"
    write_new(output / f"{name}.json", row)
    print(json.dumps({"gate": name, "status": row["status"], "exit_code": code}), flush=True)
    return row


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform-source", required=True, type=Path)
    parser.add_argument("--platform-python", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    for path in (args.platform_source, args.output):
        if not path.is_absolute() or path.is_symlink():
            parser.error("explicit absolute nonsymlink paths required")
    if not args.platform_python.is_absolute() or not args.platform_python.is_file():
        parser.error("explicit absolute Python executable required")
    if args.output.exists():
        parser.error("output must be a new exclusive directory")
    source = args.platform_source.resolve(strict=True)
    if not (source / "src/company_quantum/adapters/company_agent_provider.py").is_file():
        parser.error("actual platform provider source required")
    os.umask(0o077)
    args.output.mkdir(parents=True, exist_ok=False)
    env = offline_environment()
    for name in ("PYTEST_ADDOPTS", "PYTEST_PLUGINS", "PYTEST_CURRENT_TEST", "COMPANY_AGENT_DEPLOYMENT_MODE",
                 "QUANTUM_RELEASE_SHARE", "QUANTUM_PRODUCT_SOURCES", "QUANTUM_REVIEW_CHECKOUT"):
        env.pop(name, None)
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    env["RUFF_NO_CACHE"] = "true"
    env["MYPY_CACHE_DIR"] = str(args.output / "quality-cache")
    try:
        before = {"agent": inventory(ROOT, AGENT_INPUTS), "platform": inventory(source, PLATFORM_INPUTS)}
        identities = {
            "contract_digest": contract_digest(ROOT), "lock_digest": lock_digest(ROOT),
            "python": platform.python_version(), "python_executable": sys.executable,
            "python_sha256": sha256_file(Path(sys.executable)),
            "platform_python_sha256": sha256_file(args.platform_python),
            "system": platform.platform(),
        }
    except (OSError, ValueError, ManifestError):
        write_new(args.output / "summary.json", {
            "format": "company-agent-local-closure/1", "status": "failed", "gates": [],
            "reason": "input_inventory_unavailable", "external_acceptance": "blocked",
            "release_accepted": False, "production_authorized": False,
        })
        print("closure failed: input inventory unavailable", file=sys.stderr)
        return 1
    write_new(args.output / "inputs-before.json", before)
    platform_env = {**env, "PYTHONPATH": str(source / "src")}
    platform_python = str(args.platform_python)
    gates = [
        ("agent_local", [sys.executable, str(ROOT / "scripts/verify_acceptance.py")], ROOT, env),
        ("platform_tests", [platform_python, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                            "--tb=short", "tests/test_company_agent_provider.py",
                            "tests/test_dependency_aliases.py", "tests/test_packaging_platform.py"],
         source, platform_env),
        ("platform_quality", [platform_python, str(source / "scripts/check_quality.py"),
                              "--root", str(source), "--report", str(args.output / "platform-quality.json")],
         source, platform_env),
        ("dual_repository", [sys.executable, "-m", "pytest", "-q", "--tb=short",
                             "-m", "platform_compatibility", "tests/test_platform_compatibility.py"],
         ROOT, {**env, "COMPANY_AGENT_PLATFORM_SOURCE": str(source)}),
        ("benchmark", [sys.executable, str(ROOT / "scripts/benchmark_company_agent.py"), "--repeats", "10"],
         ROOT, env),
    ]
    results = [run(name, command, cwd, gate_env, args.output) for name, command, cwd, gate_env in gates]
    after_unavailable = False
    try:
        after = {"agent": inventory(ROOT, AGENT_INPUTS), "platform": inventory(source, PLATFORM_INPUTS)}
    except (OSError, ValueError, ManifestError):
        after = {"status": "failed", "reason": "input_inventory_unavailable"}
        after_unavailable = True
    write_new(args.output / "inputs-after.json", after)
    stable = not after_unavailable and before == after
    accepted = stable and all(row["status"] == "passed" for row in results)
    report = {"format": "company-agent-local-closure/1", "ended_at": timestamp(),
              "scope": "synthetic_offline_and_loopback_not_release_acceptance",
              "status": "passed" if accepted else "failed", "inputs_stable": stable,
              **identities, "gates": results,
              "release_accepted": False, "production_authorized": False, "external_acceptance": "blocked"}
    if after_unavailable:
        report["reason"] = "ending_input_inventory_unavailable"
    write_new(args.output / "summary.json", report)
    print(json.dumps({"status": report["status"], "inputs_stable": stable,
                      "external_acceptance": "blocked"}), flush=True)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
