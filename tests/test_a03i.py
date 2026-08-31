"""A-03i: vibe_path TwinRun uses pipeline. Skip-as-green is incomplete."""

from __future__ import annotations

import os
import shutil
import sys
import traceback
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT
sys.path.insert(0, str(ROOT / "src"))

from qagent.models.handles import HANDLE_TWIN, PROVENANCE_QCCD_TWIN
from qagent.services.vibe_path import run_vibe_path

_LIVE_URL = "http://127.0.0.1:8765"
_DEAD_URL = "http://127.0.0.1:1"
_NOTE = REPO / "docs" / "execution" / "A-03i_vibe_pipeline.md"
_STORE = ROOT / ".qagent" / "test-a03i-store"
_COPIED_TWIN = "5c9ce47cda91d673598ba1283fed4e5ab4c1c17d2c770245ecab2534e3e071a5"
_SOUTHBOUND = ("calibration", "cal", "shuttle", "ms_matrix")
_ENV_KEYS = (
    "QAGENT_TWIN_URL",
    "QAGENT_DATA_DIR",
    "QAGENT_ELN_FILE",
    "QAGENT_QDATA_URL",
    "QAGENT_QDATA_HOME",
    "QAGENT_QDATA_BIN",
    "QAGENT_QCHEM_HOME",
    "QAGENT_IONSTACK_HOME",
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


def _twin_step(path: dict[str, Any]) -> dict[str, Any]:
    for step in path.get("steps") or []:
        if isinstance(step, dict) and step.get("tool") == "ionstack_twin_run":
            return step
    raise AssertionError("vibe_path missing ionstack_twin_run step")


def test_vibe_path_default_is_pipeline() -> None:
    src = (ROOT / "src" / "qagent" / "services" / "vibe_path.py").read_text(encoding="utf-8")
    assert '"mode": "pipeline"' in src
    assert '"mode": "signoff"' not in src
    for leaked in ('"calibration"', '"shuttle"', '"ms_matrix"'):
        assert leaked not in src
    assert "import qdata" not in src
    assert "import ionstack" not in src
    assert "import qchem" not in src
    assert "import qiskit" not in src


def test_unapproved_still_needs_ask() -> None:
    with isolated_twin_url(_LIVE_URL):
        path = run_vibe_path("lab", shots=8, approved=False)
    assert path["status"] == "needs_ask"
    assert path["tool"] == "ionstack_twin_run"
    assert HANDLE_TWIN not in (path.get("handles") or {})
    step = _twin_step(path)
    assert step["status"] == "needs_ask"
    payload = step.get("payload") or {}
    assert HANDLE_TWIN not in payload
    print("unapproved vibe_path needs_ask, no twin_id")


def test_live_approved_vibe_path() -> None:
    with isolated_twin_url(_LIVE_URL):
        assert os.environ.get("QAGENT_TWIN_URL") == _LIVE_URL
        path = run_vibe_path("lab", shots=8, approved=True)
    assert path["status"] == "ok", f"expected ok, got {path['status']}: {path.get('summary')}"
    handles = path.get("handles") or {}
    twin_id = str(handles.get(HANDLE_TWIN) or "").strip()
    assert twin_id, "no live vibe_path twin_id — A-03i is not done"
    step = _twin_step(path)
    assert step["status"] == "ok", f"twin step {step['status']}: {step.get('error')}"
    payload = dict(step.get("payload") or {})
    assert payload.get(HANDLE_TWIN) == twin_id
    assert payload.get("provenance") == PROVENANCE_QCCD_TWIN
    counts = payload.get("counts")
    assert isinstance(counts, dict) and counts, f"counts={counts!r}"
    for leaked in _SOUTHBOUND:
        assert leaked not in payload
    print(
        f"live vibe_path twin_id={twin_id} provenance={payload['provenance']} "
        f"counts={counts} shots_actual={payload.get('shots_actual')}"
    )


def test_dead_url_honest_error() -> None:
    with isolated_twin_url(_DEAD_URL):
        path = run_vibe_path("lab", shots=8, approved=True)
    assert path["status"] == "error"
    assert HANDLE_TWIN not in (path.get("handles") or {})
    step = _twin_step(path)
    assert step["status"] == "error"
    assert HANDLE_TWIN not in (step.get("payload") or {})
    print(f"dead vibe_path honest error={path.get('summary')!r} no twin_id")


def test_note_copies_hit() -> None:
    assert _NOTE.is_file(), f"missing {_NOTE}"
    text = _NOTE.read_text(encoding="utf-8")
    assert _COPIED_TWIN in text
    assert "qccd-twin" in text
    assert "run_vibe_path" in text
    assert "pipeline" in text
    assert "ionstack_twin_run" in text
    assert "DEFAULT_CIRCUIT" in text
    assert "不算 G0" in text
    assert "不算 G1" in text
    assert "G0 已通过" not in text
    assert "signoff" in text
    assert "CAL" in text
    assert "不进工具" in text
    assert "skip 当绿" in text
    assert "未 commit" in text
    assert "诚实" in text


def test_this_file_does_not_skip() -> None:
    text = Path(__file__).read_text(encoding="utf-8")
    assert ("pytest" + ".skip") not in text
    assert ("unittest" + ".skip") not in text
    assert ("skip" + "Test") not in text


def main() -> int:
    if _STORE.exists():
        shutil.rmtree(_STORE)
    failed = 0
    for name, fn in (
        ("vibe_path_default_is_pipeline", test_vibe_path_default_is_pipeline),
        ("unapproved_still_needs_ask", test_unapproved_still_needs_ask),
        ("live_approved_vibe_path", test_live_approved_vibe_path),
        ("dead_url_honest_error", test_dead_url_honest_error),
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
