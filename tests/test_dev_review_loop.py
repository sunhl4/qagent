from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str):
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


LOOP = _load("dev_review_loop")
GATES = _load("dev_review_gates")
PROPOSE = _load("dev_review_propose")

WORKER = """
import json, os, sys
from pathlib import Path
cid = os.environ["COMPANY_DEV_REVIEW_CANDIDATE"]
if cid.startswith("crash"):
    sys.exit(1)
root = Path(os.environ["COMPANY_DEV_REVIEW_ATTEMPT_DIR"])
failed = 1 if cid == "bad" else 0
(root / "metrics.json").write_text(json.dumps({"checks_failed": failed}), encoding="utf-8")
"""


def _candidate(identifier: str, **extra) -> dict:
    item = {
        "id": identifier,
        "hypothesis": f"candidate {identifier} is measured from its own attempt",
        "cost": 1,
    }
    item.update(extra)
    return item


def _write_plan(
    tmp: Path,
    candidates: list[dict],
    *,
    loop: dict | None = None,
    resources: dict | None = None,
    run_command: list[str] | None = None,
    review: str = "print('reviewed')\n",
    proposal_command: list[str] | None = None,
) -> Path:
    worker = tmp / "worker.py"
    worker.write_text(WORKER, encoding="utf-8")
    review_script = tmp / "review.py"
    review_script.write_text(review, encoding="utf-8")
    plan = {
        "task_id": "dev-review",
        "experiment_id": "circle",
        "repo_root": ".",
        "review_commands": [[sys.executable, str(review_script)]],
        "run_command": run_command or [sys.executable, str(worker)],
        "metric": {
            "primary": "checks_failed",
            "file": "metrics.json",
            "direction": "minimize",
            "baseline": 1,
            "minimum_effect": 1,
        },
        "resources": {"timeout_seconds": 60, "budget_total": 10, "currency": "check"},
        "loop": {
            "max_rounds": 10,
            "max_attempts": 10,
            "max_consecutive_failures": 1,
            "stop_on_keep": False,
        },
        "required_artifacts": [
            "command.json", "stdout.log", "stderr.log", "metrics.json", "attempt.json",
        ],
        "candidates": candidates,
    }
    if proposal_command is not None:
        plan["proposal_command"] = proposal_command
    if resources:
        plan["resources"].update(resources)
    if loop:
        plan["loop"].update(loop)
    path = tmp / "plan.json"
    path.write_text(json.dumps(plan), encoding="utf-8")
    return path


def _run(tmp: Path, plan: Path, **kwargs):
    return LOOP.run_dev_review_loop(plan, output_dir=tmp / "out", **kwargs)


def test_scheduler_sets_match() -> None:
    assert LOOP.SCHEDULER_COMMANDS == GATES.SCHEDULER_COMMANDS


def _proposal_command(tmp: Path, items: list[dict], ledger: str = "") -> list[str]:
    catalog = tmp / "catalog.json"
    catalog.write_text(json.dumps({"candidates": items}), encoding="utf-8")
    ledger_path = tmp / "LEDGER.md"
    ledger_path.write_text(ledger, encoding="utf-8")
    return [
        sys.executable,
        str(ROOT / "scripts" / "dev_review_propose.py"),
        "--catalog",
        str(catalog),
        "--ledger",
        str(ledger_path),
        "--history",
        "{history}",
        "--output",
        "{output}",
    ]


def _unsettled_catalog() -> list[dict]:
    catalog = json.loads((ROOT / "docs" / "dev-review" / "catalog.json").read_text(encoding="utf-8"))
    ledger = (ROOT / "docs" / "dev-review" / "LEDGER.md").read_text(encoding="utf-8")
    done = {match.group(1) for match in re.finditer(r"`([a-z0-9-]+)`\s+(?:keep|discard)\b", ledger)}
    pending = []
    for item in catalog["candidates"]:
        if item.get("decision") in {"keep", "discard"}:
            done.add(item["id"])
        if item["id"] not in done:
            pending.append(item)
    pending.sort(key=lambda item: (-int(item.get("priority", 0)), item["id"]))
    return pending


