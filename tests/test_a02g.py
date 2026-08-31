"""A-02g live qchem hit. Skip-as-green is incomplete. No pytest required."""

from __future__ import annotations

import os
import sys
import traceback
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from qagent.adapters.qchem import _last_json_object
from qagent.models.handles import HANDLE_ASSET, HANDLE_CIRCUIT, HANDLE_TWIN
from qagent.services.invoke import invoke

NOTE = ROOT / "docs" / "execution" / "A-02g_live_hit.md"
QCHEM_HOME = "/Users/shl/nvidia/qcchem-qml-md"
_ENV_KEYS = (
    "QAGENT_QCHEM_BIN",
    "QAGENT_QCHEM_HOME",
    "QAGENT_QCHEM_PARITY_BIN",
    "QAGENT_QDATA_URL",
    "QAGENT_QDATA_HOME",
    "QAGENT_QDATA_BIN",
    "QAGENT_QDATA_PYTHON",
)
_MIXED = """2026-08-27 [INFO] qchem_stack.orchestration.pipeline_events: {"event": "pipeline.started"}
{
  "energy_after_variational": -1.1372759415451792,
  "experiment_id": null,
  "scf_energy": -1.116714325062552
}
"""


@contextmanager
def live_qchem_home() -> Iterator[None]:
    previous = {key: os.environ.get(key) for key in _ENV_KEYS}
    for key in _ENV_KEYS:
        os.environ.pop(key, None)
    os.environ["QAGENT_QCHEM_HOME"] = QCHEM_HOME
    try:
        yield
    finally:
        for key in _ENV_KEYS:
            os.environ.pop(key, None)
        for key, value in previous.items():
            if value is not None:
                os.environ[key] = value


def test_extracts_last_json_from_logs() -> None:
    parsed = _last_json_object(_MIXED)
    assert parsed["experiment_id"] is None
    assert parsed["scf_energy"] == -1.116714325062552
    pure = _last_json_object('{"experiment_id": "exp_live", "asset_id": "asset_cli"}')
    assert pure["asset_id"] == "asset_cli"


def test_live_invoke_qchem_run() -> None:
    exe = Path(QCHEM_HOME) / ".venv" / "bin" / "qchem-run"
    assert exe.is_file(), f"missing live qchem-run at {exe}"
    with live_qchem_home():
        invoked = invoke("qchem_run", "lab", {"scenario": "minimal_vqe"})
    assert invoked.status == "ok", invoked.error
    payload = dict(invoked.payload or {})
    print("A-02g payload", payload)
    assert payload.get(HANDLE_ASSET)
    assert HANDLE_TWIN not in payload
    assert HANDLE_CIRCUIT not in payload
    summary = payload.get("summary")
    assert isinstance(summary, dict)
    assert summary.get("source") == "qchem-cli"
    assert HANDLE_TWIN not in summary
    assert HANDLE_CIRCUIT not in summary


def test_note_copies_live_payload() -> None:
    assert NOTE.exists(), f"missing {NOTE}"
    text = NOTE.read_text(encoding="utf-8")
    compact = "".join(text.split())
    assert "qchem-cli" in text
    assert "asset_id" in text
    assert "minimal_vqe" in text
    assert "G0 已通过" not in text
    assert "G0已通过" not in compact
    assert "skip 当绿" in text or "skip当绿" in compact
    assert "不算 G0" in text or "不算G0" in compact
    assert "twin_id" in text
    assert any(token in text for token in ("不铸", "无 twin_id", "没有 twin_id"))
    assert '"asset_' in text or "asset_" in text


def main() -> int:
    failed = 0
    for name, fn in (
        ("extracts_last_json_from_logs", test_extracts_last_json_from_logs),
        ("live_invoke_qchem_run", test_live_invoke_qchem_run),
        ("note_copies_live_payload", test_note_copies_live_payload),
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
