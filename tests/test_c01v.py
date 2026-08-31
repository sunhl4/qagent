"""C-01v: not-ready settings open the staff model pack. Chat mux still send(批准)."""

from __future__ import annotations

import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT
SHELL = ROOT / "apps" / "customer-shell"
NOTE = REPO / "docs" / "execution" / "C-01v_staff_pack.md"
_CLAIM_PASS = ("G0 已通过", "G1 已通过", "G2 已通过", "G0 passed", "G1 passed", "G2 passed")


def _js() -> str:
    return (SHELL / "app.js").read_text(encoding="utf-8")


def _html() -> str:
    return (SHELL / "index.html").read_text(encoding="utf-8")


def _boot() -> str:
    return _js().split("async function boot")[1]


def _add_message() -> str:
    return _js().split('if (extras && extras.awaiting === "approve")')[1].split("function paintWelcome")[0]


def test_not_ready_opens_staff_pack() -> None:
    js = _js()
    html = _html()
    boot = _boot()
    open_fn = js.split("function openSettingsDialog")[1].split("function shortAssignmentId")[0]
    reveal = js.split("function revealStaffPackIfNeeded")[1].split("function openSettingsDialog")[0]
    assert "function revealStaffPackIfNeeded" in js
    assert "details.staff-pack" in reveal
    assert "pack.open = true" in reveal
    assert '!state.ready' in reveal
    assert 'role() !== "customer"' in reveal
    assert "revealStaffPackIfNeeded" in open_fn
    assert "revealStaffPackIfNeeded" in boot
    assert '$("settings").showModal()' in boot
    assert 'class="staff-pack"' in html
    assert 'id="llm_base_url"' in html
    assert 'id="llm_model"' in html
    assert 'id="secret-fieldset"' in html
    assert "/approve" not in js
    assert "twin_id=" not in js


def test_chat_bubble_still_sends_approve() -> None:
    bubble = _add_message()
    assert 'send("批准")' in bubble
    assert 'send("先不批")' in bubble
    assert "assignmentAction" not in bubble


def test_note_copies_hit() -> None:
    assert NOTE.is_file(), NOTE
    text = NOTE.read_text(encoding="utf-8")
    assert "staff-pack" in text
    assert "revealStaffPackIfNeeded" in text
    assert "不算 G0" in text
    assert 'send("批准")' in text
    assert "未 commit" in text
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
        ("not_ready_opens_staff_pack", test_not_ready_opens_staff_pack),
        ("chat_bubble_still_sends_approve", test_chat_bubble_still_sends_approve),
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
