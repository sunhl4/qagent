#!/usr/bin/env python3
"""Run the fixed single-repository pytest scope and emit private, structured execution evidence."""
from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORMAT = "company-agent-pytest-evidence/1"
# Windows dev hosts cannot express POSIX chmod bits (0444/0555/0600); the
# Ubuntu release host keeps running every gate, including posix_permissions.
EXCLUDED_MARKERS = (
    ("platform_compatibility", "latex_toolchain", "posix_permissions") if os.name == "nt"
    else ("platform_compatibility", "latex_toolchain")
)


def execute(report_path: Path) -> int:
    # This administrative process owns pytest configuration; inherited selection and
    # plugins must never turn a partial run into the advertised complete local gate.
    for name in tuple(os.environ):
        if name.startswith("PYTEST_"):
            os.environ.pop(name)
    os.environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    import pytest

    class Audit:
        def __init__(self):
            self.collected = set()
            self.expected = set()
            self.excluded = set()
            self.selected = set()
            self.deselected = set()
            self.reports = {}
            self.collection_errors = 0
            self.invalid_collection = False

        @pytest.hookimpl(hookwrapper=True, tryfirst=True)
        def pytest_collection_modifyitems(self, items):
            self.collected = {item.nodeid for item in items}
            self.invalid_collection = len(self.collected) != len(items)
            self.excluded = {item.nodeid for item in items
                             if any(item.get_closest_marker(marker) for marker in EXCLUDED_MARKERS)}
            self.expected = self.collected - self.excluded
            yield
            self.selected = {item.nodeid for item in items}
            self.invalid_collection |= len(self.selected) != len(items)

        def pytest_deselected(self, items):
            self.deselected.update(item.nodeid for item in items)

        def pytest_collectreport(self, report):
            if report.failed:
                self.collection_errors += 1

        def pytest_runtest_logreport(self, report):
            phases = self.reports.setdefault(report.nodeid, {})
            if report.when in phases or hasattr(report, "wasxfail"):
                self.invalid_collection = True
            phases[report.when] = report.outcome

    audit = Audit()
    os.chdir(ROOT)
    test_files = {path.relative_to(ROOT).as_posix() for path in (ROOT / "tests").rglob("test_*.py")}
    code = int(pytest.main([
        "-c", str(ROOT / "pyproject.toml"), "-o", "addopts=", "-q", "--tb=short",
        "--strict-config", "--strict-markers", "-p", "no:cacheprovider",
        "-m", "not " + " and not ".join(EXCLUDED_MARKERS),
        str(ROOT / "tests"),
    ], plugins=[audit]))
    passed = failed = skipped = 0
    failed_tests = set()
    for node, phases in audit.reports.items():
        outcomes = set(phases.values())
        if "failed" in outcomes:
            failed += 1
            canonical = node.split("[", 1)[0]
            if re.fullmatch(r"tests/[A-Za-z0-9_./:-]+", canonical):
                failed_tests.add(canonical)
        elif "skipped" in outcomes:
            skipped += 1
        elif phases == {"setup": "passed", "call": "passed", "teardown": "passed"}:
            passed += 1
    observed_files = {node.split("::", 1)[0] for node in audit.collected}
    complete = (
        bool(audit.expected) and bool(test_files) and observed_files == test_files
        and audit.selected == audit.expected and audit.deselected == audit.excluded
        and set(audit.reports) == audit.selected and not audit.invalid_collection
        and audit.collection_errors == 0 and passed + failed + skipped == len(audit.selected)
    )
    report = {
        "format": FORMAT, "scope": "agent_single_repository", "pytest_exit_code": code,
        "counts": {"passed": passed, "failed": failed, "skipped": skipped,
                   "deselected": len(audit.deselected)},
        "selection": {"collected": len(audit.collected), "selected": len(audit.selected),
                      "expected_selected": len(audit.expected), "expected_excluded": len(audit.excluded),
                      "test_files": len(test_files), "observed_files": len(observed_files),
                      "executed": len(audit.reports), "collection_errors": audit.collection_errors,
                      "complete": complete},
        "failed_tests": sorted(failed_tests)[:64], "excluded_markers": list(EXCLUDED_MARKERS),
    }
    # O_EXCL prevents accidentally accepting a report from an earlier run.
    with report_path.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, sort_keys=True, separators=(",", ":"), allow_nan=False)
        handle.write("\n")
    return code


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    if not args.report.is_absolute() or args.report.exists() or args.report.is_symlink():
        parser.error("report must be a new absolute path")
    return execute(args.report)


if __name__ == "__main__":
    raise SystemExit(main())
