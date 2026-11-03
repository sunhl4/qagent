"""P2 WPS-suite creation gate: bounded, honest, fail-closed office writes.

Spec source: ``WPS-SUITE-PORTING`` write slice — the agent can hand a single
.docx/.xlsx/.xmind/.mm/.txt artifact to later WPS/Excel/XMind tools, every
overshoot refusal names its cap, overwrite needs an explicit argument, and the
written bytes are re-verified so the returned sha256 is trustworthy.
"""
from __future__ import annotations

import io
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from company_agent.invoke import invoke

WORKSPACE_ROOT_ENV = "COMPANY_AGENT_TOOL_WORKSPACE"
PROJECT = "legal01"


def _workspace(tmp_path: Path, monkeypatch) -> Path:
    root = tmp_path / "mount"
    (root / PROJECT).mkdir(parents=True)
    monkeypatch.setenv(WORKSPACE_ROOT_ENV, str(root))
    return root / PROJECT


def _create(path: str, content: dict, **extra):
    args = {"project": PROJECT, "path": path, "content": content}
    args.update(extra)
    return invoke("company_office_create", "lab", args)


def test_docx_roundtrip_through_analyze(tmp_path: Path, monkeypatch) -> None:
    project = _workspace(tmp_path, monkeypatch)
    result = _create(
        "report.docx",
        {
            "blocks": [
                {"kind": "heading", "text": "季度摘要", "level": 1},
                {"kind": "paragraph", "text": "第一段正文"},
                {"kind": "paragraph", "text": "第二段正文\n续行内容"},
            ]
        },
    )
    assert result.status == "ok", result.error
    payload = result.payload
    assert payload["created"] is True
    assert payload["kind"] == "docx"
    assert payload["path"] == f"{PROJECT}/report.docx"
    assert payload["overwrote"] is False
    assert (project / "report.docx").is_file()
    assert len(payload["sha256"]) == 64
    assert set(payload["sha256"]) <= set("0123456789abcdef")

    look = invoke("company_office_analyze", "lab", {"project": PROJECT, "path": "report.docx"})
    assert look.status == "ok", look.error
    texts = [item["text"] for item in look.payload["items"]]
    assert texts[0] == "季度摘要"
    assert texts[1] == "第一段正文"
    assert "续行内容" in texts[2]

    with zipfile.ZipFile(io.BytesIO((project / "report.docx").read_bytes())) as package:
        assert "word/document.xml" in package.namelist()
        assert "word/styles.xml" in package.namelist()


def test_existing_file_refuses_without_explicit_overwrite(tmp_path: Path, monkeypatch) -> None:
    project = _workspace(tmp_path, monkeypatch)
    first = _create("notes.md", {"text": "原始标题"})
    assert first.status == "ok", first.error
    assert (project / "notes.md").read_text(encoding="utf-8") == "原始标题"

    second = _create("notes.md", {"text": "被覆盖的内容"})
    assert second.status == "error" or second.decision == "deny"
    assert "已存在" in (second.error or "")
    assert (project / "notes.md").read_text(encoding="utf-8") == "原始标题"

    third = _create("notes.md", {"text": "被覆盖的内容"}, overwrite=True)
    assert third.status == "ok", third.error
    assert third.payload["overwrote"] is True
    assert (project / "notes.md").read_text(encoding="utf-8") == "被覆盖的内容"

    fourth = _create("新文件.txt", {"text": "初稿"}, overwrite=False)
    assert fourth.status == "ok"
    assert fourth.payload["overwrote"] is False


def test_xlsx_multi_sheet_roundtrip(tmp_path: Path, monkeypatch) -> None:
    project = _workspace(tmp_path, monkeypatch)
    result = _create(
        "统计.xlsx",
        {
            "sheets": [
                {"name": "总表", "rows": [["名称", "数量"], ["离子阱", 8], ["超导", 3.5]]},
                {"name": "第二张", "rows": [["留白"], [None, "TRUE"]]},
            ]
        },
    )
    assert result.status == "ok", result.error
    payload = result.payload
    assert payload["kind"] == "xlsx"

    look = invoke("company_office_analyze", "lab", {"project": PROJECT, "path": "统计.xlsx"})
    assert look.status == "ok", look.error
    assert look.payload["total_units"] == 2

    with zipfile.ZipFile(io.BytesIO((project / "统计.xlsx").read_bytes())) as package:
        workbook = package.read("xl/workbook.xml").decode("utf-8")
        sheet1 = package.read("xl/worksheets/sheet1.xml").decode("utf-8")
        sheet2 = package.read("xl/worksheets/sheet2.xml").decode("utf-8")
    assert 'name="总表"' in workbook and 'name="第二张"' in workbook
    assert ">离子阱<" in sheet1
    # 全员带 m: 前缀:worksheet/sheetData/row/c 位于同一命名空间,Word/WPS 可开。
    assert "<m:is>" in sheet1
    assert "<m:v>3.5</m:v>" in sheet2 or "<m:is><m:t>TRUE</m:t></m:is>" in sheet2


