from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from company_agent.invoke import invoke
from company_agent.research_clock import _worktree
from company_agent.work_items import WorkItemStore

_SPEC = {
    "tenant_id": "team-a",
    "experiment_id": "exp-1",
    "task_id": "task-1",
    "project_id": "proj-1",
    "hypothesis": "warmup lowers validation loss",
    "falsifier": "the metric does not improve",
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


@pytest.fixture
def isolated(monkeypatch, tmp_path):
    monkeypatch.setenv("COMPANY_AGENT_RESEARCH_STATE", str(tmp_path / "clock"))
    monkeypatch.setenv("COMPANY_AGENT_WORK_ITEM_DB", str(tmp_path / "work.sqlite3"))
    return tmp_path


def test_compile_accepts_one_change_surface(isolated) -> None:
    result = invoke("company_research_compile", "lab", _SPEC)
    assert result.status == "ok"
    assert result.payload["ok"] is True
    assert result.payload["approval_required"] is False
    assert result.payload["error_code"] == ""
    assert result.payload["changed_path"] == "src/train/scheduler.py"


def test_compile_marks_hpc_for_approval(isolated) -> None:
    args = {**_SPEC, "resource_type": "hpc"}
    result = invoke("company_research_compile", "lab", args)
    assert result.status == "ok"
    assert result.payload["ok"] is True
    assert result.payload["approval_required"] is True


def test_unreproduced_baseline_does_not_run(isolated) -> None:
    args = {**_SPEC, "baseline_reproduced": False, "idempotency_key": "once"}
    result = invoke("company_research_run", "lab", args, approved=True)
    assert result.status == "ok"
    assert result.payload["ok"] is False
    assert result.payload["stop_reason"] == "invalid_candidate"
    assert result.payload["authority"] == "none"
    store = WorkItemStore()
    assert store.db.execute("select count(*) from tickets").fetchone()[0] == 0


def test_lab_run_records_a_candidate_and_not_a_ticket(isolated) -> None:
    asked = invoke("company_research_run", "lab", {**_SPEC, "idempotency_key": "run-1"})
    assert asked.status == "needs_ask"
    result = invoke(
        "company_research_run", "lab", {**_SPEC, "idempotency_key": "run-1"}, approved=True,
    )
    assert result.status == "ok"
    payload = result.payload
    assert payload["ok"] is True
    assert payload["executor"] == "stub"
    assert payload["stop_reason"] == "kept"
    assert payload["attempts"] == 1
    assert payload["decision"] == "keep"
    assert payload["decisions"] == "keep"
    assert payload["signal_type"] == "experiment.completed.v1"
    assert payload["authority"] == "candidate"
    assert payload["trigger_id"]
    store = WorkItemStore()
    assert store.db.execute("select count(*) from tickets").fetchone()[0] == 0
    assert store.db.execute("select count(*) from triggers").fetchone()[0] == 1
    status = invoke("company_research_status", "lab", {
        "tenant_id": "team-a", "experiment_id": "exp-1",
    })
    assert status.payload["recorded"] is True
    assert status.payload["stop_reason"] == "kept"
    assert status.payload["decisions"] == "keep"
    again = invoke(
        "company_research_run", "lab", {**_SPEC, "idempotency_key": "run-1"}, approved=True,
    )
    assert again.payload["trigger_id"] == payload["trigger_id"]
    assert store.db.execute("select count(*) from triggers").fetchone()[0] == 1


def test_same_file_runs_until_the_attempt_limit(isolated) -> None:
    args = {
        **_SPEC,
        "experiment_id": "exp-five",
        "baseline_metric": 0.95,
        "max_attempts": 5,
        "idempotency_key": "five",
    }
    result = invoke("company_research_run", "lab", args, approved=True)
    assert result.status == "ok"
    payload = result.payload
    assert payload["ok"] is True
    assert payload["executor"] == "stub"
    assert payload["stop_reason"] == "exhausted"
    assert payload["attempts"] == 5
    assert payload["decision"] == "discard"
    assert payload["decisions"] == "discard,discard,discard,discard,discard"
    assert payload["failure_count"] == 5
    assert payload["total_cost"] == 2
    assert payload["remaining_budget"] == 3
    assert payload["signal_type"] == "none"
    assert payload["authority"] == "none"
    assert payload["trigger_id"] == ""
    store = WorkItemStore()
    assert store.db.execute("select count(*) from tickets").fetchone()[0] == 0
    assert store.db.execute("select count(*) from triggers").fetchone()[0] == 0
    status = invoke("company_research_status", "algo", {
        "tenant_id": "team-a", "experiment_id": "exp-five",
    })
    assert status.payload["recorded"] is True
    assert status.payload["decisions"] == payload["decisions"]


def test_keep_stops_before_the_attempt_limit(isolated) -> None:
    args = {**_SPEC, "experiment_id": "exp-keep", "max_attempts": 5, "idempotency_key": "early"}
    result = invoke("company_research_run", "lab", args, approved=True)
    assert result.status == "ok"
    assert result.payload["stop_reason"] == "kept"
    assert result.payload["attempts"] == 1
    assert result.payload["decisions"] == "keep"
    assert result.payload["signal_type"] == "experiment.completed.v1"


def test_kept_candidate_opens_one_running_assignment(isolated, monkeypatch) -> None:
    monkeypatch.setenv("COMPANY_AGENT_SESSION_ID", "dsh:lab-session")
    result = invoke(
        "company_research_run",
        "lab",
        {**_SPEC, "experiment_id": "exp-auto", "idempotency_key": "auto-1"},
        approved=True,
    )
    assert result.status == "ok"
    trigger_id = result.payload["trigger_id"]
    assert trigger_id
    fields = {
        "action": "evaluate",
        "trigger_id": trigger_id,
        "strength": "explicit",
        "scope": "lab",
        "title": "exp-auto",
        "reason": "kept result",
        "evidence": "kept",
        "tenant_id": "team-a",
    }
    observed = invoke("company_work_item", "lab", {**fields, "mode": "observe"})
    assert observed.status == "ok"
    assert observed.payload["ticket_id"] == ""
    assert observed.payload["authority"] == "none"
    store = WorkItemStore()
    assert store.db.execute("select count(*) from tickets").fetchone()[0] == 0
    accepted = invoke("company_work_item", "lab", {**fields, "mode": "auto"})
    assert accepted.status == "ok"
    assert accepted.payload["authority"] == "mandate"
    assert accepted.payload["ticket_id"]
    assert accepted.payload["session_ref"] == "dsh:lab-session"
    assert accepted.payload["tool_pack"] == "company.workflow"
    again = invoke("company_work_item", "lab", {**fields, "mode": "auto"})
    assert again.payload["ticket_id"] == accepted.payload["ticket_id"]
    assert store.db.execute("select count(*) from tickets").fetchone()[0] == 1
    recovered = invoke("company_work_item", "lab", {"action": "recover", "tenant_id": "team-a"})
    assert recovered.status == "ok"
    assert recovered.payload["count"] == 1
    assert recovered.payload["items"][0]["execution_state"] == "running"
    assert recovered.payload["items"][0]["session_ref"] == "dsh:lab-session"


def test_qpu_run_is_a_device_handoff(isolated) -> None:
    args = {**_SPEC, "resource_type": "qpu", "idempotency_key": "qpu-1"}
    result = invoke("company_research_run", "lab", args, approved=True)
    assert result.status == "ok"
    assert result.payload["executor"] == "handoff"
    assert result.payload["stop_reason"] == "handoff"
    assert result.payload["authority"] == "candidate"
    assert result.payload["signal_type"] == "none"
    assert result.payload["resource_type"] == "qpu"
    assert result.payload["next_tool"] == "quantum_device_run"
    assert result.payload["approval_still_required"] is True
    assert result.payload["next_fields"] == "circuit_id,shots"
    store = WorkItemStore()
    text = store.db.execute("select text from triggers").fetchone()[0]
    assert text.startswith("device-approval ")
    assert store.db.execute("select count(*) from tickets").fetchone()[0] == 0


def test_run_is_hidden_outside_lab(isolated) -> None:
    args = {**_SPEC, "idempotency_key": "hidden"}
    for preset in ("boot", "algo", "sign"):
        result = invoke("company_research_run", preset, args, approved=True)
        assert result.status == "denied"
    algo = invoke("company_research_compile", "algo", _SPEC)
    assert algo.status == "ok"
    boot = invoke("company_research_compile", "boot", _SPEC)
    assert boot.status == "denied"


def test_status_is_empty_before_a_run(isolated) -> None:
    result = invoke("company_research_status", "algo", {
        "tenant_id": "team-a", "experiment_id": "exp-1",
    })
    assert result.status == "ok"
    assert result.payload["recorded"] is False
    assert result.payload["stop_reason"] == "none"
    assert result.payload["decisions"] == ""
    assert result.payload["next_tool"] == ""
    assert result.payload["approval_still_required"] is False
    assert result.payload["next_fields"] == ""


def test_sensitive_identifier_is_rejected(isolated) -> None:
    args = {**_SPEC, "hypothesis": "contains token material"}
    result = invoke("company_research_compile", "lab", args)
    assert result.status == "error"
    assert "invalid" in result.error


def test_hpc_run_hands_off_without_a_job_number(isolated) -> None:
    result = invoke(
        "company_research_run",
        "lab",
        {**_SPEC, "resource_type": "hpc", "idempotency_key": "hpc-1"},
        approved=True,
    )
    assert result.status == "ok"
    payload = result.payload
    assert payload["executor"] == "handoff"
    assert payload["stop_reason"] == "handoff"
    assert payload["authority"] == "candidate"
    assert payload["resource_type"] == "hpc"
    assert payload["next_tool"] == "hpc_submit"
    assert payload["approval_still_required"] is True
    assert payload["next_fields"] == "job_name,script"
    assert "673" not in str(payload)
    assert "twin_id" not in payload
    asked = invoke("hpc_submit", "lab", {"job_name": "smoke", "script": "/data/jobs/demo.sh"})
    assert asked.status == "needs_ask"
    store = WorkItemStore()
    text = store.db.execute("select text from triggers").fetchone()[0]
    assert text == "resource-handoff hpc hpc_submit"
    assert store.db.execute("select count(*) from tickets").fetchone()[0] == 0


def test_local_metric_keeps_the_improving_line(isolated, monkeypatch) -> None:
    root = isolated / "workspace"
    root.mkdir()
    (root / "metrics.log").write_text("val_loss=1.1000\nval_loss=0.9700\n", encoding="utf-8")
    monkeypatch.setenv("COMPANY_AGENT_RESEARCH_ROOT", str(root))
    result = invoke(
        "company_research_run",
        "lab",
        {**_SPEC, "changed_path": "metrics.log", "max_attempts": 5, "idempotency_key": "local-1"},
        approved=True,
    )
    assert result.status == "ok"
    assert result.payload["executor"] == "local"
    assert result.payload["stop_reason"] == "kept"
    assert result.payload["attempts"] == 2
    assert result.payload["decisions"] == "discard,keep"
    ledger = (isolated / "clock" / "ledger.tsv").read_text(encoding="utf-8")
    assert "keep\timprove" in ledger
    assert "hypothesis" not in ledger
    again = invoke(
        "company_research_run",
        "lab",
        {**_SPEC, "changed_path": "metrics.log", "idempotency_key": "local-2"},
        approved=True,
    )
    assert again.payload["ok"] is False
    assert again.payload["stop_reason"] == "invalid_candidate"


def test_local_timeout_stops_without_a_second_loop(isolated, monkeypatch) -> None:
    root = isolated / "workspace"
    root.mkdir()
    (root / "metrics.log").write_text("timeout\n", encoding="utf-8")
    monkeypatch.setenv("COMPANY_AGENT_RESEARCH_ROOT", str(root))
    result = invoke(
        "company_research_run",
        "lab",
        {**_SPEC, "changed_path": "metrics.log", "idempotency_key": "local-timeout"},
        approved=True,
    )
    assert result.payload["executor"] == "local"
    assert result.payload["stop_reason"] == "deadline"
    assert result.payload["failure_count"] == 1
    assert result.payload["trigger_id"] == ""


def test_local_budget_stops_before_later_lines(isolated, monkeypatch) -> None:
    root = isolated / "workspace"
    root.mkdir()
    (root / "metrics.log").write_text("val_loss=1.1000\nval_loss=0.9000\n", encoding="utf-8")
    monkeypatch.setenv("COMPANY_AGENT_RESEARCH_ROOT", str(root))
    result = invoke(
        "company_research_run",
        "lab",
        {
            **_SPEC,
            "changed_path": "metrics.log",
            "max_cost": 1,
            "max_attempts": 5,
            "idempotency_key": "local-budget",
        },
        approved=True,
    )
    assert result.payload["executor"] == "local"
    assert result.payload["stop_reason"] == "budget_exhausted"
    assert result.payload["attempts"] == 1
    assert result.payload["signal_type"] == "budget.exhausted.v1"
    assert result.payload["authority"] == "candidate"
    assert result.payload["next_fields"] == "max_cost"
    assert result.payload["approval_still_required"] is False
    status = invoke("company_research_status", "algo", {
        "tenant_id": "team-a", "experiment_id": "exp-1",
    })
    assert status.payload["next_fields"] == "max_cost"
    assert status.payload["next_tool"] == ""


def _git(root: Path, *args: str) -> None:
    git = shutil.which("git")
    if git is None:
        pytest.skip("git is unavailable")
    subprocess.run([git, *args], cwd=root, check=True, capture_output=True)


def _repo(root: Path) -> None:
    root.mkdir()
    _git(root, "init")
    (root / "README").write_text("base\n", encoding="utf-8")
    _git(root, "add", "README")
    _git(root, "-c", "user.email=dev@example.com", "-c", "user.name=dev", "commit", "-m", "base")


def test_cloud_run_hands_off_without_a_submission(isolated) -> None:
    result = invoke(
        "company_research_run",
        "lab",
        {**_SPEC, "resource_type": "cloud", "idempotency_key": "cloud-1"},
        approved=True,
    )
    assert result.status == "ok"
    payload = result.payload
    assert payload["executor"] == "handoff"
    assert payload["stop_reason"] == "handoff"
    assert payload["next_tool"] == "quantum_cloud_submit"
    assert payload["approval_still_required"] is True
    assert payload["next_fields"] == "program_path,target,shots"
    assert "twin_id" not in payload
    asked = invoke(
        "quantum_cloud_submit",
        "lab",
        {"program_path": "test.qasm", "target": "sim-fixture", "shots": 100},
    )
    assert asked.status == "needs_ask"
    store = WorkItemStore()
    text = store.db.execute("select text from triggers").fetchone()[0]
    assert text == "resource-handoff cloud quantum_cloud_submit"
    assert store.db.execute("select count(*) from tickets").fetchone()[0] == 0


def test_local_discard_removes_a_clean_worktree(isolated, monkeypatch) -> None:
    root = isolated / "repo"
    _repo(root)
    (root / "metrics.log").write_text("val_loss=1.1000\nval_loss=0.9700\n", encoding="utf-8")
    monkeypatch.setenv("COMPANY_AGENT_RESEARCH_ROOT", str(root))
    result = invoke(
        "company_research_run",
        "lab",
        {
            **_SPEC,
            "experiment_id": "exp-wt",
            "changed_path": "metrics.log",
            "max_attempts": 5,
            "idempotency_key": "wt-1",
        },
        approved=True,
    )
    assert result.status == "ok"
    assert result.payload["executor"] == "local"
    assert result.payload["decisions"] == "discard,keep"
    assert ".worktrees" not in str(result.payload)
    assert not (root / ".worktrees" / "exp-wt-attempt-1").exists()
    kept = root / ".worktrees" / "exp-wt-attempt-2"
    assert kept.is_dir()
    assert (kept / "metrics.log").read_text(encoding="utf-8") == "val_loss=0.9700\n"
    assert (root / "metrics.log").read_text(encoding="utf-8") == "val_loss=1.1000\nval_loss=0.9700\n"


def test_dirty_worktree_is_left_in_place(isolated) -> None:
    root = isolated / "repo"
    _repo(root)
    created = _worktree("create", root, "exp-dirty", 1)
    assert isinstance(created, dict) and created["state"] == "created"
    target = root / ".worktrees" / "exp-dirty-attempt-1"
    (target / "scratch.txt").write_text("local\n", encoding="utf-8")
    assert _worktree("remove", root, "exp-dirty", 1) == "dirty"
    assert target.is_dir()
    assert (target / "scratch.txt").is_file()


def test_digest_counts_runs_without_the_hypothesis(isolated, monkeypatch) -> None:
    root = isolated / "workspace"
    root.mkdir()
    (root / "metrics.log").write_text("val_loss=0.9700\n", encoding="utf-8")
    monkeypatch.setenv("COMPANY_AGENT_RESEARCH_ROOT", str(root))
    kept = invoke(
        "company_research_run",
        "lab",
        {**_SPEC, "changed_path": "metrics.log", "idempotency_key": "digest-keep"},
        approved=True,
    )
    assert kept.payload["stop_reason"] == "kept"
    handed = invoke(
        "company_research_run",
        "lab",
        {**_SPEC, "experiment_id": "exp-cloud", "resource_type": "cloud", "idempotency_key": "digest-cloud"},
        approved=True,
    )
    assert handed.payload["stop_reason"] == "handoff"
    digest = invoke("company_research_digest", "algo", {"tenant_id": "team-a"})
    assert digest.status == "ok"
    payload = digest.payload
    assert payload == {
        "ok": True,
        "runs": 2,
        "kept": 1,
        "discarded": 0,
        "handoffs": 1,
        "rejected": 0,
        "needs_decision": 0,
        "failure_count": 0,
        "total_cost": 1,
        "currency": "CNY",
    }
    assert "warmup" not in str(payload)
    denied = invoke("company_research_digest", "boot", {"tenant_id": "team-a"})
    assert denied.status == "denied"


def test_local_guardrail_discards_a_slower_improvement(isolated, monkeypatch) -> None:
    root = isolated / "workspace"
    root.mkdir()
    (root / "metrics.log").write_text(
        "val_loss=0.9700 train_time_seconds=200\nval_loss=0.9700 train_time_seconds=100\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("COMPANY_AGENT_RESEARCH_ROOT", str(root))
    result = invoke(
        "company_research_run",
        "lab",
        {
            **_SPEC,
            "changed_path": "metrics.log",
            "baseline_train_time_seconds": 100,
            "max_attempts": 5,
            "idempotency_key": "guard-1",
        },
        approved=True,
    )
    assert result.status == "ok"
    assert result.payload["decisions"] == "discard,keep"
    assert result.payload["stop_reason"] == "kept"
    ledger = (isolated / "clock" / "ledger.tsv").read_text(encoding="utf-8")
    assert "discard\tguardrail" in ledger


def test_local_seed_spread_stops_for_a_new_change(isolated, monkeypatch) -> None:
    root = isolated / "workspace"
    root.mkdir()
    (root / "metrics.log").write_text(
        "attempt=1 seed=1 val_loss=0.2000\n"
        "attempt=1 seed=2 val_loss=1.0000\n"
        "attempt=1 seed=3 val_loss=1.8000\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("COMPANY_AGENT_RESEARCH_ROOT", str(root))
    result = invoke(
        "company_research_run",
        "lab",
        {
            **_SPEC,
            "changed_path": "metrics.log",
            "min_seeds": 3,
            "max_attempts": 5,
            "idempotency_key": "seeds-1",
        },
        approved=True,
    )
    assert result.status == "ok"
    assert result.payload["attempts"] == 1
    assert result.payload["decision"] == "extend"
    assert result.payload["stop_reason"] == "stopped"
    assert result.payload["next_fields"] == "changed_path"
    digest = invoke("company_research_digest", "lab", {"tenant_id": "team-a"})
    assert digest.payload["needs_decision"] == 1
    assert "0.2000" not in str(digest.payload)
