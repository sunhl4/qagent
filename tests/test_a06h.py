"""A-06h: live interop qiskit_export_circuit. Skip-as-green is incomplete."""

from __future__ import annotations

import json
import os
import shutil
import sys
import traceback
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Mapping

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from qagent.adapters import qiskit as qiskit_adapter
from qagent.adapters.homes import ionstack_python
from qagent.adapters.pin import get_pin
from qagent.adapters.qiskit import _DEFAULT_QASM
from qagent.adapters.wrap import call_interop
from qagent.models.handles import HANDLE_CIRCUIT, HANDLE_TWIN, PROVENANCE_QCCD_TWIN
from qagent.services.invoke import invoke

_LIVE_HOME = "/Users/shl/Q-software"
_NOTE = ROOT / "docs" / "execution" / "A-06h_live_export.md"
_STORE = ROOT / ".qagent" / "test-a06h-store"
_COPIED_CIRCUIT = "circ_48613db9e404"
_COPIED_QASM_LINES = (
    "     ┌───┐     ",
    "q_0: ┤ H ├──■──",
    "     └───┘┌─┴─┐",
)
_COPIED_BODY = {"n_qubits": 2}
_SIGNED_LOOKING = frozenset({"ok", HANDLE_TWIN, "signoff", "signed", "signature"})
_ENV_KEYS = (
    "QAGENT_IONSTACK_HOME",
    "QAGENT_IONSTACK_PYTHON",
    "QAGENT_DATA_DIR",
    "QAGENT_ELN_FILE",
)


@contextmanager
def live_export_env() -> Iterator[None]:
    previous = {key: os.environ.get(key) for key in _ENV_KEYS}
    for key in _ENV_KEYS:
        os.environ.pop(key, None)
    _STORE.mkdir(parents=True, exist_ok=True)
    os.environ["QAGENT_IONSTACK_HOME"] = _LIVE_HOME
    os.environ["QAGENT_DATA_DIR"] = str(_STORE)
    os.environ["QAGENT_ELN_FILE"] = str(_STORE / "eln.jsonl")
    try:
        yield
    finally:
        for key in _ENV_KEYS:
            os.environ.pop(key, None)
        for key, value in previous.items():
            if value is not None:
                os.environ[key] = value


def _keys(obj: object) -> set[str]:
    found: set[str] = set()
    if isinstance(obj, dict):
        for key, value in obj.items():
            found.add(str(key))
            found.update(_keys(value))
        return found
    if isinstance(obj, list):
        for item in obj:
            found.update(_keys(item))
    return found


def _no_twin(payload: Mapping[str, Any]) -> None:
    keys = _keys(payload)
    blob = json.dumps(payload, ensure_ascii=False)
    leaked = _SIGNED_LOOKING & keys
    assert not leaked, leaked
    assert HANDLE_TWIN not in payload
    assert HANDLE_TWIN not in blob
    assert PROVENANCE_QCCD_TWIN not in blob
    assert payload.get("provenance") != PROVENANCE_QCCD_TWIN