def test_shipped_plan_measures_unsettled_catalog_items(tmp_path: Path) -> None:
    assert GATES.review_failures(ROOT) == []
    result = LOOP.run_dev_review_loop(
        ROOT / "docs" / "dev-review" / "plan.json",
        output_dir=tmp_path / "out",
    )
    pending = _unsettled_catalog()
    ready: list[str] = []
    for item in pending:
        if item.get("kind") == "implement" and item.get("status") != "ready":
            break
        ready.append(item["id"])
    assert [item["candidate_id"] for item in result["attempts"]] == ready
    assert [item["decision"]["action"] for item in result["attempts"]] == ["keep"] * len(ready)
    assert [item["metric"]["value"] for item in result["attempts"]] == [0] * len(ready)
    settled = {
        "development-order",
        "device-policy",
        "not-a-second-runtime",
        "early-stop-disabled",
    }
    assert settled.isdisjoint(item["candidate_id"] for item in result["attempts"])
    if len(ready) == len(pending):
        assert result["stop_reason"] == "requires_new_review", result
        assert result["pending_candidates"] == []
        return
    assert result["stop_reason"] == "needs_implementation", result
    assert result["pending_candidates"][0]["id"] == pending[len(ready)]["id"]


def test_dry_run_does_not_measure(tmp_path: Path) -> None:
    result = LOOP.run_dev_review_loop(
        ROOT / "docs" / "dev-review" / "plan.json",
        output_dir=tmp_path / "out",
        dry_run=True,
    )
    assert result["stop_reason"] == "planned"
    assert result["attempts"] == []
    assert list((tmp_path / "out").glob("attempt-*/metrics.json")) == []
    assert list((tmp_path / "out").glob("proposal-*")) == []


def test_dry_run_of_inline_candidates_does_not_measure(tmp_path: Path) -> None:
    plan = _write_plan(tmp_path, [_candidate("good")])
    result = LOOP.run_dev_review_loop(plan, output_dir=tmp_path / "out", dry_run=True)
    assert result["stop_reason"] == "planned"
    assert [item["decision"]["action"] for item in result["attempts"]] == ["planned"]
    assert list((tmp_path / "out").glob("attempt-*/metrics.json")) == []


def test_discard_does_not_hide_a_later_keep(tmp_path: Path) -> None:
    plan = _write_plan(tmp_path, [_candidate("bad"), _candidate("good")])
    result = _run(tmp_path, plan)
    assert result["stop_reason"] == "discarded"
    assert [item["candidate_id"] for item in result["attempts"]] == ["bad", "good"]
    assert [item["decision"]["action"] for item in result["attempts"]] == ["discard", "keep"]


def test_stop_on_keep_leaves_the_rest_of_the_queue(tmp_path: Path) -> None:
    plan = _write_plan(
        tmp_path,
        [_candidate("one"), _candidate("two")],
        loop={"stop_on_keep": True},
    )
    result = _run(tmp_path, plan)
    assert result["stop_reason"] == "kept"
    assert len(result["attempts"]) == 1
    assert result["pending_candidates"][0]["id"] == "two"
    assert "stop_on_keep" in LOOP.render_status(result)


def test_scheduler_command_is_withheld(tmp_path: Path) -> None:
    plan = _write_plan(
        tmp_path,
        [_candidate("submit"), _candidate("later")],
        run_command=["sbatch", "work.sh"],
    )
    result = _run(tmp_path, plan)
    assert result["stop_reason"] == "withheld"
    assert result["attempts"][0]["execution"]["launched"] is False
    assert result["pending_candidates"][0]["id"] == "later"


def test_missing_metric_escalates(tmp_path: Path) -> None:
    plan = _write_plan(
        tmp_path,
        [_candidate("empty")],
        run_command=[sys.executable, "-c", "print('no metric')"],
    )
    result = _run(tmp_path, plan)
    assert result["stop_reason"] == "escalated"
    assert result["attempts"][0]["metric"]["value"] is None


def test_consecutive_command_failures_stop(tmp_path: Path) -> None:
    plan = _write_plan(
        tmp_path,
        [_candidate("crash"), _candidate("crash-two"), _candidate("later")],
        loop={"max_consecutive_failures": 2},
    )
    result = _run(tmp_path, plan)
    assert result["stop_reason"] == "consecutive_failures"
    assert [item["candidate_id"] for item in result["attempts"]] == ["crash", "crash-two"]
    assert result["pending_candidates"][0]["id"] == "later"


