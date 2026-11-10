from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = Path(os.environ.get("COMPANY_AGENT_RUNTIME_DIR",
               Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
               / "unitqc-company-agent" / "dsh-runtime"))


def _node() -> Path:
    base = RUNTIME / "node_modules" / "node" / "bin"
    for name in ("node.exe", "node"):
        candidate = base / name
        if candidate.is_file():
            return candidate
    return base / "node"


def test_real_dsh_seat_indexes_literature_and_hands_off_scale_card(tmp_path: Path) -> None:
    node = _node()
    if not node.is_file():
        pytest.skip("pinned DSH runtime missing; run scripts/bootstrap_dsh.sh")
    from company_agent.literature_card import draft_scale_card

    workspace = tmp_path / "seat"
    workspace.mkdir()
    shutil.copytree(ROOT / "tests" / "fixtures" / "literature", workspace / "paper")
    (workspace / "search.json").write_text(
        json.dumps({"records": [{"paper_id": "demo1", "source": "arxiv", "year": 2024}]}),
        encoding="utf-8",
    )
    local = {
        "tenant_id": "team-a",
        "experiment_id": "exp-local",
        "task_id": "task-local",
        "project_id": "proj-1",
        "hypothesis": "warmup lowers validation loss",
        "falsifier": "the metric does not improve",
        "baseline_name": "recorded",
        "baseline_source": "internal",
        "baseline_metric": 1.0,
        "baseline_reproduced": True,
        "baseline_train_time_seconds": 3600,
        "changed_path": "src/train/scheduler.py",
        "primary_metric": "val_loss",
        "direction": "minimize",
        "resource_type": "cpu",
        "max_cost": 1,
        "max_attempts": 1,
        "idempotency_key": "local-1",
    }
    draft = draft_scale_card(
        local,
        experiment_id="exp-scale",
        idempotency_key="scale-1",
        hypothesis="more nodes keep the same validation loss",
        falsifier="the metric moves outside tolerance",
    )
    human = {**draft, "baseline_reproduced": True}
    node_bin = str(node.parent)
    env = {
        "PATH": node_bin + os.pathsep + os.environ.get("PATH", ""),
        "HOME": str(Path.home()),
        "DSH_TELEMETRY_MODE": "DISABLED",
        "COMPANY_AGENT_TEST_ROOT": str(ROOT),
        "COMPANY_AGENT_TEST_MODULES": str(RUNTIME / "node_modules" / ".pnpm" / "node_modules"),
        "COMPANY_AGENT_PROFILE": "company-agent",
        "COMPANY_AGENT_PRESET": "lab",
        "COMPANY_AGENT_PYTHON": sys.executable,
        "COMPANY_AGENT_PYTHONPATH": str(ROOT / "src"),
        "COMPANY_AGENT_CONTRACTS_DIR": str(ROOT / "contracts"),
        "COMPANY_AGENT_TURN_ID": f"seat-{uuid.uuid4().hex[:16]}",
        "COMPANY_AGENT_RECEIPT_DIR": tempfile.mkdtemp(prefix="company-agent-seat-"),
        "COMPANY_AGENT_RESEARCH_STATE": str(tmp_path / "clock"),
        "COMPANY_AGENT_WORK_ITEM_DB": str(tmp_path / "work.sqlite3"),
        "PROBE_WORKSPACE": str(workspace),
        "PROBE_COMPILE": json.dumps(
            {key: value for key, value in human.items() if key != "idempotency_key"},
        ),
        "PROBE_RUN": json.dumps(human),
    }
    if os.name == "nt":
        env["SystemRoot"] = os.environ.get("SystemRoot", "")
        env["windir"] = os.environ.get("windir", "")
        env["SYSTEMDRIVE"] = os.environ.get("SYSTEMDRIVE", "")
    result = subprocess.run(
        [str(node), str(ROOT / "tests" / "fixtures" / "dsh-literature-seat.mjs")],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    report = json.loads(result.stdout)
    assert report["asks"] == 1
    assert report["approvalTools"] == ["company_research_run"]
    assert [row["name"] for row in report["calls"]] == [
        "company_literature_search",
        "company_literature_fetch",
        "company_literature_index",
        "company_research_compile",
        "company_research_run",
    ]
    assert len(report["results"]) == len(report["calls"])
    by_name = {}
    for call, row in zip(report["calls"], report["results"], strict=True):
        assert row["errored"] is False, row["text"]
        by_name[call["name"]] = row["payload"]
    assert by_name["company_literature_search"]["paper_ids"] == ["demo1"]
    assert by_name["company_literature_search"]["exhaustive"] is False
    assert by_name["company_literature_index"]["clock_admitted"] is False
    assert by_name["company_literature_index"]["platform_metric_eligible"] is False
    assert "\\approx" not in json.dumps(by_name["company_literature_index"])
    assert by_name["company_research_compile"]["approval_required"] is True
    assert by_name["company_research_run"]["next_tool"] == "hpc_submit"
    assert by_name["company_research_run"]["approval_still_required"] is True
    assert "hpc_submit" not in report["approvalTools"]
