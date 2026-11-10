from __future__ import annotations

from pathlib import Path

import pytest

from company_agent.experiment_card import CardError, cells_to_args, compile_cells
from company_agent.invoke import invoke


@pytest.fixture
def isolated(monkeypatch, tmp_path):
    monkeypatch.setenv("COMPANY_AGENT_RESEARCH_STATE", str(tmp_path / "clock"))
    monkeypatch.setenv("COMPANY_AGENT_WORK_ITEM_DB", str(tmp_path / "work.sqlite3"))
    return tmp_path

_ROWS = [
    ("tenant_id", "team-a"),
    ("experiment_id", "exp-1"),
    ("task_id", "task-1"),
    ("hypothesis", "warmup lowers validation loss"),
    ("falsifier", "the metric does not improve"),
    ("baseline_name", "plain"),
    ("baseline_source", "internal"),
    ("baseline_metric", "1.0"),
    ("baseline_reproduced", "true"),
    ("changed_path", "src/train/scheduler.py"),
    ("primary_metric", "val_loss"),
    ("direction", "minimize"),
    ("resource_type", "cpu"),
    ("max_cost", "5"),
    ("max_attempts", "1"),
]


def _cells(**overrides: str) -> list[dict[str, str]]:
    values = dict(_ROWS)
    values.update(overrides)
    return [{"field": field, "value": value} for field, value in values.items()]


def test_cells_compile_without_opening_a_workbook(isolated) -> None:
    args = cells_to_args(_cells())
    assert args["baseline_reproduced"] is True
    assert args["baseline_metric"] == 1.0
    assert args["max_attempts"] == 1
    result = invoke("company_research_compile", "lab", args)
    assert result.status == "ok"
    assert result.payload["ok"] is True
    assert result.payload["error_code"] == ""
    direct = compile_cells(_cells())
    assert direct["ok"] is True
    assert not (isolated / "clock" / "records.json").exists()


def test_unreproduced_cells_do_not_start_a_run(isolated) -> None:
    result = compile_cells(_cells(baseline_reproduced="否"))
    assert result["ok"] is False
    assert result["error_code"] == "E_BASELINE_NOT_REPRODUCED"
    assert not (isolated / "clock" / "records.json").exists()


def test_an_xlsx_path_is_refused_before_compile(monkeypatch) -> None:
    def fail(_args):
        raise AssertionError("compile was called")

    monkeypatch.setattr("company_agent.experiment_card.compile_spec", fail)
    with pytest.raises(CardError, match="does not open xlsx"):
        compile_cells(_cells(baseline_source="card.xlsx"))


def test_research_plugin_does_not_open_xlsx() -> None:
    root = Path(__file__).resolve().parents[1]
    plugin = (root / "packages" / "company-agent-research" / "src" / "index.js").read_text(encoding="utf-8")
    clock = (root / "src" / "company_agent" / "research_clock.py").read_text(encoding="utf-8")
    assert "xlsx" not in plugin.casefold()
    assert "xlsx" not in clock.casefold()
    assert "openpyxl" not in clock
