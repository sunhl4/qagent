"""P4.5 WPS-suite matter gate: timeline / chronology / mindmap artifacts.

Spec source: ``WPS-SUITE-PORTING`` §4.15 — fixed files, deterministic
date normalization, upsert merge with the "reviewed anchor never dropped"
rule, empty-payload/pure-repeat refusals, six-layer mindmap truncation with
named issues, and receipts that count anchored versus unanchored items.
"""
from __future__ import annotations

import json
from pathlib import Path

from company_agent.invoke import invoke

WORKSPACE_ROOT_ENV = "COMPANY_AGENT_TOOL_WORKSPACE"
PROJECT = "case01"


def _workspace(tmp_path: Path, monkeypatch) -> Path:
    root = tmp_path / "mount"
    (root / PROJECT).mkdir(parents=True)
    monkeypatch.setenv(WORKSPACE_ROOT_ENV, str(root))
    return root / PROJECT


def _matter(kind: str, data: dict, **extra):
    args = {"project": PROJECT, "kind": kind, "data": data, "purpose": "测试写入"}
    args.update(extra)
    return invoke("company_office_matter", "lab", args)


def _file(project: Path, kind: str) -> Path:
    name = {
        "timeline": "project.company-timeline.json",
        "chronology": "project.company-chronology.json",
        "mindmap": "project.company-mindmap.json",
    }[kind]
    return project / name


def test_timeline_upsert_merges_and_protects_reviewed_anchors(
    tmp_path: Path, monkeypatch
) -> None:
    project = _workspace(tmp_path, monkeypatch)
    anchor = {"path": "证据.md", "line_ref": "L1", "quote": "事件甲"}
    invoke("company_office_create", "lab", {"purpose": "测试写入",
        "project": PROJECT, "path": "证据.md", "content": {"text": "事件甲原文"}})
    first = _matter("timeline", {"events": [
        {"id": "e1", "date": "2026年3月1日", "title": "立项会", "kind": "procedure", "evidence": [anchor]},
        {"date": "2026/03/05", "title": "周报周会"},
        {"date": "2026-03", "title": "指标复盘"},
        {"date": "2026年", "title": "年度归档"},
        {"date": "2026年3月7日", "title": "客户接待", "people": ["律师甲"]},
    ]})
    assert first.status == "ok", first.error
    payload = first.payload
    assert payload["item_count"] == 5
    assert payload["anchored_count"] == 1 and payload["unanchored_count"] == 4
    assert payload["year_from"] == "2026" and payload["year_to"] == "2026"
    assert "4 项没有出处" in payload["note"]
    stored = json.loads(_file(project, "timeline").read_text(encoding="utf-8"))
    sort_keys = [row["sort_key"] for row in stored["events"]]
    assert sort_keys == ["20260301", "20260305", "20260300", "20260000", "20260307"]

    # upsert: same id merges in place, reviewed anchor wins over an anchor-less
    # incoming row, untouched rows stay as-is.
    second = _matter("timeline", {"events": [
        {"id": "e1", "date": "2026-03-01", "title": "立项会(修订)"},
        {"id": "e9", "date": "2026-04-01", "title": "新增事项", "evidence": [{"path": "证据.md", "line_ref": "L1"}]},
    ]})
    assert second.status == "ok", second.error
    stored = json.loads(_file(project, "timeline").read_text(encoding="utf-8"))
    rows = stored["events"]
    assert len(rows) == 6
    kept = next(row for row in rows if row["id"] == "e1")
    assert kept["title"] == "立项会"  # old anchored row wins
    assert any(row.get("id") == "e9" for row in rows)
    reasons = " ".join(r["reason"] for r in second.payload["issues"])
    assert "保留旧条" in reasons

    # a pure repeat is a no-op refusal (the empty-writeback ban).
    third = _matter("timeline", {"events": [{"id": "e9", "date": "2026-04-01", "title": "新增事项",
                                             "evidence": [{"path": "证据.md", "line_ref": "L1"}]}]})
    # e9 already landed anchored — the identical row merges to the same bytes.
    assert third.status == "error"


