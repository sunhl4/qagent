"""Architecture gates for knowledge admission governance (survey P1 3.2).

Counter-examples demanded by the survey must fail closed here:

- a revoked or unapproved document never reaches search hits;
- an expired document is excluded through its validity window;
- updated source bytes without re-approval never get served under a prior
  registry identity (``stale_hash``);
- unregistered documents are out of the index whenever a registry exists;
- internal scope never leaks to the sign (external) preset audience;
- a corrupted registry degrades honestly (``registry_invalid``), it can never
  silently admit everything;
- roots without a registry keep the legacy ad-hoc index (test fixtures).
"""

from __future__ import annotations

import hashlib
import json

import pytest


def roots_module():
    import company_agent.knowledge as knowledge

    return knowledge


def _entry(root, name: str, *, audience: str = "public", approved: bool = True,
           revoked: bool = False, expires: int | None = None) -> dict:
    raw = (root / name).read_bytes()
    return {
        "file": name,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "audience": audience,
        "approved": approved,
        "revoked": revoked,
        "expires_epoch": expires,
    }


@pytest.fixture
def governed_root(tmp_path, monkeypatch):
    root = tmp_path / "kb"
    root.mkdir()
    documents = {
        "public-doc.md": "公共段落 needle public text",
        "internal-doc.md": "内部段落 needle internal text",
        "revoked-doc.md": "撤回段落 needle revoked text",
        "expired-doc.md": "过期段落 needle expired text",
        "stale-doc.md": "被更新的段落 needle stale text",
        "unregistered-doc.md": "未登记段落 needle unregistered text",
    }
    for name, text in documents.items():
        (root / name).write_text(text, encoding="utf-8", newline="\n")
    entries = [
        _entry(root, "public-doc.md"),
        _entry(root, "internal-doc.md", audience="internal"),
        _entry(root, "revoked-doc.md", revoked=True),
        _entry(root, "expired-doc.md", expires=1),
        _entry(root, "stale-doc.md"),
    ]
    # The stale doc stops being the bytes its registry identity describes.
    (root / "stale-doc.md").write_text("被更新的段落 needle stale text NEW", encoding="utf-8")
    (root / "registry.json").write_text(
        json.dumps({"version": "1.0.0", "entries": entries}), encoding="utf-8")
    monkeypatch.setattr(roots_module(), "roots", lambda: (("builtin", root),))
    return root


def _titles(result: dict) -> set[str]:
    return {row["title"] for row in result["hits"]}


def test_sign_audience_never_sees_internal_entries(governed_root) -> None:
    result = roots_module().search({"query": "needle"}, preset="sign")
    titles = _titles(result)
    assert "public-doc" in titles
    assert "internal-doc" not in titles
    assert {"audience_filtered"} <= set(result["scan"]["reasons"])


def test_internal_presets_see_internal_entries(governed_root) -> None:
    for preset in ("boot", "lab", "algo"):
        result = roots_module().search({"query": "needle"}, preset=preset)
        titles = _titles(result)
        assert {"public-doc", "internal-doc"} <= set(titles), preset


def test_revoked_expired_stale_and_unregistered_never_hit(governed_root) -> None:
    result = roots_module().search({"query": "needle"}, preset="lab")
    titles = _titles(result)
    for banned in ("revoked-doc", "expired-doc", "stale-doc", "unregistered-doc"):
        assert banned not in titles
    assert {"revoked", "expired", "stale_hash", "unregistered"} <= set(result["scan"]["reasons"])
    assert result["scan"]["complete"] is False


def test_corrupt_registry_fails_closed(governed_root) -> None:
    (governed_root / "registry.json").write_text("{not json at all", encoding="utf-8")
    result = roots_module().search({"query": "needle public"}, preset="lab")
    assert result["hits"] == []
    assert "registry_invalid" in result["scan"]["reasons"]
    assert result["scan"]["complete"] is False


def test_registry_validation_excludes_bad_entries(tmp_path, monkeypatch) -> None:
    root = tmp_path / "kb2"
    root.mkdir()
    (root / "doc.md").write_text("text needle", encoding="utf-8")
    bad = dict(_entry(root, "doc.md"), sha256="zzz")
    (root / "registry.json").write_text(
        json.dumps({"version": "1.0.0", "entries": [bad]}), encoding="utf-8")
    monkeypatch.setattr(roots_module(), "roots", lambda: (("builtin", root),))
    # A registry that fails validation never admits anything: the root is
    # skipped with the honest governance reason instead of serving content.
    result = roots_module().search({"query": "needle"}, preset="lab")
    assert result["hits"] == []
    assert "registry_invalid" in result["scan"]["reasons"]


def test_absent_registry_keeps_legacy_index(tmp_path, monkeypatch) -> None:
    root = tmp_path / "kb3"
    root.mkdir()
    (root / "doc.md").write_text("ad hoc needle unregistered content", encoding="utf-8")
    monkeypatch.setattr(roots_module(), "roots", lambda: (("builtin", root),))
    result = roots_module().search({"query": "needle"}, preset="lab")
    assert _titles(result) == {"doc"}
    assert result["scan"]["reasons"] == []


def test_workspace_builtin_registry_admits_current_files(monkeypatch) -> None:
    from company_agent.catalog import WORKSPACE_ROOT

    knowledge_root = WORKSPACE_ROOT / "knowledge"
    monkeypatch.setattr(roots_module(), "roots", lambda: (("builtin", knowledge_root),))
    result = roots_module().search({"query": "设备执行"}, preset="lab")
    assert result["hits"], "workspace knowledge must remain searchable under the registry"
    assert result["scan"]["reasons"] == []


def test_preset_guard_rejects_unknown_values(governed_root) -> None:
    with pytest.raises(TypeError):
        roots_module().search({"query": "needle"}, preset="audit-preset")
