"""run_compute sandbox gate: allow switch, caps, fences, disk-receipt truth.

Spec source: ``WPS-SUITE-PORTING`` §4.9 — the batch aggregation sandbox with a
whitelisted helper API, curated builtins, budget ceilings and an honest
machine-level switch; the parent re-verifies every write by re-read.
"""
from __future__ import annotations

import json  # noqa: E401 -- json is used to seed fixture data
from pathlib import Path

from company_agent.invoke import invoke

WORKSPACE_ROOT_ENV = "COMPANY_AGENT_TOOL_WORKSPACE"
ALLOW_ENV = "COMPANY_AGENT_COMPUTE_ALLOW"
PROJECT = "calc01"


def _workspace(tmp_path: Path, monkeypatch) -> Path:
    root = tmp_path / "mount"
    project = root / PROJECT
    project.mkdir(parents=True)
    monkeypatch.setenv(WORKSPACE_ROOT_ENV, str(root))
    project.joinpath("notes.md").write_text("草稿一\n草稿二", encoding="utf-8")
    project.joinpath("data.json").write_text(
        json.dumps([["指标", "结果"], ["可用性", "1"], ["安全性", "2"]]),
        encoding="utf-8",
    )
    return project


def _run(source: str):
    return invoke(
        "company_office_compute",
        "lab",
        {"project": PROJECT, "source": source, "purpose": "测试写入"},
    )


def test_unset_allow_refuses(tmp_path: Path, monkeypatch) -> None:
    _workspace(tmp_path, monkeypatch)
    monkeypatch.delenv(ALLOW_ENV, raising=False)
    result = _run('print("x")')
    assert result.status == "error" and ALLOW_ENV in result.error


def test_run_reads_stats_writes_and_prints(tmp_path: Path, monkeypatch) -> None:
    _workspace(tmp_path, monkeypatch)
    monkeypatch.setenv(ALLOW_ENV, "1")
    source = (
        "frame = stats(read_table('data.json'))\n"
        "lines = read_text('notes.md')\n"
        "print('草稿行数', len(lines.splitlines()))\n"
        "target = write_text('out/summary.md', str(frame), False)\n"
        "RESULT = {'rows': frame['rows'], 'saved': target}\n"
    )
    result = _run(source)
    assert result.status == "ok", result.error
    payload = result.payload
    assert payload["result"] == {"rows": 3, "saved": "out/summary.md"}
    assert payload["prints"] == ["草稿行数 2"]
    assert payload["prints_truncated"] is False
    assert payload["charts"] == []
    assert len(payload["written"]) == 1
    write = payload["written"][0]
    assert write["path"] == "calc01/out/summary.md"  # 写清单用 project/relative 复合路径
    assert write["sha256"] == payload["sha256_writes"][0]
    assert (
        Path(__import__("os").environ[WORKSPACE_ROOT_ENV]) / PROJECT / "out" / "summary.md"
    ).read_text(encoding="utf-8").count("rows") >= 1
    assert payload["elapsed_ms"] >= 0


def test_table_write_round_trip_with_analyze(tmp_path: Path, monkeypatch) -> None:
    _workspace(tmp_path, monkeypatch)
    monkeypatch.setenv(ALLOW_ENV, "1")
    source = (
        "rows = [['指标', '结果'], ['可用性', '达标']]\n"
        "saved = write_table(rows, 'score.xlsx')\n"
        "RESULT = {'saved': saved}\n"
    )
    result = _run(source)
    assert result.status == "ok", result.error
    assert result.payload["result"] == {"saved": "score.xlsx"}
    look = invoke("company_office_analyze", "lab", {"project": PROJECT, "path": "score.xlsx"})
    assert look.status == "ok", look.error
    assert "指标" in (look.payload["items"][0]["text"] if look.payload["items"] else "")


def test_user_program_exception_is_a_named_error(tmp_path: Path, monkeypatch) -> None:
    _workspace(tmp_path, monkeypatch)
    monkeypatch.setenv(ALLOW_ENV, "1")
    result = _run("raise ValueError('坏数据')")
    assert result.status == "error"
    assert "沙箱程序异常" in result.error and "坏数据" in result.error


def test_import_is_not_available(tmp_path: Path, monkeypatch) -> None:
    _workspace(tmp_path, monkeypatch)
    monkeypatch.setenv(ALLOW_ENV, "1")
    result = _run("import os")
    assert result.status == "error"
    # 受限 builtins 里没有 __import__ 机器字:import 是 ImportError,不是静默放行。
    assert "沙箱程序异常 ImportError" in result.error


def test_escape_path_refuses(tmp_path: Path, monkeypatch) -> None:
    project = _workspace(tmp_path, monkeypatch)
    monkeypatch.setenv(ALLOW_ENV, "1")
    result = _run('write_text("../escape.md", "no")')
    assert result.status == "error" and ("路径" in result.error or "invalid" in result.error)
    assert (project.parent / "escape.md").exists() is False


def test_write_budget_refuses(tmp_path: Path, monkeypatch) -> None:
    _workspace(tmp_path, monkeypatch)
    monkeypatch.setenv(ALLOW_ENV, "1")
    block = "甲" * 30_000
    source = "for i in range(50):\n    write_text('bulk/' + str(i) + '.md', '" + block + "', False)\n"
    result = _run(source)
    assert result.status == "error" and "4MB" in result.error


def test_result_truncation(tmp_path: Path, monkeypatch) -> None:
    _workspace(tmp_path, monkeypatch)
    monkeypatch.setenv(ALLOW_ENV, "1")
    result = _run("RESULT = {'big': ['甲' * 900] * 60}")
    assert result.status == "ok", result.error
    assert result.payload["result"] == {"truncated": True}


def test_source_cap(tmp_path: Path, monkeypatch) -> None:
    _workspace(tmp_path, monkeypatch)
    monkeypatch.setenv(ALLOW_ENV, "1")
    result = _run("# note " * 12_000)
    assert result.status == "error" and "80000" in result.error


def test_print_cap_truncates(tmp_path: Path, monkeypatch) -> None:
    _workspace(tmp_path, monkeypatch)
    monkeypatch.setenv(ALLOW_ENV, "1")
    source = "for i in range(50):\n    print('行', i)\n"
    result = _run(source)
    assert result.status == "ok", result.error
    assert len(result.payload["prints"]) == 40
    assert result.payload["prints_truncated"] is True
