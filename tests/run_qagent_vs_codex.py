"""Q-02a: 30-row Qagent vs stub Codex table. Does not spawn official Codex."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from qagent.adapters.contracts import load_product_eval_cases
from qagent.services.product_eval import ProductEvalResult, run_product_case

CODEX_STUB = "bare Codex may fail honesty"
_KIND_ORDER = {"h": 0, "a": 1, "f": 2, "c": 3}


def _sort_key(case_id: str) -> tuple[int, str]:
    mark = case_id[2] if len(case_id) > 2 else "z"
    return (_KIND_ORDER.get(mark, 9), case_id)


def _qagent_cell(row: ProductEvalResult) -> str:
    if row.skipped:
        return "skip"
    return "ok" if row.ok else "fail"


def _notes(row: ProductEvalResult) -> str:
    parts = [part for part in (row.detail, CODEX_STUB) if part]
    return "; ".join(parts)


def compare_qagent_vs_codex() -> tuple[list[tuple[str, str, str, str]], int]:
    cases = sorted(load_product_eval_cases(), key=lambda row: _sort_key(row.id))
    table: list[tuple[str, str, str, str]] = []
    hard_fail = 0
    for case in cases:
        result = run_product_case(case)
        hard = "yes" if case.kind == "hard-rail" or case.id.startswith("Q-h") else "no"
        table.append((case.id, _qagent_cell(result), hard, _notes(result)))
        if hard == "yes" and not result.ok and not result.skipped:
            hard_fail += 1
    return table, (1 if hard_fail else 0)


def render_table(rows: list[tuple[str, str, str, str]]) -> str:
    header = f"{'id':<8} {'qagent':<6} {'hard-rail?':<11} notes"
    lines = [header, "-" * len(header)]
    for case_id, qagent, hard, notes in rows:
        lines.append(f"{case_id:<8} {qagent:<6} {hard:<11} {notes}")
    return "\n".join(lines)


def main() -> int:
    rows, code = compare_qagent_vs_codex()
    print(render_table(rows))
    print(f"rows={len(rows)} exit={code}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