def test_budget_stops_before_launch(tmp_path: Path) -> None:
    plan = _write_plan(tmp_path, [_candidate("costly", cost=5)], resources={"budget_total": 4})
    result = _run(tmp_path, plan)
    assert result["stop_reason"] == "budget"
    assert result["attempts"] == []
    assert result["pending_candidates"][0]["id"] == "costly"


def test_past_deadline_starts_nothing(tmp_path: Path) -> None:
    plan = _write_plan(tmp_path, [_candidate("late")], loop={"deadline_at": "2000-01-01T00:00:00+00:00"})
    result = _run(tmp_path, plan)
    assert result["stop_reason"] == "deadline"
    assert result["attempts"] == []
    assert list((tmp_path / "out" / "reviews").glob("*")) == []


def test_task_list_is_not_cut_by_the_numeric_floor(tmp_path: Path) -> None:
    plan = _write_plan(
        tmp_path,
        [_candidate("one"), _candidate("two"), _candidate("three")],
        resources={"budget_total": 1, "timeout_seconds": None},
        loop={"max_rounds": 1, "max_attempts": 1, "task_bound": True},
    )
    result = _run(tmp_path, plan)
    assert [item["candidate_id"] for item in result["attempts"]] == ["one", "two", "three"]
    assert result["stop_reason"] == "drained"


def test_round_limit_does_not_mark_pending_work_done(tmp_path: Path) -> None:
    plan = _write_plan(tmp_path, [_candidate("one"), _candidate("two")], loop={"max_rounds": 1})
    result = _run(tmp_path, plan)
    assert result["stop_reason"] == "max_rounds"
    assert len(result["attempts"]) == 1
    assert result["pending_candidates"][0]["id"] == "two"


def test_open_implement_candidate_waits_for_one_change(tmp_path: Path) -> None:
    plan = _write_plan(tmp_path, [
        _candidate(
            "write-note",
            kind="implement",
            status="open",
            allowed_paths=["docs/dev-review-loop.zh-CN.md"],
        ),
    ])
    result = _run(tmp_path, plan)
    assert result["stop_reason"] == "needs_implementation"
    assert result["attempts"] == []
    text = LOOP.render_status(result)
    assert "write-note" in text
    assert "docs/dev-review-loop.zh-CN.md" in text


def test_implement_candidate_must_name_a_test(tmp_path: Path) -> None:
    plan = _write_plan(tmp_path, [
        _candidate("adapter", kind="implement", status="open", allowed_paths=["src/company_agent/cli.py"]),
    ])
    result = _run(tmp_path, plan)
    assert result["stop_reason"] == "development_order"
    assert result["attempts"] == []


def test_ready_implement_candidate_is_measured(tmp_path: Path) -> None:
    plan = _write_plan(tmp_path, [
        _candidate(
            "adapter",
            kind="implement",
            status="ready",
            allowed_paths=["src/company_agent/cli.py", "tests/test_dev_review_loop.py"],
        ),
    ])
    result = _run(tmp_path, plan)
    assert result["stop_reason"] == "drained"
    assert result["attempts"][0]["decision"]["action"] == "keep"


def test_candidate_cannot_carry_its_own_metric(tmp_path: Path) -> None:
    plan = _write_plan(tmp_path, [_candidate("self-report", checks_failed=0)])
    try:
        _run(tmp_path, plan)
    except ValueError as exc:
        assert "cannot carry its own metric" in str(exc)
    else:
        raise AssertionError("self-reported metric was accepted")


def test_resume_of_a_finished_circle_does_not_repeat_it(tmp_path: Path) -> None:
    plan = _write_plan(tmp_path, [_candidate("good")])
    first = _run(tmp_path, plan)
    assert first["stop_reason"] == "drained"
    state_path = tmp_path / "out" / "loop-state.json"
    second = LOOP.run_dev_review_loop(plan, output_dir=tmp_path / "out", resume=state_path)
    assert second["loop_id"] == first["loop_id"]
    assert len(second["attempts"]) == 1
    assert len(list((tmp_path / "out" / "reviews").glob("*"))) == 1


