"""C-01w: product face — markdown, circuit in/out, no raw handle chrome."""

from __future__ import annotations

import sys
import tempfile
import traceback
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT
sys.path.insert(0, str(ROOT / "src"))

from qagent.adapters.dsh_session import DshSessionClient
from qagent.adapters.pin import NativePin, circuit_face, circuit_program, pin_from_qasm
from qagent.entrypoints.shell_http import dispatch
from qagent.models.circuit_text import emit_qasm3, parse_qasm, program_filename
from qagent.models.handles import HANDLE_CIRCUIT, HANDLE_TWIN
from qagent.services.chat import turn

SHELL = ROOT / "apps" / "customer-shell"
NOTE = REPO / "docs" / "execution" / "C-01w_product_face.md"
_CLAIM_PASS = ("G0 已通过", "G1 已通过", "G2 已通过", "G0 passed", "G1 passed", "G2 passed")
_QASM = """OPENQASM 3.0;
include "stdgates.inc";
qubit[2] q;
h q[0];
cx q[0], q[1];
"""


def _js() -> str:
    return (SHELL / "app.js").read_text(encoding="utf-8")


def _html() -> str:
    return (SHELL / "index.html").read_text(encoding="utf-8")


def _paint_inbox() -> str:
    return _js().split("function paintInbox")[1].split("function receiptKey")[0]


def _paint_face() -> str:
    return _js().split("function paintFaceRow")[1].split("function paintReceipts")[0]


def _paint_eln() -> str:
    return _js().split("function paintEln")[1].split("async function refreshInbox")[0]


def _add_message() -> str:
    return _js().split('if (extras && extras.awaiting === "approve")')[1].split("function paintWelcome")[0]


def test_qasm_roundtrip_has_no_science_import() -> None:
    logical = parse_qasm(_QASM)
    assert logical["n_qubits"] == 2
    assert len(logical["body"]["instructions"]) == 2
    text = emit_qasm3(2, [{"name": "h", "qubits": [0]}, {"name": "cx", "qubits": [0, 1]}])
    assert "OPENQASM 3.0" in text
    assert "qubit[2] q;" in text
    assert "h q[0];" in text
    assert program_filename("uccsd", "H2") == "氢分子-UCCSD.qasm"
    print("qasm emit/parse stays in qagent models")


def test_program_http_is_not_the_face() -> None:
    folder = Path(tempfile.mkdtemp())
    store = folder / "pins.json"
    with patch("qagent.adapters.pin._STORE", store):
        pinned = NativePin().pin_circuit(
            {
                "source": "logical",
                "logical": {
                    "n_qubits": 2,
                    "body": {
                        "n_qubits": 2,
                        "ansatz": "uccsd",
                        "molecule": "H2",
                        "instructions": [
                            {"name": "h", "qubits": [0], "params": []},
                            {"name": "cx", "qubits": [0, 1], "params": []},
                        ],
                    },
                },
            }
        )
        circuit_id = pinned[HANDLE_CIRCUIT]
        face_code, face = dispatch("GET", f"/api/circuits/{circuit_id}")
        prog_code, prog = dispatch("GET", f"/api/circuits/{circuit_id}/program")
        miss_code, miss = dispatch("GET", "/api/circuits/circ_deadbeefdead/program")
        drawn = circuit_face(circuit_id)
        program = circuit_program(circuit_id)
    assert face_code == 200
    assert prog_code == 200
    assert isinstance(face, dict) and isinstance(prog, dict)
    assert "qasm3" not in face
    assert "body" not in face
    assert HANDLE_TWIN not in face
    assert prog.get("qasm3", "").startswith("OPENQASM 3.0")
    assert prog[HANDLE_CIRCUIT] == circuit_id
    assert prog.get("filename") == "氢分子-UCCSD.qasm"
    assert miss_code == 404
    assert drawn is not None
    assert "qasm3" not in drawn
    assert program is not None
    assert "qasm3" in program
    print(f"program download is a separate door circuit_id={circuit_id}")


