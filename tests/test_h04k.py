"""H-04k: list_engines manual names Pennylane reserved. Not wired."""

from __future__ import annotations

import os
import traceback
from pathlib import Path

from qagent.adapters.docs import WiredDocs

ROOT = Path(__file__).resolve().parents[1]
KNOWLEDGE = ROOT / "knowledge"
NOTE = ROOT / "docs" / "execution" / "H-04k_list_engines.md"
LIST_REL = "manuals/list_engines.md"
_FORBIDDEN_NET = ("urllib", "requests", "httpx", "socket")
_STALE = ("Pennylane 已接线", "Cirq reserved")


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


def test_manual_on_disk() -> None:
    path = KNOWLEDGE / LIST_REL
    assert path.is_file()
    raw = path.read_bytes()
    assert len(raw) <= 400
    text = raw.decode("utf-8")
    for needle in ("list_engines", "哪些包", "五包", "Cirq", "interop"):
        assert needle in text
    assert "Pennylane" in text or "pennylane" in text
    assert "reserved" in text
    for phrase in _STALE:
        assert phrase not in text
    assert "twin_id=" not in text
    assert "twin_id:" not in text
    lowered = text.lower()
    for name in _FORBIDDEN_NET:
        assert name not in lowered
    assert "import " not in lowered


def test_no_minted_twin_id() -> None:
    text = (KNOWLEDGE / LIST_REL).read_text(encoding="utf-8")
    assert "twin_id=" not in text
    for query in ("list_engines", "哪些包"):
        result = _search(query)
        for item in result.get("hits") or []:
            if item.get("source") != "knowledge":
                continue
            _assert_hit_shape(item)
            assert "twin_id=" not in item["text"]


def test_note_exists() -> None:
    assert NOTE.is_file()
    text = NOTE.read_text(encoding="utf-8")
    assert "不算接线" in text
    assert "list_engines" in text
    assert "reserved" in text


def main() -> int:
    failed = 0
    for name, fn in (
        ("list_engines_hits", test_list_engines_hits),
        ("manual_on_disk", test_manual_on_disk),
        ("no_minted_twin_id", test_no_minted_twin_id),
        ("note_exists", test_note_exists),
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