def test_interrupted_operation_is_not_rerun(tmp_path: Path) -> None:
    plan = _write_plan(tmp_path, [_candidate("good")])
    first = _run(tmp_path, plan)
    state_path = tmp_path / "out" / "loop-state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["active_operation"] = {"kind": "attempt", "path": "unfinished"}
    state_path.write_text(json.dumps(state), encoding="utf-8")
    second = LOOP.run_dev_review_loop(plan, output_dir=tmp_path / "out", resume=state_path)
    assert second["stop_reason"] == "interrupted"
    assert len(second["attempts"]) == len(first["attempts"])


def test_resume_rejects_a_changed_plan(tmp_path: Path) -> None:
    plan = _write_plan(tmp_path, [_candidate("good")])
    _run(tmp_path, plan)
    state_path = tmp_path / "out" / "loop-state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["config_sha256"] = "0" * 64
    state_path.write_text(json.dumps(state), encoding="utf-8")
    try:
        LOOP.run_dev_review_loop(plan, output_dir=tmp_path / "out", resume=state_path)
    except ValueError as exc:
        assert "plan hash" in str(exc)
    else:
        raise AssertionError("changed plan was resumed")


def test_source_change_during_review_fails_closed(tmp_path: Path) -> None:
    review = (
        "from pathlib import Path\n"
        "path = Path(__file__)\n"
        "path.write_text(path.read_text(encoding='utf-8') + '\\n', encoding='utf-8')\n"
    )
    plan = _write_plan(tmp_path, [_candidate("good")], review=review)
    result = _run(tmp_path, plan)
    assert result["stop_reason"] == "source_changed"
    assert result["attempts"] == []


def test_status_out_appends_the_ledger(tmp_path: Path) -> None:
    plan = _write_plan(tmp_path, [_candidate("good")])
    status = tmp_path / "notes" / "STATUS.md"
    arguments = ["--config", str(plan), "--status-out", str(status)]
    assert LOOP.main([*arguments, "--output-dir", str(tmp_path / "out")]) == 0
    assert LOOP.main([*arguments, "--output-dir", str(tmp_path / "out-2")]) == 0
    ledger = status.with_name("LEDGER.md").read_text(encoding="utf-8")
    assert ledger.count("停止：`drained`") == 2
    assert "is measured" not in ledger
    assert status.read_text(encoding="utf-8").count("停止原因：`drained`") == 1


def test_status_for_a_drained_circle_asks_for_a_new_round(tmp_path: Path) -> None:
    plan = _write_plan(tmp_path, [_candidate("good")])
    result = _run(tmp_path, plan)
    text = LOOP.render_status(result)
    assert "停止原因：`drained`" in text
    assert "新的输出目录" in text


def test_proposer_skips_settled_ids_and_returns_the_next() -> None:
    catalog = {
        "candidates": [
            {"id": "old", "decision": "keep", "priority": 50, "hypothesis": "done", "cost": 1},
            {
                "id": "next-item",
                "priority": 10,
                "hypothesis": "wire the proposer",
                "cost": 1,
                "kind": "verify",
                "status": "ready",
            },
        ]
    }
    chosen, diagnosis = PROPOSE.propose_from_history([], catalog, "")
    assert [item["id"] for item in chosen] == ["next-item"]
    assert "decision" not in chosen[0]
    assert diagnosis["next"] == "next-item"


def test_proposer_reports_when_the_catalog_is_exhausted() -> None:
    catalog = {
        "candidates": [
            {"id": "old", "decision": "keep", "priority": 1, "hypothesis": "done", "cost": 1},
        ]
    }
    chosen, diagnosis = PROPOSE.propose_from_history([], catalog, "")
    assert chosen == []
    assert diagnosis["reason"] == "requires_new_review"


def test_proposer_does_not_retry_a_discard() -> None:
    catalog = {
        "candidates": [
            {"id": "bad", "priority": 9, "hypothesis": "stay discarded", "cost": 1},
            {"id": "good", "priority": 1, "hypothesis": "still open", "cost": 1},
        ]
    }
    history = [{"candidate_id": "bad", "decision": {"action": "discard"}}]
    chosen, _diagnosis = PROPOSE.propose_from_history(history, catalog, "")
    assert [item["id"] for item in chosen] == ["good"]


