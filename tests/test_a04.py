"""A-04 route contract. Isolates QAGENT_ROUTE_BACKEND. No pytest required."""

from __future__ import annotations

import os
import sys
import traceback
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Mapping

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from qagent.adapters.route import WiredRoute, alt_estimate, mapqccd_estimate
from qagent.models.handles import HANDLE_TWIN
from qagent.services.boundaries import scan_forbidden_imports
from qagent.services.eval_run import DEFAULT_CIRCUIT, run_evals
from qagent.services.invoke import invoke

_TOOL = "ionstack_compile_estimate"
_ENV_KEYS = ("QAGENT_ROUTE_BACKEND",)
_SIGNED_LOOKING = frozenset({"ok", HANDLE_TWIN, "signoff", "signed", "signature"})
_CIRCUIT_ARGS = {"circuit": DEFAULT_CIRCUIT}


@contextmanager
def isolated_route_env(**overrides: str) -> Iterator[None]:
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


def _assert_estimate_contract(payload: Mapping[str, Any]) -> None:
    assert "makespan_ns" in payload
    assert isinstance(payload["makespan_ns"], (int, float))
    leaked = _SIGNED_LOOKING & set(payload)
    assert not leaked, leaked
    summary = payload.get("summary")
    if isinstance(summary, dict):
        leaked_summary = _SIGNED_LOOKING & set(summary)
        assert not leaked_summary, leaked_summary


def test_mapqccd_estimate_contract() -> None:
    payload = mapqccd_estimate(_CIRCUIT_ARGS)
    _assert_estimate_contract(payload)
    assert "ok" not in payload
    assert payload["summary"]["backend"] == "mapqccd"


def test_alt_estimate_contract() -> None:
    payload = alt_estimate(_CIRCUIT_ARGS)
    _assert_estimate_contract(payload)
    assert "ok" not in payload
    assert payload["summary"]["backend"] == "route-alt"


def test_invoke_backend_switch_keeps_tool_name() -> None:
    with isolated_route_env():
        default = invoke(_TOOL, "lab", _CIRCUIT_ARGS)
    with isolated_route_env(QAGENT_ROUTE_BACKEND="route-alt"):
        switched = invoke(_TOOL, "lab", _CIRCUIT_ARGS)
    assert default.tool == _TOOL
    assert switched.tool == _TOOL
    assert default.status == "ok"
    assert switched.status == "ok"
    assert default.payload is not None
    assert switched.payload is not None
    _assert_estimate_contract(default.payload)
    _assert_estimate_contract(switched.payload)
    assert "ok" not in default.payload
    assert "ok" not in switched.payload
    assert HANDLE_TWIN not in default.payload
    assert HANDLE_TWIN not in switched.payload
    assert default.payload["summary"]["backend"] == "mapqccd"
    assert switched.payload["summary"]["backend"] == "route-alt"
    assert default.payload["makespan_ns"] != switched.payload["makespan_ns"]


def test_wired_route_follows_env() -> None:
    port = WiredRoute()
    with isolated_route_env():
        default = port.compile_estimate(_CIRCUIT_ARGS)
    with isolated_route_env(QAGENT_ROUTE_BACKEND="route-alt"):
        switched = port.compile_estimate(_CIRCUIT_ARGS)
    _assert_estimate_contract(default)
    _assert_estimate_contract(switched)
    assert default["summary"]["backend"] == "mapqccd"
    assert switched["summary"]["backend"] == "route-alt"


def test_e12_e14() -> None:
    with isolated_route_env():
        results = {row.id: row for row in run_evals("E12", "E14")}
    assert results["E12"].ok, results["E12"].detail
    assert results["E14"].ok, results["E14"].detail


def test_adapter_does_not_import_science() -> None:
    text = (ROOT / "src/qagent/adapters/route.py").read_text(encoding="utf-8")
    hits = [row for row in scan_forbidden_imports() if "adapters/route.py" in row]
    assert hits == []
    assert "import ionstack" not in text
    assert "import qdata" not in text
    assert "import qchem" not in text
    assert "import qiskit" not in text


def main() -> int:
    failed = 0
    for name, fn in (
        ("mapqccd_estimate", test_mapqccd_estimate_contract),
        ("alt_estimate", test_alt_estimate_contract),
        ("invoke_backend_switch", test_invoke_backend_switch_keeps_tool_name),
        ("wired_route_env", test_wired_route_follows_env),
        ("e12_e14", test_e12_e14),
        ("no_science_import", test_adapter_does_not_import_science),
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
