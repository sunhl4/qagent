"""Parity gates for the remaining WPS-suite behaviors."""
from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

from company_agent import office_addin, office_edit, office_terms
from company_agent.invoke import invoke
from company_agent.office_pptx import _resolve_cli

WORKSPACE = "COMPANY_AGENT_TOOL_WORKSPACE"
PROJECT = "parity01"


def _workspace(tmp_path: Path, monkeypatch) -> Path:
    root = tmp_path / "mount"
    (root / PROJECT).mkdir(parents=True)
    monkeypatch.setenv(WORKSPACE, str(root))
    return root / PROJECT


def test_terms_suggest_role_alias() -> None:
    rows = office_terms.suggest("本合同所称“委托方”（甲方）应当签收。")
    assert any(row["find"] == "甲方" and row["replace"] == "委托方" for row in rows)
    assert len(office_terms.ROLES) == 27


def test_qa_codes_are_named() -> None:
    assert office_edit._qa_tracked(b"<w:document/>") == "xml_qa_no_tracks"
    xml = (
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:p><w:del><w:r><w:delText>合同正文甲乙丙丁戊己庚辛</w:delText></w:r></w:del>"
        "<w:ins><w:r><w:t>合同正文甲乙丙丁戊己庚壬</w:t></w:r></w:ins></w:p></w:document>"
    )
    assert office_edit._qa_tracked(xml.encode()) == "xml_qa_non_minimal_edits"
    mismatch = (
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:p><w:r><w:rPr><w:sz w:val="32"/></w:rPr><w:t>原文</w:t></w:r>'
        '<w:ins><w:r><w:rPr><w:sz w:val="21"/></w:rPr><w:t>改</w:t></w:r></w:ins></w:p>'
        "</w:document>"
    )
    assert office_edit._qa_tracked(mismatch.encode()) == "xml_qa_format_mismatch"


def test_addin_dedupes_running_and_expires_orphans() -> None:
    clock = {"now": 1000.0}
    store = office_addin.ReviewStore("token", clock=lambda: clock["now"])
    first = store.submit(b"same-bytes", "审这份")
    running = store.take(first["id"], b"same-bytes")
    assert running["state"] == "running"
    again = store.submit(b"same-bytes", "审这份")
    assert again["id"] == first["id"] and again["state"] == "running"
    queued = store.submit(b"queued-bytes", "待取")
    stale = store.take(queued["id"], b"changed")
    assert stale["state"] == "stale"
    clock["now"] += office_addin.ORPHAN_SECONDS + 1
    fresh = store.submit(b"brand-new", "另一份")
    assert store.get(first["id"])["state"] == "failed"
    assert fresh["state"] == "queued"


def test_files_copy_and_revert(tmp_path: Path, monkeypatch) -> None:
    project = _workspace(tmp_path, monkeypatch)
    (project / "note.txt").write_text("原文", encoding="utf-8")
    copied = invoke(
        "company_office_files",
        "lab",
        {
            "project": PROJECT,
            "purpose": "复制附件",
            "action": "copy",
            "ops": [{"source": "note.txt", "target": "copy.txt"}],
        },
    )
    assert copied.status == "ok", copied.error
    assert (project / "copy.txt").read_text(encoding="utf-8") == "原文"
    reverted = invoke(
        "company_office_files",
        "lab",
        {"project": PROJECT, "purpose": "撤销复制", "action": "revert"},
    )
    assert reverted.status == "ok", reverted.error
    assert not (project / "copy.txt").exists()
    assert (project / "note.txt").is_file()


def test_review_table_inserts_provenance_column(tmp_path: Path, monkeypatch) -> None:
    _workspace(tmp_path, monkeypatch)
    result = invoke(
        "company_office_review_table",
        "lab",
        {
            "project": PROJECT,
            "path": "分析.xlsx",
            "purpose": "写分析表",
            "columns": [
                {
                    "name": "结论",
                    "cells": [{"value": "达标", "line_ref": "L1", "summary": "正文"}],
                }
            ],
        },
    )
    assert result.status == "ok", result.error
    read = invoke("company_office_analyze", "lab", {"project": PROJECT, "path": "分析.xlsx"})
    assert read.status == "ok", read.error
    blob = "\n".join(item["text"] for item in read.payload["items"])
    assert "结论_依据" in blob and "L1：正文" in blob


