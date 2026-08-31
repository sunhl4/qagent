"""A-06i: live interop qiskit_import_circuit. Skip-as-green is incomplete."""

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
from qagent.adapters.qiskit import _DEFAULT_QASM
from qagent.adapters.wrap import call_interop
from qagent.models.handles import HANDLE_CIRCUIT, HANDLE_TWIN, PROVENANCE_QCCD_TWIN
from qagent.services.invoke import invoke

_LIVE_HOME = "/Users/shl/Q-software"
_NOTE = ROOT / "docs" / "execution" / "A-06i_live_import.md"
_STORE = ROOT / ".qagent" / "test-a06i-store"
_COPIED_CIRCUIT = "circ_48613db9e404"
_COPIED_N_QUBITS = 2
_FALLBACK_N_QUBITS = 2
_SIGNED_LOOKING = frozenset({"ok", HANDLE_TWIN, "signoff", "signed", "signature"})
_ENV_KEYS = (
    "QAGENT_IONSTACK_HOME",
    "QAGENT_IONSTACK_PYTHON",
    "QAGENT_DATA_DIR",
    "QAGENT_ELN_FILE",
)


@contextmanager
def live_import_env() -> Iterator[None]:
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


def test_live_invoke_import_matches_interop() -> None:
    home = Path(_LIVE_HOME)
    exe = home / ".venv" / "bin" / "python"
    assert home.is_dir(), f"live QAGENT_IONSTACK_HOME missing: {home}"
    assert exe.is_file(), f"live ionstack python missing: {exe}"
    captured: dict[str, Any] = {}
    original = qiskit_adapter.call_interop

    def _spy(action: str, args: dict[str, Any], **kwargs: Any) -> dict[str, Any] | None:
        live = original(action, args, **kwargs)
        if action == "import":
            captured["live"] = live
            captured["args"] = dict(args)
        return live

    with live_import_env():
        assert os.environ.get("QAGENT_IONSTACK_HOME") == _LIVE_HOME
        assert os.environ.get("QAGENT_DATA_DIR") == str(_STORE)
        assert not os.environ.get("QAGENT_IONSTACK_PYTHON")
        assert ionstack_python() == str(exe)
        qiskit_adapter.call_interop = _spy
        try:
            invoked = invoke("qiskit_import_circuit", "lab", {})
            wrapped = call_interop("import", {"qasm3": _DEFAULT_QASM})
        finally:
            qiskit_adapter.call_interop = original

    assert wrapped is not None, "call_interop(import) failed — A-06i is not done"
    live = captured.get("live")
    assert live is not None, "invoke missed live call_interop(import) — fallback n_qubits as green = not done"
    assert isinstance(live, dict) and not live.get("error"), f"live interop error: {live}"
    assert live.get("backend") == "ionstack.interop", f"not ionstack.interop: {live}"
    live_n = live.get("n_qubits")
    assert live_n is not None, f"live interop missing n_qubits: {live}"
    wrap_n = wrapped.get("n_qubits")
    assert wrap_n is not None, f"standalone interop missing n_qubits: {wrapped}"
    assert wrapped.get("backend") == "ionstack.interop", f"standalone not ionstack.interop: {wrapped}"
    assert HANDLE_TWIN not in wrapped
    assert HANDLE_TWIN not in live
    assert invoked.status == "ok", f"expected ok, got {invoked.status}: {invoked.error}"
    payload = dict(invoked.payload or {})
    assert payload, "qiskit_import_circuit invoke returned empty payload"
    circuit_id = str(payload.get(HANDLE_CIRCUIT) or "")
    assert circuit_id, f"import missing circuit_id: {payload}"
    assert circuit_id == _COPIED_CIRCUIT, circuit_id
    invoke_n = payload.get("n_qubits")
    assert invoke_n is not None, f"invoke missing n_qubits: {payload}"
    _no_twin(payload)
    assert int(invoke_n) == int(live_n), (
        f"invoke n_qubits={invoke_n} != interop {live_n}; "
        "fallback n_qubits as green = not done"
    )
    assert int(invoke_n) == int(wrap_n), (
        f"invoke n_qubits={invoke_n} != standalone interop {wrap_n}; "
        "fallback n_qubits as green = not done"
    )
    assert int(invoke_n) == _COPIED_N_QUBITS, invoke_n
    captured_qasm = (captured.get("args") or {}).get("qasm3")
    assert captured_qasm == _DEFAULT_QASM, "invoke and interop must use the same qasm"
    print(
        f"circuit_id={circuit_id} n_qubits={invoke_n} fallback={_FALLBACK_N_QUBITS} "
        f"interop={live} standalone={wrapped}"
    )


def test_note_copies_hit() -> None:
    assert _NOTE.is_file(), f"missing {_NOTE}"
    text = _NOTE.read_text(encoding="utf-8")
    compact = "".join(text.split())
    assert _COPIED_CIRCUIT in text
    assert str(_COPIED_N_QUBITS) in text
    assert "n_qubits" in text
    assert _LIVE_HOME in text
    assert "QAGENT_IONSTACK_HOME" in text
    assert "qiskit_import_circuit" in text
    assert "call_interop" in text
    assert '"import"' in text or "action=import" in compact
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
    assert "circuit_id" in text


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
        ("live_invoke_import_matches_interop", test_live_invoke_import_matches_interop),
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
