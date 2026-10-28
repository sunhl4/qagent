"""Check retained closure evidence, current identities and documentation without rerunning gates."""
from __future__ import annotations

import argparse
import json
import math
import re
import statistics
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
from record_closure import AGENT_INPUTS, PLATFORM_INPUTS, inventory, timestamp, write_new
from release_manifest import load_json, sha256_file
from verify_acceptance import offline_environment


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--canvas", type=Path, required=True)
    args = parser.parse_args()
    evidence = args.evidence
    assert evidence.is_absolute() and args.canvas.is_absolute()
    report = load_json(evidence / "summary.json")
    assert report["status"] == "passed" and report["inputs_stable"] is True
    assert report["release_accepted"] is report["production_authorized"] is False
    assert [row["gate"] for row in report["gates"]] == [
        "agent_local", "platform_tests", "platform_quality", "dual_repository", "benchmark",
    ]
    for row in report["gates"]:
        assert row["status"] == "passed" and row["exit_code"] == 0
        assert row["log_sha256"] == sha256_file(evidence / (row["gate"] + ".log"))
    local = load_json(evidence / "agent_local.log")
    assert local["status"] == "passed" and local["scope"] == "agent_single_repository"
    assert all(row["status"] == "passed" for row in local["checks"])
    tests = local["checks"][0]
    assert tests["counts"]["passed"] > 0
    assert tests["counts"]["failed"] == tests["counts"]["skipped"] == 0
    source = Path(report["gates"][1]["cwd"])
    before, after = (load_json(evidence / name) for name in ("inputs-before.json", "inputs-after.json"))
    current = {"agent": inventory(ROOT, AGENT_INPUTS), "platform": inventory(source, PLATFORM_INPUTS)}
    assert before == after == current
    benchmark = load_json(evidence / "benchmark.log")
    assert benchmark["version"] == "2.1" and benchmark["repeats"] == 10
    for measurement in benchmark["timings"].values():
        samples = measurement["samples_ms"]
        assert len(samples) == 10 and all(math.isfinite(value) and value >= 0 for value in samples)
        assert abs(statistics.median(samples) - measurement["median_ms"]) < 0.000501
        assert abs(sorted(samples)[math.ceil(len(samples) * 0.95) - 1] - measurement["p95_ms"]) < 0.000501
    for measurement in benchmark["quality"]["methods"].values():
        assert len(measurement["samples_ms"]) == benchmark["quality"]["cases"]
    documents = [ROOT / name for name in (
        "README.md", "docs/implementation-2026-10-09.zh-CN.md",
        "docs/implementation-2026-10-08.zh-CN.md", "docs/deployment-and-evidence.zh-CN.md",
    )]
    for document in documents:
        for link in re.findall(r"\]\(([^)]+)\)", document.read_text(encoding="utf-8")):
            if not link.startswith(("http:", "https:", "#")):
                assert (document.parent / link.split("#", 1)[0]).exists(), link
    documents.extend(source / "docs" / name for name in (
        "STATUS.md", "BACKLOG.md", "PROGRESS.md", "SOURCE_INVENTORY.md",
    ))
    documents.append(args.canvas)
    commands = [
        [sys.executable, str(ROOT / "scripts/check_static.py")],
        [sys.executable, "-m", "pytest", "-q", "--tb=short", "tests/test_no_legacy.py"],
    ]
    checks = []
    for index, command in enumerate(commands):
        with (evidence / f"delivery-check-{index}.log").open("x", encoding="utf-8") as handle:
            result = subprocess.run(command, cwd=ROOT, env=offline_environment(), stdout=handle,
                                    stderr=subprocess.STDOUT, timeout=120, check=False)
        checks.append({"command": command, "exit_code": result.returncode})
    old = load_json(ROOT / "docs/evidence/closure-20261008-05/inputs-after.json")
    changes = {}
    for repository in ("agent", "platform"):
        previous, latest = old[repository]["files"], current[repository]["files"]
        changes[repository] = {
            "added": sorted(set(latest) - set(previous)),
            "removed": sorted(set(previous) - set(latest)),
            "modified": sorted(name for name in set(previous) & set(latest)
                               if previous[name] != latest[name]),
        }
    final = {
        "format": "company-agent-post-delivery-check/1", "ended_at": timestamp(),
        "status": "passed" if all(row["exit_code"] == 0 for row in checks) else "failed",
        "scope": "evidence_identity_samples_links_static_and_document_architecture",
        "inputs_still_match_final_run": True, "commands": checks,
        "changes_since_previous_closure": changes,
        "documents_sha256": {str(path): sha256_file(path) for path in documents},
        "release_accepted": False, "production_authorized": False, "external_acceptance": "blocked",
    }
    write_new(evidence / "post-delivery.json", final)
    print(json.dumps({"status": final["status"], "inputs_still_match_final_run": True}))
    return 0 if final["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