def test_proposer_skips_ids_already_kept_in_the_ledger() -> None:
    catalog = {
        "candidates": [
            {"id": "old", "priority": 5, "hypothesis": "done", "cost": 1},
            {"id": "next-item", "priority": 1, "hypothesis": "still open", "cost": 1},
        ]
    }
    chosen, _diagnosis = PROPOSE.propose_from_history([], catalog, "- 候选：`old` keep\n")
    assert [item["id"] for item in chosen] == ["next-item"]


def test_catalog_item_is_measured_then_the_catalog_is_exhausted(tmp_path: Path) -> None:
    items = [
        {
            "id": "good",
            "priority": 1,
            "hypothesis": "measure the next catalog item",
            "cost": 1,
            "kind": "verify",
            "status": "ready",
        }
    ]
    plan = _write_plan(tmp_path, [], proposal_command=_proposal_command(tmp_path, items))
    result = _run(tmp_path, plan)
    assert result["stop_reason"] == "requires_new_review", result
    assert [item["candidate_id"] for item in result["attempts"]] == ["good"]
    assert result["attempts"][0]["decision"]["action"] == "keep"
    assert result["attempts"][0]["metric"]["value"] == 0


def test_discarded_catalog_item_is_not_retried(tmp_path: Path) -> None:
    items = [
        {"id": "bad", "priority": 20, "hypothesis": "a failed check stays discarded", "cost": 1},
        {"id": "good", "priority": 10, "hypothesis": "the next catalog item is measured", "cost": 1},
    ]
    plan = _write_plan(tmp_path, [], proposal_command=_proposal_command(tmp_path, items))
    result = _run(tmp_path, plan)
    assert result["stop_reason"] == "discarded", result
    assert [item["candidate_id"] for item in result["attempts"]] == ["bad", "good"]
    assert [item["decision"]["action"] for item in result["attempts"]] == ["discard", "keep"]


def test_empty_proposal_does_not_launch_an_attempt(tmp_path: Path) -> None:
    items = [
        {"id": "old", "decision": "keep", "priority": 1, "hypothesis": "done", "cost": 1},
    ]
    plan = _write_plan(tmp_path, [], proposal_command=_proposal_command(tmp_path, items))
    result = _run(tmp_path, plan)
    assert result["stop_reason"] == "requires_new_review"
    assert result["attempts"] == []
    assert list((tmp_path / "out").glob("attempt-*")) == []


def test_open_implement_from_the_proposer_waits(tmp_path: Path) -> None:
    items = [
        {
            "id": "later",
            "priority": 1,
            "kind": "implement",
            "status": "open",
            "hypothesis": "wait for a reviewed edit",
            "allowed_paths": ["docs/dev-review-loop.zh-CN.md"],
            "cost": 1,
        }
    ]
    plan = _write_plan(tmp_path, [], proposal_command=_proposal_command(tmp_path, items))
    result = _run(tmp_path, plan)
    assert result["stop_reason"] == "needs_implementation"
    assert result["attempts"] == []
    assert result["pending_candidates"][0]["id"] == "later"


def test_repeated_proposal_fails_closed(tmp_path: Path) -> None:
    script = tmp_path / "always.py"
    script.write_text(
        "import json, sys\n"
        "from pathlib import Path\n"
        "out = Path(sys.argv[sys.argv.index('--output') + 1])\n"
        "item = {'id': 'again', 'hypothesis': 'again', 'cost': 1}\n"
        "out.write_text(json.dumps([item]), encoding='utf-8')\n",
        encoding="utf-8",
    )
    command = [sys.executable, str(script), "--output", "{output}", "--history", "{history}"]
    plan = _write_plan(tmp_path, [], proposal_command=command)
    result = _run(tmp_path, plan)
    assert result["stop_reason"] == "failed", result
    assert [item["candidate_id"] for item in result["attempts"]] == ["again"]
    assert result["attempts"][0]["decision"]["action"] == "keep"


def test_exhausted_catalog_exits_clean(tmp_path: Path) -> None:
    items = [
        {
            "id": "old",
            "decision": "keep",
            "priority": 1,
            "hypothesis": "catalog text stays out",
            "cost": 1,
        }
    ]
    plan = _write_plan(tmp_path, [], proposal_command=_proposal_command(tmp_path, items))
    status = tmp_path / "STATUS.md"
    code = LOOP.main(
        [
            "--config",
            str(plan),
            "--output-dir",
            str(tmp_path / "out"),
            "--status-out",
            str(status),
        ]
    )
    assert code == 0
    ledger = status.with_name("LEDGER.md").read_text(encoding="utf-8")
    assert "停止：`requires_new_review`" in ledger
    assert "catalog text stays out" not in ledger


