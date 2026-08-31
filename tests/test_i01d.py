"""I-01d: aria-busy + shortcuts must not steal while typing. Text on html/js."""

from __future__ import annotations

import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHELL = ROOT / "apps" / "customer-shell"
NOTE = ROOT / "docs" / "execution" / "I-01d_a11y.md"
_ROOMS = ("实验室", "写算法", "签收台", "三房间")
_WALLS = ("Finder", "工作区门槛", "dsh-workspace", "dsh-web", "workspace chrome")


def _read(name: str) -> str:
    return (SHELL / name).read_text(encoding="utf-8")


def _setbusy() -> str:
    js = _read("app.js")
    return js.split("function setBusy")[1].split("async function send")[0]


def test_setbusy_aria_busy_stage() -> None:
    fn = _setbusy()
    js = _read("app.js")
    html = _read("index.html")
    assert "function setBusy" in js
    assert '$("stage").setAttribute("aria-busy"' in fn
    assert '"true"' in fn
    assert '"false"' in fn
    assert 'busy ? "true" : "false"' in fn
    assert '$("composer").setAttribute("aria-busy"' in fn or '$("send").setAttribute("aria-busy"' in fn
    assert 'id="stage"' in html
    assert 'id="composer"' in html
    assert 'id="send"' in html


def test_prompt_ime_composing() -> None:
    js = _read("app.js")
    handler = js.split('$("prompt").addEventListener("keydown"')[1].split("refreshInbox")[0]
    assert "ev.isComposing" in handler
    assert "if (ev.isComposing) return" in handler
    assert "Enter" in handler
    assert "shiftKey" in handler
    assert 'ev.target === $("prompt")' in handler
    assert "send()" in handler


def test_no_document_keydown_sends_chat() -> None:
    js = _read("app.js")
    assert 'document.addEventListener("keydown"' not in js
    assert "document.addEventListener('keydown'" not in js
    assert "document.onkeydown" not in js
    assert "window.addEventListener(\"keydown\"" not in js
    assert "window.addEventListener('keydown'" not in js
    assert "function typingInField" in js
    assert '"input"' in js
    assert '"textarea"' in js
    assert '"select"' in js
    assert "$(\"settings\").open" in js or '$("settings").open' in js


def test_settings_dialog_exists() -> None:
    html = _read("index.html")
    js = _read("app.js")
    assert 'id="settings"' in html
    assert "<dialog" in html
    assert 'id="settings-form"' in html
    assert 'method="dialog"' in html
    assert 'id="hpc_secret"' in html
    assert 'id="knowledge_path"' in html
    assert 'id="llm_model"' in html
    assert "settings-form" in js
    assert "stopPropagation" in js


def test_note_exists() -> None:
    assert NOTE.is_file(), NOTE
    text = NOTE.read_text(encoding="utf-8")
    assert "I-01d" in text
    assert "aria-busy" in text
    assert "isComposing" in text
    assert "method=dialog" in text or 'method="dialog"' in text
    assert "快捷键" in text or "不抢" in text


def test_no_third_loop_or_rooms() -> None:
    html = _read("index.html")
    js = _read("app.js")
    css = _read("app.css")
    blob = html + js + css
    for word in _ROOMS:
        assert word not in blob
    for word in _WALLS:
        assert word not in blob
    assert "ionstack_twin_run" not in js
    assert "btn-twin" not in html
    assert "btn-twin" not in js
    assert ".sr-only" in css
    assert "focus-visible" in css


def main() -> int:
    failed = 0
    for name, fn in (
        ("setbusy_aria_busy_stage", test_setbusy_aria_busy_stage),
        ("prompt_ime_composing", test_prompt_ime_composing),
        ("no_document_keydown_sends_chat", test_no_document_keydown_sends_chat),
        ("settings_dialog_exists", test_settings_dialog_exists),
        ("note_exists", test_note_exists),
        ("no_third_loop_or_rooms", test_no_third_loop_or_rooms),
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