def test_bad_dates_become_issues_and_are_dropped(tmp_path: Path, monkeypatch) -> None:
    project = _workspace(tmp_path, monkeypatch)
    result = _matter("chronology", {"entries": [
        {"date": "2026年3月", "fact": "事实甲"},
        {"date": "没有日期形态", "fact": "事实乙"},
    ]})
    assert result.status == "ok", result.error
    assert result.payload["item_count"] == 1
    assert result.payload["issues"][0]["reason"].startswith("日期无法识别")
    stored = json.loads(_file(project, "chronology").read_text(encoding="utf-8"))
    assert stored["entries"][0]["sort_key"] == "20260300"
    # an all-invalid batch must not overwrite anything silently.
    result = _matter("timeline", {"events": [
        {"date": "未知时间", "title": "不猜"},
        {"date": "2026-13-01", "title": "月超界"},
    ]})
    assert result.status == "error"
    assert "拒绝空写回" in (result.error or "")
    assert not _file(project, "timeline").exists()


def test_empty_payload_and_pure_replace_refusals(tmp_path: Path, monkeypatch) -> None:
    _workspace(tmp_path, monkeypatch)
    result = _matter("timeline", {"events": []})
    assert result.status == "error"
    assert "拒绝空写回" in (result.error or "")
    result = _matter("chronology", {"entries": [{"date": "日期不明", "fact": "x"}]})
    assert result.status == "error"


def test_mindmap_svg_layout_is_stable(tmp_path: Path, monkeypatch) -> None:
    _workspace(tmp_path, monkeypatch)
    result = _matter(
        "mindmap",
        {
            "root": {
                "label": "根",
                "evidence": [{"path": "证据.md"}],
                "children": [{"label": "甲"}, {"label": "乙"}],
            }
        },
    )
    assert result.status == "ok", result.error
    svg = result.payload["svg"]
    assert 'x="0" y="20"' in svg
    assert 'x="104" y="0"' in svg
    assert 'x="104" y="40"' in svg
    assert svg.count("待补出处") == 2
    again = _matter(
        "mindmap",
        {
            "root": {
                "label": "根",
                "evidence": [{"path": "证据.md"}],
                "children": [{"label": "甲"}, {"label": "乙"}],
            }
        },
    )
    assert again.status == "error" and "完全一致" in (again.error or "")


def test_mindmap_caps_depth_and_names_truncation(tmp_path: Path, monkeypatch) -> None:
    project = _workspace(tmp_path, monkeypatch)
    root = {"label": "根", "children": [{"label": "l1", "children": [{"label": "l2", "children": [
        {"label": "l3", "children": [{"label": "l4", "children": [{"label": "l5", "children": [
            {"label": "l6", "children": [{"label": "l7超层"}]}]}]}]}]}]}]}
    result = _matter("mindmap", {"root": root})
    assert result.status == "ok", result.error
    assert result.payload["issues"]
    assert any("层上限" in row["reason"] for row in result.payload["issues"])
    stored = json.loads(_file(project, "mindmap").read_text(encoding="utf-8"))
    node = stored["root"]
    depth = 1
    while node.get("children"):
        node = node["children"][0]
        depth += 1
    assert depth <= 6


def test_mindmap_shape_and_label_refusals(tmp_path: Path, monkeypatch) -> None:
    _workspace(tmp_path, monkeypatch)
    result = _matter("mindmap", {"root": {}})
    assert result.status == "error"
    assert "label" in (result.error or "")
    # 子节点单点问题走再生纪律:已命名的 issue + 丢弃该支,整树其余部分照常落盘;
    # 只有 root 本体形状无效才升级为整单 refuse。
    result = _matter("mindmap", {"root": {"label": "根", "children": [{"label": "子", "kind": "奇怪"}]}})
    assert result.status == "ok", result.error
    reasons = " ".join(row["reason"] for row in result.payload["issues"])
    assert "kind 不在允许集" in reasons


def test_replace_is_explicit_only(tmp_path: Path, monkeypatch) -> None:
    project = _workspace(tmp_path, monkeypatch)
    _matter("timeline", {"events": [{"id": "e1", "date": "2026-03-01", "title": "甲"}]})
    _matter("timeline", {"events": [{"id": "e2", "date": "2026-03-02", "title": "乙"}]})
    stored = json.loads(_file(project, "timeline").read_text(encoding="utf-8"))
    assert len(stored["events"]) == 2
    result = _matter("timeline", {"events": [{"id": "r1", "date": "2026-05-01", "title": "整份重做"}]}, mode="replace")
    assert result.status == "ok", result.error
    stored = json.loads(_file(project, "timeline").read_text(encoding="utf-8"))
    assert len(stored["events"]) == 1 and stored["events"][0]["id"] == "r1"
