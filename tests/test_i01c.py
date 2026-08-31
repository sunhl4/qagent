"""I-01c: 3080 在办 inbox. Reads shell text only; no browser."""

from __future__ import annotations

import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHELL = ROOT / "apps" / "customer-shell"
_ROOMS = ("实验室", "写算法", "签收台", "三房间")


def _read(name: str) -> str:
    return (SHELL / name).read_text(encoding="utf-8")


def test_inbox_markup() -> None:
    html = _read("index.html")
    css = _read("app.css")
    assert "在办" in html
    assert 'id="inbox"' in html
    assert 'id="inbox-list"' in html
    assert "现在没有待拍板的上机" in html
    assert "PES" not in html
    assert "<select" not in html
    assert 'id="recipe"' not in html
    assert "btn-twin" not in html
    assert 'id="stage"' in html
    for word in _ROOMS:
        assert word not in html
        assert word not in css
    assert ".inbox" in css
    assert "dsh-workspace" not in css
    assert "sidebar.brand" not in html
    assert "sidebar.brand" not in css


def test_assignments_and_approve_path() -> None:
    js = _read("app.js")
    html = _read("index.html")
    css = _read("app.css")
    assert "/api/assignments" in js
    assert "status=needs_ask" in js
    assert "批准上机" in js
    assert 'send("批准")' in js
    assert "先不上机" in js
    assert 'send("先不批")' in js
    assert "X-QAGENT-APPROVE-TOKEN" in js
    assert "/api/chat/status" in js
    assert "aria-busy" in js
    assert 'ev.target === $("prompt")' in js
    assert "btn-twin" not in js
    assert "/approve" not in js
    assert "PES" not in js
    for word in _ROOMS:
        assert word not in js
    blob = html + js + css
    assert "workspace chrome" not in blob
    assert "dsh-web" not in blob


def main() -> int:
    failed = 0
    for name, fn in (
        ("inbox_markup", test_inbox_markup),
        ("assignments_and_approve_path", test_assignments_and_approve_path),
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
