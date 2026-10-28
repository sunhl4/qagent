from __future__ import annotations

from company_agent.knowledge import search


def test_knowledge_result_has_source_and_no_absolute_path() -> None:
    payload = search({"query": "设备执行"})
    assert payload["hits"]
    hit = payload["hits"][0]
    assert set(("source", "title", "version", "snippet")) <= set(hit)
    assert not hit["source"].startswith("/")


def test_knowledge_query_term_count_is_bounded() -> None:
    try:
        search({"query": " ".join(f"term{index}" for index in range(65))})
    except ValueError as exc:
        assert "too many terms" in str(exc)
    else:
        raise AssertionError("knowledge search accepted too many terms")


def test_knowledge_search_rejects_unknown_fields() -> None:
    try:
        search({"query": "设备执行", "legacy": True})
    except ValueError as exc:
        assert "unknown fields" in str(exc)
    else:
        raise AssertionError("knowledge search accepted unknown fields")


def test_duplicate_query_terms_do_not_inflate_score() -> None:
    once = search({"query": "设备执行"})
    repeated = search({"query": "设备执行 设备执行"})
    assert once["hits"]
    assert repeated["hits"]
    assert once["hits"][0]["score"] == repeated["hits"][0]["score"]


def test_configured_knowledge_path_must_be_absolute(monkeypatch) -> None:
    monkeypatch.setenv("COMPANY_AGENT_ENABLE_CONFIGURED_KNOWLEDGE", "1")
    monkeypatch.setenv("COMPANY_AGENT_KNOWLEDGE_PATH", "relative/path")
    try:
        search({"query": "needle"})
    except ValueError as exc:
        assert "must be absolute" in str(exc)
    else:
        raise AssertionError("relative configured knowledge root was accepted")


def test_configured_knowledge_is_opt_in(monkeypatch, tmp_path) -> None:
    (tmp_path / "private.md").write_text("configured-only-needle", encoding="utf-8")
    monkeypatch.setenv("COMPANY_AGENT_KNOWLEDGE_PATH", str(tmp_path))
    monkeypatch.delenv("COMPANY_AGENT_ENABLE_CONFIGURED_KNOWLEDGE", raising=False)
    payload = search({"query": "configured-only-needle"})
    assert not [hit for hit in payload["hits"] if hit["source"].startswith("configured-")]


def test_knowledge_skips_oversized_files(monkeypatch, tmp_path) -> None:
    (tmp_path / "small.md").write_text("needle safe", encoding="utf-8")
    (tmp_path / "large.md").write_text("needle " + "x" * 1_000_001, encoding="utf-8")
    monkeypatch.setenv("COMPANY_AGENT_ENABLE_CONFIGURED_KNOWLEDGE", "1")
    monkeypatch.setenv("COMPANY_AGENT_KNOWLEDGE_PATH", str(tmp_path))
    payload = search({"query": "needle"})
    configured = [hit for hit in payload["hits"] if hit["source"].startswith("configured-")]
    assert [hit["title"] for hit in configured] == ["small"]


def test_knowledge_does_not_follow_symlinks(monkeypatch, tmp_path, make_symlink) -> None:
    outside = tmp_path.parent / "outside-secret.md"
    outside.write_text("external-needle secret", encoding="utf-8")
    make_symlink(outside, tmp_path / "linked.md")
    monkeypatch.setenv("COMPANY_AGENT_ENABLE_CONFIGURED_KNOWLEDGE", "1")
    monkeypatch.setenv("COMPANY_AGENT_KNOWLEDGE_PATH", str(tmp_path))
    payload = search({"query": "external-needle"})
    assert not [hit for hit in payload["hits"] if hit["source"].startswith("configured-")]
