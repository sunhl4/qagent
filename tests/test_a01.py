"""A-01 qdata honesty. Isolates env. No pytest required."""

from __future__ import annotations

import os
import shutil
import sys
import traceback
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from qagent.adapters.qdata import WiredQData, _FORBIDDEN_OUT, _JOB_OUT, _job_from_live
from qagent.services.boundaries import scan_forbidden_imports
from qagent.services.invoke import invoke

_ENV_KEYS = (
    "QAGENT_QDATA_URL",
    "QAGENT_QDATA_HOME",
    "QAGENT_QDATA_BIN",
    "QAGENT_QDATA_PYTHON",
)
_STORE = ROOT / ".qagent" / "test-a01-store"
_DEAD_URL = "http://127.0.0.1:1"
_ALLOWED_JOB_KEYS = {"status", "summary", "asset_id", "job_id"}


@contextmanager
def isolated_qdata_env(**overrides: str) -> Iterator[None]:
    previous = {key: os.environ.get(key) for key in _ENV_KEYS}
    for key in _ENV_KEYS:
        os.environ.pop(key, None)
    os.environ.update(overrides)
    try:
        yield
    finally:
        for key in _ENV_KEYS:
            os.environ.pop(key, None)
        for key, value in previous.items():
            if value is not None:
                os.environ[key] = value


def _store_args(**extra: object) -> dict:
    _STORE.mkdir(parents=True, exist_ok=True)
    args: dict = {"data_dir": str(_STORE), **extra}
    return args


def test_forbidden_out_kept() -> None:
    assert _FORBIDDEN_OUT == {"bitstrings", "rows", "pauli_terms", "counts_full", "result_full"}
    assert _JOB_OUT == {"status", "summary", "asset_id"}


def test_dead_url_submit_fails() -> None:
    port = WiredQData()
    with isolated_qdata_env(QAGENT_QDATA_URL=_DEAD_URL):
        try:
            result = port.submit_job(_store_args(kind="surrogate", payload={}))
        except RuntimeError as exc:
            text = str(exc)
            assert "HTTP" in text
            assert "reachable" in text
        else:
            raise AssertionError(f"expected RuntimeError, got {result!r}")
        invoked = invoke("qdata_submit_job", "lab", {"kind": "surrogate", "payload": {}})
    assert invoked.status == "error"
    payload = dict(invoked.payload or {})
    assert payload.get("status") != "done"
    assert "job_id" not in payload
    assert "done" not in str(invoked.error or "")


def test_dead_url_get_job_fails() -> None:
    port = WiredQData()
    with isolated_qdata_env(QAGENT_QDATA_URL=_DEAD_URL):
        try:
            result = port.get_job(_store_args(job_id="job_dead"))
        except RuntimeError as exc:
            assert "HTTP" in str(exc)
        else:
            raise AssertionError(f"expected RuntimeError, got {result!r}")
        invoked = invoke("qdata_get_job", "lab", {"job_id": "job_dead"})
    assert invoked.status == "error"
    assert (invoked.payload or {}).get("status") != "done"


def test_get_job_payload_keys() -> None:
    port = WiredQData()
    with isolated_qdata_env():
        submitted = port.submit_job(_store_args(kind="shadow-predict", payload={}))
        job = port.get_job(_store_args(job_id=submitted["job_id"]))
    assert set(job) <= _ALLOWED_JOB_KEYS
    assert set(job) <= _JOB_OUT | ({"job_id"} & set(job))
    assert not _FORBIDDEN_OUT & set(job)
    assert "bitstrings" not in job
    assert "rows" not in job
    assert job.get("status") != "done"
    assert "asset_id" in job
    assert "twin_id" not in job
    if isinstance(job.get("summary"), dict):
        assert not _FORBIDDEN_OUT & set(job["summary"])


def test_job_from_live_strips_forbidden() -> None:
    fat = {
        "status": "running",
        "summary": {
            "kind": "surrogate",
            "bitstrings": ["11"],
            "rows": [2],
            "pauli_terms": ["Z0"],
            "counts_full": {"11": 1},
            "result_full": {"x": 1},
        },
        "asset_id": "asset_live",
        "job_id": "job_live",
        "bitstrings": ["00"],
        "rows": [1],
        "pauli_terms": ["X0"],
        "counts_full": {"00": 4},
        "result_full": {"y": 2},
        "twin_id": "twin_must_not_leak",
        "counts": {"00": 4},
    }
    out = _job_from_live(fat)
    assert set(out) <= _ALLOWED_JOB_KEYS
    assert set(out) <= _JOB_OUT
    assert not _FORBIDDEN_OUT & set(out)
    assert "bitstrings" not in out
    assert "twin_id" not in out
    assert "counts" not in out
    assert "job_id" not in out
    assert out["status"] == "running"
    assert out["asset_id"] == "asset_live"
    assert not _FORBIDDEN_OUT & set(out["summary"])


def test_run_recipe_local_card_without_cli() -> None:
    port = WiredQData()
    with isolated_qdata_env():
        recipe = port.run_recipe(_store_args(name="a2_chem_pes"))
        invoked = invoke("qdata_run_recipe", "lab", {"name": "a2_spin_shadow"})
    assert recipe.get("asset_id")
    assert recipe["summary"]["source"] == "qagent-local-card"
    assert invoked.status == "ok"
    assert invoked.payload is not None
    assert invoked.payload.get("asset_id")
    assert invoked.payload["summary"]["source"] == "qagent-local-card"
    assert "twin_id" not in recipe
    assert "twin_id" not in invoked.payload


def test_cli_failure_raises() -> None:
    port = WiredQData()
    with isolated_qdata_env(QAGENT_QDATA_BIN="/no/such/qagent-qdata-bin"):
        try:
            result = port.run_recipe(_store_args(name="a2_chem_pes"))
        except RuntimeError:
            pass
        else:
            raise AssertionError(f"expected RuntimeError, got {result!r}")
        invoked = invoke("qdata_run_recipe", "lab", {"name": "a2_chem_pes"})
    assert invoked.status == "error"
    assert (invoked.payload or {}).get("status") != "done"
    assert (invoked.payload or {}).get("summary", {}).get("source") != "qagent-local-card"


def test_adapter_does_not_import_qdata_or_mint_twin() -> None:
    text = (ROOT / "src/qagent/adapters/qdata.py").read_text(encoding="utf-8")
    hits = [row for row in scan_forbidden_imports() if "adapters/qdata.py" in row]
    assert hits == []
    assert "from qdata " not in text
    assert "from qdata." not in text
    assert "import qdata\n" not in text
    assert "twin_id" not in text


def main() -> int:
    if _STORE.exists():
        shutil.rmtree(_STORE)
    failed = 0
    for name, fn in (
        ("forbidden_out_kept", test_forbidden_out_kept),
        ("dead_url_submit", test_dead_url_submit_fails),
        ("dead_url_get_job", test_dead_url_get_job_fails),
        ("get_job_payload_keys", test_get_job_payload_keys),
        ("job_from_live_strips", test_job_from_live_strips_forbidden),
        ("run_recipe_local_card", test_run_recipe_local_card_without_cli),
        ("cli_failure_raises", test_cli_failure_raises),
        ("no_qdata_import_or_twin", test_adapter_does_not_import_qdata_or_mint_twin),
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
