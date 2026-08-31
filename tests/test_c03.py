"""C-03: settings cloud_url is the only cloud entry. IBM stays deny."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import traceback
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from qagent.adapters.qiskit import WiredQiskit
from qagent.adapters.workplace_store import dsh_env_path
from qagent.models.fill import FillSlotError
from qagent.models.handles import HANDLE_TWIN, PROVENANCE_QCCD_TWIN
from qagent.models.invoke import STATUS_DENIED
from qagent.services.engines import list_engines
from qagent.services.invoke import invoke
from qagent.services.policy import decide
from qagent.services.product_eval import run_product_evals
from qagent.services.workplace import (
    apply_env,
    cloud_url,
    load_workplace,
    probe_cloud,
    save_workplace,
    workplace_status,
)

_NOTE = ROOT / "docs" / "execution" / "C-03_cloud.md"
_FIVE = ("qdata", "qchem", "ionstack", "route", "qiskit")
_PRESETS = ("lab", "algo", "sign")
_DUMMY = "https://cloud.example.test"
_DEAD = "http://127.0.0.1:1"
_SECRET = "sk-c03-never-echo-xyz"
_HPC = "c03-hpc-n3v3r-echo"
_QTM = "c03-qtm-n3v3r-echo"
_ENV_KEYS = (
    "QAGENT_WORKPLACE_FILE",
    "QAGENT_SECRETS_FILE",
    "QAGENT_DSH_ENV_FILE",
    "QAGENT_CLOUD_URL",
    "DEEPSEEK_BASE_URL",
    "DEEPSEEK_API_KEY",
    "DEEPSEEK_MODEL",
)


@contextmanager
def _temp_workplace():
    previous = {key: os.environ.get(key) for key in _ENV_KEYS}
    tmp = tempfile.TemporaryDirectory()
    try:
        folder = Path(tmp.name)
        os.environ["QAGENT_WORKPLACE_FILE"] = str(folder / "workplace.json")
        os.environ["QAGENT_SECRETS_FILE"] = str(folder / "secrets.json")
        os.environ["QAGENT_DSH_ENV_FILE"] = str(folder / "dsh.env")
        for key in ("QAGENT_CLOUD_URL", "DEEPSEEK_BASE_URL", "DEEPSEEK_API_KEY", "DEEPSEEK_MODEL"):
            os.environ.pop(key, None)
        yield folder
    finally:
        tmp.cleanup()
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _assert_ibm_denied() -> None:
    for preset in _PRESETS:
        assert decide("qiskit_ibm_run", preset, {}) == "deny"
        result = invoke("qiskit_ibm_run", preset, {})
        assert result.decision == "deny"
        assert result.status == STATUS_DENIED
        assert result.status != "done"
        payload = dict(result.payload or {})
        assert HANDLE_TWIN not in payload
        assert payload.get("provenance") != PROVENANCE_QCCD_TWIN
        assert payload.get("status") != "done"


def test_empty_workplace_unsets_cloud_env() -> None:
    with _temp_workplace():
        os.environ["QAGENT_CLOUD_URL"] = "https://stale.example"
        row = load_workplace()
        assert row.cloud_url == ""
        assert cloud_url(row) == ""
        apply_env(row)
        assert row.cloud_url == ""
        assert cloud_url() == ""
        assert "QAGENT_CLOUD_URL" not in os.environ
        probed = probe_cloud(row)
        assert probed["configured"] is False
        assert probed["status"] == "not_configured"
        assert probed["status"] != "done"
        assert HANDLE_TWIN not in probed


def test_save_cloud_url_sets_env_and_status() -> None:
    with _temp_workplace():
        row = save_workplace(
            {"cloud_url": _DUMMY},
            {"llm_api_key": _SECRET, "hpc_secret": _HPC, "quantum_secret": _QTM},
        )
        assert row.cloud_url == _DUMMY
        apply_env(row)
        assert os.environ.get("QAGENT_CLOUD_URL") == _DUMMY
        assert cloud_url() == _DUMMY
        status = workplace_status()
        dumped = json.dumps(status, ensure_ascii=False)
        assert status["workplace"]["cloud_url"] == _DUMMY
        assert _DUMMY in dumped
        assert _SECRET not in dumped
        assert _HPC not in dumped
        assert _QTM not in dumped
        public = status["workplace"]
        assert "llm_api_key" not in public
        assert "hpc_secret" not in public
        assert "quantum_secret" not in public
        env_blob = json.dumps(dict(os.environ), ensure_ascii=False)
        assert _HPC not in env_blob
        assert _QTM not in env_blob
        env_text = dsh_env_path().read_text(encoding="utf-8")
        assert "QAGENT_CLOUD_URL" not in env_text
        assert _DUMMY not in env_text


def test_ibm_run_deny_cloud_off_and_on() -> None:
    with _temp_workplace():
        apply_env()
        assert cloud_url() == ""
        assert "QAGENT_CLOUD_URL" not in os.environ
        _assert_ibm_denied()
        save_workplace({"cloud_url": _DUMMY})
        assert os.environ.get("QAGENT_CLOUD_URL") == _DUMMY
        _assert_ibm_denied()
        try:
            WiredQiskit().ibm_run({})
        except FillSlotError as exc:
            assert exc.slot_id == "S-QISKIT-05"
        else:
            raise AssertionError("ibm_run must fill even when cloud_url is set")


def test_dead_cloud_url_is_honest() -> None:
    with _temp_workplace():
        save_workplace({"cloud_url": _DEAD})
        assert os.environ.get("QAGENT_CLOUD_URL") == _DEAD
        try:
            result = probe_cloud()
        except RuntimeError as exc:
            text = str(exc)
            assert "HTTP" in text
            assert "reachable" in text
            assert HANDLE_TWIN not in text
            assert "done" not in text
        else:
            raise AssertionError(f"dead cloud URL must not look done: {result!r}")
        _assert_ibm_denied()


def test_qc05_still_ok() -> None:
    rows = run_product_evals("Q-c05")
    assert [row.id for row in rows] == ["Q-c05"]
    assert rows[0].ok and not rows[0].skipped, rows[0].detail


def test_note_exists() -> None:
    assert _NOTE.is_file()
    text = _NOTE.read_text(encoding="utf-8")
    assert "QAGENT_CLOUD_URL" in text
    assert "qiskit_ibm_run" in text


def test_five_pack_unchanged() -> None:
    ids = [pack.id for pack in list_engines()]
    assert ids[:5] == list(_FIVE)
    assert set(_FIVE) <= set(ids)


def main() -> int:
    failed = 0
    for name, fn in (
        ("empty_workplace_unsets_cloud_env", test_empty_workplace_unsets_cloud_env),
        ("save_cloud_url_sets_env_and_status", test_save_cloud_url_sets_env_and_status),
        ("ibm_run_deny_cloud_off_and_on", test_ibm_run_deny_cloud_off_and_on),
        ("dead_cloud_url_is_honest", test_dead_cloud_url_is_honest),
        ("qc05_still_ok", test_qc05_still_ok),
        ("note_exists", test_note_exists),
        ("five_pack_unchanged", test_five_pack_unchanged),
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
