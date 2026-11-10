from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = Path(os.environ.get("COMPANY_AGENT_RUNTIME_DIR",
               Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
               / "unitqc-company-agent/dsh-runtime"))
PYTHON = Path(sys.executable)


@pytest.mark.parametrize(("scenario", "calls", "asks", "outcomes"), [
    ("deny_boot", 0, 0, []), ("deny_algo", 0, 0, []),
    ("reject", 0, 1, ["rejected"]), ("allow", 1, 1, ["allowed-once"]),
    ("twice", 2, 2, ["allowed-once", "allowed-once"]), ("missing", 0, 0, ["unavailable"]),
    ("cancel_before", 0, 1, ["cancelled"]), ("late", 0, 1, ["cancelled"]),
    ("cancel_after", 1, 1, ["allowed-once"]), ("timeout_after", 1, 1, ["allowed-once"]),
])
def test_real_dsh_approval_lifecycle(scenario, calls, asks, outcomes):
    node = RUNTIME / "node_modules/node/bin/node"
    assert node.is_file(), "pinned DSH runtime missing; run scripts/bootstrap_dsh.sh"
    assert PYTHON.is_file(), "managed test Python missing"
    # Fully specified environment: no developer model/provider credentials or proxy inheritance.
    env = {"PATH": "/usr/bin:/bin", "HOME": str(Path.home()),
           "DSH_TELEMETRY_MODE": "DISABLED", "COMPANY_AGENT_TEST_ROOT": str(ROOT),
           "COMPANY_AGENT_TEST_MODULES": str(RUNTIME / "node_modules/.pnpm/node_modules"),
           "COMPANY_AGENT_PROFILE": "company-agent", "COMPANY_AGENT_PRESET": "lab",
           "COMPANY_AGENT_PYTHON": str(PYTHON), "COMPANY_AGENT_PYTHONPATH": str(ROOT / "src"),
           "COMPANY_AGENT_CONTRACTS_DIR": str(ROOT / "contracts"),
           # Hermetic ledger: each fixture run owns a fresh turn identity and
           # receipt root, keeping termination budgets per-turn facts instead
           # of cross-suite accumulation.
           "COMPANY_AGENT_TURN_ID": f"fixture-{uuid.uuid4().hex[:16]}",
           "COMPANY_AGENT_RECEIPT_DIR": tempfile.mkdtemp(prefix="company-agent-fixture-")}
    # Windows node aborts at process init (ncrypto::CSPRNG) without SystemRoot,
    # and subprocessEnvironment() requires absolute PATH entries, so the POSIX
    # "/usr/bin:/bin" hermetic PATH only applies off-Windows.
    if os.name == "nt":
        env["SystemRoot"] = os.environ.get("SystemRoot", "")
        env["windir"] = os.environ.get("windir", "")
        env["PATH"] = os.environ.get("PATH", "")
    result = subprocess.run([str(node), str(ROOT / "tests/fixtures/dsh-lifecycle.mjs"), scenario],
                            cwd=ROOT, env=env, capture_output=True, text=True, timeout=45)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["calls"] == calls
    assert report["asks"] == asks
    decided = [row for row in report["audit"] if row["type"] == "approval/decided"]
    asked = [row for row in report["audit"] if row["type"] == "approval/asked"]
    assert [row["data"]["outcome"] for row in decided] == outcomes
    assert len(asked) == len(decided)
    assert [row["data"]["id"] for row in asked] == [row["data"]["id"] for row in decided]
    assert len({row["data"]["id"] for row in asked}) == len(asked)
    expected_reason = (
        "Company Agent device execution approval: provider=ionstack-twinrun; "
        "circuit_id=circ_fixture; shots=1; "
        "subject=circuit:circ_fixture; limit=shots:1; handoff=no"
    )
    if asks:
        assert report["approvalRequests"] == [
            {"toolName": "quantum_device_run", "reason": expected_reason}
            for _ in range(asks)
        ]
        assert [row["data"]["reason"] for row in asked] == [expected_reason] * asks
    else:
        assert report["approvalRequests"] == []
    assert "turn/start" in report["eventTypes"] and "turn/end" in report["eventTypes"]
    assert "tool/call" in report["eventTypes"] and "tool/result" in report["eventTypes"]
    assert report["generation"] >= 1
    if scenario in {"allow", "twice"}:
        results = [event for event in report["results"] if event["type"] == "tool/result"]
        assert all(not event["data"]["message"]["content"][0]["isError"] for event in results)
    if scenario in {"cancel_after", "timeout_after"}:
        diagnostics = [json.loads(line.removeprefix("company-agent-diagnostic:"))
                       for line in result.stderr.splitlines() if line.startswith("company-agent-diagnostic:")]
        unknown = [row for row in diagnostics if row["execution_state"] == "unknown"]
        assert unknown and unknown[-1]["request_id"].startswith("req_")
        assert unknown[-1]["error_category"] == ("cancelled" if scenario == "cancel_after" else "timeout")
        if scenario == "timeout_after":
            assert "outcome unknown; do not retry automatically" in result.stdout
