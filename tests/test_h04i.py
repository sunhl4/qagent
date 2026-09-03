"""H-04i: knowledge hits claim_blocked / cirq_claim_twin_id."""

from __future__ import annotations

import os
import re
import tempfile
import traceback
from pathlib import Path

from qagent.adapters.docs import WiredDocs

ROOT = Path(__file__).resolve().parents[1]
KNOWLEDGE = ROOT / "knowledge"
NOTE = ROOT / "docs" / "execution" / "H-04i_eln_claim.md"
ELN_REL = "manuals/eln.md"
_FORBIDDEN_NET = ("urllib", "requests", "httpx", "socket")
_FORBIDDEN_FAKE = ("twin_fixture", "twin_demo", "twin_leak", "twin_abc")
_FORBIDDEN_PASS = ("G0 已通过", "G2 已通过")
_HANDLES = frozenset({"circuit_id", "asset_id", "twin_id"})
_ID_RE = re.compile(r"\b[a-z]+_id\b")
_EMPTY_DETAIL = "知识库是空的。没有这条。"
_MISS_QUERY = "this-query-should-miss-zzzz-h04i"
_QUERIES = ("claim_blocked", "cirq_claim_twin_id")
_H04F_LOCK = (
    "GET /api/eln",
    "recipe_pin",
    "estimate",
    "twin_signoff",
    "b3",
    "assignment",
    "twin_id",
    "TwinRun",
    "POST",
    "密钥",
    "电路正文",
)


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


def test_claim_hits() -> None:
    for query in _QUERIES:
        _assert_knowledge_file(query, ELN_REL)


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
    assert "没有这条" in detail


def test_no_network_in_manual() -> None:
    text = (KNOWLEDGE / ELN_REL).read_text(encoding="utf-8")
    lowered = text.lower()
    for name in _FORBIDDEN_NET:
        assert name not in lowered
    assert "import " not in lowered


def test_no_minted_twin_id() -> None:
    text = (KNOWLEDGE / ELN_REL).read_text(encoding="utf-8")
    assert "twin_id=" not in text
    assert "twin_id:" not in text
    for fake in _FORBIDDEN_FAKE:
        assert fake not in text
    extra = set(_ID_RE.findall(text)) - _HANDLES
    assert not extra, extra
    for query in _QUERIES:
        result = _search(query)
        for item in result.get("hits") or []:
            if item.get("source") != "knowledge":
                continue
            _assert_hit_shape(item)
            assert "twin_id=" not in item["text"]
            assert "twin_id:" not in item["text"]
            for fake in _FORBIDDEN_FAKE:
                assert fake not in item["text"]


def test_note_exists() -> None:
    assert NOTE.is_file()
    text = NOTE.read_text(encoding="utf-8")
    assert "QAGENT_KNOWLEDGE_PATH" in text
    assert "claim_blocked" in text
    assert "cirq_claim_twin_id" in text
    assert "GET /api/eln" in text
    for phrase in _FORBIDDEN_PASS:
        assert phrase not in text


def test_manual_on_disk() -> None:
    path = KNOWLEDGE / ELN_REL
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert len(text) <= 400
    for lock in _H04F_LOCK:
        assert lock in text, lock
    assert "claim_blocked" in text
    assert "cirq_claim_twin_id" in text
    assert "短 reason" in text
    assert "Cirq 拒铸" in text
    assert "twin_id=" not in text
    assert "twin_id:" not in text
    assert "import " not in text.lower()
    for name in _FORBIDDEN_NET:
        assert name not in text.lower()
    for phrase in _FORBIDDEN_PASS:
        assert phrase not in text
    extra = set(_ID_RE.findall(text)) - _HANDLES
    assert not extra, extra


def main() -> int:
    failed = 0
    for name, fn in (
        ("claim_hits", test_claim_hits),
        ("empty_lib_honest", test_empty_lib_honest),
        ("no_network_in_manual", test_no_network_in_manual),
        ("no_minted_twin_id", test_no_minted_twin_id),
        ("note_exists", test_note_exists),
        ("manual_on_disk", test_manual_on_disk),
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
