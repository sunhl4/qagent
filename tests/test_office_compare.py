"""P2 WPS-suite comparison gate: read-only line diff, bounded and honest.

Spec source: ``WPS-SUITE-PORTING`` L2 / §4.10 — only-read comparison over
the units a human sees; mixed/binary kinds refuse; exact counts plus 40
bounded hunk samples with an explicit truncated flag.
"""
from __future__ import annotations

from pathlib import Path

from company_agent.invoke import invoke

WORKSPACE_ROOT_ENV = "COMPANY_AGENT_TOOL_WORKSPACE"
PROJECT = "cmp01"


def _workspace(tmp_path: Path, monkeypatch) -> Path:
    root = tmp_path / "mount"
    (root / PROJECT).mkdir(parents=True)
    monkeypatch.setenv(WORKSPACE_ROOT_ENV, str(root))
    return root / PROJECT


def _text(path: str, content: str) -> None:
    result = invoke(
        "company_office_create", "lab", {"project": PROJECT, "path": path, "content": {"text": content}}
    )
    assert result.status == "ok", result.error


def _compare(a: str, b: str):
    return invoke("company_office_compare", "lab", {"project": PROJECT, "file_a": a, "file_b": b})


def test_line_diff_reports_counts_and_hunks(tmp_path: Path, monkeypatch) -> None:
    _workspace(tmp_path, monkeypatch)
    _text("a.md", "第一行\n共用的中段文本\n结尾甲\n\n尾段")
    _text("b.md", "第一行\n共用的中段文本2\n结尾乙\n新行")
    result = _compare("a.md", "b.md")
    assert result.status == "ok", result.error
    payload = result.payload
    assert payload["kind"] == "text"
    assert payload["identical"] is False
    # difflib 对这两种可读文本给出的是"单一 changed 区块"的确定性结果:
    # b.md 独有的 3 行与 a.md 无镜像的 4 行(含空行)如实计数。
    assert payload["added"] == 3
    assert payload["removed"] == 4
    assert payload["truncated"] is False
    assert payload["hunks"] and payload["hunks"][0]["kind"] in {"changed", "added", "removed"}
    first = payload["hunks"][0]
    assert first["at_a"] == 2 and first["at_b"] == 2
    assert all(len(row) <= 200 for row in first["before"] + first["after"])
    assert payload["trust"] == "untrusted_reference_data"
    assert len(payload["sha256_a"]) == 64 and len(payload["sha256_b"]) == 64


def test_identical_files_are_a_fact(tmp_path: Path, monkeypatch) -> None:
    _workspace(tmp_path, monkeypatch)
    _text("same.md", "一行\n两行")
    result = _compare("same.md", "same.md")
    assert result.status == "ok"
    assert result.payload["identical"] is True
    assert result.payload["added"] == 0 and result.payload["removed"] == 0
    assert result.payload["hunks"] == []


def test_docx_paragraph_diff_uses_analyze_anchors(tmp_path: Path, monkeypatch) -> None:
    _workspace(tmp_path, monkeypatch)
    invoke(
        "company_office_create", "lab",
        {"project": PROJECT, "path": "old.docx", "content": {"blocks": [
            {"kind": "paragraph", "text": "共同开头。"},
            {"kind": "paragraph", "text": "旧句甲。"},
        ]}},
    )
    invoke(
        "company_office_create", "lab",
        {"project": PROJECT, "path": "new.docx", "content": {"blocks": [
            {"kind": "paragraph", "text": "共同开头。"},
            {"kind": "paragraph", "text": "新句乙。"},
        ]}},
    )
    result = _compare("old.docx", "new.docx")
    assert result.status == "ok", result.error
    assert result.payload["kind"] == "docx"
    assert result.payload["removed"] == 1 and result.payload["added"] == 1
    hunk = result.payload["hunks"][0]
    assert hunk["before"] == ["旧句甲。"] and hunk["after"] == ["新句乙。"]


def test_mixed_and_missing_files_fail_closed(tmp_path: Path, monkeypatch) -> None:
    _workspace(tmp_path, monkeypatch)
    _text("a.md", "x")
    result = _compare("a.md", "b.docx")
    assert result.status == "error"
    result = _compare("a.md", "no-such-file.md")
    assert result.status == "error"
    assert "not" in (result.error or "") or "可用" in (result.error or "")


def test_unit_cap_refuses_instead_of_comparing_a_stand_in(
    tmp_path: Path, monkeypatch
) -> None:
    _workspace(tmp_path, monkeypatch)
    big = "\n".join(f"行_{n}" for n in range(4001))
    _text("big.txt", big)
    _text("small.txt", "其他")
    result = _compare("big.txt", "small.txt")
    assert result.status == "error"
    assert "4000" in (result.error or "")


def test_docx_and_unknown_kind_refuse(tmp_path: Path, monkeypatch) -> None:
    _workspace(tmp_path, monkeypatch)
    invoke(
        "company_office_create", "lab",
        {"project": PROJECT, "path": "a.xlsx", "content": {"sheets": [
            {"name": "表1", "rows": [["头"], ["值"]]}
        ]}},
    )
    _text("b.md", "x")
    result = _compare("a.xlsx", "b.md")
    assert result.status == "error"
    assert "不支持" in (result.error or "")
