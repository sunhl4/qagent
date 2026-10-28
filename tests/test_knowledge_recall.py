"""P5-B2 knowledge recall governance: immediacy, expiry boundary, multi-root isolation.

The four P5 hardening claims were verified here against the kernel gate:

- revocation is immediately visible to the next search in the same process
  (the registry is re-read per call; there is no cached admission state);
- the expiry cut is the exact recorded epoch: visible before, gone after;
- multiple configured roots serve their own registries; a revocation in one
  root never widens or narrows another root's facts, and audience mixing
  across roots stays per-root;
- a changed document stops being served under the old identity (stale_hash)
  and becomes searchable again once it is re-approved under a new digest.
"""

from __future__ import annotations

import hashlib
import json
import time


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


def _write_registry(root, entries: list[dict]) -> None:
    (root / "registry.json").write_text(
        json.dumps({"version": "1.0.0", "entries": entries}), encoding="utf-8")


def _hits(result: dict) -> set[str]:
    return {row["title"] for row in result["hits"]}


def test_revocation_is_immediate_to_the_next_search(tmp_path, monkeypatch) -> None:
    root = tmp_path / "kb"
    root.mkdir()
    (root / "doc.md").write_text("needle 撤权前的段落", encoding="utf-8")
    _write_registry(root, [_entry(root, "doc.md")])
    monkeypatch.setattr(roots_module(), "roots", lambda: (("builtin", root),))
    first = roots_module().search({"query": "needle"}, preset="lab")
    assert "doc" in _hits(first)
    _write_registry(root, [_entry(root, "doc.md", revoked=True)])
    second = roots_module().search({"query": "needle"}, preset="lab")
    assert _hits(second) == set()
    assert "revoked" in second["scan"]["reasons"]
    # Restoring the row is immediately visible too — no cached side state.
    _write_registry(root, [_entry(root, "doc.md")])
    third = roots_module().search({"query": "needle"}, preset="lab")
    assert "doc" in _hits(third)


def test_expiry_boundary_is_the_exact_epoch(tmp_path, monkeypatch) -> None:
    root = tmp_path / "kb"
    root.mkdir()
    (root / "doc.md").write_text("needle 时效边界段落", encoding="utf-8")
    boundary = int(time.time()) + 2
    _write_registry(root, [_entry(root, "doc.md", expires=boundary)])
    class Frozen:
        epoch = boundary - 2
    monkeypatch.setattr(roots_module().time, "time", lambda: Frozen.epoch)
    monkeypatch.setattr(roots_module(), "roots", lambda: (("builtin", root),))
    before = roots_module().search({"query": "needle"}, preset="lab")
    assert "doc" in _hits(before)
    Frozen.epoch = boundary
    at = roots_module().search({"query": "needle"}, preset="lab")
    # The cut uses ``time > expires``: the recorded epoch itself is still valid.
    assert "doc" in _hits(at)
    Frozen.epoch = boundary + 1
    after = roots_module().search({"query": "needle"}, preset="lab")
    assert _hits(after) == set() and "expired" in after["scan"]["reasons"]


def test_multi_root_isolation(tmp_path, monkeypatch) -> None:
    root_a = tmp_path / "kb-a"
    root_b = tmp_path / "kb-b"
    root_a.mkdir()
    root_b.mkdir()
    for root in (root_a, root_b):
        (root / "shared-name.md").write_text(
            f"needle 来自{root.name}的同名段落", encoding="utf-8", newline="\n",
        )
    _write_registry(root_a, [_entry(root_a, "shared-name.md")])
    _write_registry(root_b, [_entry(root_b, "shared-name.md", audience="internal")])

    monkeypatch.setattr(
        roots_module(), "roots",
        lambda: (("builtin", root_a), ("configured-1", root_b)),
    )
    internal = roots_module().search({"query": "needle"}, preset="lab")
    # Root A serves its own public fact; root B contains the internal fact and
    # serves it to every internal audience (boot/lab/algo). Titles collapse to
    # the shared document stem, so distinguish by root identity instead.
    titles = _hits(internal)
    assert titles == {"shared-name"}
    source_units = {row["source"].split(":", 1)[0] for row in internal["hits"]}
    assert source_units == {"builtin", "configured-1"}
    _write_registry(root_a, [_entry(root_a, "shared-name.md", revoked=True)])
    inner = roots_module().search({"query": "needle"}, preset="lab")
    sources = {row["source"].split(":", 1)[0] for row in inner["hits"]}
    assert inner["scan"]["reasons"] == ["revoked"]
    assert sources == {"configured-1"}, "root A revocation must not affect root B"
    # Sign (public audience) still loses root B's internal row while root A stays revoked.
    sign = roots_module().search({"query": "needle"}, preset="sign")
    assert _hits(sign) == set()
    assert {"revoked", "audience_filtered"} == set(sign["scan"]["reasons"])


def test_drift_serializing_round_trip(tmp_path, monkeypatch) -> None:
    root = tmp_path / "kb"
    root.mkdir()
    (root / "doc.md").write_text("needle drift 秋季版本", encoding="utf-8")
    _write_registry(root, [_entry(root, "doc.md")])
    monkeypatch.setattr(roots_module(), "roots", lambda: (("builtin", root),))
    assert "doc" in _hits(roots_module().search({"query": "needle"}, preset="lab"))
    (root / "doc.md").write_text("needle drift 冬季版本", encoding="utf-8")
    stale = roots_module().search({"query": "needle"}, preset="lab")
    assert _hits(stale) == set() and "stale_hash" in stale["scan"]["reasons"]
    # Re-approval under the new digest restores the document to recall.
    _write_registry(root, [_entry(root, "doc.md")])
    assert "doc" in _hits(roots_module().search({"query": "needle"}, preset="lab"))
