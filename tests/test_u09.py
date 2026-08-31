"""U-09: 3080 task workspace. Costume off; locks stay. Not a G0 claim."""

from __future__ import annotations

import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT
SHELL = ROOT / "apps" / "customer-shell"
NOTE = REPO / "docs" / "execution" / "U-09_console.md"
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


def test_console_skeleton() -> None:
    html = _html()
    css = _css()
    js = _js()
    assert 'class="nav"' in html
    assert 'data-nav="task"' in html
    assert 'data-nav="machine"' in html
    assert 'data-nav="record"' in html
    assert 'data-tab="task"' in html
    assert 'data-tab="machine"' in html
    assert 'data-tab="record"' in html
    assert 'data-settings-tab="workspace"' in html
    assert 'data-settings-tab="machine"' in html
    assert 'data-settings-tab="capability"' in html
    assert "在办" in html
    assert "实验记录 / ELN" in html
    assert 'id="gov-lamps"' in html
    assert ">对话</h3>" in html
    assert "composer-kicker" in html
    assert "grid-row: 2 / 4" in css
    assert "grid-row: 3" in css
    assert "--gold-dim" in css
    assert "--radius" in css
    assert "--shadow" in css
    assert "sidebar.brand" not in css
    assert "function showInspector" in js
    assert "function showSettingsPage" in js
    assert "function paintGov" in js
    print("console skeleton: nav + inspector tabs + settings pages")


def test_asks_lamp_does_not_print_jsonl_count() -> None:
    lamps = _js().split("function faceGovLamps")[1].split("function faceGovLife")[0]
    assert "待批" in lamps
    assert "state.hasAsk" in lamps
    assert "${label} ${value}" not in lamps
    assert "lamps.asks" not in lamps
    print("asks lamp lights from open asks, never prints jsonl length")


def test_gold_stays_on_permit_only() -> None:
    css = _css()
    act = _rule(css, "button.act {")
    assert "background: var(--elev)" in act
    assert "var(--gold)" not in act
    scoped = css.split(".permit button.act", 1)[1].split("}", 1)[0]
    assert "background: var(--gold)" in scoped
    assert ".inbox-row button.act" in css
    assert "color-mix(in srgb, var(--gold) 45%" in _rule(css, ".permit {")
    print("gold stays on permit and rail approve")


def test_hard_rails() -> None:
    js = _js()
    css = _css()
    html = _html()
    blob = html + js + css
    bubble = js.split('if (extras && extras.awaiting === "approve")')[1].split("function paintWelcome")[0]
    assert 'send("批准")' in bubble
    assert 'send("先不批")' in bubble
    assert 'className = "permit"' in bubble
    assert "assignmentAction" not in bubble
    assert "ionstack_twin_run" not in js
    assert "twin_id=" not in js
    assert "a2_chem_pes" not in blob
    painter = js.split("function paintSessions")[1].split("function circuitMount")[0]
    assert "addEventListener" not in painter
    assert "/api/chat/switch" not in js
    for word in _ROOMS + _WALLS:
        assert word not in blob, word
    print("hard rails stay green under U-09")


def test_note_copies_hit() -> None:
    assert NOTE.is_file(), NOTE
    text = NOTE.read_text(encoding="utf-8")
    assert "U-09" in text
    assert "不算 G0" in text
    assert "未 commit" in text
    assert "ionstack_twin_run" in text
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
        ("console_skeleton", test_console_skeleton),
        ("asks_lamp_does_not_print_jsonl_count", test_asks_lamp_does_not_print_jsonl_count),
        ("gold_stays_on_permit_only", test_gold_stays_on_permit_only),
        ("hard_rails", test_hard_rails),
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
