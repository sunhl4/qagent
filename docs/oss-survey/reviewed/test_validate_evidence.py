"""Offline regression tests for the survey evidence checker only."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import validate_evidence as checker


class EvidenceChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.base = self.root / "docs" / "oss-survey" / "reviewed"
        self.base.mkdir(parents=True)
        self.source = self.root / "upstream"
        self.source.mkdir()
        (self.source / "code.py").write_text("def run():\n    return True\n")
        (self.source / "test_code.py").write_text("assert run() is True\n")
        (self.source / "LICENSE").write_text("Example license fixture\n")
        (self.source / "SPEC").write_text("Fixture contract specification\n")
        self.doc = "docs/oss-survey/reviewed/H01-example.zh-CN.md"
        (self.root / self.doc).write_text("# Example\n\nSHA: " + "a" * 40 + "\n\n```1:2:code.py\ndef run():\n    return True\n```\n")
        (self.base / "projects.json").write_text(json.dumps({"projects": [{"id": 1, "repo": "owner/example"}]}))
        self.row = {
            "id": 1, "repo": "owner/example", "clone_path": str(self.source),
            "commit": "a" * 40, "commit_date": "2026-10-22", "doc": self.doc,
            "license_summary": "test fixture only", "verification": "static-source-review",
            "evidence": [
                {"path": "code.py", "start": 1, "end": 2, "kind": "implementation", "note": "entry"},
                {"path": "code.py", "start": 1, "end": 1, "kind": "implementation", "note": "definition"},
                {"path": "code.py", "start": 2, "end": 2, "kind": "implementation", "note": "return"},
                {"path": "test_code.py", "start": 1, "end": 1, "kind": "test", "note": "assertion"},
                {"path": "LICENSE", "start": 1, "end": 1, "kind": "license", "note": "license fixture"},
                {"path": "SPEC", "start": 1, "end": 1, "kind": "spec", "note": "fixture specification"},
            ],
        }

    def check(self):
        (self.base / "evidence-fixture.json").write_text(json.dumps([self.row]))
        with patch.object(checker, "BASE", self.base), patch.object(checker, "WORKSPACE", self.root), patch.object(checker, "git_head", return_value="a" * 40):
            return checker.validate()

    def test_valid_bundle(self):
        report = self.check()
        self.assertTrue(report["passed"], report)
        self.assertEqual(report["source_quotations"], 1)
        self.assertEqual(report["evidence_anchors"], 6)

    def test_changed_source_version_rejected(self):
        self.row["commit"] = "b" * 40
        self.assertIn("version drift", " ".join(self.check()["errors"]))

    def test_misquoted_source_rejected(self):
        (self.root / self.doc).write_text("```1:2:code.py\ndef run():\n    return False\n```\n")
        self.assertIn("quotation mismatch", " ".join(self.check()["errors"]))

    def test_out_of_bounds_anchor_rejected(self):
        self.row["evidence"][0]["end"] = 999
        self.assertIn("invalid evidence lines", " ".join(self.check()["errors"]))

    def test_traversal_anchor_rejected(self):
        self.row["evidence"][0]["path"] = "../secret"
        self.assertIn("safe relative path", " ".join(self.check()["errors"]))

    def test_missing_tests_need_explicit_gap(self):
        self.row["evidence"][3]["kind"] = "spec"
        self.assertIn("test_gap", " ".join(self.check()["errors"]))
        self.row["test_gap"] = "This fixture intentionally has no upstream tests"
        report = self.check()
        self.assertTrue(report["passed"], report)
        self.assertEqual(len(report["warnings"]), 1)

    def test_missing_license_rejected(self):
        self.row["evidence"][4]["kind"] = "spec"
        self.assertIn("license evidence", " ".join(self.check()["errors"]))

    def test_duplicate_evidence_rejected(self):
        self.row["evidence"][5] = dict(self.row["evidence"][0])
        self.assertIn("duplicate evidence", " ".join(self.check()["errors"]))

    def test_duplicate_project_rejected(self):
        (self.base / "evidence-second.json").write_text(json.dumps([self.row]))
        self.assertIn("duplicate project", " ".join(self.check()["errors"]))

    def test_missing_project_rejected(self):
        (self.base / "projects.json").write_text(json.dumps({"projects": [
            {"id": 1, "repo": "owner/example"}, {"id": 2, "repo": "owner/missing"}
        ]}))
        self.assertIn("missing project", " ".join(self.check()["errors"]))

    def test_undeclared_companion_source_rejected(self):
        self.row["evidence"][0]["source_repo"] = "other/companion"
        self.assertIn("undeclared evidence", " ".join(self.check()["errors"]))

    def test_license_absence_must_remain_explicit(self):
        self.row["evidence"][4]["kind"] = "spec"
        self.row["license_gap"] = "No upstream license grant found; reuse is not approved"
        report = self.check()
        self.assertTrue(report["passed"], report)
        self.assertIn("license gap", " ".join(report["warnings"]))

    def test_full_sha_must_appear_in_document(self):
        (self.root / self.doc).write_text("```1:2:code.py\ndef run():\n    return True\n```\n")
        self.assertIn("full source SHA", " ".join(self.check()["errors"]))

    def test_dirty_tracked_source_is_rejected(self):
        with patch.object(checker.subprocess, "check_output", return_value=" M code.py\n"):
            with self.assertRaisesRegex(ValueError, "source files changed"):
                checker.git_head(self.source)

    def test_unexpected_repository_rejected(self):
        self.row["repo"] = "other/project"
        self.assertIn("repository does not match", " ".join(self.check()["errors"]))


if __name__ == "__main__":
    unittest.main()
