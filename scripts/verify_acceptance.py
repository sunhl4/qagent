#!/usr/bin/env python3
"""Offline gates by default; real acceptance opens the existing human-supervised DSH UI."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROVIDERS = {
    "platform": ("COMPANY_QUANTUM_PLATFORM_INVOKE_URL", "COMPANY_QUANTUM_PLATFORM_TOKEN"),
    "simulator": ("COMPANY_AGENT_SIMULATOR_INVOKE_URL", "COMPANY_AGENT_SIMULATOR_TOKEN"),
    "compiler": ("COMPANY_AGENT_COMPILER_INVOKE_URL", "COMPANY_AGENT_COMPILER_TOKEN"),
    "device": ("COMPANY_AGENT_DEVICE_INVOKE_URL", "COMPANY_AGENT_DEVICE_TOKEN"),
    "cloud": ("COMPANY_AGENT_CLOUD_INVOKE_URL", "COMPANY_AGENT_CLOUD_TOKEN"),
    "hpc": ("COMPANY_AGENT_HPC_INVOKE_URL", "COMPANY_AGENT_HPC_TOKEN"),
}


def offline_environment() -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if not key.startswith("PYTEST_")}
    for key in (
        *[key for pair in PROVIDERS.values() for key in pair],
        "COMPANY_AGENT_MANAGED_ACCESS", "COMPANY_AGENT_TOOL_WORKSPACE", "UQC_CLOUD_API_KEY",
        "COMPANY_AGENT_HPC_USER", "COMPANY_AGENT_HPC_HOST", "COMPANY_RELAY_API_KEY",
        "UQC_CLOUD_PROBE_PYTHON",
        "DEEPSEEK_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "COMPANY_AGENT_APPROVAL_CONTEXT",
        "COMPANY_AGENT_KNOWLEDGE_PATH",
        "COMPANY_AGENT_ENABLE_CONFIGURED_KNOWLEDGE",
        "PYTHONPATH",
        "PYTHONHOME",
        "NODE_OPTIONS",
        "LD_PRELOAD",
        "LD_LIBRARY_PATH",
    ):
        env.pop(key, None)
    env.update(
        {
            "PYTHONPATH": str(ROOT / "src"),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONNOUSERSITE": "1",
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
            "COMPANY_AGENT_CONTRACTS_DIR": str(ROOT / "contracts"),
            "DSH_TELEMETRY_MODE": "DISABLED",
        }
    )
    return env


def _test_evidence(row: dict, evidence: Path | None) -> dict:
    # Mirror the exclusion policy of scripts/acceptance_pytest.py: the extra
    # posix_permissions marker only exists on Windows, where os.chmod cannot
    # express the probed POSIX bits; the Ubuntu release host keeps the full list.
    exclusions = ["platform_compatibility", "latex_toolchain"]
    if os.name == "nt":
        exclusions.append("posix_permissions")
    row.update(counts={key: 0 for key in ("passed", "failed", "skipped", "deselected")},
               failed_tests=[], scope="agent_single_repository",
               excluded_markers=exclusions)
    try:
        if evidence is None:
            raise ValueError("missing evidence")
        # Reuse the existing strict bounded reader without exposing raw pytest output.
        spec = importlib.util.spec_from_file_location("acceptance_json", ROOT / "scripts/release_manifest.py")
        if spec is None or spec.loader is None:
            raise ValueError("reader unavailable")
        reader = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(reader)
        try:
            report = reader.load_json(evidence)
        except reader.ManifestError as exc:
            raise ValueError("invalid evidence") from exc
        if not isinstance(report, dict) or set(report) != {
            "format", "scope", "pytest_exit_code", "counts", "selection", "failed_tests", "excluded_markers",
        }:
            raise ValueError("invalid fields")
        if (report["format"] != "company-agent-pytest-evidence/1"
                or report["scope"] != row["scope"] or report["excluded_markers"] != row["excluded_markers"]
                or type(report["pytest_exit_code"]) is not int
                or report["pytest_exit_code"] != row["exit_code"]):
            raise ValueError("invalid identity")
        counts, selection = report["counts"], report["selection"]
        if not isinstance(counts, dict) or set(counts) != set(row["counts"]) or any(
            type(value) is not int or value < 0 for value in counts.values()
        ):
            raise ValueError("invalid counts")
        fields = {"collected", "selected", "expected_selected", "expected_excluded", "test_files",
                  "observed_files", "executed", "collection_errors", "complete"}
        if not isinstance(selection, dict) or set(selection) != fields or any(
            type(selection[key]) is not int or selection[key] < 0 for key in fields - {"complete"}
        ) or type(selection["complete"]) is not bool:
            raise ValueError("invalid selection")
        failures = report["failed_tests"]
        if not isinstance(failures, list) or len(failures) > 64 or any(
            not isinstance(node, str) or not re.fullmatch(r"tests/[A-Za-z0-9_./:-]+", node)
            for node in failures
        ):
            raise ValueError("invalid failures")
        row.update(counts=counts, selection=selection, failed_tests=failures)
        complete = (
            selection["complete"] and selection["selected"] > 0 and selection["test_files"] > 0
            and selection["selected"] == selection["expected_selected"] == selection["executed"]
            and selection["expected_excluded"] == counts["deselected"]
            and selection["collected"] == selection["selected"] + counts["deselected"]
            and selection["test_files"] == selection["observed_files"]
            and selection["collection_errors"] == 0
            and sum(counts[key] for key in ("passed", "failed", "skipped")) == selection["selected"]
        )
        if not complete:
            row.update(status="failed", reason="incomplete_test_selection")
        elif counts["failed"] or failures:
            row.update(status="failed", reason="tests_failed")
        elif counts["skipped"] and row["status"] == "passed":
            row.update(status="blocked", reason="tests_skipped")
    except (OSError, ValueError, TypeError, KeyError):
        row.update(status="failed", reason="invalid_test_evidence")
    return row


def _kill_process_tree(process: subprocess.Popen[str]) -> None:
    """Terminate a timed-out gate on POSIX and Windows without leaking children."""
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/pid", str(process.pid), "/T", "/F"],
                capture_output=True, check=False, timeout=10,
            )
        except (OSError, subprocess.SubprocessError):
            process.kill()
        return
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (OSError, ProcessLookupError):
        process.kill()


def run_gate(name: str, command: list[str], timeout: int = 900, *, evidence: Path | None = None) -> dict:
    start = time.monotonic()
    try:
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            env=offline_environment(),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        try:
            output, _ = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            _kill_process_tree(process)
            process.communicate()
            return {"check": name, "status": "failed", "reason": "timeout"}
    except OSError:
        return {"check": name, "status": "blocked", "reason": "executable_unavailable"}
    row = {
        "check": name,
        "status": "passed" if process.returncode == 0 else "failed",
        "exit_code": process.returncode,
        "elapsed_ms": int((time.monotonic() - start) * 1000),
    }
    if name == "tests":
        return _test_evidence(row, evidence)
    return row


def local_checks() -> list[dict]:
    checks = []
    runtime = Path(
        os.environ.get(
            "COMPANY_AGENT_RUNTIME_DIR",
            Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
            / "unitqc-company-agent/dsh-runtime",
        )
    )
    for relative in ("node_modules/node/bin/node", "node_modules/@deepseek-ai/dsh/lib/bin.js"):
        candidate = runtime / relative
        if not candidate.is_file():
            checks.append({"check": "dsh_runtime", "status": "blocked", "reason": "run_bootstrap_dsh"})
            break
        if relative.endswith("/node"):
            try:
                version = subprocess.run(
                    [str(candidate), "--version"], capture_output=True, text=True,
                    timeout=5, check=False,
                )
            except (OSError, subprocess.SubprocessError):
                checks.append({"check": "dsh_runtime", "status": "blocked", "reason": "pinned_node_unavailable"})
                break
            if version.returncode != 0 or version.stdout.strip() != "v22.22.0":
                checks.append({"check": "dsh_runtime", "status": "blocked", "reason": "pinned_node_version_mismatch"})
                break
    for module in ("pytest", "ruff", "build", "hypothesis"):
        if importlib.util.find_spec(module) is None:
            checks.append(
                {
                    "check": f"dependency_{module}",
                    "status": "blocked",
                    "reason": "install_runtime_python_dev_lock",
                }
            )
    if checks:
        return checks
    with tempfile.TemporaryDirectory(prefix="company-acceptance-tests-") as temporary:
        evidence = Path(temporary) / "pytest.json"
        checks.append(run_gate("tests", [sys.executable, str(ROOT / "scripts/acceptance_pytest.py"),
                                         "--report", str(evidence)], evidence=evidence))
    checks.append(run_gate("static", [sys.executable, str(ROOT / "scripts/check_static.py")]))
    checks.append(run_gate("dsh_profiles", [sys.executable, str(ROOT / "scripts/verify_dsh_profiles.py")]))
    checks.append(
        run_gate("retrieval_benchmark", [sys.executable, str(ROOT / "scripts/benchmark_company_agent.py")])
    )
    return checks


def _copy_profile_for_acceptance(source: Path, destination: Path) -> None:
    """Copy managed profile configuration and materialize local plugins."""
    shutil.copytree(
        source,
        destination,
        symlinks=False,
        ignore=shutil.ignore_patterns("node_modules", ".dsh-home"),
    )
    _copy_managed_profile_packages(source, destination)


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
        package_name = name.split("/", 1)[1] if "/" in name else ""
        if not package_name:
            raise RuntimeError("profile package name is invalid")
        package_source = ROOT / "packages" / package_name
        package_target = destination / "node_modules" / "@unitqc" / package_name
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


def real_checks(args) -> list[dict]:
    """Static supervised preflight; provider calls remain blocked."""
    checks = []
    has_model = bool(os.environ.get("DEEPSEEK_API_KEY", "").strip())
    checks.append({
        "check": "model_configuration",
        "status": "passed" if has_model else "blocked",
        "reason": "environment_present_not_verified" if has_model else "model_credentials_missing",
    })
    sys.path.insert(0, str(ROOT / "src"))
    from company_agent.providers import clients

    for client in clients():
        configured = client.configured()
        checks.append({
            "check": f"{client.id}_configuration",
            "status": "passed" if configured else "blocked",
            "reason": "configured_not_verified" if configured else "provider_configuration_missing",
        })
    assets = bool(args.asset_id and args.circuit_id and args.algorithm)
    checks.append({
        "check": "test_assets",
        "status": "passed" if assets else "blocked",
        "reason": "provided_not_verified" if assets else "test_assets_missing",
    })
    for name in (
        "model_task_quality", "platform_service", "simulator_service", "compiler_service",
        "device_service", "authentication_negative_cases", "device_reconciliation",
    ):
        checks.append({"check": name, "status": "blocked", "reason": "requires_supervised_dsh_evidence"})
    return checks


def supervised_prompts(args) -> list[dict]:
    return [
        {"case": "capability_discovery", "prompt": "请列出公司能力及其 provider，不执行科学任务。"},
        {"case": "chinese_knowledge", "prompt": "设备执行为什么每次都要审批？请给出知识来源和内容版本。"},
        {
            "case": "algorithm_catalog",
            "prompt": "先调用平台算法目录发现当前可用算法，不要编造算法名。"
            "说明名单来自 uniqon，不执行算法。",
        },
        {
            "case": "workflow_branches",
            "prompt": "请静态校验两条算法和电路分支，显式绑定模拟的上游来源。"
            "说明 valid 的范围，不执行该计划。",
        },
        {
            "case": "missing_provider",
            "prompt": "在移除对应 provider 配置的独立会话中请求模拟。"
            "应诚实失败，不能伪造结果；此步骤需运维先隔离配置。",
        },
        {
            "case": "science_contracts",
            "prompt": "用批准的测试资产逐项验证平台、模拟与编译服务。",
            "asset_id": args.asset_id,
            "circuit_id": args.circuit_id,
            "algorithm": args.algorithm,
            "shots": 1,
            "checks": [
                "authentication",
                "request_correlation",
                "provenance",
                "closed_summary",
                "quantity_boundaries",
            ],
        },
        {
            "case": "device_approval",
            "prompt": "仅在隔离验收设备上申请执行一次，shots=1。"
            "先 Reject 验证零执行；新调用再 Allow once；重复调用必须重新询问。"
            "遇结果未知立即停止，不重试，通过服务运维按 request_id 核对状态。",
            "circuit_id": args.circuit_id,
            "checks": ["server_counter", "operator_approval", "reconciliation_record"],
        },
    ]


def evidence_check(args) -> dict:
    if args.evidence is None:
        return {
            "check": "manual_evidence",
            "status": "blocked",
            "reason": "evidence_missing",
            "physical_truth_certified": False,
        }
    spec = importlib.util.spec_from_file_location(
        "verify_manual_evidence", ROOT / "scripts/verify_manual_evidence.py"
    )
    if spec is None or spec.loader is None:
        return {
            "check": "manual_evidence",
            "status": "failed",
            "reason": "evidence_verifier_unavailable",
            "physical_truth_certified": False,
        }
    verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)
    evidence = args.evidence.absolute()
    attestation = args.evidence_attestation.absolute() if args.evidence_attestation else None
    trust = args.evidence_trust_config.absolute() if args.evidence_trust_config else None
    try:
        report = verifier.verify_paths(
            evidence,
            attestation_path=attestation,
            trust_path=trust,
            expected_contract_digest=args.contract_digest,
            expected_lock_digest=args.lock_digest,
            expected_manifest_digest=args.release_manifest_digest,
        )
    except (verifier.EvidenceError, OSError):
        return {
            "check": "manual_evidence",
            "status": "failed",
            "reason": "evidence_invalid",
            "physical_truth_certified": False,
        }
    return {
        "check": "manual_evidence",
        "status": "blocked",
        "reason": report["external_acceptance"],
        "evidence_class": report["evidence_class"],
        "operator_attested": report["operator_attested"],
        "physical_truth_certified": False,
        "structural_status": report["status"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("local", "real"), default="local")
    parser.add_argument(
        "--launch", action="store_true", help="real mode: open existing DSH Runtime for review"
    )
    parser.add_argument("--asset-id")
    parser.add_argument("--circuit-id")
    parser.add_argument("--algorithm")
    parser.add_argument(
        "--evidence", type=Path, help="real mode: import a deidentified supervised evidence bundle"
    )
    parser.add_argument("--evidence-attestation", type=Path)
    parser.add_argument("--evidence-trust-config", type=Path)
    parser.add_argument("--contract-digest")
    parser.add_argument("--lock-digest")
    parser.add_argument("--release-manifest-digest")
    args = parser.parse_args(argv)
    if args.launch and args.mode != "real":
        parser.error("--launch requires --mode real")
    if args.evidence is not None and args.mode != "real":
        parser.error("--evidence requires --mode real")
    if (args.evidence_attestation is None) != (args.evidence_trust_config is None):
        parser.error("--evidence-attestation and --evidence-trust-config must be supplied together")
    if (
        args.evidence_attestation is not None
        or any((args.contract_digest, args.lock_digest, args.release_manifest_digest))
    ) and args.evidence is None:
        parser.error("evidence linkage options require --evidence")
    for value, name in (
        (args.contract_digest, "contract"),
        (args.lock_digest, "lock"),
        (args.release_manifest_digest, "release manifest"),
    ):
        if value is not None and not re.fullmatch(r"sha256:[0-9a-f]{64}", value):
            parser.error(f"invalid {name} digest")
    for key, prefix in (("asset_id", "asset_"), ("circuit_id", "circ_")):
        value = getattr(args, key)
        if value is not None and (len(value) > 256 or not re.fullmatch(prefix + r"[A-Za-z0-9_-]+", value)):
            parser.error(f"invalid {key}")
    if args.algorithm is not None and not re.fullmatch(r"[a-z][a-z0-9_.-]{0,127}", args.algorithm):
        parser.error("invalid algorithm")
    checks = local_checks() if args.mode == "local" else real_checks(args)
    if args.mode == "real":
        checks.append(evidence_check(args))
    status = (
        "failed"
        if any(row["status"] == "failed" for row in checks)
        else ("blocked" if any(row["status"] == "blocked" for row in checks) else "passed")
    )
    report = {
        "version": "1.3",
        "mode": args.mode,
        "scope": "agent_single_repository" if args.mode == "local" else "supervised_preflight",
        "platform_compatibility": "separate_gate_required",
        "status": status,
        "checks": checks,
        "external_acceptance": "blocked",
        "production_authorized": False,
        "release_accepted": False,
        "device_approval": "per_call_in_dsh_only",
    }
    if args.mode == "real":
        report["scope"] = "configuration_evidence_structure_and_supervised_entry_not_service_acceptance"
        report["cases"] = supervised_prompts(args)
    print(json.dumps(report, ensure_ascii=False, separators=(",", ":")), flush=True)
    if args.launch:
        prerequisite_checks = [
            row for row in checks if row["check"].endswith("configuration") or row["check"] == "test_assets"
        ]
        if any(row["status"] != "passed" for row in prerequisite_checks):
            return 2
        env = os.environ.copy()
        env.pop("COMPANY_AGENT_APPROVAL_CONTEXT", None)
        env.update(
            {
                "COMPANY_AGENT_PROFILE": "company-agent",
                "COMPANY_AGENT_PRESET": "lab",
                "COMPANY_AGENT_PYTHON": sys.executable,
            }
        )
        # No prompt injection, approval marker, policy override, or replacement execution loop.
        # Use isolated state and a free loopback port, never mutate a production session.
        with tempfile.TemporaryDirectory(prefix="company-acceptance-") as home:
            try:
                _copy_profile_for_acceptance(
                    ROOT / "profiles/company-agent", Path(home) / "profiles/company-agent"
                )
            except (OSError, RuntimeError, shutil.Error):
                print(json.dumps({
                    "version": "1.3", "mode": args.mode, "scope": "agent_single_repository",
                    "platform_compatibility": "separate_gate_required", "status": "blocked",
                    "checks": [{"check": "profile_isolation", "status": "blocked",
                                "reason": "profile_copy_unavailable"}],
                    "external_acceptance": "blocked", "production_authorized": False,
                    "release_accepted": False, "device_approval": "per_call_in_dsh_only",
                }, ensure_ascii=False, separators=(",", ":")), flush=True)
                return 2
            with socket.socket() as listener:
                listener.bind(("127.0.0.1", 0))
                port = listener.getsockname()[1]
            env.update({"COMPANY_AGENT_DSH_HOME": home, "COMPANY_AGENT_DSH_PORT": str(port)})
            subprocess.run(["bash", str(ROOT / "scripts/start_runtime.sh")], cwd=ROOT, env=env, check=False)
    return {"passed": 0, "failed": 1, "blocked": 2}[status]


if __name__ == "__main__":
    raise SystemExit(main())
