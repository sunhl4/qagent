"""Architecture gates for the managed analysis templates (survey P1 3.1)."""

from __future__ import annotations

import pytest

from company_agent.analysis import render
from company_agent.catalog import load_presets, load_templates, load_tools
from company_agent.invoke import invoke


@pytest.fixture(autouse=True)
def receipt_store(tmp_path, monkeypatch) -> None:
    store = tmp_path / "receipts"
    store.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("COMPANY_AGENT_RECEIPT_DIR", str(store))


def _metrics(items: list[dict]) -> dict:
    return {"schema_version": "scientific-metrics/1.0", "items": items}


def test_templates_contract_covers_four_managed_templates() -> None:
    templates = load_templates()
    assert set(templates) == {
        "metric-summary", "shots-audit", "metric-quantiles", "shots-chart",
    }
    for template in templates.values():
        assert template["error_behavior"] == {"structural": "fail_closed", "domain": "flagged"}
        assert set(template["sources"]) <= set(load_tools())


def test_analysis_tool_visible_in_every_preset() -> None:
    presets = load_presets()["presets"]
    assert all("company_analysis_render" in row["visible_tools"] for row in presets.values())


def test_metric_summary_complete_with_charts_grouped_by_unit() -> None:
    payload = render({
        "template": "metric-summary",
        "metrics": _metrics([
            {"name": "fidelity", "kind": "probability", "value": 0.9712, "unit": "dimensionless"},
            {"name": "purity", "kind": "uncertainty", "value": 0.002, "unit": "dimensionless"},
            {"name": "circuits", "kind": "count", "value": 12, "unit": "count"},
            {"name": "samples", "kind": "count", "value": 1024, "unit": "count"},
        ]),
    })
    assert payload["status"] == "complete" and payload["audit"]["complete"] is True
    assert payload["audit"]["items"] == 4
    assert payload["audit"]["reasons"] == []
    assert payload["audit"]["units"] == ["dimensionless", "count"]
    assert payload["audit"]["min_value"] == 0.002 and payload["audit"]["max_value"] == 1024
    assert [chart["unit"] for chart in payload["charts"]] == ["count", "dimensionless"]
    assert all(chart["kind"] == "bar" and chart["items"] for chart in payload["charts"])


def test_domain_violations_flag_without_failing() -> None:
    payload = render({
        "template": "metric-summary",
        "metrics": _metrics([
            {"name": "p", "kind": "probability", "value": 1.4, "unit": "dimensionless"},
            {"name": "c", "kind": "state", "value": -3, "unit": "count"},
            {"name": "u", "kind": "uncertainty", "value": -0.01, "unit": "dimensionless"},
        ]),
    })
    assert payload["status"] == "flagged"
    assert payload["audit"]["complete"] is False
    assert set(payload["audit"]["reasons"]) == {"range_violation", "invalid_unit"}
    # A flagged table must not be drawn: no chart can render misleading numbers.
    assert payload["charts"] == []


def test_duplicate_names_flag() -> None:
    payload = render({
        "template": "metric-summary",
        "metrics": _metrics([
            {"name": "keep", "kind": "count", "value": 1, "unit": "count"},
            {"name": "keep", "kind": "count", "value": 2, "unit": "count"},
        ]),
    })
    assert payload["audit"]["reasons"] == ["duplicate_name"]
    assert payload["charts"] == []


def test_empty_table_flags_empty_without_failure() -> None:
    payload = render({"template": "metric-summary", "metrics": _metrics([])})
    assert payload["status"] == "flagged" and payload["audit"]["reasons"] == ["empty"]
    assert payload["audit"]["complete"] is False and payload["charts"] == []


def test_shot_delivery_audit_flags_under_and_overdelivery() -> None:
    under = render({"template": "shots-audit", "shots": {"requested": 1000, "actual": 940}})
    assert under["status"] == "flagged" and under["audit"]["reasons"] == ["underdelivery"]
    over = render({"template": "shots-audit", "shots": {"requested": 100, "actual": 120}})
    assert over["audit"]["reasons"] == ["overdelivery"]
    exact = render({"template": "shots-audit", "shots": {"requested": 8, "actual": 8}})
    assert exact["status"] == "complete" and exact["charts"] == []


def test_unknown_template_fails_closed() -> None:
    with pytest.raises(ValueError, match="unknown analysis template"):
        render({"template": "unknown-benchmark-template", "metrics": _metrics([])})


def test_malformed_shots_record_fails_closed() -> None:
    with pytest.raises(ValueError, match="shots delivery record"):
        render({"template": "shots-audit", "shots": {"requested": 0, "actual": 1}})
    with pytest.raises(ValueError, match="requires a shots delivery record"):
        render({"template": "shots-audit"})


def test_wrong_schema_version_fails_closed() -> None:
    with pytest.raises(ValueError, match="schema version"):
        render({"template": "metric-summary",
                "metrics": {"schema_version": "scientific-metrics/9.9", "items": []}})