def test_template_and_cell_cap(tmp_path: Path, monkeypatch) -> None:
    project = _workspace(tmp_path, monkeypatch)
    created = invoke(
        "company_office_create",
        "lab",
        {"purpose": "测试写入", 
            "project": PROJECT,
            "path": "memo.docx",
            "content": {
                "template": "legal-memo",
                "blocks": [
                    {"kind": "paragraph", "text": "备忘录"},
                    {"kind": "table", "rows": [["事项", "结论"]]},
                ],
            },
        },
    )
    assert created.status == "ok", created.error
    import zipfile

    with zipfile.ZipFile(project / "memo.docx") as package:
        xml = package.read("word/document.xml")
    assert b"docGrid" in xml and b"tblBorders" in xml
    from company_agent.office_create import OfficeCreateError, _xlsx_package

    try:
        _xlsx_package({"sheets": [{"name": "S", "rows": [["x"] * 17 for _ in range(5000)]}]})
    except OfficeCreateError as exc:
        assert "80000" in str(exc)
    else:
        raise AssertionError("80000 cell cap should refuse")


def test_range_anchor_and_ambiguous_quote(tmp_path: Path, monkeypatch) -> None:
    project = _workspace(tmp_path, monkeypatch)
    invoke(
        "company_office_create",
        "lab",
        {"purpose": "测试写入", 
            "project": PROJECT,
            "path": "表.xlsx",
            "content": {"sheets": [{"name": "数据", "rows": [["甲点值", "乙"], ["甲点值", "丙"]]}]},
        },
    )
    sha = invoke("company_office_analyze", "lab", {"project": PROJECT, "path": "表.xlsx"}).payload["sha256"]
    ranged = invoke(
        "company_office_validate",
        "lab",
        {
            "project": PROJECT,
            "references": [{"id": "r1", "path": "表.xlsx", "line_ref": "S数据!A1:A2", "quote": "甲点值"}],
            "sources": [{"path": "表.xlsx", "sha256": sha}],
        },
    )
    assert ranged.status == "ok", ranged.error
    assert ranged.payload["status"] == "FAILED"
    assert ranged.payload["issues"][0]["code"] == "ambiguous"
    (project / "note.txt").write_text("唯一锚点\n", encoding="utf-8")
    sha_t = invoke(
        "company_office_analyze", "lab", {"project": PROJECT, "path": "note.txt"}
    ).payload["sha256"]
    single = invoke(
        "company_office_validate",
        "lab",
        {
            "project": PROJECT,
            "references": [{"id": "r2", "path": "note.txt", "line_ref": "L1", "quote": "唯一锚点"}],
            "sources": [{"path": "note.txt", "sha256": sha_t}],
        },
    )
    assert single.payload["status"] == "PASSED"
    assert single.payload["citations"][0]["render"].startswith("@@")


def test_resolve_cli_prefers_explicit_then_bundled(tmp_path: Path, monkeypatch) -> None:
    explicit = tmp_path / "officecli.exe"
    explicit.write_bytes(b"cli")
    assert _resolve_cli(str(explicit)) == str(explicit)
    monkeypatch.delenv("COMPANY_AGENT_OFFICECLI", raising=False)
    from company_agent import office_pptx

    root = office_pptx._repo_root()
    tag = office_pptx._platform_tag()
    dest = root / "resources" / "officecli" / tag
    dest.mkdir(parents=True, exist_ok=True)
    binary = dest / ("officecli.exe" if __import__("os").name == "nt" else "officecli")
    binary.write_bytes(b"bundled")
    try:
        monkeypatch.setattr(office_pptx.shutil, "which", lambda name: None)
        assert Path(_resolve_cli()).resolve() == binary.resolve()
    finally:
        binary.unlink(missing_ok=True)


def test_deliver_matter_folder_and_blocked_export(tmp_path: Path, monkeypatch) -> None:
    project = _workspace(tmp_path, monkeypatch)
    (project / "draft.docx").write_bytes(b"PK\x03\x04not-a-real-docx")
    placed = invoke(
        "company_office_deliver",
        "lab",
        {"purpose": "测试写入", "project": PROJECT, "path": "draft.docx", "matter": "m1", "title": "函"},
    )
    # magic is not required by deliver; the copy should land under cases/
    if placed.status == "ok":
        assert "/cases/m1/artifacts/" in placed.payload["path"]
    blocked = invoke(
        "company_office_deliver",
        "lab",
        {"purpose": "测试写入", 
            "project": PROJECT,
            "path": "draft.docx",
            "references": [{"id": "r", "path": "missing.txt", "line_ref": "L1", "quote": "x"}],
            "sources": [],
        },
    )
    assert blocked.status == "error" and "拒绝正式导出" in blocked.error


def test_preview_page_has_no_model_loop() -> None:
    page = Path("view/office-preview/index.html").read_text(encoding="utf-8")
    assert "does not call a model" in page or "不" in page
    assert "company_office" not in page or "receipt" in page
    assert "data.hunks" in page


