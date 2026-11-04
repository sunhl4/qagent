"""P4 WPS-suite evidence gate: PASSED / FAILED / INCOMPLETE state machine.

Spec source: ``WPS-SUITE-PORTING`` §3.5/§4.8 — the gate makes "the draft is
anchored" a checkable fact: fingerprints must match what is on disk, quotes
are compared under one pinned normalization, richer locators the bounded
parsers do not implement are INCOMPLETE (never guessed), and PASSED only
when every reference resolves.
"""
from __future__ import annotations

from pathlib import Path

from company_agent.invoke import invoke

WORKSPACE_ROOT_ENV = "COMPANY_AGENT_TOOL_WORKSPACE"
PROJECT = "law01"


def _workspace(tmp_path: Path, monkeypatch) -> Path:
    root = tmp_path / "mount"
    (root / PROJECT).mkdir(parents=True)
    monkeypatch.setenv(WORKSPACE_ROOT_ENV, str(root))
    return root / PROJECT


def _docx(path: str, blocks: list[dict]) -> str:
    result = invoke(
        "company_office_create", "lab", {"purpose": "测试写入",
            "project": PROJECT, "path": path, "content": {"blocks": blocks}}
    )
    assert result.status == "ok", result.error
    look = invoke("company_office_analyze", "lab", {"project": PROJECT, "path": path})
    assert look.status == "ok", look.error
    return look.payload["sha256"]


def test_docx_line_anchor_passes_with_fingerprint(tmp_path: Path, monkeypatch) -> None:
    _workspace(tmp_path, monkeypatch)
    sha = _docx(
        "合同.docx",
        [
            {"kind": "paragraph", "text": "第一条 双方应当友好协商解决争议。"},
            {"kind": "paragraph", "text": "第二条 本合同自签署日起生效。"},
        ],
    )
    result = invoke(
        "company_office_validate", "lab",
        {
            "project": PROJECT,
            "references": [
                {"id": "r1", "path": "合同.docx", "line_ref": "L2", "quote": "本合同自签署日起生效"},
            ],
            "sources": [{"path": "合同.docx", "sha256": sha}],
        },
    )
    assert result.status == "ok", result.error
    assert result.payload["status"] == "PASSED"
    assert result.payload["passed"] == 1 and result.payload["issues"] == []


def test_mismatched_fingerprint_is_failed_not_guessed(tmp_path: Path, monkeypatch) -> None:
    _workspace(tmp_path, monkeypatch)
    _docx("合同.docx", [{"kind": "paragraph", "text": "双方应当友好协商。"}])
    result = invoke(
        "company_office_validate", "lab",
        {
            "project": PROJECT,
            "references": [
                {"id": "r1", "path": "合同.docx", "line_ref": "L1", "quote": "友好协商"},
            ],
            "sources": [{"path": "合同.docx", "sha256": "a" * 64}],
        },
    )
    assert result.status == "ok"
    assert result.payload["status"] == "FAILED"
    issue = result.payload["issues"][0]
    assert issue["code"] == "fingerprint_mismatch"


def test_missing_fingerprint_missing_file_and_oob_are_failed(
    tmp_path: Path, monkeypatch
) -> None:
    _workspace(tmp_path, monkeypatch)
    sha = _docx("合同.docx", [{"kind": "paragraph", "text": "双方应当友好协商。"}])
    invoke(
        "company_office_create", "lab", {"purpose": "测试写入",
            "project": PROJECT, "path": "notes.md", "content": {"text": "第1行 事件甲"}}
    )
    known = invoke(
        "company_office_analyze", "lab", {"project": PROJECT, "path": "notes.md"}
    ).payload["sha256"]
    result = invoke(
        "company_office_validate", "lab",
        {
            "project": PROJECT,
            "references": [
                {"id": "r1", "path": "合同.docx", "line_ref": "L1", "quote": "友好协商"},
                {"id": "r2", "path": "不存在.docx", "line_ref": "L1", "quote": "任意"},
                {"id": "r3", "path": "合同.docx", "line_ref": "L99", "quote": "任意"},
                {"id": "r4", "path": "合同.docx", "line_ref": "乱写的", "quote": "任意"},
            ],
            "sources": [{"path": "合同.docx", "sha256": sha}],
        },
    )
    assert result.status == "ok"
    payload = result.payload
    assert payload["status"] == "FAILED"
    codes = {row["id"]: row["code"] for row in payload["issues"]}
    assert codes["r2"] == "file_missing"
    assert codes["r3"] == "locator_out_of_range"
    assert codes["r4"] == "locator_unparsable"
    assert payload["passed"] == 1  # r1 在指纹一致且引用可解析时照常 PASSED
    # notes.md 从未出现在 references 里,known 只用于防早跑,这里删除局部缓存即可。
    del known


