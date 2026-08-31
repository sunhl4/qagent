"""R-03c: unsigned assignment/receipt face must not look signed. Text on html/js/css."""

from __future__ import annotations

import re
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHELL = ROOT / "apps" / "customer-shell"
_ROOMS = ("实验室", "写算法", "签收台", "三房间")


def _read(name: str) -> str:
    return (SHELL / name).read_text(encoding="utf-8")


def _blob() -> str:
    return _read("index.html") + _read("app.js") + _read("app.css")


def test_signed_vs_unsigned_classes() -> None:
    html = _read("index.html")
    js = _read("app.js")
    css = _read("app.css")
    assert "face-unsigned" in html
    assert "face-signed" not in html
    assert "function faceKind" in js
    assert 'value === "signed"' in js
    assert 'return "signed"' in js
    assert 'return "waiting"' in js
    assert 'return "stopped"' in js
    assert "face-signed" in js
    assert "face-waiting" in js
    assert "face-stopped" in js
    assert ".face-signed" in css
    assert ".face-waiting" in css
    assert ".face-stopped" in css
    assert ".face-unsigned" in css
    assert ".face-signed .face-seal" in css
    assert "--seal" in css
    assert "var(--seal)" in css
    waiting = css.split(".face-waiting")[1].split(".face-stopped")[0]
    stopped = css.split(".face-stopped")[1].split(".face-signed")[0]
    assert "var(--seal)" not in waiting
    assert "var(--seal)" not in stopped


def test_signed_label_not_default_empty_or_ask() -> None:
    html = _read("index.html")
    js = _read("app.js")
    assert "已签收" not in html
    assert "现在没有待拍板的上机" in html
    assert "还没有封条回执" in html
    assert "未签收不会盖绿印" in html
    assert 'id="inbox-empty"' in html
    assert 'id="receipt-empty"' in html
    assert '|| "已签收"' not in js
    assert 'row.status || "needs_ask"' in js
    assert 'status || "needs_ask"' in js
    assert 'if (value === "signed") return "已签收"' in js
    assert 'if (value === "needs_ask") return "待批准"' in js
    assert 'return "未签收"' in js
    label_fn = js.split("function faceLabel")[1].split("function signedTwinId")[0]
    assert label_fn.index('value === "signed"') < label_fn.index('"已签收"')
    assert "status=needs_ask" in js
    assert "filter((row) => row && row.status === \"needs_ask\")" in js


def test_c01_i01c_copy_kept() -> None:
    html = _read("index.html")
    js = _read("app.js")
    css = _read("app.css")
    blob = html + js + css
    assert "在办" in html
    assert "平常话" in html
    assert "批准上机" in js
    assert 'send("批准")' in js
    assert "先不上机" in js
    assert 'id="inbox"' in html
    assert 'id="inbox-list"' in html
    assert "status=needs_ask" in js
    assert "btn-twin" not in blob
    for word in _ROOMS:
        assert word not in blob


def test_no_fake_twin_id_in_markup() -> None:
    html = _read("index.html")
    js = _read("app.js")
    css = _read("app.css")
    static = html + css
    assert "twin_id" not in html
    assert "twin_id" not in css
    assert not re.search(r"twin_[0-9A-Za-z]{3,}", static)
    assert "twin_fixture" not in js
    assert "twin_demo" not in js
    assert "twin_leak" not in js
    assert 'String(row.status || "") !== "signed"' in js
    assert "handles.twin_id" in js
    twin_fn = js.split("function signedTwinId")[1].split("function inboxKey")[0]
    assert "!== \"signed\"" in twin_fn
    assert "handles.twin_id" in twin_fn
    assert twin_fn.index("!== \"signed\"") < twin_fn.index("handles.twin_id")
    assert "kind === \"signed\"" in js
    assert "face-seal" in js


def main() -> int:
    failed = 0
    for name, fn in (
        ("signed_vs_unsigned_classes", test_signed_vs_unsigned_classes),
        ("signed_label_not_default_empty_or_ask", test_signed_label_not_default_empty_or_ask),
        ("c01_i01c_copy_kept", test_c01_i01c_copy_kept),
        ("no_fake_twin_id_in_markup", test_no_fake_twin_id_in_markup),
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
