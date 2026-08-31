"""A-04g: live interop compile_estimate. Skip-as-green is incomplete."""

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

from qagent.adapters.homes import ionstack_python
from qagent.adapters.route import mapqccd_estimate
from qagent.adapters.wrap import call_interop
from qagent.models.handles import HANDLE_TWIN
from qagent.services.eval_run import DEFAULT_CIRCUIT
from qagent.services.invoke import invoke

_LIVE_HOME = "/Users/shl/Q-software"
_TOOL = "ionstack_compile_estimate"
_NOTE = ROOT / "docs" / "execution" / "A-04g_live_estimate.md"
_STORE = ROOT / ".qagent" / "test-a04g-store"
_COPIED_LIVE = 3040.0
_COPIED_FORMULA = 4800.0
_SIGNED_LOOKING = frozenset({"ok", HANDLE_TWIN, "signoff", "signed", "signature"})
_ENV_KEYS = (
    "QAGENT_IONSTACK_HOME",
    "QAGENT_IONSTACK_PYTHON",
    "QAGENT_ROUTE_BACKEND",
    "QAGENT_DATA_DIR",
    "QAGENT_ELN_FILE",
)


@contextmanager
def live_estimate_env() -> Iterator[None]:
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


def _no_signoff(payload: Mapping[str, Any]) -> None:
    keys = _keys(payload)
    blob = json.dumps(payload, ensure_ascii=False)
    leaked = _SIGNED_LOOKING & keys
    assert not leaked, leaked
    assert "ok" not in payload
    assert HANDLE_TWIN not in payload
    assert HANDLE_TWIN not in blob
    summary = payload.get("summary")
    if isinstance(summary, dict):
        leaked_summary = _SIGNED_LOOKING & set(summary)
        assert not leaked_summary, leaked_summary


def test_live_invoke_estimate_not_formula() -> None:
    home = Path(_LIVE_HOME)
    exe = home / ".venv" / "bin" / "python"
    assert home.is_dir(), f"live QAGENT_IONSTACK_HOME missing: {home}"
    assert exe.is_file(), f"live ionstack python missing: {exe}"
    args = {"circuit": DEFAULT_CIRCUIT}
    formula = mapqccd_estimate(args)
    formula_ns = float(formula["makespan_ns"])
    with live_estimate_env():
        assert os.environ.get("QAGENT_IONSTACK_HOME") == _LIVE_HOME
        assert os.environ.get("QAGENT_DATA_DIR") == str(_STORE)
        assert not os.environ.get("QAGENT_ROUTE_BACKEND")
        assert os.environ.get("QAGENT_ROUTE_BACKEND") != "route-alt"
        assert ionstack_python() == str(exe)
        wrapped = call_interop("estimate", {"circuit": DEFAULT_CIRCUIT})
        invoked = invoke(_TOOL, "lab", args)
    assert wrapped is not None, "call_interop(estimate) failed — A-04g is not done"
    assert "makespan_ns" in wrapped, f"interop payload missing makespan_ns: {wrapped}"
    assert "ok" not in wrapped, f"interop leaked ok: {wrapped}"
    assert invoked.status == "ok", f"expected ok, got {invoked.status}: {invoked.error}"
    payload = dict(invoked.payload or {})
    assert payload, "compile_estimate invoke returned empty payload"
    assert "makespan_ns" in payload
    assert isinstance(payload["makespan_ns"], (int, float))
    _no_signoff(payload)
    live_ns = float(payload["makespan_ns"])
    assert live_ns == float(wrapped["makespan_ns"]), (
        f"invoke {live_ns} != interop {wrapped.get('makespan_ns')!r}"
    )
    assert live_ns != formula_ns, (
        f"live makespan_ns={live_ns} equals formula {formula_ns}; "
        "formula fallback as green = not done"
    )
    print(
        f"live makespan_ns={live_ns} formula={formula_ns} "
        f"interop={wrapped} invoke={payload}"
    )


def test_note_copies_hit() -> None:
    assert _NOTE.is_file(), f"missing {_NOTE}"
    text = _NOTE.read_text(encoding="utf-8")
    compact = "".join(text.split())
    assert str(int(_COPIED_LIVE)) in text
    assert str(int(_COPIED_FORMULA)) in text
    assert "1200" in text
    assert "makespan_ns" in text
    assert "invoke" in text
    assert "ionstack_compile_estimate" in text
    assert "DEFAULT_CIRCUIT" in text
    assert "mapqccd_estimate" in text
    assert "QAGENT_IONSTACK_HOME" in text
    assert _LIVE_HOME in text
    assert "call_interop" in text
    assert "estimate" in text
    assert "不算 G0" in text or "不算G0" in compact
    assert "G0 已通过" not in text
    assert "G0已通过" not in compact
    assert "skip 当绿" in text or "skip当绿" in compact
    assert "未 commit" in text or "未commit" in compact
    assert "apply_env" in text
    assert "workplace.json" in text
    assert "route-alt" in text
    assert "twin_id" in text
    assert any(token in text for token in ("无 twin_id", "没有 twin_id", "无 `twin_id`"))
    assert "ok" in text


def test_this_file_does_not_skip() -> None:
    text = Path(__file__).read_text(encoding="utf-8")
    assert ("pytest" + ".skip") not in text
    assert ("unittest" + ".skip") not in text
    assert ("skip" + "Test") not in text
    assert ("from qagent.services." + "workplace") not in text
    assert ("apply" + "_env(") not in text
    assert ("QAGENT_ROUTE_BACKEND=" + '"route-alt"') not in text
    assert ("QAGENT_ROUTE_BACKEND=" + "'route-alt'") not in text


def main() -> int:
    if _STORE.exists():
        shutil.rmtree(_STORE)
    failed = 0
    for name, fn in (
        ("live_invoke_estimate_not_formula", test_live_invoke_estimate_not_formula),
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
