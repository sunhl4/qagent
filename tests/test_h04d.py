"""H-04d: knowledge path hits TwinRun fields; empty lib is honest."""

from __future__ import annotations

import os
import tempfile
import traceback
from pathlib import Path

import qagent.adapters.docs as docs_mod
from qagent.adapters.docs import WiredDocs

ROOT = Path(__file__).resolve().parents[1]
KNOWLEDGE = ROOT / "knowledge"
MANUAL_REL = "manuals/twinrun_fields.md"
NOTE = ROOT / "docs" / "execution" / "H-04d_knowledge_hits.md"
_HANDBOOK_QUERY = "TwinRun circuit.body mode shots"
_MISS_QUERY = "this-query-should-miss-zzzz-h04d"
_FORBIDDEN_NET = ("urllib", "requests", "httpx", "socket")
_EMPTY_DETAIL = "知识库是空的。没有这条。"


def _restore_knowledge(previous: str | None) -> None:
    if previous is None:
        os.environ.pop("QAGENT_KNOWLEDGE_PATH", None)
    else:
        os.environ["QAGENT_KNOWLEDGE_PATH"] = previous


def _assert_hit_shape(item: dict) -> None:
    assert item.get("path")
    assert item.get("source") in {"handbook", "knowledge"}
    assert "text" in item
    assert len(item["text"]) <= 400


def test_knowledge_twinrun_hits() -> None:
    previous = os.environ.get("QAGENT_KNOWLEDGE_PATH")
    try:
        os.environ["QAGENT_KNOWLEDGE_PATH"] = str(KNOWLEDGE)
        result = WiredDocs().search({"query": _HANDBOOK_QUERY})
    finally:
        _restore_knowledge(previous)
    assert result.get("empty") is False
    assert result["hits"]
    knowledge = [item for item in result["hits"] if item["source"] == "knowledge"]
    assert knowledge
    manuals = [item for item in knowledge if item["path"].replace("\\", "/") == MANUAL_REL]
    assert manuals, knowledge
    hit = manuals[0]
    _assert_hit_shape(hit)
    blob = hit["text"].lower()
    assert "mode" in blob
    assert "shots" in blob
    assert "circuit.body" in blob
    for item in knowledge:
        assert "twin_id" not in item["text"]


def test_empty_lib_honest() -> None:
    previous = os.environ.get("QAGENT_KNOWLEDGE_PATH")
    try:
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["QAGENT_KNOWLEDGE_PATH"] = tmp
            result = WiredDocs().search({"query": _MISS_QUERY})
    finally:
        _restore_knowledge(previous)
    assert result.get("empty") is True
    assert result["hits"] == []
    detail = result.get("detail") or ""
    assert detail == _EMPTY_DETAIL
    assert "没有这条" in detail


def test_no_network() -> None:
    source = Path(docs_mod.__file__).read_text(encoding="utf-8")
    for name in _FORBIDDEN_NET:
        assert name not in source


def test_no_twin_id_in_excerpts() -> None:
    previous = os.environ.get("QAGENT_KNOWLEDGE_PATH")
    try:
        os.environ["QAGENT_KNOWLEDGE_PATH"] = str(KNOWLEDGE)
        result = WiredDocs().search({"query": _HANDBOOK_QUERY})
    finally:
        _restore_knowledge(previous)
    knowledge = [item for item in result["hits"] if item["source"] == "knowledge"]
    assert knowledge
    for item in knowledge:
        _assert_hit_shape(item)
        assert "twin_id" not in item["text"]


def test_note_exists() -> None:
    assert NOTE.is_file()
    text = NOTE.read_text(encoding="utf-8")
    assert "QAGENT_KNOWLEDGE_PATH" in text
    assert "TwinRun" in text
    assert "empty" in text


def test_layout_three_roots() -> None:
    for name in ("manuals", "specs", "patents"):
        folder = KNOWLEDGE / name
        assert folder.is_dir()
        assert any(path.suffix.lower() in {".md", ".txt"} for path in folder.iterdir())
    assert (KNOWLEDGE / MANUAL_REL).is_file()


def main() -> int:
    failed = 0
    for name, fn in (
        ("knowledge_twinrun_hits", test_knowledge_twinrun_hits),
        ("empty_lib_honest", test_empty_lib_honest),
        ("no_network", test_no_network),
        ("no_twin_id_in_excerpts", test_no_twin_id_in_excerpts),
        ("note_exists", test_note_exists),
        ("layout_three_roots", test_layout_three_roots),
    ):
        try:
            fn()
            print(f"ok  {name}")
        except Exception:
            failed += 1
            print(f"FAIL {name}")
            traceback.print_exc()
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
