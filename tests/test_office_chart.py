"""P3 WPS-suite chart gate: deterministic, bounded, spec-first rendering.

Spec source: ``WPS-SUITE-PORTING`` §4.9 — the same declarative spec always
produces byte-identical SVG and a canonical spec JSON under
``artifacts/charts/<chart_id>.*``, and the reviewer reads the spec, not
pixels. Overshoot is refused, never truncated; pie accepts one series only.
"""
from __future__ import annotations

import json
from pathlib import Path

from company_agent.invoke import invoke

WORKSPACE_ROOT_ENV = "COMPANY_AGENT_TOOL_WORKSPACE"
PROJECT = "charts01"


def _workspace(tmp_path: Path, monkeypatch) -> Path:
    root = tmp_path / "mount"
    (root / PROJECT).mkdir(parents=True)
    monkeypatch.setenv(WORKSPACE_ROOT_ENV, str(root))
    return root / PROJECT


def _chart(spec: dict, **extra):
    args = {"project": PROJECT, "spec": spec, "purpose": "测试写入"}
    args.update(extra)
    return invoke("company_office_chart", "lab", args)


def test_deterministic_pairs_written_and_rerun_protected(
    tmp_path: Path, monkeypatch
) -> None:
    project = _workspace(tmp_path, monkeypatch)
    spec = {
        "title": "单元合格率季度对比",
        "type": "bar",
        "unit": "%",
        "source": "验收记录",
        "categories": ["一季度", "二季度"],
        "series": [{"name": "合格率", "values": [92.5, 97.1]}],
    }
    first = _chart(spec)
    assert first.status == "ok", first.error
    payload = first.payload
    assert len(payload["chart_id"]) == 16
    assert payload["fence"].startswith("```lm-chart\n")
    assert payload["fence"].rstrip().endswith("```")
    (project / "artifacts" / "charts" / f"{payload['chart_id']}.json").is_file()
    svg_file = project / "artifacts" / "charts" / f"{payload['chart_id']}.svg"
    assert svg_file.is_file()
    svg_first = svg_file.read_text(encoding="utf-8")
    assert "<rect" in svg_first and "sans-serif" in svg_first

    second = _chart(spec)
    assert second.status == "error"  # same id refuses without overwrite
    third = _chart(spec, overwrite=True)
    assert third.status == "ok", third.error
    assert third.payload["overwrote"] is True
    assert third.payload["sha256_svg"] == payload["sha256_svg"]
    assert third.payload["bytes_svg"] == payload["bytes_svg"]

    canonical = json.loads(
        (project / "artifacts" / "charts" / f"{payload['chart_id']}.json").read_text(encoding="utf-8")
    )
    assert canonical["type"] == "bar"
    assert canonical["series"][0]["values"] == [92.5, 97.1]


def test_pie_rejects_multi_series_and_nonfinite_refuses(
    tmp_path: Path, monkeypatch
) -> None:
    _workspace(tmp_path, monkeypatch)
    pie = _chart(
        {
            "title": "占比",
            "type": "pie",
            "categories": ["甲", "乙"],
            "series": [{"name": "分享", "values": [3, 1]}, {"name": "分享2", "values": [2, 2]}],
        }
    )
    assert pie.status == "error"
    assert "pie" in (pie.error or "")
    negative = _chart(
        {
            "title": "占比",
            "type": "pie",
            "categories": ["甲", "乙"],
            "series": [{"name": "分享", "values": [-3, 1]}],
        }
    )
    assert negative.status == "error"
    mismatched = _chart(
        {
            "title": "对齐",
            "type": "bar",
            "categories": ["甲", "乙"],
            "series": [{"name": "线", "values": [1.0, 2.0, 3.0]}],
        }
    )
    assert mismatched.status == "error"
    assert "长度不一致" in (mismatched.error or "")
    bad_type = _chart(
        {"title": "x", "type": "scatter", "categories": ["一"], "series": [{"name": "n", "values": [1]}]}
    )
    assert bad_type.status == "error" and bad_type.decision == "deny"


def test_line_and_stacked_render_within_budget(tmp_path: Path, monkeypatch) -> None:
    _workspace(tmp_path, monkeypatch)
    line = _chart(
        {
            "title": "残差走势",
            "type": "line",
            "unit": "idx",
            "categories": ["T1", "T2", "T3"],
            "series": [{"name": "残差", "values": [3, 1, 4]}, {"name": "均值", "values": [2.5, 2.5, 2.5]}],
        }
    )
    assert line.status == "ok", line.error
    stacked = _chart(
        {
            "title": "堆叠",
            "type": "stacked_bar",
            "categories": ["A", "B"],
            "series": [{"name": "s1", "values": [1, 2]}, {"name": "s2", "values": [1, 1]}],
        }
    )
    assert stacked.status == "ok", stacked.error
    assert stacked.payload["bytes_svg"] <= 800_000