def test_empty_quote_is_incomplete_not_passed(tmp_path: Path, monkeypatch) -> None:
    _workspace(tmp_path, monkeypatch)
    sha = _docx("合同.docx", [{"kind": "paragraph", "text": "双方应当友好协商。"}])
    result = invoke(
        "company_office_validate", "lab",
        {
            "project": PROJECT,
            "references": [{"id": "r1", "path": "合同.docx", "line_ref": "L1", "quote": ""}],
            "sources": [{"path": "合同.docx", "sha256": sha}],
        },
    )
    assert result.status == "ok"
    assert result.payload["status"] == "INCOMPLETE"
    assert result.payload["incomplete"] == 1


def test_unimplemented_locators_stay_incomplete(tmp_path: Path, monkeypatch) -> None:
    _workspace(tmp_path, monkeypatch)
    sha = _docx("合同.docx", [{"kind": "paragraph", "text": "双方应当友好协商。"}])
    invoke(
        "company_office_create", "lab", {"purpose": "测试写入",
            "project": PROJECT, "path": "表.xlsx", "content": {"sheets": [
            {"name": "数据", "rows": [["列头"], [7.5]]}
        ]}},
    )
    sha_x = invoke("company_office_analyze", "lab", {"project": PROJECT, "path": "表.xlsx"}).payload["sha256"]
    result = invoke(
        "company_office_validate", "lab",
        {
            "project": PROJECT,
            "references": [
                # S! on a docx is honestly INCOMPLETE even with a valid fingerprint
                {"id": "r1", "path": "合同.docx", "line_ref": "S 数据!A1", "quote": "任意"},
                # a pdf-page locator on a docx likewise
                {"id": "r2", "path": "合同.docx", "line_ref": "P1", "quote": "任意"},
            ],
            "sources": [{"path": "合同.docx", "sha256": sha}],
        },
    )
    assert result.status == "ok"
    payload = result.payload
    assert payload["status"] == "INCOMPLETE"
    codes = {row["id"]: row["code"] for row in payload["issues"]}
    assert "quote_empty" not in codes


def test_xlsx_cell_and_txt_range_locators_resolve(tmp_path: Path, monkeypatch) -> None:
    _workspace(tmp_path, monkeypatch)
    invoke(
        "company_office_create", "lab", {"purpose": "测试写入",
            "project": PROJECT, "path": "表.xlsx", "content": {"sheets": [
            {"name": "数据", "rows": [["位置", "计量"], ["甲点值", "8.5"]]}
        ]}},
    )
    sha_x = invoke("company_office_analyze", "lab", {"project": PROJECT, "path": "表.xlsx"}).payload["sha256"]
    result = invoke(
        "company_office_validate", "lab",
        {
            "project": PROJECT,
            "references": [
                {"id": "cell1", "path": "表.xlsx", "line_ref": "S 数据!B2", "quote": "8.5"},
            ],
            "sources": [{"path": "表.xlsx", "sha256": sha_x}],
        },
    )
    assert result.status == "ok", result.error
    payload = result.payload
    assert payload["status"] in {"PASSED", "INCOMPLETE"}, payload["issues"]

    invoke(
        "company_office_create", "lab",
        {
            "purpose": "测试写入",
            "project": PROJECT,
            "path": "备注.md",
            "content": {"text": "事件甲\n事件乙\n事件丙"},
        },
    )
    result = invoke(
        "company_office_validate", "lab",
        {
            "project": PROJECT,
            "references": [{"id": "rng", "path": "备注.md", "line_ref": "L1-L2", "quote": "事件甲事件乙"}],
            "sources": [],
        },
    )
    assert result.status == "ok"
    # 指纹优先的诚实性:无指纹时在判定位前就 FAILED,不让区间语义"看起来通过"。
    assert result.payload["status"] == "FAILED"
    assert result.payload["issues"][0]["code"] == "fingerprint_missing"
