#!/usr/bin/env python3
"""Measured checks for one development and review circle.

`review` exits non-zero when any check fails. `run` always writes metrics.json
for the requested candidate and exits zero when that file is written. The
metric is the measurement; a candidate cannot pass by printing a number.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ORDER_SENTENCE = "先改合同，再改 Python adapter，再改 DSH 插件，最后改测试。"
RUNTIME_SENTENCE = "DSH 是唯一 Agent Runtime"
LOOP_NAME = "dev_review_loop"
PRODUCT_ROOTS = ("src", "packages", "profiles", "contracts")
TEXT_SUFFIXES = {".py", ".js", ".mjs", ".json", ".md", ".ts", ".toml"}
SCHEDULER_COMMANDS = frozenset(
    {
        "sbatch",
        "srun",
        "salloc",
        "scancel",
        "squeue",
        "scontrol",
        "qsub",
        "qstat",
        "qdel",
        "bsub",
        "bjobs",
        "bkill",
        "msub",
        "yhbatch",
        "yhrun",
        "yhalloc",
    }
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _plan(repo: Path) -> dict:
    return json.loads(_read(repo / "docs" / "dev-review" / "plan.json"))


def _commands(plan: dict) -> list[list[str]]:
    commands = [list(item) for item in plan["review_commands"]]
    commands.append(list(plan["run_command"]))
    proposal = plan.get("proposal_command")
    if proposal:
        commands.append(list(proposal))
    return commands


def _catalog_count(repo: Path) -> int:
    path = repo / "docs" / "dev-review" / "catalog.json"
    if not path.is_file():
        return 0
    payload = json.loads(_read(path))
    items = payload.get("candidates", [])
    return len(items) if isinstance(items, list) else 0


def check_development_order(repo: Path) -> list[str]:
    failures: list[str] = []
    agents = repo / "AGENTS.md"
    if not agents.is_file() or ORDER_SENTENCE not in _read(agents):
        failures.append("development order sentence missing")
    for relative in ("contracts", "src/company_agent", "packages", "tests"):
        if not (repo / relative).is_dir():
            failures.append(f"missing directory {relative}")
    return failures


def check_device_policy(repo: Path) -> list[str]:
    policy = json.loads(_read(repo / "contracts" / "policy.json"))
    failures: list[str] = []
    if policy.get("device_ask_presets") != ["lab", "sign"]:
        failures.append("device ask presets drifted")
    if policy.get("device_deny_presets") != ["boot", "algo"]:
        failures.append("device deny presets drifted")
    ask = set(policy.get("device_ask_presets") or [])
    deny = set(policy.get("device_deny_presets") or [])
    if ask & deny or ask | deny != {"lab", "sign", "boot", "algo"}:
        failures.append("device preset partition drifted")
    return failures


def _product_hits(repo: Path, needle: str) -> list[str]:
    hits: list[str] = []
    skipped = {"node_modules", "__pycache__", ".dsh-module-fallback", ".dsh-home"}
    for name in PRODUCT_ROOTS:
        root = repo / name
        if not root.exists():
            hits.append(f"missing product root {name}")
            continue
        for directory, subdirs, names in os.walk(root, followlinks=False):
            subdirs[:] = [item for item in subdirs if item not in skipped]
            for filename in names:
                path = Path(directory) / filename
                if path.suffix.lower() not in TEXT_SUFFIXES:
                    continue
                try:
                    if not path.is_file() or path.stat().st_size > 1_000_000:
                        continue
                    text = path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                if needle in text:
                    hits.append(path.relative_to(repo).as_posix())
    return hits


def check_not_a_second_runtime(repo: Path) -> list[str]:
    failures: list[str] = []
    agents = repo / "AGENTS.md"
    if not agents.is_file() or RUNTIME_SENTENCE not in _read(agents):
        failures.append("runtime sentence missing")
    hits = _product_hits(repo, LOOP_NAME)
    if hits:
        failures.append("dev review loop is referenced from the product tree: " + ", ".join(hits))
    return failures


def check_early_stop_disabled(repo: Path) -> list[str]:
    plan = _plan(repo)
    loop = plan["loop"]
    failures: list[str] = []
    if loop.get("stop_on_keep") is not False:
        failures.append("stop_on_keep is enabled")
    count = max(len(plan.get("candidates", [])), _catalog_count(repo))
    if _catalog_count(repo) and not plan.get("proposal_command"):
        failures.append("proposal command missing")
    task_bound = loop.get("task_bound") is True
    resources = plan.get("resources") if isinstance(plan.get("resources"), dict) else {}
    if task_bound:
        if int(loop.get("max_rounds", 0)) < 1000:
            failures.append("max_rounds floor is below 1000")
        if int(loop.get("max_attempts", 0)) < 1000:
            failures.append("max_attempts floor is below 1000")
        if float(resources.get("budget_total", 0)) < 1000:
            failures.append("budget floor is below 1000")
        timeout = resources.get("timeout_seconds")
        if timeout is not None and float(timeout) < 3600:
            failures.append("command timeout cuts a long task")
    else:
        if int(loop.get("max_rounds", 0)) < count:
            failures.append("max_rounds is below the candidate count")
        if int(loop.get("max_attempts", 0)) < count:
            failures.append("max_attempts is below the candidate count")
    for command in _commands(plan):
        for token in command:
            if Path(str(token)).name in SCHEDULER_COMMANDS:
                failures.append(f"scheduler command in plan: {token}")
    return failures


def _classify_sample(payload: dict) -> dict | str:
    script = ROOT / "scripts" / "failure_once.mjs"
    node = shutil.which("node")
    if not script.is_file():
        return "failure script missing"
    if node is None:
        return "node is unavailable"
    completed = subprocess.run(
        [node, "--experimental-strip-types", str(script)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=20,
        check=False,
    )
    if not completed.stdout.strip():
        return "failure script returned no record"
    try:
        parsed = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return "failure script returned invalid json"
    if not isinstance(parsed, dict):
        return "failure script returned invalid json"
    return parsed


def check_failure_record(repo: Path) -> list[str]:
    failures: list[str] = []
    script = repo / "scripts" / "failure_once.mjs"
    if script.is_file() and "hypothesis" in _read(script):
        failures.append("failure script accepts card text")
    clock = repo / "src" / "company_agent" / "research_clock.py"
    if not clock.is_file():
        return ["research clock missing"]
    source = _read(clock)
    if "failure_once.mjs" not in source:
        failures.append("research clock does not classify failures")
    if source.count("failures.jsonl") != 1:
        failures.append("failure record is read back by the clock")
    timeout = _classify_sample({"stage": "execution", "portErrorCode": "TIMEOUT"})
    unknown = _classify_sample({"stage": "unknown_execution"})
    if isinstance(timeout, str) or isinstance(unknown, str):
        failures.append(timeout if isinstance(timeout, str) else unknown)
        return failures
    allowed = {"ok", "category", "code", "stage", "retryable"}
    if set(timeout) - allowed or set(unknown) - allowed:
        failures.append("failure record has extra fields")
    if timeout.get("ok") is not True or timeout.get("category") != "environment":
        failures.append("timeout was not classified as environment")
    if timeout.get("code") != "TIMEOUT" or timeout.get("retryable") is not True:
        failures.append("timeout record drifted")
    if unknown.get("category") != "unknown" or unknown.get("retryable") is not False:
        failures.append("unknown execution is retryable")
    return failures


def check_proposal_continues(repo: Path) -> list[str]:
    failures: list[str] = []
    catalog_path = repo / "docs" / "dev-review" / "catalog.json"
    proposer = repo / "scripts" / "dev_review_propose.py"
    loop = repo / "scripts" / "dev_review_loop.py"
    if not catalog_path.is_file() or not proposer.is_file():
        return ["catalog or proposer missing"]
    command = _plan(repo).get("proposal_command")
    if not isinstance(command, list) or "scripts/dev_review_propose.py" not in command:
        failures.append("proposal command missing")
    source = _read(loop)
    if "requires_new_review" not in source or "_propose_next" not in source:
        failures.append("loop does not stop when the catalog is exhausted")
    catalog = json.loads(_read(catalog_path))
    items = [item for item in catalog.get("candidates", []) if isinstance(item, dict)]
    kept = {item.get("id") for item in items if item.get("decision") in {"keep", "discard"}}
    expected = {
        "development-order",
        "device-policy",
        "not-a-second-runtime",
        "early-stop-disabled",
    }
    if not expected <= kept:
        failures.append("reviewed checks are not marked settled")
    chosen = [item for item in items if item.get("id") == "proposal-continues"]
    expected_paths = [
        "scripts/dev_review_loop.py",
        "scripts/dev_review_propose.py",
        "tests/test_dev_review_loop.py",
    ]
    if len(chosen) != 1 or chosen[0].get("allowed_paths") != expected_paths:
        failures.append("proposal candidate paths drifted")
    elif chosen[0].get("kind") != "implement" or chosen[0].get("status") != "ready":
        failures.append("proposal candidate is not ready")
    return failures


def check_charter_boundary(repo: Path) -> list[str]:
    failures: list[str] = []
    tools = json.loads(_read(repo / "contracts" / "tools.json"))
    by_name = {item["name"]: item for item in tools["tools"]}
    pattern = (
        "^$|^(hypothesis(,baseline)?(,metric)?(,budget)?"
        "|baseline(,metric)?(,budget)?|metric(,budget)?|budget)$"
    )
    for name in ("company_research_run", "company_research_status"):
        output = by_name[name]["output"]
        required = output["required"]
        if "charter_action" not in required or "charter_fields" not in required:
            failures.append(f"{name} omits the charter fields")
        action = output["properties"]["charter_action"]["enum"]
        if action != ["", "opened", "changed", "same"]:
            failures.append(f"{name} charter action drifted")
        if output["properties"]["charter_fields"]["pattern"] != pattern:
            failures.append(f"{name} charter fields drifted")
    clock = _read(repo / "src" / "company_agent" / "research_clock.py")
    if "charter_slots" not in clock or '"charter_action"' not in clock:
        failures.append("research clock does not record a charter")
    digest = clock.split("def read_digest", 1)[1].split("def read_status", 1)[0]
    if "charter_" in digest:
        failures.append("digest returns charter fields")
    return failures


def check_surface_discards(repo: Path) -> list[str]:
    source = _read(repo / "scripts" / "dev_review_loop.py")
    hidden = "目录已经用尽，且有候选没有达到指标"
    exhausted = "已审阅目录已经用尽，需要新的书面协议。"
    if hidden not in source or exhausted not in source:
        return ["empty catalog can hide a discarded attempt"]
    if source.find(hidden) > source.find(exhausted):
        return ["discard is reported after catalog exhaustion"]
    return []


def check_seat_card_once(repo: Path) -> list[str]:
    root = str(repo / "src")
    if root not in sys.path:
        sys.path.insert(0, root)
    from company_agent.invoke import invoke

    card = {
        "tenant_id": "team-a",
        "experiment_id": "exp-seat",
        "task_id": "task-seat",
        "project_id": "proj-seat",
        "hypothesis": "one approved card records a short receipt",
        "falsifier": "the metric does not move",
        "baseline_name": "plain",
        "baseline_source": "internal",
        "baseline_metric": 1.0,
        "baseline_reproduced": True,
        "changed_path": "src/train/scheduler.py",
        "primary_metric": "val_loss",
        "direction": "minimize",
        "resource_type": "gpu",
        "max_cost": 5,
        "max_attempts": 1,
    }
    keys = ("COMPANY_AGENT_RESEARCH_STATE", "COMPANY_AGENT_WORK_ITEM_DB")
    previous = {key: os.environ.get(key) for key in keys}
    try:
        with tempfile.TemporaryDirectory() as folder:
            state_dir = Path(folder)
            os.environ["COMPANY_AGENT_RESEARCH_STATE"] = str(state_dir / "clock")
            os.environ["COMPANY_AGENT_WORK_ITEM_DB"] = str(state_dir / "work.sqlite3")
            compiled = invoke("company_research_compile", "lab", card)
            if compiled.status != "ok" or not (compiled.payload or {}).get("ok"):
                return ["research compile did not accept the card"]
            run_card = {**card, "idempotency_key": "seat-card-once"}
            asked = invoke("company_research_run", "lab", run_card)
            if asked.status != "needs_ask":
                return ["research run did not ask before approval"]
            result = invoke("company_research_run", "lab", run_card, approved=True)
            payload = result.payload if isinstance(result.payload, dict) else {}
            if result.status != "ok" or payload.get("stop_reason") != "kept":
                return ["research run did not keep the card"]
            if payload.get("attempts") != 1 or payload.get("decisions") != "keep":
                return ["research run receipt drifted"]
            if not payload.get("trigger_id") or "twin_id" in payload:
                return ["research run receipt is not a short candidate"]
            blocked = {
                **run_card,
                "experiment_id": "exp-blocked",
                "baseline_reproduced": False,
                "idempotency_key": "seat-card-blocked",
            }
            rejected = invoke("company_research_run", "lab", blocked, approved=True)
            rejected_payload = rejected.payload if isinstance(rejected.payload, dict) else {}
            if rejected_payload.get("stop_reason") != "invalid_candidate":
                return ["unreproduced baseline still ran"]
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    return []


def check_probe_path(repo: Path) -> list[str]:
    host = _read(repo / "apps" / "company-workspace" / "host.mjs")
    if "/home/sunhl/" in host:
        return ["cloud probe bakes a developer machine path"]
    if "UQC_CLOUD_PROBE_PYTHON" not in host or "'python3'" not in host:
        return ["cloud probe lost its configured interpreter"]
    return []


def check_cloud_api_unset(repo: Path) -> list[str]:
    host = _read(repo / "apps" / "company-workspace" / "host.mjs")
    if "cloud.unitaryqubit.com" in host or "|| '8003'" in host:
        return ["workspace cloud API still has a baked endpoint"]
    if "UQC_CLOUD_API_BASE_URL" not in host:
        return ["workspace cloud API lost its configured endpoint"]
    return []


def check_probe_endpoint(repo: Path) -> list[str]:
    probe = _read(repo / "apps" / "company-workspace" / "uqc-cloud-probe.py")
    if "cloud.unitaryqubit.com" in probe or 'or "8003"' in probe:
        return ["cloud probe dials a baked endpoint"]
    if "missing_endpoint" not in probe or 'getattr(signal, "SIGALRM", None)' not in probe:
        return ["cloud probe lost its unset and windows timeout path"]
    return []


def check_card_cells(repo: Path) -> list[str]:
    card = _read(repo / "src" / "company_agent" / "experiment_card.py")
    plugin = _read(repo / "packages" / "company-agent-research" / "src" / "index.js")
    clock = _read(repo / "src" / "company_agent" / "research_clock.py")
    failures: list[str] = []
    if "def cells_to_args" not in card or "def compile_cells" not in card:
        failures.append("experiment card cells are not compiled")
    if "does not open xlsx" not in card:
        failures.append("experiment card lost its workbook refusal")
    if "xlsx" in plugin.casefold() or "xlsx" in clock.casefold() or "openpyxl" in clock:
        failures.append("research plugin opens a workbook")
    return failures


def check_metric_floor(repo: Path) -> list[str]:
    plan = _plan(repo)
    loop = plan["loop"]
    resources = plan.get("resources") if isinstance(plan.get("resources"), dict) else {}
    failures: list[str] = []
    if int(loop.get("max_rounds", 0)) < 1000 or int(loop.get("max_attempts", 0)) < 1000:
        failures.append("round and attempt floors are below 1000")
    if float(resources.get("budget_total", 0)) < 1000:
        failures.append("budget floor is below 1000")
    if resources.get("timeout_seconds") is not None:
        failures.append("command timeout cuts a long task")
    handbook = _read(repo / "docs" / "dev-review-loop.zh-CN.md")
    if "1000 轮" not in handbook or "总预算 1000" not in handbook:
        failures.append("written floor still quotes the old cap")
    if "研究实验卡的 `max_attempts` 仍是 1 到 5" not in handbook:
        failures.append("research card attempt limit was raised")
    return failures


def check_resource_tables(repo: Path) -> list[str]:
    host = _read(repo / "apps" / "company-workspace" / "host.mjs")
    probe = _read(repo / "apps" / "company-workspace" / "uqc-cloud-probe.py")
    page = _read(repo / "docs" / "quantum-agent-architecture.zh-CN.html")
    test = _read(repo / "tests" / "ui" / "shell-host.test.mjs")
    failures: list[str] = []
    if "export function projectSqueueLine" not in host or "projectHpcFiles" not in host:
        failures.append("hpc rows are still split on spaces and literal newlines")
    if "portal_ok_without_ssh" not in host or "portal_ok_without_ssh" not in page:
        failures.append("an open portal with no login node still looks unconfigured")
    if "不显示成空结果" not in page:
        failures.append("missing cluster jobs are shown as an empty success")
    if '"kind":' not in probe or '"state":' not in probe:
        failures.append("cloud devices do not fill the resource columns")
    if "projectSqueueLine('5010" not in test or 'rows[0]["kind"]' not in _read(
        repo / "tests" / "test_cloud.py"
    ):
        failures.append("resource table projection is not tested")
    return failures


def check_local_workspace(repo: Path) -> list[str]:
    host = _read(repo / "apps" / "company-workspace" / "host.mjs")
    page = _read(repo / "docs" / "quantum-agent-architecture.zh-CN.html")
    test = _read(repo / "tests" / "ui" / "shell-host.test.mjs")
    failures: list[str] = []
    if "jsonRoute('/company-workspace/workspace'" not in host or "localFiles" not in host:
        failures.append("workspace route does not read the host registry")
    if "/company-workspace/workspace" not in page or "不显示成空目录" not in page:
        failures.append("workspace page does not read the host directory")
    if "notes.txt" not in test or "/company-workspace/workspace" not in test:
        failures.append("workspace route test does not list a real directory")
    return failures


def check_workbench_receipts(repo: Path) -> list[str]:
    page = _read(repo / "docs" / "quantum-agent-architecture.zh-CN.html")
    host = _read(repo / "apps" / "company-workspace" / "host.mjs")
    test = _read(repo / "tests" / "ui" / "shell-host.test.mjs")
    failures: list[str] = []
    if "/company-workspace/workbench/tasks" not in page:
        failures.append("workbench page does not read the receipt route")
    if "空列表不当成没有任务" not in page:
        failures.append("unavailable receipts are treated as an empty task list")
    if "not_projected" not in page:
        failures.append("receipts are shown as approved or billed")
    if "/company-workspace/workbench/tasks" not in host:
        failures.append("receipt route is missing")
    if "空列表不当成没有任务" not in test or "not_projected" not in test:
        failures.append("workbench page test does not pin the receipt view")
    return failures


def check_portal_script(repo: Path) -> list[str]:
    host = _read(repo / "apps" / "company-workspace" / "host.mjs")
    test = _read(repo / "tests" / "ui" / "shell-host.test.mjs")
    handbook = _read(repo / "docs" / "super-dsh-handbook-2026-11-06.zh-CN.md")
    failures: list[str] = []
    if "rewriteText" not in host or "sandbox=" in host:
        failures.append("portal proxy lost its rewrite or widened the sandbox")
    if "window.portalReady=true" not in test or "/company-workspace/portal/hpc/app.js" not in test:
        failures.append("portal static script is not checked")
    if "云门户嵌入脚本此前返回 404" in handbook:
        failures.append("handbook still says the embed script is unchecked")
    if "不放宽 iframe 沙箱" not in handbook:
        failures.append("handbook dropped the sandbox rule")
    return failures


def check_portal_page_unset(repo: Path) -> list[str]:
    page = _read(repo / "docs" / "quantum-agent-architecture.zh-CN.html")
    failures: list[str] = []
    for literal in ("https://220.178.61.185:8443", "http://192.168.110.37"):
        if literal in page:
            failures.append("portal base is invented in the workspace page")
    if "connectionUrls" in page:
        failures.append("workspace page still keeps its own portal address")
    return failures


def check_portal_unset(repo: Path) -> list[str]:
    host = _read(repo / "apps" / "company-workspace" / "host.mjs")
    failures: list[str] = []
    for literal in ("https://220.178.61.185:8443", "http://192.168.110.37"):
        if literal in host:
            failures.append("portal base is invented in the workspace host")
    if "portal not configured" not in host:
        failures.append("unset portal does not stay closed")
    return failures


def check_kernel_stays(repo: Path) -> list[str]:
    failures: list[str] = []
    cli = _read(repo / "scripts" / "dsh-cli.mjs")
    if "COMPANY_AGENT_DSH_ENTRY" not in cli or "module.runCli()" not in cli:
        failures.append("launcher no longer calls the installed DSH runtime")
    host = _read(repo / "apps" / "company-workspace" / "host.mjs")
    if "second client" not in host:
        failures.append("workspace host no longer stays on the native client")
    style = _read(repo / "apps" / "company-workspace" / "workspace.css")
    if "stays DSH-native" not in style:
        failures.append("workspace style no longer stays on the native chrome")
    loop = _read(repo / "scripts" / "dev_review_loop.py")
    if "scripts/dsh-cli.mjs" not in loop or '"apps/"' not in loop or '"view/"' not in loop:
        failures.append("loop does not keep the kernel frozen and the native UI editable")
    if "启动界面可以改" not in loop or "公司账号和密码" not in loop:
        failures.append("startup screen is treated as the installed runtime")
    return failures


def check_loop_writes_code(repo: Path) -> list[str]:
    loop = _read(repo / "scripts" / "dev_review_loop.py")
    proposer = _read(repo / "scripts" / "dev_review_propose.py")
    body = loop.split("def run_dev_review_loop", 1)[-1]
    failures: list[str] = []
    if "def _apply_candidate_edits" not in loop or "_restore_files" not in body:
        failures.append("loop does not apply reviewed edits")
    if '"edits"' not in proposer:
        failures.append("proposer drops the edit list")
    return failures


def check_release_boundary(repo: Path) -> list[str]:
    failures: list[str] = []
    plan = repo / "docs" / "release-completion.zh-CN.md"
    deployment = repo / "docs" / "deployment-and-evidence.zh-CN.md"
    if not plan.is_file():
        return ["release plan missing"]
    text = _read(plan)
    required = (
        "DSH 仍是唯一 Agent Runtime",
        "S4、S5、S6 不开始",
        "production_authorized=false",
        "允许一次",
    )
    failures.extend(item for item in required if item not in text)
    if "production_authorized=false" not in _read(deployment):
        failures.append("deployment evidence no longer stays unauthorized")
    return failures


def check_snapshot_matches_ledger(repo: Path) -> list[str]:
    status = _read(repo / "docs" / "dev-review" / "STATUS.md")
    ledger = _read(repo / "docs" / "dev-review" / "LEDGER.md")
    heads = re.findall(r"^## \S+ `([^`]+)`$", ledger, re.M)
    shown = re.findall(r"^- 循环：`([^`]+)`$", status, re.M)
    if not heads or shown != [heads[-1]]:
        return ["status loop id is not the latest ledger round"]
    last = ledger.rsplit("\n## ", 1)[-1]
    ledger_stop = re.search(r"停止：`([^`]+)`", last)
    status_stop = re.search(r"停止原因：`([^`]+)`", status)
    if ledger_stop is None or status_stop is None or ledger_stop.group(1) != status_stop.group(1):
        return ["status stop reason disagrees with the latest ledger round"]
    return []


CHECKS: dict[str, Callable[[Path], list[str]]] = {
    "development-order": check_development_order,
    "device-policy": check_device_policy,
    "not-a-second-runtime": check_not_a_second_runtime,
    "early-stop-disabled": check_early_stop_disabled,
    "failure-record": check_failure_record,
    "proposal-continues": check_proposal_continues,
    "charter-boundary": check_charter_boundary,
    "surface-discards": check_surface_discards,
    "snapshot-matches-ledger": check_snapshot_matches_ledger,
    "release-boundary": check_release_boundary,
    "seat-card-once": check_seat_card_once,
    "loop-writes-code": check_loop_writes_code,
    "kernel-stays": check_kernel_stays,
    "portal-unset": check_portal_unset,
    "portal-page-unset": check_portal_page_unset,
    "portal-script": check_portal_script,
    "card-cells": check_card_cells,
    "workbench-receipts": check_workbench_receipts,
    "metric-floor": check_metric_floor,
    "local-workspace": check_local_workspace,
    "resource-tables": check_resource_tables,
    "probe-path": check_probe_path,
    "cloud-api-unset": check_cloud_api_unset,
    "probe-endpoint": check_probe_endpoint,
}


def open_edit_ids(repo: Path) -> list[str]:
    """Every unsettled catalog item the loop will apply in this run."""
    catalog_path = repo / "docs" / "dev-review" / "catalog.json"
    if not catalog_path.is_file():
        return []
    catalog = json.loads(_read(catalog_path))
    ledger_path = repo / "docs" / "dev-review" / "LEDGER.md"
    ledger = _read(ledger_path) if ledger_path.is_file() else ""
    done = {match.group(1) for match in re.finditer(r"`([a-z0-9-]+)`\s+(?:keep|discard)\b", ledger)}
    pending: list[dict] = []
    for item in catalog.get("candidates", []):
        if not isinstance(item, dict):
            continue
        if item.get("decision") in {"keep", "discard"}:
            done.add(str(item.get("id") or ""))
        if str(item.get("id") or "") not in done:
            pending.append(item)
    pending.sort(key=lambda item: (-int(item.get("priority", 0)), str(item.get("id"))))
    identifiers: list[str] = []
    for chosen in pending:
        edits = chosen.get("edits") or []
        identifier = str(chosen.get("id") or "")
        if chosen.get("status") == "open" and isinstance(edits, list) and edits and identifier:
            identifiers.append(identifier)
    return identifiers


def next_open_edit_id(repo: Path) -> str | None:
    """The first unsettled open edit, kept for callers that ask for one id."""
    identifiers = open_edit_ids(repo)
    return identifiers[0] if identifiers else None


def review_failures(repo: Path) -> list[str]:
    failures: list[str] = []
    pending = set(open_edit_ids(repo))
    for name, check in CHECKS.items():
        if name in pending:
            continue
        failures.extend(f"{name}: {item}" for item in check(repo))
    return failures


def write_metrics(attempt: Path, failures: list[str]) -> None:
    attempt.mkdir(parents=True, exist_ok=True)
    payload = {"checks_failed": len(failures), "checks": failures}
    text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    (attempt / "metrics.json").write_text(text, encoding="utf-8", newline="\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Development review gates")
    parser.add_argument("mode", choices=("review", "run"))
    parser.add_argument("--candidate", default="")
    parser.add_argument("--attempt-dir", default="")
    args = parser.parse_args(argv)
    if args.mode == "review":
        failures = review_failures(ROOT)
        if failures:
            print("\n".join(failures), file=sys.stderr)
            return 1
        print(f"review passed: {len(CHECKS)} checks")
        return 0
    attempt = Path(args.attempt_dir or "")
    if not args.candidate or not attempt:
        print("run requires --candidate and --attempt-dir", file=sys.stderr)
        return 2
    check = CHECKS.get(args.candidate)
    failures = [f"unknown candidate {args.candidate}"] if check is None else check(ROOT)
    write_metrics(attempt, failures)
    print(f"checks_failed={len(failures)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
