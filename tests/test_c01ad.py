"""C-01ad: user turn stays a conversation turn; fault strip is labelled. Not a G0 claim."""

from __future__ import annotations

import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT
SHELL = ROOT / "apps" / "customer-shell"
NOTE = REPO / "docs" / "execution" / "C-01ad_turns_and_fault.md"
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


def test_user_turn_stays_a_conversation_turn() -> None:
    css = _css()
    user = _rule(css, ".msg.user {")
    assert "align-self: flex-end" in user
    assert "border-right: 2px solid" in user
    assert "var(--ion)" in user
    assert "border-radius: 0" in user
    assert "background: transparent" in user
    assert "box-shadow: none" in user
    assert "#d5e4ef" not in user
    print("user turn keeps its conversation seat; no bubble, no hardcoded hex")


def test_fault_strip_is_labelled_not_model_speech() -> None:
    css = _css()
    js = _js()
    tag = _rule(css, ".msg.fault .msg-body::before {")
    assert 'content: "故障"' in tag
    assert "var(--stop)" in tag
    assert "letter-spacing: 0.18em" in tag
    fault = _rule(css, ".msg.fault {")
    assert "border-left-color: var(--stop)" in fault
    assert "这次没连上。再发一句即可。" in js
    assert "function humanChatFault" in js
    assert "function readJson" in js
    print("fault carries a 故障 label; recovery copy and parsers stay")


def test_busy_pulse_stops_under_reduced_motion() -> None:
    css = _css()
    assert ".msg.busy .msg-body::after" in css
    reduced = css.split("@media (prefers-reduced-motion: reduce)", 1)[1]
    assert ".msg.busy .msg-body::after" in reduced
    assert "animation: none" in reduced
    print("busy paper stays; pulse stops when the person asks for less motion")


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
    poll = js.split("async function pollStatus")[1].split("async function saveSettings")[0]
    assert "misses >= 8" in poll
    for word in _ROOMS + _WALLS:
        assert word not in blob, word
    print("permit, polling tolerance, and product locks stay green")


def test_note_copies_hit() -> None:
    assert NOTE.is_file(), NOTE
    text = NOTE.read_text(encoding="utf-8")
    assert "C-01ad" in text
    assert "不算 G0" in text
    assert "未 commit" in text
    assert "ionstack_twin_run" in text
    assert "故障" in text
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
        ("user_turn_stays_a_conversation_turn", test_user_turn_stays_a_conversation_turn),
        ("fault_strip_is_labelled_not_model_speech", test_fault_strip_is_labelled_not_model_speech),
        ("busy_pulse_stops_under_reduced_motion", test_busy_pulse_stops_under_reduced_motion),
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
