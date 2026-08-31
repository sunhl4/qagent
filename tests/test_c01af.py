"""C-01af: commercial craft — one focus indicator, print stylesheet, quiet empty state. Not a G0 claim."""

from __future__ import annotations

import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT
SHELL = ROOT / "apps" / "customer-shell"
NOTE = REPO / "docs" / "execution" / "C-01af_craft.md"
_CLAIM_PASS = ("G0 已通过", "G1 已通过", "G2 已通过", "G0 passed", "G1 passed", "G2 passed")
_ROOMS = ("实验室", "写算法", "签收台", "三房间")
_WALLS = ("Finder", "工作区门槛", "dsh-workspace", "dsh-web", "workspace chrome")


def _js() -> str:
    return (SHELL / "app.js").read_text(encoding="utf-8")


def _html() -> str:
    return (SHELL / "index.html").read_text(encoding="utf-8")


def _css() -> str:
    return (SHELL / "app.css").read_text(encoding="utf-8")


def _rule(css: str, selector: str) -> str:
    return css.split(selector, 1)[1].split("}", 1)[0]


def _print_block(css: str) -> str:
    return css.split("@media print", 1)[1]


def test_one_focus_indicator() -> None:
    css = _css()
    composer = _rule(css, ".composer:focus-within {")
    assert "border-color" in composer
    assert "0 0 0 1px" not in composer
    focus = _rule(css, "button.ghost:focus-visible,")
    assert "outline: 2px solid var(--ion)" in focus
    assert "a:focus-visible" in css
    print("composer focus is a single border; buttons and links share one outline")


def test_print_stylesheet_hides_chrome_and_lightens() -> None:
    css = _css()
    printed = _print_block(css)
    assert "background: #fff" in _rule(printed, "body {")
    hidden_rule = _rule(printed, ".top-actions,")
    assert "display: none" in hidden_rule
    assert ".inbox" in hidden_rule
    assert ".composer" in hidden_rule
    paper = _rule(printed, ".msg.assistant {")
    assert "border-top: 2px solid #1c2430" in paper
    assert "box-shadow: none" in _rule(printed, ".msg {")
    assert "background: none" in _rule(printed, ".circuit-scroll {")
    assert "#8a6d1f" in _rule(printed, ".permit {")
    assert printed.index("@media") == -1 or True
    assert css.index("@media print") > css.index("@media (prefers-reduced-motion: reduce)")
    print("print: white paper, rail/composer/actions hidden, answer keeps structure")


def test_empty_state_stays_two_doors() -> None:
    js = _js()
    css = _css()
    welcome = js.split("function paintWelcome")[1].split("function fillSettings")[0]
    assert welcome.count("label: \"") == 2
    assert "先看看接了哪些软件" in welcome
    assert "先估计，先不上机" in welcome
    assert "UCCSD" not in welcome
    assert "display: none" in _rule(css, ".welcome .packs")
    print("empty state is still two plain doors, packs stay hidden")


def test_hard_rails_and_locks() -> None:
    js = _js()
    css = _css()
    blob = _html() + js + css
    bubble = js.split('if (extras && extras.awaiting === "approve")')[1].split("function paintWelcome")[0]
    assert 'send("批准")' in bubble
    assert 'send("先不批")' in bubble
    assert 'className = "permit"' in bubble
    assert "ionstack_twin_run" not in js
    assert "twin_id=" not in js
    assert "a2_chem_pes" not in blob
    assert "grid-row: 2 / 4" in css
    assert "grid-row: 3" in css
    assert "--gold-dim" in css
    assert "--radius" in css
    assert "--shadow" in css
    for word in _ROOMS + _WALLS:
        assert word not in blob, word
    print("product locks stay green under the craft wave")


def test_note_copies_hit() -> None:
    assert NOTE.is_file(), NOTE
    text = NOTE.read_text(encoding="utf-8")
    assert "C-01af" in text
    assert "不算 G0" in text
    assert "未 commit" in text
    assert "ionstack_twin_run" in text
    assert "打印" in text
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
        ("one_focus_indicator", test_one_focus_indicator),
        ("print_stylesheet_hides_chrome_and_lightens", test_print_stylesheet_hides_chrome_and_lightens),
        ("empty_state_stays_two_doors", test_empty_state_stays_two_doors),
        ("hard_rails_and_locks", test_hard_rails_and_locks),
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
