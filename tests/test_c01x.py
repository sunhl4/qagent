"""C-01x: current-task rail, customer voice, keep the drawn circuit."""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT
sys.path.insert(0, str(ROOT / "src"))

from qagent.adapters.dsh_session import fold_history
from qagent.entrypoints.shell_http import _chat_http_face, _circuit_http_meta
from qagent.models.assignment import Assignment
from qagent.models.circuit_pick import prefer_circuit
from qagent.models.customer_voice import CUSTOMER_VOICE_HINT, redact_customer_text
from qagent.models.handles import HANDLE_CIRCUIT
from qagent.services.chat import turn

SHELL = ROOT / "apps" / "customer-shell"
NOTE = REPO / "docs" / "execution" / "C-01x_current_task.md"
SKILL = ROOT / "skills" / "vibe-across-engines" / "SKILL.md"
_CLAIM_PASS = ("G0 已通过", "G1 已通过", "G2 已通过", "G0 passed", "G1 passed", "G2 passed")


def _js() -> str:
    return (SHELL / "app.js").read_text(encoding="utf-8")


def _html() -> str:
    return (SHELL / "index.html").read_text(encoding="utf-8")


def _css() -> str:
    return (SHELL / "app.css").read_text(encoding="utf-8")


def _paint_inbox() -> str:
    return _js().split("function paintInbox")[1].split("function receiptKey")[0]


def _paint_receipts() -> str:
    return _js().split("function paintReceipts")[1].split("const ELN_KIND_MAP")[0]


def _paint_eln() -> str:
    return _js().split("function paintEln")[1].split("async function refreshInbox")[0]


def _add_message() -> str:
    return _js().split('if (extras && extras.awaiting === "approve")')[1].split("function paintWelcome")[0]


def _poll() -> str:
    return _js().split("async function pollStatus")[1].split("async function saveSettings")[0]


def test_voice_redacts_handles_and_internal_names() -> None:
    text = redact_customer_text(
        "circ_abcdef12ffffff via qchem_run and uccsd_pauli; asset_abc123; twin_abcdef12ffffff"
    )
    assert "circ_" not in text
    assert "asset_" not in text
    assert "twin_" not in text
    assert "qchem_run" not in text
    assert "uccsd_pauli" not in text
    assert "这份线路" in text
    assert "这份数据" in text
    assert "签收回执" in text
    hidden = "a2" + "_chem_pes"
    assert redact_customer_text(hidden) == "这份计算"
    assert redact_customer_text("irrep a1_g stays") == "irrep a1_g stays"
    face = _chat_http_face(
        {
            "reply": "circ_abcdef12ffffff qchem_run",
            "session_id": "session-deadbeef",
            "used_tools": ["qchem_run"],
        }
    )
    assert "circ_" not in face["reply"]
    assert "qchem_run" not in face["reply"]
    assert "session_id" not in face
    assert "used_tools" not in face
    chat = Path(ROOT / "src" / "qagent" / "services" / "chat.py").read_text(encoding="utf-8")
    assert "CUSTOMER_VOICE_HINT" in chat
    assert "不要把句柄念给客户听" in chat
    assert "短结论" in CUSTOMER_VOICE_HINT
    assert turn is not None
    print("customer voice redacts handles before the HTTP face")


def test_rail_shows_current_task_only() -> None:
    html = _html()
    css = _css()
    inbox = _paint_inbox()
    receipts = _paint_receipts()
    eln = _paint_eln()
    assert "本任务" in html
    assert "在办" in html
    assert "asks.slice(-8)" in inbox
    assert "newestAssignment(asks)" in inbox
    assert "signed.concat(other)" in receipts
    assert "slice(0, 8)" in receipts
    assert "newestAssignment(shown)" in receipts
    assert "updated_at" in _js().split("function newestAssignment")[1].split("function paintInbox")[0]
    row = Assignment(
        assignment_id="asg_c01xface01",
        room="lab",
        brief="x",
        recipe="none",
        shots=1,
        status="draft",
    )
    face = row.face_payload()
    assert face.get("created_at")
    assert face.get("updated_at")
    assert "columns" not in face
    assert "brief" not in face
    assert "shown.slice(-8)" in eln
    assert "recent.slice(-1)" in eln
    assert ".welcome .packs" in css
    assert "display: none" in css.split(".welcome .packs")[1].split("}")[0]
    print("rail keeps eight-window strings and paints the current task")