def test_live_invoke_export_matches_interop() -> None:
    home = Path(_LIVE_HOME)
    exe = home / ".venv" / "bin" / "python"
    assert home.is_dir(), f"live QAGENT_IONSTACK_HOME missing: {home}"
    assert exe.is_file(), f"live ionstack python missing: {exe}"
    captured: dict[str, Any] = {}
    original = qiskit_adapter.call_interop

    def _spy(action: str, args: dict[str, Any], **kwargs: Any) -> dict[str, Any] | None:
        live = original(action, args, **kwargs)
        if action == "export":
            captured["live"] = live
            captured["args"] = dict(args)
        return live

    with live_export_env():
        assert os.environ.get("QAGENT_IONSTACK_HOME") == _LIVE_HOME
        assert os.environ.get("QAGENT_DATA_DIR") == str(_STORE)
        assert not os.environ.get("QAGENT_IONSTACK_PYTHON")
        assert ionstack_python() == str(exe)
        imported = invoke("qiskit_import_circuit", "lab", {})
        assert imported.status == "ok", f"import expected ok, got {imported.status}: {imported.error}"
        imported_payload = dict(imported.payload or {})
        circuit_id = str(imported_payload.get(HANDLE_CIRCUIT) or "")
        assert circuit_id, f"import missing circuit_id: {imported_payload}"
        assert circuit_id == _COPIED_CIRCUIT, circuit_id
        _no_twin(imported_payload)
        stored = get_pin(circuit_id) or {}
        body = stored.get("logical") or {}
        assert body == _COPIED_BODY, body
        qiskit_adapter.call_interop = _spy
        try:
            invoked = invoke("qiskit_export_circuit", "lab", {"circuit_id": circuit_id})
            wrapped = call_interop("export", {"body": body})
        finally:
            qiskit_adapter.call_interop = original

    assert wrapped is not None, "call_interop(export) failed — A-06h is not done"
    live = captured.get("live")
    assert live is not None, "invoke missed live call_interop(export) — default fallback as green = not done"
    assert isinstance(live, dict) and not live.get("error"), f"live interop error: {live}"
    assert live.get("backend") == "ionstack.interop", f"not ionstack.interop: {live}"
    live_qasm = live.get("qasm3")
    assert isinstance(live_qasm, str) and live_qasm, f"live interop missing qasm3: {live}"
    wrap_qasm = wrapped.get("qasm3")
    assert isinstance(wrap_qasm, str) and wrap_qasm, f"standalone interop missing qasm3: {wrapped}"
    assert wrapped.get("backend") == "ionstack.interop", f"standalone not ionstack.interop: {wrapped}"
    assert HANDLE_TWIN not in wrapped
    assert invoked.status == "ok", f"expected ok, got {invoked.status}: {invoked.error}"
    payload = dict(invoked.payload or {})
    assert payload, "qiskit_export_circuit invoke returned empty payload"
    invoke_qasm = payload.get("qasm3")
    assert isinstance(invoke_qasm, str) and invoke_qasm, f"invoke missing qasm3: {payload}"
    assert payload.get(HANDLE_CIRCUIT) == circuit_id, payload
    _no_twin(payload)
    assert invoke_qasm == live_qasm, (
        f"invoke qasm3 != interop qasm3; "
        "default fallback as green = not done"
    )
    assert invoke_qasm == wrap_qasm, (
        f"invoke qasm3 != standalone interop qasm3; "
        "default fallback as green = not done"
    )
    if invoke_qasm == _DEFAULT_QASM:
        assert live.get("backend") == "ionstack.interop"
        assert wrapped.get("backend") == "ionstack.interop"
    else:
        assert invoke_qasm != _DEFAULT_QASM
    for line in _COPIED_QASM_LINES:
        assert line in invoke_qasm, line
    print(
        f"circuit_id={circuit_id} qasm3={invoke_qasm!r} default={_DEFAULT_QASM!r} "
        f"interop={live} standalone={wrapped}"
    )


def test_note_copies_hit() -> None:
    assert _NOTE.is_file(), f"missing {_NOTE}"
    text = _NOTE.read_text(encoding="utf-8")
    compact = "".join(text.split())
    assert _COPIED_CIRCUIT in text
    assert _LIVE_HOME in text
    assert "QAGENT_IONSTACK_HOME" in text
    assert "qiskit_import_circuit" in text
    assert "qiskit_export_circuit" in text
    assert "call_interop" in text
    assert '"export"' in text or "action=export" in compact
    assert "qasm3" in text
    for line in _COPIED_QASM_LINES:
        assert line in text, line
    assert "OPENQASM 3.0" in text
    assert "_DEFAULT_QASM" in text or "默认" in text
    assert "ionstack.interop" in text
    assert "不算 G0" in text or "不算G0" in compact
    assert "G0 已通过" not in text
    assert "G0已通过" not in compact
    assert "skip 当绿" in text or "skip当绿" in compact
    assert "未 commit" in text or "未commit" in compact
    assert "apply_env" in text
    assert "workplace.json" in text
    assert "twin_id" in text
    assert any(token in text for token in ("无 twin_id", "没有 twin_id", "无 `twin_id`"))
    assert "qccd-twin" in text
    assert "ok" in text


def test_this_file_does_not_skip() -> None:
    text = Path(__file__).read_text(encoding="utf-8")
    assert ("pytest" + ".skip") not in text
    assert ("unittest" + ".skip") not in text
    assert ("skip" + "Test") not in text
    assert ("from qagent.services." + "workplace") not in text
    assert ("apply" + "_env(") not in text


def main() -> int:
    if _STORE.exists():
        shutil.rmtree(_STORE)
    failed = 0
    for name, fn in (
        ("live_invoke_export_matches_interop", test_live_invoke_export_matches_interop),
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
    if _STORE.exists():
        shutil.rmtree(_STORE)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
