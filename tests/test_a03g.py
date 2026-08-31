"""A-03g: live invoke identity + pipeline TwinRun. Skip-as-green is incomplete."""

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

from qagent.models.handles import HANDLE_TWIN, PROVENANCE_QCCD_TWIN
from qagent.services.eval_run import DEFAULT_CIRCUIT
from qagent.services.invoke import invoke

_LIVE_URL = "http://127.0.0.1:8765"
_SHOTS = 8
_NOTE = ROOT / "docs" / "execution" / "A-03g_live_hit.md"
_OLD_LIVE = ROOT / "docs" / "execution" / "A-03_live.md"
_STORE = ROOT / ".qagent" / "test-a03g-store"
_COPIED_TWIN = "5c9ce47cda91d673598ba1283fed4e5ab4c1c17d2c770245ecab2534e3e071a5"
_ENV_KEYS = (
    "QAGENT_TWIN_URL",
    "QAGENT_DATA_DIR",
    "QAGENT_ELN_FILE",
)


@contextmanager
def live_twin_env() -> Iterator[None]:
    previous = {key: os.environ.get(key) for key in _ENV_KEYS}
    for key in _ENV_KEYS:
        os.environ.pop(key, None)
    _STORE.mkdir(parents=True, exist_ok=True)
    os.environ["QAGENT_TWIN_URL"] = _LIVE_URL
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


def _no_twin_id(payload: Mapping[str, Any] | None) -> None:
    blob = json.dumps(payload or {}, ensure_ascii=False)
    assert HANDLE_TWIN not in _keys(payload or {})
    assert HANDLE_TWIN not in blob


def test_live_invoke_identity_no_twin_id() -> None:
    with live_twin_env():
        assert os.environ.get("QAGENT_TWIN_URL") == _LIVE_URL
        invoked = invoke("ionstack_twin_identity", "lab", {})
    assert invoked.status == "ok", f"expected ok, got {invoked.status}: {invoked.error}"
    payload = dict(invoked.payload or {})
    assert payload, "identity invoke returned empty payload"
    assert payload.get("live") is True, f"identity live={payload.get('live')!r}; Twin not proven"
    assert payload.get("preset") == "t_junction"
    assert isinstance(payload.get("n_qubits"), int)
    assert set(payload) == {"preset", "n_qubits", "live"}
    _no_twin_id(payload)
    print(
        f"live identity preset={payload['preset']} n_qubits={payload['n_qubits']} "
        f"live={payload['live']} keys={sorted(payload)}"
    )


def test_live_invoke_pipeline_twin_run() -> None:
    args = {
        "mode": "pipeline",
        "shots": _SHOTS,
        "circuit": DEFAULT_CIRCUIT,
    }
    with live_twin_env():
        invoked = invoke("ionstack_twin_run", "lab", args, approved=True)
    assert invoked.status == "ok", f"expected ok, got {invoked.status}: {invoked.error}"
    payload = dict(invoked.payload or {})
    assert payload, "TwinRun invoke returned empty payload"
    twin_id = str(payload.get(HANDLE_TWIN) or "").strip()
    assert twin_id, "no live TwinRun twin_id — A-03g is not done"
    assert payload.get("provenance") == PROVENANCE_QCCD_TWIN, (
        f"provenance={payload.get('provenance')!r}"
    )
    counts = payload.get("counts")
    assert isinstance(counts, dict) and counts, f"counts={counts!r}"
    assert args["mode"] == "pipeline"
    print(
        f"live twin_id={twin_id} provenance={payload['provenance']} "
        f"counts={counts} shots_actual={payload.get('shots_actual')}"
    )


def test_note_copies_hit() -> None:
    assert _NOTE.is_file(), f"missing {_NOTE}"
    text = _NOTE.read_text(encoding="utf-8")
    assert _COPIED_TWIN in text
    assert "qccd-twin" in text
    assert "t_junction" in text
    assert "live" in text
    assert "invoke" in text
    assert "ionstack_twin_identity" in text
    assert "ionstack_twin_run" in text
    assert "pipeline" in text
    assert "DEFAULT_CIRCUIT" in text
    assert "identity 单独不算已通" in text
    assert "pipeline TwinRun 才算" in text
    assert "不算 G0" in text
    assert "不算 G2" in text
    assert "不算接线 Pennylane" in text
    assert "G0 已通过" not in text
    assert "signoff mode requires calibration" in text
    assert "CAL" in text
    assert "不进工具" in text
    assert "A-03_live" in text
    assert "未打" in text
    assert "未证明" in text
    assert "未改" in text
    assert "ionstack.py" in text
    assert "未 commit" in text
    assert "skip 当绿" in text


def test_a03_live_contract_untouched() -> None:
    assert _OLD_LIVE.is_file(), f"missing {_OLD_LIVE}"
    text = _OLD_LIVE.read_text(encoding="utf-8")
    assert "未打" in text
    assert "未证明" in text
    assert "unproven" in text.lower()
    assert "活 Twin **未证明**" in text or "活 Twin**未证明**" in text.replace(" ", "")


def main() -> int:
    if _STORE.exists():
        shutil.rmtree(_STORE)
    failed = 0
    for name, fn in (
        ("live_invoke_identity_no_twin_id", test_live_invoke_identity_no_twin_id),
        ("live_invoke_pipeline_twin_run", test_live_invoke_pipeline_twin_run),
        ("note_copies_hit", test_note_copies_hit),
        ("a03_live_contract_untouched", test_a03_live_contract_untouched),
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
