"""H-01m: dedicated agent picks tools per request. UCCSD is a path, not the only reply."""

from __future__ import annotations

import json
import os
import re
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from qagent.adapters.dsh_session import DshSessionClient, fold_history
from qagent.models.handles import HANDLE_ASSET, HANDLE_CIRCUIT, HANDLE_TWIN
from qagent.services.boundaries import scan_forbidden_imports
from qagent.services.chat import reset_chat, turn
from qagent.services.workplace import save_workplace

NOTE = ROOT / "docs" / "execution" / "H-01m_agent_not_frozen.md"
JS = ROOT / "apps" / "customer-shell" / "app.js"
QCHEM_TS = ROOT / "packages" / "qagent-qchem" / "src" / "index.ts"
QCHEM_JSON = ROOT / "contracts" / "tools" / "qchem_run.json"
VIBE = ROOT / "skills" / "vibe-across-engines" / "SKILL.md"
SKILL = ROOT / "skills" / "h2-uccsd" / "SKILL.md"
VIS = ROOT / "profiles" / "qagent" / "skill-visibility.json"
ASSIGNMENT = ROOT / "src" / "qagent" / "services" / "assignment.py"
QCHEM_PY = ROOT / "src" / "qagent" / "adapters" / "qchem.py"
FOLDER = ROOT / ".qagent" / "test-h01m"
_HANDLES = frozenset({HANDLE_CIRCUIT, HANDLE_ASSET, HANDLE_TWIN})
_KNOWN = _HANDLES | {"rpc_id", "approval_id", "sessionId"}
_ID_RE = re.compile(r"\b[a-z]+_id\b")
_FROZEN = ("H2 UCCSD / circuit diagram", "要 H₂ 的 UCCSD", "要 H2 的 UCCSD")


def _text(path: Path) -> str:
    assert path.is_file(), f"missing {path}"
    return path.read_text(encoding="utf-8")


def _welcome() -> str:
    return _text(JS).split("function paintWelcome")[1].split("function fillSettings")[0]


def _history_ok(events: list[dict]) -> dict:
    return {"result": {"ok": True, "value": {"events": events, "hasMore": False}}}


def _assistant(text: str) -> dict:
    return {
        "event": {
            "type": "assistant/message",
            "data": {"message": {"content": [{"type": "text", "text": text}]}},
        }
    }


def _uccsd_events() -> list[dict]:
    return [
        {"event": {"type": "turn/start", "data": {}}},
        {
            "event": {
                "type": "tool/result",
                "data": {
                    "message": {
                        "name": "qchem_run",
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    '{"asset_id":"asset_old","circuit_id":'
                                    '"circ_bbbbbbbbbbbb","n_qubits":4,'
                                    '"summary":{"ansatz":"uccsd"}}'
                                ),
                            }
                        ],
                    }
                },
            }
        },
        _assistant("这是 H2 UCCSD 电路。"),
        {"event": {"type": "turn/end", "data": {}}},
    ]


def _next_events() -> list[dict]:
    return _uccsd_events() + [
        {"event": {"type": "turn/start", "data": {}}},
        {
            "event": {
                "type": "tool/call",
                "data": {"name": "qagent_list_engines", "callId": "c-next"},
            }
        },
        _assistant("已经看见公司软件包，没有新电路。"),
        {"event": {"type": "turn/end", "data": {}}},
    ]


class Evolving:
    def __init__(self) -> None:
        self.prompted = False
        self.histories = 0

    def __call__(self, method: str, payload: dict) -> dict:
        if method == "session.create":
            return {"result": {"ok": True, "value": {"sessionId": "sess_h01m"}}}
        if method == "session.prompt":
            self.prompted = True
            return {"result": {"ok": True, "value": {"accepted": True}}}
        if method == "session.history":
            if not self.prompted:
                return _history_ok(_uccsd_events())
            self.histories += 1
            if self.histories < 2:
                return _history_ok(_uccsd_events() + [{"event": {"type": "turn/start", "data": {}}}])
            return _history_ok(_next_events())
        raise AssertionError(method)


def test_note() -> None:
    text = _text(NOTE)
    assert "H-01m" in text
    assert "专用" in text or "agent" in text.lower()
    assert "写死" in text or "不是唯一" in text
    assert "uccsd_pauli" in text
    assert "circuit_id" in text
    assert "不算 G0" in text
    assert HANDLE_TWIN in text
    print("note names dedicated agent not frozen to UCCSD")


