"""C-01ac: permit card for machine approval; gold only on permit/seal. Not a G0 claim."""

from __future__ import annotations

import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT
SHELL = ROOT / "apps" / "customer-shell"
NOTE = REPO / "docs" / "execution" / "C-01ac_permit.md"
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


def _bubble() -> str:
    return _js().split('if (extras && extras.awaiting === "approve")')[1].split("function paintWelcome")[0]


def test_approve_is_a_permit_card() -> None:
    bubble = _bubble()
    assert 'className = "permit"' in bubble
    assert "permit-title" in bubble
    assert "permit-note" in bubble
    assert "许可单" in bubble
    assert "上我们的机器前要你拍板" in bubble
    assert "article.appendChild(permit)" in bubble
    assert 'send("批准")' in bubble
    assert 'send("先不批")' in bubble
    assert "批准上机" in bubble
    assert "先不上机" in bubble
    assert "assignmentAction" not in bubble
    print("approve renders as a permit card; send mux stays")


def test_permit_estimate_is_conditional_not_invented() -> None:
    bubble = _bubble()
    assert "makespan_ns" in bubble
    assert "估计 · " in bubble
    assert "Number.isFinite(estimateNs)" in bubble
    assert "permit-estimate" in bubble
    print("estimate draws only when the field arrives; never invented")


def test_gold_only_on_permit_and_inbox_approve() -> None:
    css = _css()
    act = _rule(css, "button.act {")
    assert "background: var(--elev)" in act
    assert "var(--gold)" not in act
    scoped = css.split(".permit button.act", 1)[1].split("}", 1)[0]
    assert "background: var(--gold)" in scoped
    assert ".inbox-row button.act" in css
    assert ".permit {" in css
    assert "color-mix(in srgb, var(--gold) 45%" in _rule(css, ".permit {")
    assert "--gold-dim" in css
    print("default act is ink; gold stays on permit and rail approve")


def test_seal_meaning_is_text_not_color() -> None:
    js = _js()
    row = js.split("function paintFaceRow")[1].split("function paintReceipts")[0]
    label = js.split("function faceLabel")[1].split("function signedTwinId")[0]
    assert 'className = "face-seal"' in row
    assert 'aria-hidden' in row
    assert 'return "已签收"' in label
    print("seal dot is aria-hidden decoration; 已签收 is real text")


def test_hard_rails_and_layout_locks() -> None:
    js = _js()
    css = _css()
    blob = _html() + js + css
    assert "ionstack_twin_run" not in js
    assert "twin_id=" not in js
    assert "a2_chem_pes" not in blob
    assert "grid-row: 2 / 4" in css
    assert "grid-row: 3" in css
    assert "--radius" in css
    assert "--shadow" in css
    assert "composer-kicker" in _html()
    assert "在办" in _html()
    assert "实验记录 / ELN" in _html()
    for word in _ROOMS + _WALLS:
        assert word not in blob, word
    print("hard rails and layout locks stay green")


def test_note_copies_hit() -> None:
    assert NOTE.is_file(), NOTE
    text = NOTE.read_text(encoding="utf-8")
    assert "C-01ac" in text
    assert "不算 G0" in text
    assert "未 commit" in text
    assert "ionstack_twin_run" in text
    assert "许可单" in text
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
        ("approve_is_a_permit_card", test_approve_is_a_permit_card),
        ("permit_estimate_is_conditional_not_invented", test_permit_estimate_is_conditional_not_invented),
        ("gold_only_on_permit_and_inbox_approve", test_gold_only_on_permit_and_inbox_approve),
        ("seal_meaning_is_text_not_color", test_seal_meaning_is_text_not_color),
        ("hard_rails_and_layout_locks", test_hard_rails_and_layout_locks),
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
