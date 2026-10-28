"""Evidence recorder unit tests execute only tiny local Python processes."""
from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("record_closure", ROOT / "scripts/record_closure.py")
RECORDER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RECORDER)


def test_inventory_binds_contents_modes_and_input_set(tmp_path, make_symlink):
    source = tmp_path / "src"
    source.mkdir()
    file = source / "sample.py"
    file.write_text("value = 1\n")
    first = RECORDER.inventory(tmp_path, ("src",))
    file.write_text("value = 2\n")
    assert RECORDER.inventory(tmp_path, ("src",)) != first
    file.write_text("value = 1\n")
    assert RECORDER.inventory(tmp_path, ("src",)) == first
    file.chmod(0o400)
    assert RECORDER.inventory(tmp_path, ("src",)) != first
    file.chmod(0o644)
    (source / "extra.py").write_text("value = 3\n")
    assert RECORDER.inventory(tmp_path, ("src",)) != first
    make_symlink(file, source / "linked.py")
    with pytest.raises(ValueError, match="symlink"):
        RECORDER.inventory(tmp_path, ("src",))


@pytest.mark.parametrize(("code", "summary", "status"), [
    (0, "2 passed", "passed"), (1, "1 failed, 1 passed", "failed"),
    (0, "1 failed, 1 passed", "failed"),
    (0, "2 passed, 1 skipped", "failed"), (0, "2 passed, 1 deselected", "failed"),
    (0, "no tests collected", "failed"),
])
def test_test_gate_records_actual_counts_and_exclusive_outputs(tmp_path, code, summary, status):
    command = [sys.executable, "-I", "-c", f"print({summary!r}); raise SystemExit({code})"]
    row = RECORDER.run("dual_repository", command, tmp_path, {"PATH": "/usr/bin:/bin"}, tmp_path)
    assert row["status"] == status
    assert row["exit_code"] == code
    assert json.loads((tmp_path / "dual_repository.json").read_text()) == row
    with pytest.raises(FileExistsError):
        RECORDER.run("dual_repository", command, tmp_path, {}, tmp_path)


@pytest.mark.parametrize("mutation", [
    None, "empty", "status", "missing_check", "check_status", "no_tests", "bool_count",
    "failed", "skipped", "real_mode", "authorization",
])
def test_local_gate_requires_a_complete_successful_report(tmp_path, mutation):
    report = {
        "status": "passed", "mode": "local", "scope": "agent_single_repository",
        "external_acceptance": "blocked", "release_accepted": False, "production_authorized": False,
        "checks": [{"check": name, "status": "passed"} for name in (
            "tests", "static", "dsh_profiles", "retrieval_benchmark",
        )],
    }
    counts = {"passed": 2, "failed": 0, "skipped": 0, "deselected": 1}
    report["checks"][0]["counts"] = counts
    if mutation == "status":
        report["status"] = "blocked"
    elif mutation == "missing_check":
        report["checks"].pop()
    elif mutation == "check_status":
        report["checks"][-1]["status"] = "failed"
    elif mutation == "no_tests":
        counts["passed"] = 0
    elif mutation == "bool_count":
        counts["passed"] = True
    elif mutation in {"failed", "skipped"}:
        counts[mutation] = 1
    elif mutation == "real_mode":
        report["mode"] = "real"
    elif mutation == "authorization":
        report["production_authorized"] = True
    output = "" if mutation == "empty" else json.dumps(report)
    command = [sys.executable, "-I", "-c", f"print({output!r})"]
    row = RECORDER.run("agent_local", command, tmp_path, {"PATH": "/usr/bin:/bin"}, tmp_path)
    assert row["exit_code"] == 0
    assert row["status"] == ("passed" if mutation is None else "failed")
    if mutation is not None:
        assert row["reason"] == "invalid_local_acceptance_report"


def test_inventory_rejects_a_linked_input_root(tmp_path, make_symlink):
    source = tmp_path / "source"
    source.mkdir()
    (source / "example.py").write_text("value = 1\n")
    make_symlink(source, tmp_path / "src", target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        RECORDER.inventory(tmp_path, ("src",))


@pytest.mark.parametrize("ending_error", [
    OSError, ValueError, RECORDER.ManifestError,
])
def test_ending_inventory_failure_writes_failed_summary(tmp_path, monkeypatch, ending_error):
    source = tmp_path / "platform"
    adapter = source / "src/company_quantum/adapters/company_agent_provider.py"
    adapter.parent.mkdir(parents=True)
    adapter.write_text("# synthetic fixture\n")
    output = tmp_path / "evidence"
    calls = []

    def inventory(*_args):
        calls.append(True)
        if len(calls) == 3:
            raise ending_error("synthetic ending input unavailable")
        return {"sha256": "sha256:" + "1" * 64, "files": {}}

    monkeypatch.setattr(RECORDER, "ROOT", tmp_path / "agent")
    monkeypatch.setattr(RECORDER, "inventory", inventory)
    monkeypatch.setattr(RECORDER, "contract_digest", lambda _: "sha256:" + "2" * 64)
    monkeypatch.setattr(RECORDER, "lock_digest", lambda _: "sha256:" + "3" * 64)
    monkeypatch.setattr(RECORDER.os, "umask", lambda _: 0o077)
    monkeypatch.setattr(RECORDER, "run", lambda name, *_: {"gate": name, "status": "passed"})
    result = RECORDER.main([
        "--platform-source", str(source), "--platform-python", sys.executable,
        "--output", str(output),
    ])
    assert result == 1
    report = json.loads((output / "summary.json").read_text())
    assert report["status"] == "failed"
    assert report["inputs_stable"] is False
    assert report["reason"] == "ending_input_inventory_unavailable"
    assert report["contract_digest"] == "sha256:" + "2" * 64
    assert len(report["gates"]) == 5
    assert report["release_accepted"] is report["production_authorized"] is False
    assert json.loads((output / "inputs-after.json").read_text())["status"] == "failed"


def test_output_json_never_overwrites(tmp_path):
    path = tmp_path / "report.json"
    RECORDER.write_new(path, {"status": "failed"})
    with pytest.raises(FileExistsError):
        RECORDER.write_new(path, {"status": "passed"})
    assert json.loads(path.read_text())["status"] == "failed"
    assert os.path.isfile(path)
