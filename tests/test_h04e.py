"""H-04e: knowledge hits list_engines / estimate / receipt."""

from __future__ import annotations

import os
import tempfile
import traceback
from pathlib import Path

from qagent.adapters.docs import WiredDocs

ROOT = Path(__file__).resolve().parents[1]
KNOWLEDGE = ROOT / "knowledge"
NOTE = ROOT / "docs" / "execution" / "H-04e_more_manuals.md"
LIST_REL = "manuals/list_engines.md"
ESTIMATE_REL = "manuals/route_estimate.md"
RECEIPT_REL = "manuals/receipt.md"
NEW_MANUALS = (LIST_REL, ESTIMATE_REL, RECEIPT_REL)
_FORBIDDEN_NET = ("urllib", "requests", "httpx", "socket")
_EMPTY_DETAIL = "知识库是空的。没有这条。"
_MISS_QUERY = "this-query-should-miss-zzzz-h04e"


def _restore_knowledge(previous: str | None) -> None:
    if previous is None:
        os.environ.pop("QAGENT_KNOWLEDGE_PATH", None)
    else:
        os.environ["QAGENT_KNOWLEDGE_PATH"] = previous


def _search(query: str) -> dict:
    previous = os.environ.get("QAGENT_KNOWLEDGE_PATH")
    try:
        os.environ["QAGENT_KNOWLEDGE_PATH"] = str(KNOWLEDGE)
        return WiredDocs().search({"query": query})
    finally:
        _restore_knowledge(previous)


def _assert_hit_shape(item: dict) -> None:
    assert item.get("path")
    assert item.get("source") in {"handbook", "knowledge"}
    assert "text" in item
    assert len(item["text"]) <= 400


def _knowledge_paths(result: dict) -> set[str]:
    return {
        item["path"].replace("\\", "/")
        for item in result.get("hits") or []
        if item.get("source") == "knowledge"
    }


def _assert_knowledge_file(query: str, rel: str) -> None:
    result = _search(query)
    assert result.get("empty") is False
    assert result["hits"]
    paths = _knowledge_paths(result)
    assert rel in paths, (query, paths)
    hit = next(
        item
        for item in result["hits"]
        if item.get("source") == "knowledge" and item["path"].replace("\\", "/") == rel
    )
    _assert_hit_shape(hit)


def test_list_engines_hits() -> None:
    for query in ("list_engines", "哪些包"):
        _assert_knowledge_file(query, LIST_REL)


def test_estimate_hits() -> None:
    for query in ("makespan_ns", "估计"):
        _assert_knowledge_file(query, ESTIMATE_REL)


def test_receipt_hits() -> None:
    for query in ("receipt", "verify_receipt"):
        _assert_knowledge_file(query, RECEIPT_REL)


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


def test_no_network_in_manuals() -> None:
    for rel in NEW_MANUALS:
        text = (KNOWLEDGE / rel).read_text(encoding="utf-8")
        lowered = text.lower()
        for name in _FORBIDDEN_NET:
            assert name not in lowered
        assert "import " not in lowered


def test_no_minted_twin_id() -> None:
    for rel in NEW_MANUALS:
        text = (KNOWLEDGE / rel).read_text(encoding="utf-8")
        assert "twin_id=" not in text
        assert "twin_id:" not in text
    for query in ("list_engines", "makespan_ns", "verify_receipt"):
        result = _search(query)
        for item in result.get("hits") or []:
            if item.get("source") != "knowledge":
                continue
            _assert_hit_shape(item)
            assert "twin_id=" not in item["text"]


def test_note_exists() -> None:
    assert NOTE.is_file()
    text = NOTE.read_text(encoding="utf-8")
    assert "QAGENT_KNOWLEDGE_PATH" in text
    assert "list_engines" in text
    assert "makespan_ns" in text


def test_manuals_on_disk() -> None:
    assert (KNOWLEDGE / "manuals" / "twinrun_fields.md").is_file()
    for rel in NEW_MANUALS:
        path = KNOWLEDGE / rel
        assert path.is_file(), rel
        assert len(path.read_text(encoding="utf-8")) <= 400


def main() -> int:
    failed = 0
    for name, fn in (
        ("list_engines_hits", test_list_engines_hits),
        ("estimate_hits", test_estimate_hits),
        ("receipt_hits", test_receipt_hits),
        ("empty_lib_honest", test_empty_lib_honest),
        ("no_network_in_manuals", test_no_network_in_manuals),
        ("no_minted_twin_id", test_no_minted_twin_id),
        ("note_exists", test_note_exists),
        ("manuals_on_disk", test_manuals_on_disk),
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
