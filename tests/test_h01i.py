"""H-01i: product dsh does not register sandbox. Skip-as-green is incomplete."""

from __future__ import annotations

import re
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from qagent.adapters.contracts import load_eval_cases
from qagent.models.handles import HANDLE_ASSET, HANDLE_CIRCUIT, HANDLE_TWIN
from qagent.services.eval_run import run_eval
from qagent.services.invoke import invoke
from qagent.services.policy import decide

NOTE = ROOT / "docs" / "execution" / "H-01i_no_dsh_sandbox.md"
INDEX = ROOT / "packages" / "qagent-qdata" / "src" / "index.ts"
ASSIGNMENT = ROOT / "src" / "qagent" / "services" / "assignment.py"
_HANDLES = frozenset({HANDLE_CIRCUIT, HANDLE_ASSET, HANDLE_TWIN})
_KNOWN = _HANDLES | {"run_record_id", "job_id", "rpc_id", "approval_id"}
_ID_RE = re.compile(r"\b[a-z]+_id\b")


def _text(path: Path) -> str:
    assert path.is_file(), f"missing {path}"
    return path.read_text(encoding="utf-8")


def test_note() -> None:
    text = _text(NOTE)
    assert "H-01i" in text
    assert "qdata_sandbox_exec" in text
    assert "invoke" in text
    assert "E11" in text
    assert "twin_id" in text
    assert "accepted:true" in text
    print("note names dsh unregister, E11 invoke stays")


def test_qdata_plugin_does_not_register_sandbox() -> None:
    text = _text(INDEX)
    assert "H-01i" in text
    assert "registerInvokeTool" in text
    assert "qdata_run_recipe" in text
    assert 'registerInvokeTool(ctx, "qdata_sandbox_exec"' not in text
    assert '"qdata_sandbox_exec"' not in text
    assert '"run_record_id"' in text
    assert '"job_id"' in text
    print("dsh plugin does not register sandbox")


def test_e11_invoke_still_blocks_southbound() -> None:
    assert decide("qdata_sandbox_exec", "lab", {"code": "print(1)"}) == "allow"
    blocked = invoke(
        "qdata_sandbox_exec",
        "lab",
        {"code": "from ionstack.api.twin_run import execute_twin_run\nexecute_twin_run()"},
    )
    assert blocked.status == "ok"
    assert blocked.payload.get("ok") is False
    assert blocked.payload.get("rest_called") is False
    e11 = next(case for case in load_eval_cases() if case.id == "E11")
    assert e11.preset == "lab"
    row = run_eval(e11)
    assert row.ok is True, row.detail
    print("E11 invoke still blocks southbound")


def test_no_fourth_handle_or_extra_pipeline() -> None:
    for path in (INDEX, NOTE):
        for match in _ID_RE.findall(_text(path)):
            assert match in _KNOWN, (path.name, match)
    assert _text(ASSIGNMENT).count('"mode": "pipeline"') == 3
    print("still three handles; pipeline count frozen")


def main() -> int:
    failed = 0
    for name, fn in (
        ("note", test_note),
        ("qdata_plugin_does_not_register_sandbox", test_qdata_plugin_does_not_register_sandbox),
        ("e11_invoke_still_blocks_southbound", test_e11_invoke_still_blocks_southbound),
        ("no_fourth_handle_or_extra_pipeline", test_no_fourth_handle_or_extra_pipeline),
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
