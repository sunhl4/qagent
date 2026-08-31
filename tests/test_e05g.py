"""A-03h: run_eval(E05) uses pipeline TwinRun. Skip-as-green is incomplete."""

from __future__ import annotations

import os
import shutil
import sys
import traceback
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from qagent.adapters.contracts import load_eval_cases
from qagent.models.handles import HANDLE_TWIN, PROVENANCE_QCCD_TWIN
from qagent.models.invoke import STATUS_ERROR, STATUS_OK
from qagent.models.types import EvalCase
from qagent.services.eval_run import DEFAULT_CIRCUIT, _scenario, _twin_args, run_eval

_LIVE_URL = "http://127.0.0.1:8765"
_DEAD_URL = "http://127.0.0.1:1"
_NOTE = ROOT / "docs" / "execution" / "A-03h_e05_pipeline.md"
_STORE = ROOT / ".qagent" / "test-e05g-store"
_COPIED_TWIN = "5c9ce47cda91d673598ba1283fed4e5ab4c1c17d2c770245ecab2534e3e071a5"
_SOUTHBOUND = ("calibration", "cal", "shuttle", "ms_matrix")
_ENV_KEYS = (
    "QAGENT_TWIN_URL",
    "QAGENT_DATA_DIR",
    "QAGENT_ELN_FILE",
)


@contextmanager
def isolated_twin_url(url: str) -> Iterator[None]:
    previous = {key: os.environ.get(key) for key in _ENV_KEYS}
    for key in _ENV_KEYS:
        os.environ.pop(key, None)
    _STORE.mkdir(parents=True, exist_ok=True)
    os.environ["QAGENT_TWIN_URL"] = url
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


def _e05() -> EvalCase:
    return next(case for case in load_eval_cases() if case.id == "E05")


def _no_twin_id(payload: object) -> None:
    if isinstance(payload, dict):
        assert HANDLE_TWIN not in payload


def test_twin_args_default_is_pipeline() -> None:
    args = _twin_args()
    assert args["mode"] == "pipeline"
    assert args["mode"] != "signoff"
    assert args["shots"] == 1000
    assert args["circuit"] == DEFAULT_CIRCUIT
    for leaked in _SOUTHBOUND:
        assert leaked not in args
    src = (ROOT / "src" / "qagent" / "services" / "eval_run.py").read_text(encoding="utf-8")
    assert '"mode": "pipeline"' in src
    assert 'body = {"mode": "signoff"' not in src


def test_live_run_eval_e05() -> None:
    case = _e05()
    store: dict[str, Any] = {}
    with isolated_twin_url(_LIVE_URL):
        assert os.environ.get("QAGENT_TWIN_URL") == _LIVE_URL
        results = _scenario(case, store)
        result = run_eval(case, {})
    assert result.ok, f"live E05 not ok: {result.detail}"
    primary = results["primary"]
    assert primary.status == STATUS_OK, f"expected ok, got {primary.status}: {primary.error}"
    payload = dict(primary.payload or {})
    assert payload, "live E05 returned empty payload"
    twin_id = str(payload.get(HANDLE_TWIN) or "").strip()
    assert twin_id, "no live TwinRun twin_id — A-03h is not done"
    assert store.get("E05") == twin_id
    counts = payload.get("counts")
    assert isinstance(counts, dict) and counts, f"counts={counts!r}"
    assert payload.get("provenance") == PROVENANCE_QCCD_TWIN, (
        f"provenance={payload.get('provenance')!r}"
    )
    for leaked in _SOUTHBOUND:
        assert leaked not in payload
    print(
        f"live E05 twin_id={twin_id} provenance={payload['provenance']} "
        f"counts={counts} shots_actual={payload.get('shots_actual')}"
    )


def test_dead_url_honest_error() -> None:
    case = _e05()
    store: dict[str, Any] = {}
    with isolated_twin_url(_DEAD_URL):
        results = _scenario(case, store)
        result = run_eval(case, {})
    assert result.ok, f"dead E05 must stay honest-ok: {result.detail}"
    primary = results["primary"]
    assert primary.status == STATUS_ERROR, f"expected error, got {primary.status}"
    _no_twin_id(primary.payload)
    assert HANDLE_TWIN not in store
    assert "E05" not in store
    print(f"dead E05 honest error={primary.error!r} no twin_id")


def test_note_copies_hit() -> None:
    assert _NOTE.is_file(), f"missing {_NOTE}"
    text = _NOTE.read_text(encoding="utf-8")
    assert _COPIED_TWIN in text
    assert "qccd-twin" in text
    assert "run_eval" in text
    assert "E05" in text
    assert "pipeline" in text
    assert "_twin_args" in text
    assert "DEFAULT_CIRCUIT" in text
    assert "ionstack_twin_run" in text
    assert "不算 G0" in text
    assert "不算 G3" in text
    assert "G0 已通过" not in text
    assert "signoff" in text
    assert "CAL" in text
    assert "不进工具" in text
    assert "skip 当绿" in text
    assert "未 commit" in text
    assert "诚实" in text


def main() -> int:
    if _STORE.exists():
        shutil.rmtree(_STORE)
    failed = 0
    for name, fn in (
        ("twin_args_default_is_pipeline", test_twin_args_default_is_pipeline),
        ("live_run_eval_e05", test_live_run_eval_e05),
        ("dead_url_honest_error", test_dead_url_honest_error),
        ("note_copies_hit", test_note_copies_hit),
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
