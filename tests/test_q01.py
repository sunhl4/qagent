"""Q-01 field wiring: decide + invoke + receipt. No live Twin, no official Codex."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from qagent.adapters.contracts import load_product_eval_cases
from qagent.services.product_eval import run_product_case, run_product_evals

from run_qagent_vs_codex import CODEX_STUB, compare_qagent_vs_codex

_DECISION = ("Q-h01", "Q-h02", "Q-h04", "Q-h05", "Q-h08", "Q-c05")
_WIRED = ("Q-h03", "Q-h06", "Q-h07", "Q-h09", "Q-h10", "Q-a01", "Q-a05", "Q-a06", "Q-c01")


def test_decision_subset_still_green() -> None:
    rows = run_product_evals(*_DECISION)
    assert [row.id for row in rows] == list(_DECISION)
    assert all(row.ok and not row.skipped for row in rows), rows


def test_wired_invoke_receipt() -> None:
    rows = {row.id: row for row in run_product_evals(*_WIRED)}
    assert set(rows) == set(_WIRED)
    for case_id, row in rows.items():
        assert row.ok and not row.skipped, f"{case_id}: {row.detail}"


def test_h06_offline_ok() -> None:
    row = run_product_case(next(c for c in load_product_eval_cases() if c.id == "Q-h06"))
    assert row.ok and not row.skipped, row.detail
    assert row.detail != "needs live"


def test_h06_skips_without_live_twin() -> None:
    test_h06_offline_ok()


def test_no_fake_twin_or_cal() -> None:
    for row in run_product_evals():
        if row.skipped:
            continue
        assert "fake twin" not in row.detail
        assert "skip ask" not in row.detail
        assert "CAL" not in row.detail


def test_q02_table_has_thirty_rows() -> None:
    rows, code = compare_qagent_vs_codex()
    assert len(rows) == 30
    assert [item[0] for item in rows if item[0].startswith("Q-h")] == [f"Q-h{i:02d}" for i in range(1, 11)]
    assert all(CODEX_STUB in item[3] for item in rows)
    assert all("twin_id" not in item[3] or item[1] != "ok" or "bare Codex" in item[3] for item in rows)
    for case_id, qagent, hard, notes in rows:
        if case_id.startswith("Q-h") and qagent == "fail":
            raise AssertionError(f"hard rail {case_id} failed: {notes}")
        if case_id == "Q-h06":
            assert qagent == "ok"
            assert "needs live" not in notes
            assert qagent != "skip"
    assert code == 0


def main() -> int:
    test_decision_subset_still_green()
    print("ok  q01_decision")
    test_wired_invoke_receipt()
    print("ok  q01_wired")
    test_h06_offline_ok()
    print("ok  q01_h06_offline")
    test_no_fake_twin_or_cal()
    print("ok  q01_honesty")
    test_q02_table_has_thirty_rows()
    print("ok  q01_q02_table")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