def test_preset_sign_flow_and_deny_boundary() -> None:
    ok = invoke("company_analysis_render", "sign", {
        "template": "metric-summary",
        "metrics": _metrics([
            {"name": "shots_kept", "kind": "probability", "value": 0.5, "unit": "dimensionless"}
        ]),
    })
    assert ok.status == "ok" and ok.payload["template"] == "metric-summary"
    # metrics are the required input for the metrics-table template
    with pytest.raises(ValueError, match="metrics table"):
        render({"template": "metric-summary"})


def test_outputs_never_carry_script_or_path_shaped_content() -> None:
    payload = render({
        "template": "metric-summary",
        "metrics": _metrics([{"name": "ack", "kind": "count", "value": 1, "unit": "count"}]),
    })
    raw = str(payload)
    for marker in ("http://", "https://", "<script", "qasm", "bitstring", "/home/"):
        assert marker not in raw.casefold()


def test_metric_quantiles_order_statistics_are_exact() -> None:
    values = [0.41, 0.52, 0.30, 0.99, 0.71, 0.66, 0.18, 0.83, 0.57, 0.61]
    payload = render({
        "template": "metric-quantiles",
        "metrics": _metrics([
            {"name": f"run{i:02d}", "kind": "probability", "value": value, "unit": "dimensionless"}
            for i, value in enumerate(values)
        ]),
    })
    assert payload["status"] == "complete" and payload["audit"]["reasons"] == []
    assert payload["audit"]["items"] == 10
    assert payload["audit"]["units"] == ["dimensionless"]
    assert payload["audit"]["min_value"] == 0.18 and payload["audit"]["max_value"] == 0.99
    ordered = sorted(values)
    chart = payload["charts"][0]
    assert chart["kind"] == "bar" and chart["unit"] == "dimensionless"
    assert [(row["name"], row["value"]) for row in chart["items"]] == [
        ("min", 0.18),
        ("q25", ordered[2]),   # floor(0.25 * 9) = 2
        ("median", ordered[4]),
        ("q75", ordered[6]),   # floor(0.75 * 9) = 6
        ("max", 0.99),
    ]


def test_metric_quantiles_single_value_and_empty() -> None:
    single = render({"template": "metric-quantiles", "metrics": _metrics([
        {"name": "one", "kind": "count", "value": 7, "unit": "count"},
    ])})
    assert single["status"] == "complete"
    assert [(row["name"], row["value"]) for row in single["charts"][0]["items"]] == [
        ("min", 7), ("q25", 7), ("median", 7), ("q75", 7), ("max", 7),
    ]
    empty = render({"template": "metric-quantiles", "metrics": _metrics([])})
    assert empty["status"] == "flagged" and empty["charts"] == []
    assert empty["audit"]["reasons"] == ["empty"]


def test_metric_quantiles_flags_draw_nothing_and_budget_clamps() -> None:
    flagged = render({"template": "metric-quantiles", "metrics": _metrics([
        {"name": "a", "kind": "probability", "value": 2.0, "unit": "dimensionless"},
        {"name": "b", "kind": "count", "value": 1, "unit": "count"},
    ])})
    assert flagged["status"] == "flagged" and flagged["charts"] == []
    assert "range_violation" in flagged["audit"]["reasons"]
    table = _metrics([
        {"name": f"m{i:02d}", "kind": "state", "value": i, "unit": f"unit{i:02d}"}
        for i in range(12)
    ])
    payload = render({"template": "metric-quantiles", "metrics": table})
    assert payload["status"] == "flagged"
    assert payload["charts"] == []
    assert "chart_budget" in payload["audit"]["reasons"]


def test_metric_quantiles_reuses_standard_fail_closes() -> None:
    with pytest.raises(ValueError, match="metrics table"):
        render({"template": "metric-quantiles"})
    with pytest.raises(ValueError, match="schema version"):
        render({"template": "metric-quantiles", "metrics": {"schema_version": "x/9", "items": []}})
    with pytest.raises(ValueError, match="finite number"):
        render({"template": "metric-quantiles", "metrics": _metrics([
            {"name": "one", "kind": "count", "value": "bad", "unit": "count"},
        ])})


def test_shots_chart_draws_the_gap_even_when_flagged() -> None:
    under = render({"template": "shots-chart", "shots": {"requested": 1000, "actual": 640}})
    assert under["status"] == "flagged" and under["audit"]["reasons"] == ["underdelivery"]
    assert under["charts"] == [{
        "kind": "bar",
        "unit": "count",
        "items": [{"name": "requested", "value": 1000}, {"name": "actual", "value": 640}],
    }]
    over = render({"template": "shots-chart", "shots": {"requested": 100, "actual": 120}})
    assert over["audit"]["reasons"] == ["overdelivery"]
    assert over["charts"][0]["items"][1] == {"name": "actual", "value": 120}
    exact = render({"template": "shots-chart", "shots": {"requested": 8, "actual": 8}})
    assert exact["status"] == "complete"
    assert {"name": "requested", "value": 8} in exact["charts"][0]["items"]


def test_shots_chart_structural_failures_fail_closed() -> None:
    for args in (
        {},
        {"shots": {"requested": 0, "actual": 1}},
        {"shots": {"requested": 10, "actual": -1}},
        {"shots": {"requested": 1.5, "actual": 1}},
    ):
        with pytest.raises(ValueError, match="shots delivery record"):
            render({"template": "shots-chart", **args})
