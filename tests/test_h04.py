from __future__ import annotations

import os
import tempfile
import traceback
from pathlib import Path

import qagent.adapters.docs as docs_mod
from qagent.adapters.docs import WiredDocs

_FORBIDDEN_NET = ("urllib", "requests", "httpx", "socket")
_HANDBOOK_QUERY = "TwinRun circuit.body mode shots"
_MISS_QUERY = "this-query-should-miss-zzzz-h04c"


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


def test_excerpt_length() -> None:
    marker = "UNIQUE_MARKER_H04C_EXCERPT"
    body = ("HEAD " * 80) + marker + (" TAIL" * 80)
    assert len(body) > 400
    previous = os.environ.get("QAGENT_KNOWLEDGE_PATH")
    try:
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "long.md").write_text(body, encoding="utf-8")
            os.environ["QAGENT_KNOWLEDGE_PATH"] = tmp
            result = WiredDocs().search({"query": marker.lower()})
        knowledge = [item for item in result["hits"] if item["source"] == "knowledge"]
        assert result["empty"] is False
        assert knowledge
        hit = knowledge[0]
        _assert_hit_shape(hit)
        assert hit["path"] == "long.md"
        assert marker in hit["text"]
    finally:
        _restore_knowledge(previous)


def test_miss_is_empty() -> None:
    previous = os.environ.get("QAGENT_KNOWLEDGE_PATH")
    try:
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["QAGENT_KNOWLEDGE_PATH"] = tmp
            result = WiredDocs().search({"query": _MISS_QUERY})
        assert result["empty"] is True
        assert result["hits"] == []
        assert result.get("detail")
    finally:
        _restore_knowledge(previous)


def test_no_network_imports() -> None:
    source = Path(docs_mod.__file__).read_text(encoding="utf-8")
    for name in _FORBIDDEN_NET:
        assert name not in source


def test_twinrun_handbook_keywords() -> None:
    previous = os.environ.get("QAGENT_KNOWLEDGE_PATH")
    try:
        os.environ.pop("QAGENT_KNOWLEDGE_PATH", None)
        result = WiredDocs().search({"query": _HANDBOOK_QUERY})
    finally:
        _restore_knowledge(previous)
    assert result["hits"]
    assert result.get("empty") is False
    handbook = [item for item in result["hits"] if item["source"] == "handbook"]
    assert handbook
    hit = handbook[0]
    _assert_hit_shape(hit)
    assert "twin_run" in hit["path"]
    assert "mode" in hit["text"]


def test_max_hits() -> None:
    previous = os.environ.get("QAGENT_KNOWLEDGE_PATH")
    try:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for index in range(12):
                (root / f"n{index}.md").write_text(f"needle-h04c file {index}", encoding="utf-8")
            os.environ["QAGENT_KNOWLEDGE_PATH"] = tmp
            result = WiredDocs().search({"query": "needle-h04c"})
        assert result["hits"]
        assert len(result["hits"]) <= 8
        for item in result["hits"]:
            _assert_hit_shape(item)
    finally:
        _restore_knowledge(previous)


def main() -> int:
    failed = 0
    for name, fn in (
        ("excerpt_length", test_excerpt_length),
        ("miss_is_empty", test_miss_is_empty),
        ("no_network_imports", test_no_network_imports),
        ("twinrun_handbook", test_twinrun_handbook_keywords),
        ("max_hits", test_max_hits),
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