def test_prompts_are_not_frozen_to_uccsd() -> None:
    welcome = _welcome()
    plugin = _text(QCHEM_TS)
    contract = _text(QCHEM_JSON)
    vibe = _text(VIBE)
    vis_rows = json.loads(_text(VIS))["skills"]
    lab_ids = {row["id"] for row in vis_rows if "lab" in row["visible"]}
    for blob in (welcome, plugin, contract):
        for phrase in _FROZEN:
            assert phrase not in blob, phrase
    assert "UCCSD" not in welcome
    assert "uccsd_pauli" not in welcome
    assert "H2 UCCSD / circuit diagram" not in plugin
    assert "Do not default to uccsd_pauli" in plugin
    assert "人没点名" in vibe
    assert "把每一次对话都做成" in vibe
    assert "h2-uccsd" not in lab_ids
    assert "vibe-across-engines" in lab_ids
    assert "默认建议，不是唯一入口" in _text(SKILL)
    print("welcome / qchem_run / skills do not force UCCSD")


def test_fold_history_keeps_this_turn_only() -> None:
    first = fold_history({"events": _uccsd_events()}, session_id="sess_h01m")
    assert first["reply"] == "这是 H2 UCCSD 电路。"
    assert (first.get("circuit") or {}).get(HANDLE_CIRCUIT) == "circ_bbbbbbbbbbbb"
    nxt = fold_history({"events": _next_events()}, session_id="sess_h01m")
    assert nxt["reply"] == "已经看见公司软件包，没有新电路。"
    assert "UCCSD" not in nxt["reply"]
    assert "circuit" not in nxt
    assert nxt["used_tools"] == ["qagent_list_engines"]
    assert nxt["turn_index"] == 2
    print("next turn does not keep the old UCCSD circuit")


def test_chat_waits_for_new_turn() -> None:
    previous = {
        key: os.environ.get(key)
        for key in (
            "QAGENT_WORKPLACE_FILE",
            "QAGENT_SECRETS_FILE",
            "QAGENT_DSH_ENV_FILE",
            "QAGENT_DSH_SESSION_FILE",
            "QAGENT_DSH_WAIT_S",
        )
    }
    FOLDER.mkdir(parents=True, exist_ok=True)
    os.environ["QAGENT_WORKPLACE_FILE"] = str(FOLDER / "workplace.json")
    os.environ["QAGENT_SECRETS_FILE"] = str(FOLDER / "secrets.json")
    os.environ["QAGENT_DSH_ENV_FILE"] = str(FOLDER / "dsh.env")
    os.environ["QAGENT_DSH_SESSION_FILE"] = str(FOLDER / "dsh-session.json")
    os.environ["QAGENT_DSH_WAIT_S"] = "2"
    reset_chat()
    save_workplace({"llm_base_url": "http://127.0.0.1:9/v1", "llm_model": "unitqc-local"})
    try:
        out = turn(message="我们接了哪些软件？", client=DshSessionClient(transport=Evolving()))
    finally:
        reset_chat()
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    assert "软件包" in out["reply"]
    assert "UCCSD" not in out["reply"]
    assert out.get("circuit") is None
    assert "qagent_list_engines" in out.get("used_tools", [])
    print("chat returns the new turn, not the old UCCSD bubble")


def test_face_still_can_draw_and_ask() -> None:
    js = _text(JS)
    assert "批准上机" in js
    assert 'send("批准")' in js
    assert "ionstack_twin_run" not in js
    assert "circuitMount" in js
    assert "drawCircuitSvg" in js
    assert "i < 180" in js.split("async function pollStatus")[1].split("async function saveSettings")[0]
    print("face can still draw a circuit when this turn pins one")


def test_no_fourth_handle_or_src_qchem_import() -> None:
    for path in (NOTE, QCHEM_TS, SKILL, VIBE):
        for match in _ID_RE.findall(_text(path)):
            assert match in _KNOWN, (path.name, match)
    assert _text(ASSIGNMENT).count('"mode": "pipeline"') == 3
    text = _text(QCHEM_PY)
    assert "import qchem" not in text
    assert "from qchem " not in text
    assert "from qchem." not in text
    hits = [row for row in scan_forbidden_imports() if "adapters/qchem.py" in row]
    assert hits == []
    print("still three handles; qagent/src does not import qchem")


def main() -> int:
    failed = 0
    for name, fn in (
        ("note", test_note),
        ("prompts_are_not_frozen_to_uccsd", test_prompts_are_not_frozen_to_uccsd),
        ("fold_history_keeps_this_turn_only", test_fold_history_keeps_this_turn_only),
        ("chat_waits_for_new_turn", test_chat_waits_for_new_turn),
        ("face_still_can_draw_and_ask", test_face_still_can_draw_and_ask),
        ("no_fourth_handle_or_src_qchem_import", test_no_fourth_handle_or_src_qchem_import),
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