def test_upload_pins_without_qasm_on_face() -> None:
    folder = Path(tempfile.mkdtemp())
    with patch("qagent.adapters.pin._STORE", folder / "pins.json"):
        code, row = dispatch("POST", "/api/circuits", {"qasm3": _QASM})
        bad, err = dispatch("POST", "/api/circuits", {"qasm3": ""})
        pinned = pin_from_qasm(_QASM)
    assert code == 200
    assert isinstance(row, dict)
    assert str(row.get(HANDLE_CIRCUIT) or "").startswith("circ_")
    assert "qasm3" not in row
    assert "body" not in row
    assert HANDLE_TWIN not in row
    assert row.get("n_qubits") == 2
    assert row.get("gates")
    assert bad == 400
    assert isinstance(err, dict)
    assert err.get("error")
    assert pinned[HANDLE_CIRCUIT].startswith("circ_")
    print("upload pins a face row without qasm3")


def test_wait_timeout_does_not_reuse_old_turn() -> None:
    events = [
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
                                "text": '{"circuit_id":"circ_oldoldold1","n_qubits":4}',
                            }
                        ],
                    }
                },
            }
        },
        {
            "event": {
                "type": "assistant/message",
                "data": {"message": {"content": [{"type": "text", "text": "上一轮回复"}]}},
            }
        },
        {"event": {"type": "turn/end", "data": {}}},
    ]

    class Frozen:
        def __call__(self, method: str, payload: dict) -> dict:
            if method == "session.create":
                return {"result": {"ok": True, "value": {"sessionId": "sess_c01w"}}}
            if method == "session.prompt":
                return {"result": {"ok": True, "value": {"accepted": True}}}
            if method == "session.history":
                return {"result": {"ok": True, "value": {"events": events, "hasMore": False}}}
            raise AssertionError(method)

    client = DshSessionClient(transport=Frozen())
    session_id = client.create()
    before = client.snapshot(session_id)
    client.prompt(session_id, "下一句")
    out = client.wait_for_turn(session_id, timeout=0.05, since=before)
    assert out.get("reply") == ""
    assert out.get("circuit") is None
    assert out.get("running") is True
    print("stale wait does not keep the old circuit")


def test_face_hides_handles_and_keeps_approve() -> None:
    js = _js()
    html = _html()
    inbox = _paint_inbox()
    face = _paint_face()
    eln = _paint_eln()
    bubble = _add_message()
    assert "function fillRichText" in js
    assert "function redactHandles" in js
    assert "下载这份线路" in js
    assert "附上线路" in html
    assert 'id="btn-attach"' in html
    assert "/program" in js
    assert "这份线路" in inbox
    assert "已备好的数据" in inbox
    assert "这份线路" in face
    assert "已在我们的机器上签收" in face
    assert "这份线路" in eln
    assert "线路 · ${" not in js
    assert "资产 · ${" not in js
    assert "circ_${" not in js
    assert "ionstack_twin_run" not in js
    assert 'send("批准")' in bubble
    assert 'send("先不批")' in bubble
    assert "assignmentAction" not in bubble
    assert "/approve" not in js
    assert "twin_id=" not in js
    print("face chrome is human; approve mux stays")


def test_chat_keeps_qasm_out_of_turn_body() -> None:
    text = Path(ROOT / "src" / "qagent" / "services" / "chat.py").read_text(encoding="utf-8")
    http = Path(ROOT / "src" / "qagent" / "entrypoints" / "shell_http.py").read_text(encoding="utf-8")
    assert "qasm3" not in text
    assert "不要把句柄念给客户听" in text
    assert 'body.get("circuit_id")' in http
    assert "circuit_program" in http
    assert "pin_from_qasm" in http
    assert turn is not None
    print("chat turn does not carry qasm3")


def test_note_copies_hit() -> None:
    assert NOTE.is_file(), NOTE
    text = NOTE.read_text(encoding="utf-8")
    assert "C-01w" in text
    assert "下载" in text
    assert "OpenQASM" in text
    assert "不算 G0" in text
    assert "未 commit" in text
    assert "不许出现" in text
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
        ("qasm_roundtrip_has_no_science_import", test_qasm_roundtrip_has_no_science_import),
        ("program_http_is_not_the_face", test_program_http_is_not_the_face),
        ("upload_pins_without_qasm_on_face", test_upload_pins_without_qasm_on_face),
        ("wait_timeout_does_not_reuse_old_turn", test_wait_timeout_does_not_reuse_old_turn),
        ("face_hides_handles_and_keeps_approve", test_face_hides_handles_and_keeps_approve),
        ("chat_keeps_qasm_out_of_turn_body", test_chat_keeps_qasm_out_of_turn_body),
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
