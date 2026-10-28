"""Verify this run's retained evidence and final documentation without repeating service gates."""
from __future__ import annotations

import argparse
import json
import math
import re
import statistics
import subprocess
import sys
from pathlib import Path

EVIDENCE = Path(__file__).resolve().parent
ROOT = EVIDENCE.parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from record_closure import AGENT_INPUTS, PLATFORM_INPUTS, inventory, timestamp, write_new  # noqa: E402
from release_manifest import sha256_file  # noqa: E402
from verify_acceptance import offline_environment  # noqa: E402


def read(name):
    return json.loads((EVIDENCE / name).read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--canvas", type=Path, required=True)
    args = parser.parse_args()
    assert args.canvas.is_absolute() and args.canvas.is_file()
    summary = read("summary.json")
    assert summary["status"] == "passed" and summary["inputs_stable"] is True
    assert summary["release_accepted"] is summary["production_authorized"] is False
    assert len(summary["gates"]) == 5
    for gate in summary["gates"]:
        assert gate["status"] == "passed" and gate["exit_code"] == 0
        assert sha256_file(EVIDENCE / (gate["gate"] + ".log")) == gate["log_sha256"]
    local = read("agent_local.log")
    assert local["checks"][0]["counts"] == {
        "passed": 587, "failed": 0, "skipped": 0, "deselected": 1,
    }
    assert all(check["status"] == "passed" for check in local["checks"])
    source = Path(next(gate["cwd"] for gate in summary["gates"] if gate["gate"] == "platform_tests"))
    before, after = read("inputs-before.json"), read("inputs-after.json")
    current = {"agent": inventory(ROOT, AGENT_INPUTS), "platform": inventory(source, PLATFORM_INPUTS)}
    assert before == after == current
    benchmark = read("benchmark.log")
    assert benchmark["repeats"] == 10 and benchmark["version"] == "2.1"
    for measurement in benchmark["timings"].values():
        samples = measurement["samples_ms"]
        assert len(samples) == 10 and all(math.isfinite(item) and item >= 0 for item in samples)
        # Stored samples retain six decimals; published statistics retain three.
        assert abs(statistics.median(samples) - measurement["median_ms"]) < 0.000501
        rank = math.ceil(len(samples) * 0.95) - 1
        assert abs(sorted(samples)[rank] - measurement["p95_ms"]) < 0.000501
    for method in benchmark["quality"]["methods"].values():
        assert len(method["samples_ms"]) == benchmark["quality"]["cases"]
    documents = [ROOT / name for name in (
        "README.md", "docs/implementation-2026-10-08.zh-CN.md",
        "docs/deployment-and-evidence.zh-CN.md",
    )]
    for document in documents:
        for link in re.findall(r"\]\(([^)]+)\)", document.read_text(encoding="utf-8")):
            if not link.startswith(("http:", "https:", "#")):
                assert (document.parent / link.split("#", 1)[0]).exists(), link
    documents.extend(source / "docs" / name for name in (
        "STATUS.md", "BACKLOG.md", "PROGRESS.md", "SOURCE_INVENTORY.md",
        "DECISIONS.md", "ARCHITECTURE.md", "architecture.html",
    ))
    documents.append(args.canvas)
    env = offline_environment()
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    commands = [
        [sys.executable, "scripts/check_static.py"],
        [sys.executable, "-m", "pytest", "-q", "--tb=short", "tests/test_no_legacy.py"],
    ]
    rows = []
    for index, command in enumerate(commands):
        with (EVIDENCE / f"delivery-check-{index}.log").open("x", encoding="utf-8") as log:
            code = subprocess.run(command, cwd=ROOT, env=env, stdout=log,
                                  stderr=subprocess.STDOUT, timeout=120).returncode
        rows.append({"command": command, "exit_code": code})
    report = {
        "format": "company-agent-post-delivery-check/1", "ended_at": timestamp(),
        "status": "passed" if all(row["exit_code"] == 0 for row in rows) else "failed",
        "scope": "retained_evidence_identity_samples_links_static_and_document_architecture",
        "inputs_still_match_final_run": True, "commands": rows,
        "documents_sha256": {str(path): sha256_file(path) for path in documents},
        "external_acceptance": "blocked", "release_accepted": False, "production_authorized": False,
    }
    write_new(EVIDENCE / "post-delivery.json", report)
    print(json.dumps({"status": report["status"], "inputs_still_match_final_run": True}))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
