"""C-01z: local KaTeX on the customer face. Not Overleaf. Not a G0 claim."""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT
sys.path.insert(0, str(ROOT / "src"))

from qagent.entrypoints.shell_http import _safe_static_path
from qagent.models.customer_voice import CUSTOMER_VOICE_HINT

SHELL = ROOT / "apps" / "customer-shell"
KATEX = SHELL / "vendor" / "katex"
NOTE = REPO / "docs" / "execution" / "C-01z_katex.md"
SKILL = ROOT / "skills" / "vibe-across-engines" / "SKILL.md"
_CLAIM_PASS = ("G0 已通过", "G1 已通过", "G2 已通过", "G0 passed", "G1 passed", "G2 passed")
_ROOMS = ("实验室", "写算法", "签收台", "三房间")
_WALLS = ("Finder", "工作区门槛", "dsh-workspace", "dsh-web", "workspace chrome")


def _js() -> str:
    return (SHELL / "app.js").read_text(encoding="utf-8")


def _html() -> str:
    return (SHELL / "index.html").read_text(encoding="utf-8")


def _css() -> str:
    return (SHELL / "app.css").read_text(encoding="utf-8")


def _add_message() -> str:
    return _js().split('if (extras && extras.awaiting === "approve")')[1].split("function paintWelcome")[0]


def _fill() -> str:
    return _js().split("function fillRichText")[1].split("function downloadCircuitProgram")[0]


def _face_load() -> str:
    return _js().split("async function loadCircuitFace")[1].split("function drawCircuitSvg")[0]


def test_vendor_and_html_wire() -> None:
    html = _html()
    js = _js()
    css = _css()
    assert (KATEX / "katex.min.js").is_file()
    assert (KATEX / "katex.min.css").is_file()
    assert (KATEX / "fonts" / "KaTeX_Main-Regular.woff2").is_file()
    assert (KATEX / "VERSION").read_text(encoding="utf-8").strip() == "0.16.22"
    assert (KATEX / "katex.min.js").stat().st_size > 100000
    assert "/static/vendor/katex/katex.min.css" in html
    assert "/static/vendor/katex/katex.min.js" in html
    assert html.index("/static/vendor/katex/katex.min.js") < html.index("/static/app.js")
    assert "cdn.jsdelivr" not in html
    assert "cdn.jsdelivr" not in js
    assert "function renderMath" in js
    assert "function splitMath" in js
    assert "function takeDisplayMath" in js
    assert "function fillRichText" in js
    assert "throwOnError: false" in js
    assert "trust: false" in js
    assert ".math-block" in css
    assert ".math-inline" in css
    print("vendor katex is local and wired")


def test_static_path_stays_inside_shell() -> None:
    js = _safe_static_path("vendor/katex/katex.min.js")
    css = _safe_static_path("vendor/katex/katex.min.css")
    font = _safe_static_path("vendor/katex/fonts/KaTeX_Main-Regular.woff2")
    assert js is not None and js.is_file()
    assert css is not None and css.is_file()
    assert font is not None and font.is_file()
    assert _safe_static_path("app.js") is not None
    assert _safe_static_path("../index.html") is None
    assert _safe_static_path("vendor/katex/../../../etc/passwd") is None
    assert _safe_static_path(".env") is None
    assert _safe_static_path("vendor/../app.js") is None
    assert _safe_static_path("vendor/katex/NOTICE") is None
    print("static vendor paths stay under the shell")


def test_fill_does_not_dump_reply_html() -> None:
    fill = _fill()
    face = _face_load()
    assert "innerHTML" not in fill
    assert "takeDisplayMath" in fill
    assert "电路还没钉住，画不出图。" in face
    assert "data.error" not in face
    print("math nodes stay off the whole reply; pin miss is human")


def test_approve_and_hard_rails() -> None:
    js = _js()
    html = _html()
    css = _css()
    bubble = _add_message()
    blob = html + js + css
    assert 'send("批准")' in bubble
    assert 'send("先不批")' in bubble
    assert "assignmentAction" not in bubble
    assert "ionstack_twin_run" not in js
    assert "twin_id=" not in js
    assert "a2_chem_pes" not in blob
    for word in _ROOMS + _WALLS:
        assert word not in blob, word
    print("approve mux and hard rails stay")


def test_voice_tells_model_the_face_renders() -> None:
    assert "短结论" in CUSTOMER_VOICE_HINT
    assert "脸会渲染" in CUSTOMER_VOICE_HINT
    assert r"\(...\)" in CUSTOMER_VOICE_HINT
    skill = SKILL.read_text(encoding="utf-8")
    assert "短结论" in skill
    assert "脸会渲染" in skill
    assert "不必改成 Unicode" in skill
    print("voice and skill keep latex delimiters")


def test_note_copies_hit() -> None:
    assert NOTE.is_file(), NOTE
    text = NOTE.read_text(encoding="utf-8")
    assert "C-01z" in text
    assert "不算 G0" in text
    assert "未 commit" in text
    assert "ionstack_twin_run" in text
    assert "KaTeX" in text
    assert "Overleaf" in text
    for phrase in _CLAIM_PASS:
        assert phrase not in text


def test_this_file_does_not_skip() -> None:
    text = Path(__file__).read_text(encoding="utf-8")
    assert ("pytest" + ".skip") not in text
    assert ("unittest" + ".skip") not in text
    assert ("skip" + "Test") not in text


def main() -> int:
    failed = 0
    for name, fn in (
        ("vendor_and_html_wire", test_vendor_and_html_wire),
        ("static_path_stays_inside_shell", test_static_path_stays_inside_shell),
        ("fill_does_not_dump_reply_html", test_fill_does_not_dump_reply_html),
        ("approve_and_hard_rails", test_approve_and_hard_rails),
        ("voice_tells_model_the_face_renders", test_voice_tells_model_the_face_renders),
        ("note_copies_hit", test_note_copies_hit),
        ("this_file_does_not_skip", test_this_file_does_not_skip),
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
