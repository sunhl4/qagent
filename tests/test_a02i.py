"""A-02i: live qchem_run then dequant_gate. Skip-as-green is incomplete."""

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

from qagent.models.handles import B3_VERDICTS, HANDLE_ASSET, HANDLE_CIRCUIT, HANDLE_TWIN
from qagent.services.invoke import invoke

QCHEM_HOME = "/Users/shl/nvidia/qcchem-qml-md"
_NOTE = ROOT / "docs" / "execution" / "A-02i_dequant.md"
_STORE = ROOT / ".qagent" / "test-a02i-store"
_COPIED_ASSET = "asset_8b00a737b406"
_COPIED_VERDICT = "inconclusive"
_COPIED_DEQUANT = {
    "b3": {"verdict": "inconclusive", "qem_contract_ok": False},
    "qem_contract_ok": False,
}
_ENV_KEYS = (
    "QAGENT_QCHEM_BIN",
    "QAGENT_QCHEM_HOME",
    "QAGENT_QCHEM_PARITY_BIN",
    "QAGENT_QDATA_URL",
    "QAGENT_QDATA_HOME",
    "QAGENT_QDATA_BIN",
    "QAGENT_QDATA_PYTHON",
    "QAGENT_DATA_DIR",
    "QAGENT_ELN_FILE",
    "QAGENT_KNOWLEDGE_PATH",
)
_FORBIDDEN = (
    "bitstrings",
    "pauli_terms",
    "counts_full",
    "result_full",
    "qasm",
    "qasm3",
    "circuit_body",
    HANDLE_TWIN,
    HANDLE_CIRCUIT,
    "Pauli",
    "OPENQASM",
)


@contextmanager
def live_qchem_store() -> Iterator[None]:
    previous = {key: os.environ.get(key) for key in _ENV_KEYS}
    for key in _ENV_KEYS:
        os.environ.pop(key, None)
    _STORE.mkdir(parents=True, exist_ok=True)
    os.environ["QAGENT_QCHEM_HOME"] = QCHEM_HOME
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
    elif isinstance(obj, list):
        for item in obj:
            found.update(_keys(item))
    return found


def _no_forbidden(payload: Mapping[str, Any]) -> None:
    keys = _keys(payload)
    blob = json.dumps(payload, ensure_ascii=False)
    assert HANDLE_TWIN not in keys
    assert HANDLE_TWIN not in blob
    assert HANDLE_CIRCUIT not in keys
    for name in _FORBIDDEN:
        if name in {"Pauli", "OPENQASM"}:
            assert name not in blob
            continue
        assert name not in keys


def test_live_qchem_then_dequant() -> None:
    exe = Path(QCHEM_HOME) / ".venv" / "bin" / "qchem-run"
    assert exe.is_file(), f"missing live qchem-run at {exe}"
    with live_qchem_store():
        assert os.environ.get("QAGENT_QCHEM_HOME") == QCHEM_HOME
        assert os.environ.get("QAGENT_DATA_DIR") == str(_STORE)
        assert not os.environ.get("QAGENT_QDATA_URL")
        ran = invoke("qchem_run", "lab", {"scenario": "minimal_vqe"})
        assert ran.status == "ok", f"run expected ok, got {ran.status}: {ran.error}"
        run_payload = dict(ran.payload or {})
        assert run_payload, "qchem_run returned empty payload"
        asset_id = str(run_payload.get(HANDLE_ASSET) or "").strip()
        assert asset_id, "no live asset_id — A-02i is not done"
        summary = run_payload.get("summary") if isinstance(run_payload.get("summary"), dict) else {}
        assert summary.get("source") == "qchem-cli", f"source={summary.get('source')!r}"
        assert summary.get("source") != "qagent-local-card"
        assert HANDLE_TWIN not in run_payload
        assert HANDLE_CIRCUIT not in run_payload
        _no_forbidden(run_payload)
        dequant_args = {HANDLE_ASSET: asset_id}
        assert "force_verdict" not in dequant_args
        got = invoke("qdata_dequant_gate", "lab", dequant_args)
    assert got.status == "ok", f"dequant_gate expected ok, got {got.status}: {got.error}"
    payload = dict(got.payload or {})
    assert payload, "dequant_gate returned empty payload"
    b3 = payload.get("b3")
    assert isinstance(b3, dict) and b3, f"dequant_gate missing b3: {payload!r}"
    verdict = str(b3.get("verdict") or "").strip()
    assert verdict, "dequant_gate missing b3.verdict — A-02i is not done"
    assert verdict in B3_VERDICTS, f"b3.verdict not in enum: {verdict!r}"
    assert HANDLE_TWIN not in payload
    _no_forbidden(payload)
    print(
        f"live asset_id={asset_id} b3.verdict={verdict} "
        f"dequant={json.dumps(payload, ensure_ascii=False)}"
    )


def test_note_copies_hit() -> None:
    assert _NOTE.is_file(), f"missing {_NOTE}"
    text = _NOTE.read_text(encoding="utf-8")
    compact = "".join(text.split())
    assert _COPIED_ASSET, "note copy is empty — A-02i is not done"
    assert _COPIED_ASSET in text
    assert _COPIED_VERDICT in text
    assert json.dumps(_COPIED_DEQUANT, ensure_ascii=False) in text or (
        '"verdict": "inconclusive"' in text and '"qem_contract_ok": false' in text
    )
    assert "qchem-cli" in text
    assert "minimal_vqe" in text
    assert "invoke" in text
    assert "qchem_run" in text
    assert "qdata_dequant_gate" in text
    assert "asset_id" in text
    assert "b3.verdict" in text
    assert "QAGENT_DATA_DIR" in text
    assert "QAGENT_QCHEM_HOME" in text
    assert "不算 G0" in text or "不算G0" in compact
    assert "G0 已通过" not in text
    assert "G0已通过" not in compact
    assert "skip 当绿" in text or "skip当绿" in compact
    assert "未 commit" in text
    assert "apply_env" in text
    assert "workplace.json" in text
    assert "QAGENT_QDATA_URL" in text
    assert "force_verdict" in text
    assert "不要 force_verdict" in text
    assert "twin_id" in text
    assert any(token in text for token in ("不铸", "无 twin_id", "没有 twin_id"))


def test_this_file_does_not_skip() -> None:
    text = Path(__file__).read_text(encoding="utf-8")
    assert ("pytest" + ".skip") not in text
    assert ("unittest" + ".skip") not in text
    assert ("skip" + "Test") not in text
    assert ("from qagent.services." + "workplace") not in text
    assert ("apply" + "_env(") not in text
    assert ("{" + '"force_verdict"') not in text
    assert ('"force_verdict"' + ":") not in text


def main() -> int:
    if _STORE.exists():
        shutil.rmtree(_STORE)
    failed = 0
    for name, fn in (
        ("live_qchem_then_dequant", test_live_qchem_then_dequant),
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