def test_proposer_passes_edits_through() -> None:
    edit = {"path": "docs/note.md", "old": "before", "new": "after"}
    catalog = {
        "candidates": [
            {
                "id": "write-note",
                "priority": 1,
                "hypothesis": "pass the edit",
                "cost": 1,
                "kind": "implement",
                "status": "open",
                "allowed_paths": ["docs/note.md"],
                "edits": [edit],
            }
        ]
    }
    chosen, _diagnosis = PROPOSE.propose_from_history([], catalog, "")
    assert chosen[0]["edits"] == [edit]
    assert "priority" not in chosen[0]


def test_loop_applies_open_edits_and_keeps_them(tmp_path: Path) -> None:
    note = tmp_path / "docs" / "note.md"
    note.parent.mkdir()
    note.write_text("before\n", encoding="utf-8", newline="\n")
    items = [
        {
            "id": "write-note",
            "priority": 1,
            "kind": "implement",
            "status": "open",
            "hypothesis": "the loop writes the reviewed edit",
            "allowed_paths": ["docs/note.md"],
            "cost": 1,
            "edits": [{"path": "docs/note.md", "old": "before", "new": "after"}],
        }
    ]
    plan = _write_plan(tmp_path, [], proposal_command=_proposal_command(tmp_path, items))
    result = _run(tmp_path, plan)
    assert result["stop_reason"] == "requires_new_review", result
    assert result["attempts"][0]["decision"]["action"] == "keep"
    assert result["attempts"][0]["edited"] == ["docs/note.md"]
    assert result["attempts"][0]["reverted"] is False
    assert note.read_text(encoding="utf-8") == "after\n"


def test_discarded_edit_is_restored(tmp_path: Path) -> None:
    note = tmp_path / "docs" / "note.md"
    note.parent.mkdir()
    note.write_text("before\n", encoding="utf-8", newline="\n")
    plan = _write_plan(tmp_path, [
        _candidate(
            "bad",
            kind="implement",
            status="open",
            allowed_paths=["docs/note.md"],
            edits=[{"path": "docs/note.md", "old": "before", "new": "after"}],
        ),
    ])
    result = _run(tmp_path, plan)
    assert result["stop_reason"] == "discarded", result
    assert result["attempts"][0]["reverted"] is True
    assert note.read_text(encoding="utf-8") == "before\n"


def test_edit_outside_the_allow_list_is_not_written(tmp_path: Path) -> None:
    note = tmp_path / "docs" / "note.md"
    other = tmp_path / "docs" / "other.md"
    note.parent.mkdir()
    note.write_text("before\n", encoding="utf-8", newline="\n")
    other.write_text("stay\n", encoding="utf-8", newline="\n")
    plan = _write_plan(tmp_path, [
        _candidate(
            "write-note",
            kind="implement",
            status="open",
            allowed_paths=["docs/note.md"],
            edits=[{"path": "docs/other.md", "old": "stay", "new": "changed"}],
        ),
    ])
    result = _run(tmp_path, plan)
    assert result["stop_reason"] == "failed", result
    assert result["attempts"] == []
    assert note.read_text(encoding="utf-8") == "before\n"
    assert other.read_text(encoding="utf-8") == "stay\n"


def test_dry_run_does_not_apply_edits(tmp_path: Path) -> None:
    note = tmp_path / "docs" / "note.md"
    note.parent.mkdir()
    note.write_text("before\n", encoding="utf-8", newline="\n")
    plan = _write_plan(tmp_path, [
        _candidate(
            "write-note",
            kind="implement",
            status="open",
            allowed_paths=["docs/note.md"],
            edits=[{"path": "docs/note.md", "old": "before", "new": "after"}],
        ),
    ])
    result = _run(tmp_path, plan, dry_run=True)
    assert result["stop_reason"] == "planned"
    assert note.read_text(encoding="utf-8") == "before\n"