def test_drawn_circuit_is_not_replaced() -> None:
    js = _js()
    poll = _poll()
    bubble = _add_message()
    assert "function circuitScore" in js
    assert "return false" in js.split("function rememberCircuit")[1].split("function circuitTitle")[0]
    assert "score && score >= state.currentCircuitScore" in js
    assert "rememberCircuit(data, true)" in js
    assert "rememberCircuit(extras.circuit)" in js
    assert 'querySelector(".circuit-face")' in poll
    assert "&& rememberCircuit(data.circuit)" in poll
    assert "replaceWith(circuitMount" in poll
    assert "dataset.circuitId" in _js().split("function circuitMount")[1].split("async function loadCircuitFace")[0]
    assert poll.index("rememberCircuit") < poll.index("replaceWith")
    sized = _circuit_http_meta(
        {
            HANDLE_CIRCUIT: "circ_deadbeefdead",
            "n_qubits": 4,
            "n_instructions": 194,
            "gates": [{"name": "h", "qubits": [0]}],
            "qasm3": "OPENQASM 3.0;",
            "body": {},
        }
    )
    assert sized["n_qubits"] == 4
    assert sized["n_instructions"] == 194
    assert "qasm3" not in sized
    assert "body" not in sized
    assert "gates" not in sized
    assert 'send("批准")' in bubble
    assert 'send("先不批")' in bubble
    assert "assignmentAction" not in bubble
    assert "ionstack_twin_run" not in js
    assert "twin_id=" not in js
    print("poll keeps the mounted circuit; approve mux stays")


def test_fold_keeps_richer_circuit() -> None:
    rich = prefer_circuit(
        {"circuit_id": "circ_aaaaaaaaaaaa", "n_qubits": 4, "n_instructions": 194},
        {"circuit_id": "circ_bbbbbbbbbbbb"},
    )
    assert rich is not None
    assert rich["circuit_id"] == "circ_aaaaaaaaaaaa"
    snap = fold_history(
        {
            "events": [
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
                                            '{"circuit_id":"circ_aaaaaaaaaaaa",'
                                            '"n_qubits":4,"n_instructions":194,'
                                            '"summary":{"ansatz":"uccsd"}}'
                                        ),
                                    }
                                ],
                            }
                        },
                    }
                },
                {
                    "event": {
                        "type": "tool/result",
                        "data": {
                            "message": {
                                "name": "qiskit_export_circuit",
                                "content": [
                                    {
                                        "type": "text",
                                        "text": '{"circuit_id":"circ_bbbbbbbbbbbb","n_qubits":2}',
                                    }
                                ],
                            }
                        },
                    }
                },
            ]
        },
        session_id="session-c01x",
    )
    circuit = snap.get("circuit")
    assert isinstance(circuit, dict)
    assert circuit[HANDLE_CIRCUIT] == "circ_aaaaaaaaaaaa"
    assert circuit.get("n_qubits") == 4
    assert circuit.get("n_instructions") == 194
    print("later thin export does not win the fold")


def test_skill_still_forbids_export_for_diagram() -> None:
    skill = SKILL.read_text(encoding="utf-8")
    assert "短结论" in skill
    assert "不要报工具名" in skill
    assert "qiskit_export_circuit" in skill
    assert "人没点名" in skill
    plugin = (ROOT / "packages" / "qagent-qiskit" / "src" / "index.ts").read_text(encoding="utf-8")
    assert "qiskit_export_circuit" in plugin
    assert "Do not call this to draw a diagram" in plugin
    print("skill and qiskit plugin tell the model not to export for a picture")


def test_note_copies_hit() -> None:
    assert NOTE.is_file(), NOTE
    text = NOTE.read_text(encoding="utf-8")
    assert "C-01x" in text
    assert "本任务" in text
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
        ("voice_redacts_handles_and_internal_names", test_voice_redacts_handles_and_internal_names),
        ("rail_shows_current_task_only", test_rail_shows_current_task_only),
        ("drawn_circuit_is_not_replaced", test_drawn_circuit_is_not_replaced),
        ("fold_keeps_richer_circuit", test_fold_keeps_richer_circuit),
        ("skill_still_forbids_export_for_diagram", test_skill_still_forbids_export_for_diagram),
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