def _docx(path: str, text: str) -> None:
    created = invoke(
        "company_office_create",
        "lab",
        {"purpose": "测试写入", 
            "project": PROJECT,
            "path": path,
            "content": {"blocks": [{"kind": "paragraph", "text": text}]},
        },
    )
    assert created.status == "ok", created.error


def test_cross_file_ambiguity_writes_nothing(tmp_path: Path, monkeypatch) -> None:
    project = _workspace(tmp_path, monkeypatch)
    _docx("a.docx", "唯一句子甲。")
    _docx("b.docx", "甲和甲。")
    before_a = (project / "a.docx").read_bytes()
    before_b = (project / "b.docx").read_bytes()
    result = invoke(
        "company_office_edit",
        "lab",
        {"purpose": "测试写入", 
            "project": PROJECT,
            "path": "a.docx",
            "edits": [{"find": "唯一句子甲", "replace": "唯一句子乙"}],
            "files": [
                {"path": "a.docx", "edits": [{"find": "唯一句子甲", "replace": "唯一句子乙"}]},
                {"path": "b.docx", "edits": [{"find": "甲", "replace": "乙"}]},
            ],
        },
    )
    assert result.status == "error"
    assert "occurrences" in (result.error or "")
    assert (project / "a.docx").read_bytes() == before_a
    assert (project / "b.docx").read_bytes() == before_b


def test_cross_file_missing_anchor_does_not_block(tmp_path: Path, monkeypatch) -> None:
    project = _workspace(tmp_path, monkeypatch)
    _docx("a.docx", "第一份正文。")
    _docx("b.docx", "第二份正文。")
    before_a = (project / "a.docx").read_bytes()
    before_b = (project / "b.docx").read_bytes()
    result = invoke(
        "company_office_edit",
        "lab",
        {"purpose": "测试写入", 
            "project": PROJECT,
            "path": "a.docx",
            "edits": [{"find": "不存在", "replace": "x"}],
            "files": [
                {"path": "a.docx", "edits": [{"find": "不存在", "replace": "x"}]},
                {"path": "b.docx", "edits": [{"find": "第二份", "replace": "另一份"}]},
            ],
        },
    )
    assert result.status == "ok", result.error
    assert (project / "a.docx").read_bytes() == before_a
    assert (project / "b.docx").read_bytes() != before_b
    manifest = project / "cache" / "redline-manifests" / "b.docx.redline-manifest.json"
    assert manifest.is_file()
    assert '"openWord": false' in manifest.read_text(encoding="utf-8")


def test_qa_failure_restores_live_file(tmp_path: Path, monkeypatch) -> None:
    project = _workspace(tmp_path, monkeypatch)
    _docx("draft.docx", "合同正文甲乙丙丁。")
    before = (project / "draft.docx").read_bytes()
    monkeypatch.setattr(office_edit, "_qa_tracked", lambda _xml: "xml_qa_format_mismatch")
    result = invoke(
        "company_office_edit",
        "lab",
        {"purpose": "测试写入", 
            "project": PROJECT,
            "path": "draft.docx",
            "edits": [{"find": "合同正文", "replace": "合同正本"}],
        },
    )
    assert result.status == "error"
    assert "degraded:xml_qa_format_mismatch" in (result.error or "")
    assert (project / "draft.docx").read_bytes() == before
    copy = project / "cache" / "redline-degraded" / "draft.docx"
    assert copy.is_file() and copy.read_bytes() != before


def test_word_compare_marks_moves_and_writes_comp(tmp_path: Path, monkeypatch) -> None:
    project = _workspace(tmp_path, monkeypatch)
    left = invoke(
        "company_office_create",
        "lab",
        {"purpose": "测试写入", "project": PROJECT, "path": "a.md", "content": {"text": "甲 乙 丙"}},
    )
    right = invoke(
        "company_office_create",
        "lab",
        {"purpose": "测试写入", "project": PROJECT, "path": "b.md", "content": {"text": "丙 乙 甲"}},
    )
    assert left.status == "ok" and right.status == "ok"
    result = invoke(
        "company_office_compare",
        "lab",
        {
            "project": PROJECT,
            "file_a": "a.md",
            "file_b": "b.md",
            "granularity": "word",
            "output_path": "diff.comp.json",
        },
    )
    assert result.status == "ok", result.error
    assert result.payload["moved"] == 2
    assert result.payload["added"] == 0 and result.payload["removed"] == 0
    assert result.payload["comp_path"].endswith("diff.comp.json")
    assert (project / "a.md").read_text(encoding="utf-8").startswith("甲")
    assert "moved" in (project / "diff.comp.json").read_text(encoding="utf-8")


