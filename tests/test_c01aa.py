"""C-01aa: harden chat face + instrument console. Not a G0 claim."""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT
sys.path.insert(0, str(ROOT / "src"))

from qagent.services import chat as chat_mod

SHELL = ROOT / "apps" / "customer-shell"
NOTE = REPO / "docs" / "execution" / "C-01aa_console_face.md"
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


def _send() -> str:
    return _js().split("async function send")[1].split("async function pollStatus")[0]


def _poll() -> str:
    return _js().split("async function pollStatus")[1].split("async function saveSettings")[0]


def test_chat_recovers_instead_of_giving_up() -> None:
    js = _js()
    send = _send()
    poll = _poll()
    snap = Path(ROOT / "src" / "qagent" / "services" / "chat.py").read_text(encoding="utf-8")
    assert "function readJson" in js
    assert "function humanChatFault" in js
    assert "assistant fault" in send
    assert "连线晃了一下" in send
    assert "await pollStatus(shown)" in send
    assert "这次没连上。再发一句即可。" in js
    assert "misses" in poll
    assert "misses >= 8" in poll
    assert poll.count("return;") <= 1
    assert "还在办。结果出来后会出现在这边。" in snap
    assert "同一条 dsh session" not in snap
    assert "不会改用自研循环。" in snap
    assert "这一轮没办完" in Path(ROOT / "src" / "qagent" / "entrypoints" / "shell_http.py").read_text(encoding="utf-8")
    print("chat face keeps polling; running copy stays human")


def test_console_tokens_and_locks() -> None:
    css = _css()
    html = _html()
    welcome = _welcome()
    blob = html + _js() + css
    assert "--radius" in css
    assert "--shadow" in css
    assert "--gold-dim" in css
    assert "grid-row: 2 / 4" in css
    assert "grid-row: 3" in css
    assert "display: none" in css.split(".welcome .packs")[1].split("}")[0]
    assert "composer-kicker" in html
    assert "不必报内部配方名" in html
    assert "在办" in html
    assert "实验记录 / ELN" in html
    assert "附上线路" in html
    assert "你想做什么？" in welcome
    assert "先看看接了哪些软件" in welcome
    assert "先估计，先不上机" in welcome
    assert _LINE in welcome
    assert 'class="packs"' in welcome
    assert "UCCSD" not in welcome
    assert "sidebar.brand" not in css
    for word in _ROOMS + _WALLS:
        assert word not in blob, word
    print("console tokens keep the product locks")


def test_approve_and_hard_rails() -> None:
    js = _js()
    bubble = _add_message()
    assert 'send("批准")' in bubble
    assert 'send("先不批")' in bubble
    assert "assignmentAction" not in bubble
    assert "ionstack_twin_run" not in js
    assert "twin_id=" not in js
    assert "a2_chem_pes" not in (_html() + js + _css())
    assert "function fillRichText" in js
    assert "function renderMath" in js
    print("approve mux and katex stay")


def test_note_copies_hit() -> None:
    assert NOTE.is_file(), NOTE
    text = NOTE.read_text(encoding="utf-8")
    assert "C-01aa" in text
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


def test_running_placeholder_is_human() -> None:
    assert chat_mod._from_snap({"reply": "", "running": True}, action="run")["reply"] == (
        "还在办。结果出来后会出现在这边。"
    )


def main() -> int:
    failed = 0
    for name, fn in (
        ("chat_recovers_instead_of_giving_up", test_chat_recovers_instead_of_giving_up),
        ("console_tokens_and_locks", test_console_tokens_and_locks),
        ("approve_and_hard_rails", test_approve_and_hard_rails),
        ("running_placeholder_is_human", test_running_placeholder_is_human),
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
