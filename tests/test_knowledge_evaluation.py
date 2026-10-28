"""Exercise explicit offline corpus evaluation without disclosing input text."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from company_agent import knowledge

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("knowledge_evaluation", ROOT / "scripts/evaluate_knowledge.py")
assert SPEC and SPEC.loader
EVALUATION = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EVALUATION)


@pytest.fixture
def corpus_cases(tmp_path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "source.md").write_text("alpha retrieval evidence", encoding="utf-8")
    cases = tmp_path / "cases.json"
    spec = {
        "version": "1.0", "scope": "synthetic",
        "cases": [
            {"id": "Found", "query": "alpha", "relevant": ["source.md"]},
            {"id": "Empty", "query": "unmatchedword", "relevant": []},
        ],
    }
    cases.write_text(json.dumps(spec), encoding="utf-8")
    return corpus, cases, spec


def test_evaluation_measures_ranks_without_source_or_question(corpus_cases):
    corpus, cases, _ = corpus_cases
    report = EVALUATION.evaluate(corpus, cases)
    assert report["top1"] == report["recall_at8"] == report["mrr_at8"] == 1
    assert report["empty_accuracy"] == 1 and report["complete_scans"]
    assert report["business_acceptance"] == "not_real_corpus"
    assert report["scientific_or_model_execution"] is False
    assert report["contract_digest"].startswith("sha256:")
    serialized = json.dumps(report)
    for text in ("alpha", "source.md", "unmatchedword", str(corpus)):
        assert text not in serialized


@pytest.mark.parametrize("change", ["traversal", "duplicate", "longquery", "badquery", "unknown"])
def test_evaluation_rejects_invalid_cases(corpus_cases, change):
    corpus, cases, spec = corpus_cases
    if change == "traversal":
        spec["cases"][0]["relevant"] = ["../cases.json"]
    elif change == "duplicate":
        spec["cases"][1]["id"] = "Found"
    elif change == "longquery":
        spec["cases"][0]["query"] = "a " * 501
    elif change == "badquery":
        spec["cases"][0]["query"] = 123
    else:
        spec["cases"][0]["extra"] = True
    cases.write_text(json.dumps(spec), encoding="utf-8")
    with pytest.raises((ValueError, TypeError)):
        EVALUATION.evaluate(corpus, cases)


def test_deidentified_scope_still_requires_review(corpus_cases):
    corpus, cases, spec = corpus_cases
    spec["scope"] = "operator_deidentified"
    cases.write_text(json.dumps(spec), encoding="utf-8")
    assert EVALUATION.evaluate(corpus, cases)["business_acceptance"] == "requires_operator_review"


def test_evaluation_cli_refuses_overwrite_and_reports_partial_scan(corpus_cases, tmp_path, monkeypatch):
    corpus, cases, _ = corpus_cases
    output = tmp_path / "report.json"
    args = ["--corpus", str(corpus), "--cases", str(cases), "--output", str(output)]
    monkeypatch.setattr(knowledge, "_MAX_KNOWLEDGE_ENTRIES", 0)
    assert EVALUATION.main(args) == 1
    original = output.read_bytes()
    assert json.loads(original)["complete_scans"] is False
    monkeypatch.setattr(knowledge, "_MAX_KNOWLEDGE_ENTRIES", 20000)
    assert EVALUATION.main(args) == 1
    assert output.read_bytes() == original


def test_evaluation_rejects_symlinked_corpus(corpus_cases, tmp_path, make_symlink):
    corpus, cases, _ = corpus_cases
    link = tmp_path / "link"
    make_symlink(corpus, link, target_is_directory=True)
    with pytest.raises(ValueError, match="nonsymlink"):
        EVALUATION.evaluate(link, cases)