def test_review_table_clears_column_when_type_changes(tmp_path: Path, monkeypatch) -> None:
    project = _workspace(tmp_path, monkeypatch)
    column = {
        "name": "结论",
        "type": "text",
        "prompt": "提取结论",
        "cells": [{"value": "达标", "line_ref": "L1", "summary": "正文"}],
    }
    first = invoke(
        "company_office_review_table",
        "lab",
        {
            "project": PROJECT,
            "path": "分析.xlsx",
            "purpose": "写分析表",
            "table_id": "t1",
            "columns": [column],
        },
    )
    assert first.status == "ok", first.error
    assert first.payload["cleared"] == []
    column["type"] = "number"
    second = invoke(
        "company_office_review_table",
        "lab",
        {
            "project": PROJECT,
            "path": "分析.xlsx",
            "purpose": "改列类型",
            "table_id": "t1",
            "overwrite": True,
            "columns": [column],
        },
    )
    assert second.status == "ok", second.error
    assert second.payload["cleared"] == ["结论"]
    ana = json.loads((project / "analysis_tables" / "t1.ana.json").read_text(encoding="utf-8"))
    row = json.loads((project / "analysis_tables" / "t1.row.1.json").read_text(encoding="utf-8"))
    assert ana["columns"][0]["type"] == "number"
    assert row["cells"]["结论"] == ""


def test_addin_binds_loopback_and_page_has_no_inline_script(monkeypatch) -> None:
    import base64
    import threading
    import urllib.request

    monkeypatch.setenv("COMPANY_AGENT_ADDIN", "1")
    server = office_addin.serve("token", 0)
    twin = server.loopback_v6
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        assert server.server_address[0] == "127.0.0.1"
        if twin is not None:
            assert twin.server_address[0] == "::1"
            assert twin.server_address[1] == server.server_address[1]
        html = Path("view/office-addin/taskpane.html").read_text(encoding="utf-8")
        script = Path("view/office-addin/taskpane.js").read_text(encoding="utf-8")
        host = Path("view/office-addin/wps/host.js").read_text(encoding="utf-8")
        assert html.index("config.js") < html.index("wps/host.js") < html.index("taskpane.js")
        assert "<script>" not in html
        assert "Word.run" not in script and "Word.run" not in host
        port = server.server_address[1]
        page = urllib.request.urlopen(f"http://127.0.0.1:{port}/word-addin/taskpane.html")
        assert page.status == 200
        assert b"taskpane.css" in page.read()
        assert any("taskpane.html" in item for item in server.visits)
        body = json.dumps({
            "instruction": "审这份",
            "file": base64.b64encode(b"docx-bytes").decode("ascii"),
        }).encode("utf-8")
        request = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/word-addin/reviews",
            data=body,
            headers={"Authorization": "Bearer token", "Content-Type": "application/json"},
        )
        posted = json.loads(urllib.request.urlopen(request).read().decode("utf-8"))
        assert posted["fingerprint"]
        assert posted["fingerprint"] != office_addin._fingerprint(b"")
    finally:
        server.shutdown()
        server.server_close()
        if twin is not None:
            twin.server_close()


def test_accept_folds_only_the_new_disposition_part(tmp_path: Path, monkeypatch) -> None:
    project = _workspace(tmp_path, monkeypatch)
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:body><w:p><w:ins w:id="7" w:author="company-agent">'
        "<w:r><w:t>新增</w:t></w:r></w:ins></w:p></w:body></w:document>"
    )
    legacy = '<dispositions><item id="7" decision="accept"/></dispositions>'
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as package:
        package.writestr("word/document.xml", document)
        package.writestr("word/lawmind-disposition.xml", legacy)
    (project / "draft.docx").write_bytes(buffer.getvalue())
    read = invoke(
        "company_office_surface", "lab",
        {"purpose": "测试写入", "project": PROJECT, "path": "draft.docx", "action": "read"},
    )
    assert read.status == "ok", read.error
    assert read.payload["revisions"][0]["folded"] is False
    accepted = invoke(
        "company_office_surface", "lab",
        {
            "purpose": "测试写入",
            "project": PROJECT,
            "path": "draft.docx",
            "action": "accept",
            "revision_id": "7",
            "author": "company-agent",
        },
    )
    assert accepted.status == "ok", accepted.error
    assert accepted.payload["revisions"][0]["folded"] is True
    packed = zipfile.ZipFile(project / "draft.docx")
    assert "word/company-disposition.xml" in packed.namelist()
    assert b"w:ins" in packed.read("word/document.xml")
