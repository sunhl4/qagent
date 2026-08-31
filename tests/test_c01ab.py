"""C-01ab: assistant answer reads as science paper. CSS-only wave. Not a G0 claim."""

from __future__ import annotations

import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT
SHELL = ROOT / "apps" / "customer-shell"
NOTE = REPO / "docs" / "execution" / "C-01ab_science_paper.md"
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


def test_paper_measure_and_rhythm() -> None:
    css = _css()
    assert ".msg.assistant .msg-body" in css
    assert "max-width: 72ch" in _rule(css, ".msg.assistant .msg-body")
    assert "margin: 0 0 14px" in _rule(css, ".msg-body p {")
    heads = _rule(css, ".msg-body h3, .msg-body h4, .msg-body h5 {")
    assert "margin: 20px 0 10px" in heads
    assert ".msg-body > h3:first-child" in css
    assert "font-family: var(--serif)" in _rule(css, ".msg-body h3 {")
    assert "line-height: 1.75" in _rule(css, ".msg.assistant {")
    print("paper measure and reading rhythm on the assistant answer")


def test_booktabs_table_not_grid() -> None:
    css = _css()
    table = _rule(css, ".msg-body table {")
    assert "border-top: 2px solid var(--line-strong)" in table
    assert "border-bottom: 2px solid var(--line-strong)" in table
    cells = _rule(css, ".msg-body th, .msg-body td {")
    assert "border: 0" in cells
    head = _rule(css, ".msg-body thead th {")
    assert "border-bottom: 1px solid var(--line)" in head
    assert "color: var(--ink)" in head
    assert "var(--gold)" not in head
    assert ".msg-body th { color: var(--gold)" not in css
    print("tables read as booktabs; header is ink, not gold")


def test_math_and_code_read_as_print() -> None:
    css = _css()
    block = _rule(css, ".msg-body .math-block {")
    assert "margin: 20px 0" in block
    assert "overflow-x: auto" in block
    assert "margin: 0.2em 0" in _rule(css, ".msg-body .katex-display {")
    code = _rule(css, ".msg-body code {")
    assert "font-family: var(--mono)" in code
    assert "--mono" in css.split("*: {", 1)[0]
    assert "var(--gold)" not in code
    assert "var(--ion)" not in code
    print("display math has air; code is mono and quiet")


def test_circuit_figure_sits_on_paper() -> None:
    css = _css()
    face = _rule(css, ".circuit-face {")
    assert "background: transparent" in face
    assert "border-top: 1px solid var(--line)" in face
    assert "border-bottom: 1px solid var(--line)" in face
    assert "border-radius: 0" in face
    cap = _rule(css, ".circuit-cap {")
    assert "letter-spacing: 0.08em" in cap
    assert "下载这份线路" in _js()
    print("circuit figure sits on the paper with a caption, download stays")


def test_structure_and_hard_rails_untouched() -> None:
    js = _js()
    css = _css()
    blob = _html() + js + css
    bubble = js.split('if (extras && extras.awaiting === "approve")')[1].split("function paintWelcome")[0]
    assert 'send("批准")' in bubble
    assert 'send("先不批")' in bubble
    assert "assignmentAction" not in bubble
    assert "ionstack_twin_run" not in js
    assert "twin_id=" not in js
    assert "a2_chem_pes" not in blob
    assert "grid-row: 2 / 4" in css
    assert "grid-row: 3" in css
    assert "--gold-dim" in css
    assert "--radius" in css
    assert "--shadow" in css
    assert "display: none" in _rule(css, ".welcome .packs")
    for word in _ROOMS + _WALLS:
        assert word not in blob, word
    print("structure locks and hard rails stay green")


def test_note_copies_hit() -> None:
    assert NOTE.is_file(), NOTE
    text = NOTE.read_text(encoding="utf-8")
    assert "C-01ab" in text
    assert "不算 G0" in text
    assert "未 commit" in text
    assert "ionstack_twin_run" in text
    assert "科学纸" in text
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
        ("paper_measure_and_rhythm", test_paper_measure_and_rhythm),
        ("booktabs_table_not_grid", test_booktabs_table_not_grid),
        ("math_and_code_read_as_print", test_math_and_code_read_as_print),
        ("circuit_figure_sits_on_paper", test_circuit_figure_sits_on_paper),
        ("structure_and_hard_rails_untouched", test_structure_and_hard_rails_untouched),
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