def test_xmind_package_opens(tmp_path: Path, monkeypatch) -> None:
    project = _workspace(tmp_path, monkeypatch)
    result = _create(
        "脑图.xmind",
        {
            "root": {
                "title": "项目图谱",
                "children": [
                    {"title": "设备", "children": [{"title": "离子阱"}, {"title": "超导"}]},
                    {"title": "数据", "children": [{"title": "资产清单"}]},
                ],
            }
        },
    )
    assert result.status == "ok", result.error
    assert result.payload["kind"] == "xmind"
    with zipfile.ZipFile(io.BytesIO((project / "脑图.xmind").read_bytes())) as package:
        names = package.namelist()
        content = package.read("content.xml").decode("utf-8")
        package.read("META-INF/manifest.xml")
    assert "content.xml" in names
    tree = ET.fromstring(content)
    titles = [element.text or "" for element in tree.iter() if element.tag.endswith("title")]
    assert titles.count("项目图谱") == 1
    assert "离子阱" in titles and "资产清单" in titles


def test_freemind_mm_structure(tmp_path: Path, monkeypatch) -> None:
    project = _workspace(tmp_path, monkeypatch)
    result = _create(
        "导图.mm",
        {"root": {"title": "根", "children": [{"title": "分支一"}, {"title": "分支二"}]}},
    )
    assert result.status == "ok", result.error
    assert result.payload["kind"] == "mindmap"
    tree = ET.fromstring((project / "导图.mm").read_text(encoding="utf-8"))
    assert tree.tag == "map"
    nodes = list(tree.iter("node"))
    assert [node.get("TEXT") for node in nodes] == ["根", "分支一", "分支二"]


def test_cap_overshoot_refuses(tmp_path: Path, monkeypatch) -> None:
    _workspace(tmp_path, monkeypatch)
    sheets = [{"name": f"S{index}", "rows": [["x"]]} for index in range(1, 34)]
    wide = _create("wide.xlsx", {"sheets": sheets})
    assert wide.status == "error" or wide.decision == "deny"
    assert "32" in (wide.error or "") or wide.status == "denied"

    fat_root = {"title": "root", "children": [{"title": f"n{index}"} for index in range(512)]}
    fat = _create("fat.xmind", {"root": fat_root})
    assert fat.status == "error" and "512" in fat.error

    blocks = [{"kind": "paragraph", "text": f"段{index}"} for index in range(2001)]
    long_doc = _create("long.docx", {"blocks": blocks})
    assert long_doc.status == "error" and "2000" in long_doc.error


def test_unsupported_and_broken_targets_refuse(tmp_path: Path, monkeypatch) -> None:
    project = _workspace(tmp_path, monkeypatch)
    deck = _create("deck.pptx", {"blocks": [{"kind": "paragraph", "text": "x"}]})
    assert deck.status == "error" and "不支持的生成类型" in deck.error
    photo = _create("照片.png", {"text": "x"})
    assert photo.status == "error" and "不支持的生成类型" in photo.error

    (project / "out.docx").mkdir()
    directory = _create("out.docx", {"blocks": [{"kind": "paragraph", "text": "x"}]})
    assert directory.status == "error" and "目录" in directory.error


def test_text_and_md_plain_output(tmp_path: Path, monkeypatch) -> None:
    project = _workspace(tmp_path, monkeypatch)
    result = _create("纪要.md", {"text": "# 纪要\n\n- 事项一\n- 事项二\n"})
    assert result.status == "ok", result.error
    assert result.payload["kind"] == "text"
    assert (project / "纪要.md").read_text(encoding="utf-8") == "# 纪要\n\n- 事项一\n- 事项二\n"


def test_workspace_escapes_fail_closed(tmp_path: Path, monkeypatch) -> None:
    _workspace(tmp_path, monkeypatch)
    for args in (
        {"project": PROJECT, "path": "../outside.docx", "content": {"text": "x"}},
        {"project": "../evil", "path": "a.docx", "content": {"text": "x"}},
        {"project": PROJECT, "path": "", "content": {"text": "x"}},
        {"project": PROJECT, "path": "a.docx", "content": "不是对象"},
        {"project": PROJECT, "path": "a.docx", "content": {"text": "x"}, "overwrite": "yes"},
    ):
        result = invoke("company_office_create", "lab", args)
        assert result.status in {"denied", "error"}, args
        assert result.status == "error" or result.decision == "deny"
