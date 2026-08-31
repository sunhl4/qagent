"""A-02 qchem honesty. Isolates env. No pytest required."""

from __future__ import annotations

import os
import stat
import sys
import tempfile
import traceback
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from qagent.adapters.qchem import WiredQChem
from qagent.models.handles import HANDLE_ASSET, HANDLE_CIRCUIT, HANDLE_TWIN
from qagent.services.boundaries import scan_forbidden_imports
from qagent.services.invoke import invoke

_ENV_KEYS = (
    "QAGENT_QCHEM_BIN",
    "QAGENT_QCHEM_HOME",
    "QAGENT_QCHEM_PARITY_BIN",
    "QAGENT_QDATA_URL",
    "QAGENT_QDATA_HOME",
    "QAGENT_QDATA_BIN",
    "QAGENT_QDATA_PYTHON",
)
_DEAD_BIN = "/no/such/qagent-qchem-bin"
_FAKE_CLI = r"""#!/usr/bin/env python3
import json
print(json.dumps({
    "experiment_id": "exp_live",
    "asset_id": "asset_cli",
    "scenario": "minimal_vqe",
    "twin_id": "twin_must_not_leak",
    "circuit_id": "circ_not_a_handle",
    "qasm3": "OPENQASM 3.0; qubit q;",
    "pauli_terms": ["Z0"],
}))
"""
_FAIL_CLI = """#!/usr/bin/env python3
import sys
sys.stderr.write("qchem-run exploded\\n")
sys.exit(2)
"""


@contextmanager
def isolated_qchem_env(**overrides: str) -> Iterator[None]:
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


def _write_exe(directory: Path, name: str, body: str) -> Path:
    path = directory / name
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def _assert_honest_payload(payload: dict) -> None:
    assert payload.get(HANDLE_ASSET)
    assert HANDLE_TWIN not in payload
    assert HANDLE_CIRCUIT not in payload
    assert "qasm3" not in payload
    assert "circuit" not in payload
    summary = payload.get("summary")
    if isinstance(summary, dict):
        assert HANDLE_TWIN not in summary
        assert HANDLE_CIRCUIT not in summary
        assert "qasm3" not in summary
        assert summary.get("source") != "done-on-machine"


def test_no_bin_local_card() -> None:
    port = WiredQChem()
    with isolated_qchem_env():
        result = port.run({"scenario": "minimal_vqe"})
        invoked = invoke("qchem_run", "lab", {"scenario": "minimal_vqe"})
    _assert_honest_payload(result)
    assert result["summary"]["source"] == "qagent-local-card"
    assert invoked.status == "ok"
    assert invoked.payload is not None
    _assert_honest_payload(invoked.payload)
    assert invoked.payload["summary"]["source"] == "qagent-local-card"


def test_missing_bin_not_qchem_cli() -> None:
    port = WiredQChem()
    with isolated_qchem_env(QAGENT_QCHEM_BIN=_DEAD_BIN):
        try:
            result = port.run({"scenario": "minimal_vqe"})
        except RuntimeError as exc:
            assert "qchem CLI" in str(exc)
        else:
            raise AssertionError(f"expected RuntimeError, got {result!r}")
        invoked = invoke("qchem_run", "lab", {"scenario": "minimal_vqe"})
    assert invoked.status == "error"
    payload = dict(invoked.payload or {})
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    assert summary.get("source") != "qchem-cli"


def test_home_missing_bin_not_qchem_cli() -> None:
    port = WiredQChem()
    with tempfile.TemporaryDirectory() as raw:
        home = Path(raw)
        with isolated_qchem_env(QAGENT_QCHEM_HOME=str(home)):
            try:
                result = port.run({"scenario": "minimal_vqe"})
            except RuntimeError as exc:
                assert "not present" in str(exc)
            else:
                raise AssertionError(f"expected RuntimeError, got {result!r}")
            invoked = invoke("qchem_run", "lab", {"scenario": "minimal_vqe"})
    assert invoked.status == "error"
    summary = (invoked.payload or {}).get("summary") if isinstance((invoked.payload or {}).get("summary"), dict) else {}
    assert summary.get("source") != "qchem-cli"


