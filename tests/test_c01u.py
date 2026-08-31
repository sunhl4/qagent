"""C-01u: settings save is honest on 403 and missing URL. Chat mux still send(批准)."""

from __future__ import annotations

import json
import traceback
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT
SHELL = ROOT / "apps" / "customer-shell"
NOTE = REPO / "docs" / "execution" / "C-01u_save_settings.md"
_CLAIM_PASS = ("G0 已通过", "G1 已通过", "G2 已通过", "G0 passed", "G1 passed", "G2 passed")
_FACE = "http://127.0.0.1:3080"
_FORBIDDEN = {"error": "approval requires QAGENT_SHELL_TOKEN"}


def _js() -> str:
    return (SHELL / "app.js").read_text(encoding="utf-8")


def _html() -> str:
    return (SHELL / "index.html").read_text(encoding="utf-8")


def _save() -> str:
    return _js().split("async function saveSettings")[1].split("async function boot")[0]


def _add_message() -> str:
    return _js().split('if (extras && extras.awaiting === "approve")')[1].split("function paintWelcome")[0]


def _call(method: str, path: str, body: dict[str, Any] | None = None, *, token: bool) -> tuple[int, dict[str, Any]]:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-QAGENT-DEBUG-TOKEN"] = "workbench-review"
        headers["X-QAGENT-APPROVE-TOKEN"] = "workbench-review"
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(_FACE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            raw = response.read().decode("utf-8")
            code = int(response.status)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        code = exc.code
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise AssertionError(f"3080 not reachable ({path}): {exc}") from exc
    parsed = json.loads(raw) if raw else {}
    if not isinstance(parsed, dict):
        raise AssertionError(f"3080 JSON must be an object: {raw!r}")
    return code, parsed


def test_save_is_honest_on_forbidden_and_url() -> None:
    js = _js()
    html = _html()
    save = _save()
    assert "!res.ok" in save
    assert "保存要组内 token" in save
    assert "?token=" in save
    assert "https://api.deepseek.com/v1" in save
    assert "还要填接口地址" in save
    assert "设置已保存。还缺模型地址或模型名。" in save
    assert "设置已保存。现在可以直接说话。" in save
    assert "https://api.deepseek.com/v1" in html
    assert "密钥 → API Key" in html
    assert "?token=" in html
    assert "llm_api_key" in html
    assert 'id="secret-fieldset"' in html
    assert "/approve" not in js
    assert "twin_id=" not in js


def test_put_workplace_without_token_is_403() -> None:
    code, payload = _call(
        "PUT",
        "/api/workplace",
        {"llm_model": "deepseek-chat", "llm_base_url": "https://api.deepseek.com/v1"},
        token=False,
    )
    assert code == 403, payload
    assert payload == _FORBIDDEN
    print("PUT /api/workplace without token is 403")


def test_chat_bubble_still_sends_approve() -> None:
    bubble = _add_message()
    assert 'send("批准")' in bubble
    assert 'send("先不批")' in bubble
    assert "assignmentAction" not in bubble


def test_note_copies_hit() -> None:
    assert NOTE.is_file(), NOTE
    text = NOTE.read_text(encoding="utf-8")
    assert "保存要组内 token" in text
    assert "?token=" in text
    assert "https://api.deepseek.com/v1" in text
    assert "API Key" in text
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
        ("save_is_honest_on_forbidden_and_url", test_save_is_honest_on_forbidden_and_url),
        ("put_workplace_without_token_is_403", test_put_workplace_without_token_is_403),
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
