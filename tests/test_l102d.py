"""L1-02d: E13 honesty. Oneshot without app-server is not tests_green."""

from __future__ import annotations

import json
import traceback
from pathlib import Path

from qagent.adapters.codex import WiredCodex
from qagent.adapters.contracts import ROOT
from qagent.services.eval_run import run_evals

_HANDLE = "twin" + "_id"
_TOOL = "ionstack_" + "twin" + "_run"
_E13 = ROOT / "contracts" / "eval" / "E13.json"
_NOTE = ROOT / "docs" / "execution" / "L1-02d_e13_honest.md"


def _payload_blob(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True)


def test_oneshot_honest_not_green() -> None:
    out = WiredCodex().oneshot({"task": "add a test ProblemProvider"})
    blob = _payload_blob(out)
    assert out.get("needs_app_server") is True
    assert out.get("tests_green") is False
    assert out.get("not_wired") is True
    assert _HANDLE not in blob
    assert _TOOL not in blob
    assert "TwinRun" not in blob


def test_e13_eval_ok() -> None:
    rows = {row.id: row for row in run_evals("E13")}
    assert rows["E13"].ok, rows["E13"].detail


def test_e17_eval_still_ok() -> None:
    rows = {row.id: row for row in run_evals("E17")}
    assert rows["E17"].ok, rows["E17"].detail


def test_e13_contract_text() -> None:
    text = _E13.read_text(encoding="utf-8")
    raw = json.loads(text)
    assert "needs_app_server" in text
    assert any(item.get("needs_app_server") is True for item in raw["assertions"])
    assert not any(item.get("tests_green") is True for item in raw["assertions"])
    assert '"tests_green": true' not in text
    assert '"tests_green":true' not in text.replace(" ", "")


def test_note_exists() -> None:
    assert _NOTE.exists()
    text = _NOTE.read_text(encoding="utf-8")
    assert "needs_app_server" in text
    assert "tests_green" in text


def main() -> int:
    failed = 0
    for name, fn in (
        ("oneshot_honest", test_oneshot_honest_not_green),
        ("e13_eval", test_e13_eval_ok),
        ("e17_eval", test_e17_eval_still_ok),
        ("e13_contract", test_e13_contract_text),
        ("note", test_note_exists),
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
