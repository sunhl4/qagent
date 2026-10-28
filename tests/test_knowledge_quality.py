from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path

import pytest

from company_agent import knowledge

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def knowledge_root(tmp_path, monkeypatch):
    monkeypatch.setattr(knowledge, "roots", lambda: (("builtin", tmp_path),))
    return tmp_path


def test_fixed_chinese_quality_beats_whitespace():
    spec = importlib.util.spec_from_file_location("benchmark", ROOT / "scripts/benchmark_company_agent.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = module.retrieval_evaluation()
    methods = result["methods"]
    assert all(len(method["samples_ms"]) == result["cases"] for method in methods.values())
    assert methods["cjk_bigrams"]["recall_at_8"] == 1
    assert methods["cjk_bigrams"]["mrr_at_8"] >= methods["whitespace"]["mrr_at_8"]
    assert methods["cjk_bigrams"]["empty_accuracy"] == 1


@pytest.mark.parametrize("repeats", [1, 10, 20])
def test_benchmark_keeps_samples_and_uses_nearest_rank(monkeypatch, repeats):
    spec = importlib.util.spec_from_file_location("benchmark", ROOT / "scripts/benchmark_company_agent.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # Keep deliberately unsorted samples; the report must preserve measurement order.
    samples = list(range(repeats, 0, -1))
    ticks = iter(value for sample in samples for value in (0.0, sample / 1000))
    monkeypatch.setattr(module.time, "perf_counter", lambda: next(ticks))
    calls = []
    result = module.measure(lambda: calls.append(True), repeats)
    assert len(calls) == repeats
    assert result["samples_ms"] == samples
    assert result["median_ms"] == (repeats + 1) / 2
    expected_p95 = 19 if repeats == 20 else repeats
    assert result["p95_ms"] == expected_p95
    assert result["p95_method"] == "nearest_rank"


def test_top_eight_is_not_partial_scan(knowledge_root):
    for index in range(12):
        (knowledge_root / f"note{index}.md").write_text("needle")
    result = knowledge.search({"query": "needle"})
    assert len(result["hits"]) == 8
    assert result["scan"] == {"complete": True, "reasons": [], "entries": 12, "files": 12, "bytes": 72}


@pytest.mark.parametrize(("budget", "limit", "reason"), [
    ("_MAX_KNOWLEDGE_ENTRIES", 1, "entry_budget"),
    ("_MAX_KNOWLEDGE_FILES", 1, "file_budget"),
    ("_MAX_KNOWLEDGE_TOTAL_BYTES", 6, "byte_budget"),
    ("_MAX_KNOWLEDGE_FILE_BYTES", 3, "oversized_file"),
])
def test_partial_scan_budgets_are_explicit(knowledge_root, monkeypatch, budget, limit, reason):
    for name in ("a.md", "b.md"):
        (knowledge_root / name).write_text("needle")
    monkeypatch.setattr(knowledge, budget, limit)
    result = knowledge.search({"query": "needle"})
    assert result["scan"]["complete"] is False
    assert reason in result["scan"]["reasons"]
    assert str(knowledge_root) not in json.dumps(result)


def test_exact_entry_limit_is_complete(knowledge_root, monkeypatch):
    (knowledge_root / "a.md").write_text("needle")
    monkeypatch.setattr(knowledge, "_MAX_KNOWLEDGE_ENTRIES", 1)
    assert knowledge.search({"query": "needle"})["scan"]["complete"]


def test_depth_limit_is_reported(knowledge_root, monkeypatch):
    nested = knowledge_root / "nested"
    nested.mkdir()
    (nested / "a.md").write_text("needle")
    monkeypatch.setattr(knowledge, "_MAX_KNOWLEDGE_DEPTH", 0)
    assert knowledge.search({"query": "needle"})["scan"]["reasons"] == ["depth_limit"]


def test_read_error_is_reported(knowledge_root, monkeypatch):
    (knowledge_root / "a.md").write_bytes(b"\xff")
    assert knowledge.search({"query": "needle"})["scan"]["reasons"] == ["read_error"]
    monkeypatch.setattr(knowledge.os, "scandir", lambda _: (_ for _ in ()).throw(PermissionError()))
    assert knowledge.search({"query": "needle"})["scan"]["reasons"] == ["read_error"]


def test_changed_read_is_reported(knowledge_root, monkeypatch):
    path = knowledge_root / "a.md"
    path.write_text("needle")
    original = Path.open

    def changed(self, *args, **kwargs):
        return io.BytesIO(b"needle changed") if self == path else original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", changed)
    result = knowledge.search({"query": "needle"})
    assert result["scan"]["reasons"] == ["changed_file"] and not result["hits"]


def test_long_relative_metadata_is_reported(knowledge_root):
    nested = knowledge_root / ("a" * 180) / ("b" * 180) / ("c" * 180)
    try:
        nested.mkdir(parents=True)
        (nested / "note.md").write_text("needle")
    except OSError:
        # POSIX handles ~540-char relative paths; Windows without long-path
        # support raises before creation, so this host cannot express the gate.
        pytest.skip("long relative paths unsupported on this host")
    assert knowledge.search({"query": "needle"})["scan"]["reasons"] == ["metadata_limit"]


def test_path_query_is_data_not_a_read_request(knowledge_root):
    (knowledge_root / "note.md").write_text("safe company knowledge")
    result = knowledge.search({"query": "../../etc/passwd"})
    assert result["hits"] == [] and result["scan"]["complete"]