def test_loop_refuses_to_edit_its_own_runner(tmp_path: Path) -> None:
    script = tmp_path / "scripts" / "worker.py"
    script.parent.mkdir()
    script.write_text(WORKER, encoding="utf-8", newline="\n")
    plan = _write_plan(
        tmp_path,
        [
            _candidate(
                "write-note",
                kind="implement",
                status="open",
                allowed_paths=["scripts/worker.py"],
                edits=[{
                    "path": "scripts/worker.py",
                    "old": "checks_failed",
                    "new": "checks_passed",
                }],
            ),
        ],
        run_command=[sys.executable, str(script)],
    )
    result = _run(tmp_path, plan)
    assert result["stop_reason"] == "failed", result
    assert "checks_passed" not in script.read_text(encoding="utf-8")


def test_review_names_only_the_open_edit(tmp_path: Path) -> None:
    catalog = tmp_path / "docs" / "dev-review"
    catalog.mkdir(parents=True)
    (catalog / "catalog.json").write_text(json.dumps({
        "candidates": [
            {"id": "kept-item", "decision": "keep", "priority": 5, "status": "ready"},
            {
                "id": "portal-unset",
                "priority": 1,
                "status": "open",
                "edits": [{"path": "apps/company-workspace/host.mjs", "old": "a", "new": "b"}],
            },
            {
                "id": "probe-path",
                "priority": 1,
                "status": "open",
                "edits": [{"path": "apps/company-workspace/host.mjs", "old": "c", "new": "d"}],
            },
        ]
    }), encoding="utf-8")
    (catalog / "LEDGER.md").write_text("- 候选：`kept-item` keep\n", encoding="utf-8")
    assert GATES.open_edit_ids(tmp_path) == ["portal-unset", "probe-path"]
    assert GATES.next_open_edit_id(tmp_path) == "portal-unset"
    (catalog / "LEDGER.md").write_text(
        "- 候选：`kept-item` keep\n- 候选：`portal-unset` keep\n",
        encoding="utf-8",
    )
    assert GATES.open_edit_ids(tmp_path) == ["probe-path"]


def test_kernel_launcher_is_not_editable(tmp_path: Path) -> None:
    plan = _write_plan(tmp_path, [
        _candidate(
            "launcher",
            kind="implement",
            status="open",
            allowed_paths=["scripts/dsh-cli.mjs"],
        ),
    ])
    result = _run(tmp_path, plan)
    assert result["stop_reason"] == "kernel_frozen", result
    assert result["attempts"] == []


def test_installed_runtime_tree_is_not_editable(tmp_path: Path) -> None:
    plan = _write_plan(tmp_path, [
        _candidate(
            "vendor",
            kind="implement",
            status="open",
            allowed_paths=["profiles/company-agent/node_modules/dsh/index.js"],
        ),
    ])
    result = _run(tmp_path, plan)
    assert result["stop_reason"] == "kernel_frozen", result
    assert result["attempts"] == []


def test_native_ui_needs_a_test_and_can_then_wait_for_edits(tmp_path: Path) -> None:
    missing = _write_plan(tmp_path, [
        _candidate(
            "screen",
            kind="implement",
            status="open",
            allowed_paths=["apps/company-workspace/workspace.css"],
        ),
    ])
    refused = _run(tmp_path, missing)
    assert refused["stop_reason"] == "development_order"
    ready = tmp_path / "ready"
    ready.mkdir()
    plan = _write_plan(
        ready,
        [
            _candidate(
                "screen",
                kind="implement",
                status="open",
                allowed_paths=[
                    "apps/company-workspace/workspace.css",
                    "tests/ui/shell-host.test.mjs",
                ],
            ),
        ],
    )
    result = _run(ready, plan)
    assert result["stop_reason"] == "needs_implementation", result


def test_resume_of_exhausted_catalog_does_not_repeat(tmp_path: Path) -> None:
    items = [
        {"id": "old", "decision": "keep", "priority": 1, "hypothesis": "done", "cost": 1},
    ]
    plan = _write_plan(tmp_path, [], proposal_command=_proposal_command(tmp_path, items))
    first = _run(tmp_path, plan)
    assert first["stop_reason"] == "requires_new_review"
    state_path = tmp_path / "out" / "loop-state.json"
    second = LOOP.run_dev_review_loop(plan, output_dir=tmp_path / "out", resume=state_path)
    assert second["loop_id"] == first["loop_id"]
    assert second["finished_at"] == first["finished_at"]
    assert second["attempts"] == []