def test_failing_bin_not_qchem_cli() -> None:
    port = WiredQChem()
    with tempfile.TemporaryDirectory() as raw:
        exe = _write_exe(Path(raw), "qchem-run", _FAIL_CLI)
        with isolated_qchem_env(QAGENT_QCHEM_BIN=str(exe)):
            try:
                result = port.run({"scenario": "minimal_vqe"})
            except RuntimeError:
                pass
            else:
                raise AssertionError(f"expected RuntimeError, got {result!r}")
            invoked = invoke("qchem_run", "lab", {"scenario": "minimal_vqe"})
    assert invoked.status == "error"
    summary = (invoked.payload or {}).get("summary") if isinstance((invoked.payload or {}).get("summary"), dict) else {}
    assert summary.get("source") != "qchem-cli"


def test_payload_has_asset_id_no_twin() -> None:
    port = WiredQChem()
    with isolated_qchem_env():
        result = port.run({"scenario": "minimal_vqe"})
        invoked = invoke("qchem_run", "lab", {"scenario": "minimal_vqe"})
    assert result[HANDLE_ASSET]
    assert HANDLE_TWIN not in result
    assert invoked.payload is not None
    assert invoked.payload[HANDLE_ASSET]
    assert HANDLE_TWIN not in invoked.payload


def test_live_cli_asset_id_no_circuit_handle() -> None:
    port = WiredQChem()
    with tempfile.TemporaryDirectory() as raw:
        exe = _write_exe(Path(raw), "qchem-run", _FAKE_CLI)
        with isolated_qchem_env(QAGENT_QCHEM_BIN=str(exe)):
            result = port.run({"scenario": "minimal_vqe"})
            invoked = invoke("qchem_run", "lab", {"scenario": "minimal_vqe"})
    _assert_honest_payload(result)
    assert result[HANDLE_ASSET]
    assert result["summary"]["source"] == "qchem-cli"
    assert invoked.status == "ok"
    assert invoked.payload is not None
    _assert_honest_payload(invoked.payload)
    assert invoked.payload["summary"]["source"] == "qchem-cli"


def test_export_parity_requires_asset_id() -> None:
    port = WiredQChem()
    with isolated_qchem_env():
        try:
            result = port.export_parity({})
        except ValueError as exc:
            assert "asset_id" in str(exc)
        else:
            raise AssertionError(f"expected ValueError, got {result!r}")
        table = port.export_parity({"asset_id": "asset_local"})
        invoked = invoke("qchem_export_parity", "lab", {})
    assert table.get("table_id")
    assert invoked.status == "error"


def test_adapter_does_not_import_qchem() -> None:
    text = (ROOT / "src/qagent/adapters/qchem.py").read_text(encoding="utf-8")
    hits = [row for row in scan_forbidden_imports() if "adapters/qchem.py" in row]
    assert hits == []
    assert "import qchem" not in text
    assert "from qchem " not in text
    assert "from qchem." not in text


def main() -> int:
    failed = 0
    for name, fn in (
        ("no_bin_local_card", test_no_bin_local_card),
        ("missing_bin_not_qchem_cli", test_missing_bin_not_qchem_cli),
        ("home_missing_bin_not_qchem_cli", test_home_missing_bin_not_qchem_cli),
        ("failing_bin_not_qchem_cli", test_failing_bin_not_qchem_cli),
        ("payload_asset_no_twin", test_payload_has_asset_id_no_twin),
        ("live_cli_no_circuit_handle", test_live_cli_asset_id_no_circuit_handle),
        ("export_parity_requires_asset_id", test_export_parity_requires_asset_id),
        ("no_import_qchem", test_adapter_does_not_import_qchem),
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
