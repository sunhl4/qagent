"""C-01ae: session journal + read-only 对话 list. No switch, no replay. Not a G0 claim."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import traceback
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
REPO = ROOT
sys.path.insert(0, str(SRC))
os.environ.setdefault("QAGENT_DSH_MUX", "0")

from qagent.adapters.dsh_session_store import (  # noqa: E402
    archive_session_id,
    journal_session,
    list_journal,
    load_session_id,
    save_session_id,
    session_path,
)
from qagent.entrypoints.shell_http import dispatch  # noqa: E402
from qagent.services.chat import list_sessions, reset_chat, turn  # noqa: E402
from qagent.services.workplace import save_workplace  # noqa: E402

SHELL = ROOT / "apps" / "customer-shell"
HTTP = SRC / "qagent" / "entrypoints" / "shell_http.py"
NOTE = REPO / "docs" / "execution" / "C-01ae_sessions.md"
_CLAIM_PASS = ("G0 已通过", "G1 已通过", "G2 已通过", "G0 passed", "G1 passed", "G2 passed")
_ROOMS = ("实验室", "写算法", "签收台", "三房间")
_WALLS = ("Finder", "工作区门槛", "dsh-workspace", "dsh-web", "workspace chrome")
_TENANT = {"X-QAGENT-TENANT": "acme"}
_ENV_KEYS = (
    "QAGENT_WORKPLACE_FILE",
    "QAGENT_SECRETS_FILE",
    "QAGENT_DSH_SESSION_FILE",
    "QAGENT_DSH_URL",
    "QAGENT_DSH_MUX",
    "QAGENT_DSH_WAIT_S",
    "QAGENT_AGENT_THREAD",
)


@contextmanager
def isolated() -> Iterator[Path]:
    previous = {key: os.environ.get(key) for key in _ENV_KEYS}
    tmp = tempfile.TemporaryDirectory()
    try:
        folder = Path(tmp.name)
        os.environ["QAGENT_WORKPLACE_FILE"] = str(folder / "workplace.json")
        os.environ["QAGENT_SECRETS_FILE"] = str(folder / "secrets.json")
        os.environ["QAGENT_DSH_SESSION_FILE"] = str(folder / "dsh-session.json")
        os.environ["QAGENT_DSH_URL"] = "http://127.0.0.1:9"
        os.environ["QAGENT_DSH_MUX"] = "0"
        os.environ["QAGENT_DSH_WAIT_S"] = "0"
        os.environ["QAGENT_AGENT_THREAD"] = str(folder / "thread.json")
        yield folder
    finally:
        tmp.cleanup()
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


class _FakeWorker:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def create(self, **kwargs: object) -> str:
        return "sess_ae"

    def snapshot(self, session_id: str) -> dict:
        return {"reply": "", "event_count": 0, "assistant_index": 0, "turn_index": 0}

    def prompt(self, session_id: str, text: str, **kwargs: object) -> dict:
        self.prompts.append(text)
        return {"accepted": True}

    def wait_for_turn(self, session_id: str, **kwargs: object) -> dict:
        return {"reply": "算好了。", "running": False, "awaiting": None, "cards": []}


def _js() -> str:
    return (SHELL / "app.js").read_text(encoding="utf-8")


def _html() -> str:
    return (SHELL / "index.html").read_text(encoding="utf-8")


def _css() -> str:
    return (SHELL / "app.css").read_text(encoding="utf-8")


def test_store_journal_roundtrip() -> None:
    with isolated():
        save_session_id("sess_a")
        staff = json.loads(session_path().read_text(encoding="utf-8"))
        assert staff == {"sessionId": "sess_a"}, staff
        journal_session("sess_a", title="扫氢分子")
        journal_session("sess_a", title="别的标题")
        journal_session("")
        rows = list_journal()
        assert len(rows) == 1
        row = rows[0]
        assert row.get("session_id") == "sess_a"
        assert row.get("title") == "扫氢分子"
        assert row.get("archived") is False
        assert row.get("created_at") and row.get("updated_at")
        archive_session_id("sess_a")
        assert list_journal()[0].get("archived") is True
        archive_session_id("sess_missing")
        print("journal sidecar: title set once, archive marks, staff file stays {sessionId}")


def test_journal_tenant_isolation() -> None:
    with isolated():
        journal_session("sess_acme", tenant_id="acme", title="甲方的对话")
        journal_session("sess_globex", tenant_id="globex", title="乙方的对话")
        mine = list_journal(tenant_id="acme")
        theirs = list_journal(tenant_id="globex")
        staff = list_journal()
        assert [row.get("session_id") for row in mine] == ["sess_acme"]
        assert [row.get("session_id") for row in theirs] == ["sess_globex"]
        assert staff == []
        print("journal buckets stay per tenant")


def test_turn_journals_and_list_sessions() -> None:
    with isolated():
        save_workplace({"llm_base_url": "http://127.0.0.1:9/v1", "llm_model": "local-model"})
        worker = _FakeWorker()
        out = turn(message="扫氢分子，6-31G 基组，先看能量", client=worker, tenant_id="acme")
        assert out.get("reply") == "算好了。"
        assert worker.prompts
        rows = list_sessions(tenant_id="acme").get("sessions") or []
        assert len(rows) == 1
        row = rows[0]
        assert row.get("title") == "扫氢分子，6-31G 基组，先看能量"
        assert row.get("current") is True
        assert row.get("archived") is False
        assert "session_id" not in row
        reset_chat(tenant_id="acme")
        after = list_sessions(tenant_id="acme").get("sessions") or []
        assert len(after) == 1
        assert after[0].get("current") is False
        assert after[0].get("archived") is True
        assert list_sessions(tenant_id="globex").get("sessions") == []
        print("turn journals with a title; reset archives instead of vanishing")


def test_http_sessions_read_only_face() -> None:
    with isolated():
        save_workplace({"llm_base_url": "http://127.0.0.1:9/v1", "llm_model": "local-model"})
        worker = _FakeWorker()
        turn(message="看看 circ_abc12345 这条线路", client=worker, tenant_id="acme")
        code, payload = dispatch("GET", "/api/chat/sessions", None, _TENANT)
        assert code == 200
        rows = (payload or {}).get("sessions") or []
        assert len(rows) == 1
        title = str(rows[0].get("title") or "")
        assert "circ_abc12345" not in title
        blob = json.dumps(payload, ensure_ascii=False)
        assert "sess_ae" not in blob
        assert "session_id" not in blob
        assert rows[0].get("current") is True
        code, other = dispatch("GET", "/api/chat/sessions", None, {"X-QAGENT-TENANT": "globex"})
        assert code == 200
        assert (other or {}).get("sessions") == []
        code, _ = dispatch("POST", "/api/chat/sessions", {}, _TENANT)
        assert code == 404
        print("GET /api/chat/sessions: tenant-scoped, redacted, no ids, no write path")


def test_face_paints_record_not_rooms() -> None:
    js = _js()
    html = _html()
    css = _css()
    assert 'id="session-face"' in html
    assert ">对话</h3>" in html
    assert 'id="session-list"' in html
    assert 'id="session-empty"' in html
    assert "function paintSessions" in js
    assert 'fetch("/api/chat/sessions"' in js
    inbox = js.split("async function refreshInbox")[1].split("function paintGov")[0]
    assert "/api/chat/sessions" in inbox
    painter = js.split("function paintSessions")[1].split("function circuitMount")[0]
    assert "当前" in painter
    assert "已清" in painter
    assert "addEventListener" not in painter
    assert "/api/chat/switch" not in js
    assert "/api/chat/switch" not in HTTP.read_text(encoding="utf-8")
    for selector in (".session-face", ".session-list", ".session-row", ".session-name", ".session-meta"):
        assert selector in css, selector
    print("face shows a read-only record: 当前/已清, no switch, no rooms")


def test_hard_rails_and_locks() -> None:
    js = _js()
    css = _css()
    blob = _html() + js + css
    bubble = js.split('if (extras && extras.awaiting === "approve")')[1].split("function paintWelcome")[0]
    assert 'send("批准")' in bubble
    assert 'send("先不批")' in bubble
    assert "ionstack_twin_run" not in js
    assert "twin_id=" not in js
    assert "a2_chem_pes" not in blob
    assert "grid-row: 2 / 4" in css
    assert "grid-row: 3" in css
    assert "在办" in _html()
    assert "实验记录 / ELN" in _html()
    for word in _ROOMS + _WALLS:
        assert word not in blob, word
    print("product locks stay green under the sessions wave")


def test_note_copies_hit() -> None:
    assert NOTE.is_file(), NOTE
    text = NOTE.read_text(encoding="utf-8")
    assert "C-01ae" in text
    assert "不算 G0" in text
    assert "未 commit" in text
    assert "snapshot" in text
    assert "不假装回看" in text
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
        ("store_journal_roundtrip", test_store_journal_roundtrip),
        ("journal_tenant_isolation", test_journal_tenant_isolation),
        ("turn_journals_and_list_sessions", test_turn_journals_and_list_sessions),
        ("http_sessions_read_only_face", test_http_sessions_read_only_face),
        ("face_paints_record_not_rooms", test_face_paints_record_not_rooms),
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
