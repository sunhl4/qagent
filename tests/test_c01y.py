"""C-01y: commercial face — layout, starters, new chat. Not a frozen UCCSD path."""

from __future__ import annotations

import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT
SHELL = ROOT / "apps" / "customer-shell"
NOTE = REPO / "docs" / "execution" / "C-01y_commercial_face.md"
_CLAIM_PASS = ("G0 已通过", "G1 已通过", "G2 已通过", "G0 passed", "G1 passed", "G2 passed")
_ROOMS = ("实验室", "写算法", "签收台", "三房间")
_WALLS = ("Finder", "工作区门槛", "dsh-workspace", "dsh-web", "workspace chrome")
_LINE = "${pack.label} · ${pack.kind} · ${pack.status}"


def _js() -> str:
    return (SHELL / "app.js").read_text(encoding="utf-8")


def _html() -> str:
    return (SHELL / "index.html").read_text(encoding="utf-8")


def _css() -> str:
    return (SHELL / "app.css").read_text(encoding="utf-8")


def _welcome() -> str:
    return _js().split("function paintWelcome")[1].split("function fillSettings")[0]


def _add_message() -> str:
    return _js().split('if (extras && extras.awaiting === "approve")')[1].split("function paintWelcome")[0]


def test_layout_and_tokens() -> None:
    css = _css()
    html = _html()
    assert "--radius" in css
    assert "--shadow" in css
    assert "--gold-dim" in css
    assert ".inbox { grid-column: 2; grid-row: 2 / 4; }" in css or "grid-row: 2 / 4" in css
    assert ".composer { grid-column: 1; grid-row: 3; }" in css or "grid-row: 3" in css
    assert 'id="btn-new"' in html
    assert "新对话" in html
    assert "Enter 发送" in html
    assert "不必报内部配方名" in html
    assert "在办" in html
    assert "实验记录 / ELN" in html
    assert "附上线路" in html
    print("commercial tokens and rail layout stay")


def test_starters_are_not_uccsd() -> None:
    welcome = _welcome()
    js = _js()
    assert "你想做什么？" in welcome
    assert 'class="starters"' in welcome
    assert "先看看接了哪些软件" in welcome
    assert "先估计，先不上机" in welcome
    assert "UCCSD" not in welcome
    assert "uccsd_pauli" not in welcome
    assert "氢分子" not in welcome
    assert _LINE in welcome
    assert 'class="packs"' in welcome
    pack_loop = welcome.split("(status.engines || []).forEach")[1]
    assert "innerHTML" not in pack_loop
    newchat = js.split("function newChat")[1].split("async function boot")[0]
    assert "function newChat" in js
    assert "/api/agent/reset" in newchat
    assert "token()" in newchat
    assert newchat.index("token()") < newchat.index("/api/agent/reset")
    assert "setBusy(true)" in newchat
    assert "这一页已清空" in newchat
    assert "approval requires" not in js
    assert "data.error" not in newchat
    print("starters stay generic; packs lock stays")


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
    assert "btn-twin" not in blob
    assert "sidebar.brand" not in css
    for word in _ROOMS + _WALLS:
        assert word not in blob, word
    print("approve mux and hard rails stay")


def test_note_copies_hit() -> None:
    assert NOTE.is_file(), NOTE
    text = NOTE.read_text(encoding="utf-8")
    assert "C-01y" in text
    assert "不算 G0" in text
    assert "未 commit" in text
    assert "ionstack_twin_run" in text
    assert "你想做什么？" in text
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
        ("layout_and_tokens", test_layout_and_tokens),
        ("starters_are_not_uccsd", test_starters_are_not_uccsd),
        ("approve_and_hard_rails", test_approve_and_hard_rails),
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
