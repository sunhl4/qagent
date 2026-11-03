"""P-audit WPS-suite format gate: read-only docx format audit, honest caps.

Spec source: ``WPS-SUITE-PORTING`` §4.12 — three scopes, GB/T 9704-2012 draft
baseline (marked replaceable), ``unchecked`` honesty. The fixtures here are
raw OOXML packages so the sectPr/style-sheet geometry is exact, and one test
cross-checks the L{n} numbering against ``company_office_analyze``.
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

from company_agent.invoke import invoke

WORKSPACE_ROOT_ENV = "COMPANY_AGENT_TOOL_WORKSPACE"
PROJECT = "audit01"

_CT = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package'
    '.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/word/document.xml" ContentType="application/vnd'
    '.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
    '<Override PartName="/word/styles.xml" ContentType="application/vnd'
    '.openxmlformats-officedocument.wordprocessingml.styles+xml"/></Types>'
)
_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument'
    '/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>'
)
_W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
_SECT = (
    '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
    '<w:pgMar w:top="2098" w:right="1474" w:bottom="1984" w:left="1587"/>'
    "</w:sectPr>"
)
_HEADING_STYLES = (
    '<w:style w:type="paragraph" w:styleId="1"><w:name w:val="heading 1"/>'
    '<w:pPr><w:outlineLvl w:val="0"/><w:spacing w:line="560" w:lineRule="exact"/>'
    '<w:ind w:firstLineChars="0"/></w:pPr><w:rPr><w:rFonts w:eastAsia="黑体"/></w:rPr>'
    "</w:style>"
    '<w:style w:type="paragraph" w:styleId="2"><w:name w:val="heading 2"/>'
    '<w:pPr><w:outlineLvl w:val="1"/><w:ind w:firstLineChars="0"/></w:pPr>'
    '<w:rPr><w:rFonts w:eastAsia="楷体_GB2312"/></w:rPr></w:style>'
    '<w:style w:type="paragraph" w:styleId="3"><w:name w:val="heading 3"/>'
    '<w:pPr><w:outlineLvl w:val="2"/><w:ind w:firstLineChars="0"/></w:pPr></w:style>'
)
_STYLES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
    "<w:docDefaults><w:rPrDefault><w:rPr>"
    '<w:rFonts w:eastAsia="仿宋_GB2312"/><w:sz w:val="32"/></w:rPr></w:rPrDefault>'
    '<w:pPrDefault><w:pPr><w:spacing w:line="560" w:lineRule="exact"/>'
    '<w:ind w:firstLineChars="200"/></w:pPr></w:pPrDefault></w:docDefaults>'
    f"{_HEADING_STYLES}"
    "</w:styles>"
)


def _workspace(tmp_path: Path, monkeypatch) -> Path:
    root = tmp_path / "mount"
    project = root / PROJECT
    project.mkdir(parents=True)
    monkeypatch.setenv(WORKSPACE_ROOT_ENV, str(root))
    return project


def _docx_bytes(document: str, styles: str = _STYLES) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as package:
        package.writestr("[Content_Types].xml", _CT)
        package.writestr("_rels/.rels", _RELS)
        package.writestr("word/document.xml", document)
        package.writestr("word/styles.xml", styles)
    return buffer.getvalue()


def _title(font: str = "方正小标宋简体", sz: str = "44", jc: str = "center") -> str:
    run_props = f'<w:rFonts w:eastAsia="{font}"/><w:sz w:val="{sz}"/>'
    return (
        f'<w:p><w:pPr><w:rPr>{run_props}</w:rPr><w:jc w:val="{jc}"/></w:pPr>'
        f'<w:r><w:rPr>{run_props}</w:rPr><w:t>关于演练的通知</w:t></w:r></w:p>'
    )


def _body(text: str = "正文第一段,仿宋三号,行距二十八磅,首行缩进两字。", props: str = "") -> str:
    return f'<w:p>{props}<w:r><w:t>{text}</w:t></w:r></w:p>'


def _conformant_document() -> str:
    h1 = '<w:p><w:pPr><w:pStyle w:val="1"/></w:pPr><w:r><w:t>一级条目</w:t></w:r></w:p>'
    h2 = '<w:p><w:pPr><w:pStyle w:val="2"/></w:pPr><w:r><w:t>二级条目</w:t></w:r></w:p>'
    h3 = '<w:p><w:pPr><w:pStyle w:val="3"/></w:pPr><w:r><w:t>三级条目</w:t></w:r></w:p>'
    return f"<w:document {_W}><w:body>{_title()}{_body()}{h1}{h2}{h3}{_SECT}</w:body></w:document>"


def _write(project: Path, name: str, payload: bytes) -> None:
    (project / name).write_bytes(payload)


def _audit(mode: str, name: str = "draft.docx"):
    return invoke("company_office_audit", "lab", {"project": PROJECT, "path": name, "mode": mode})


def test_baseline_conformant_document_passes_with_facts(tmp_path: Path, monkeypatch) -> None:
    project = _workspace(tmp_path, monkeypatch)
    _write(project, "draft.docx", _docx_bytes(_conformant_document()))
    result = _audit("baseline")
    assert result.status == "ok", result.error
    payload = result.payload
    assert payload["mode"] == "baseline"
    assert payload["path"] == "audit01/draft.docx"
    assert len(payload["sha256"]) == 64 and payload["bytes"] > 0
    assert payload["sections"] == 1
    assert payload["paragraphs_total"] == 5 and payload["paragraphs_checked"] == 5
    assert payload["truncated"] is False
    assert payload["rule_set"]["id"] == "gbt-9704-2012-draft"
    assert payload["rule_set"]["status"] == "draft-pending-confirmation"
    facts = {row["key"]: row["value"] for row in payload["facts"]}
    assert facts["page_size"] == "210.0x297.0mm"
    assert facts["margin_top"] == "37.0mm" and facts["margin_bottom"] == "35.0mm"
    assert facts["margin_left"] == "28.0mm" and facts["margin_right"] == "26.0mm"
    assert facts["title_font"] == "方正小标宋简体" and facts["title_pt"] == "22.0pt"
    assert payload["issues"] == []
    codes = {row["code"] for row in payload["unchecked"]}
    assert {"page_furniture", "tables", "char_details", "style_depth"} <= codes
    assert payload["trust"] == "untrusted_reference_data"


def test_margin_violation_names_side_and_value(tmp_path: Path, monkeypatch) -> None:
    project = _workspace(tmp_path, monkeypatch)
    narrow = _SECT.replace('w:top="2098"', 'w:top="1134"')
    document = _conformant_document().replace(_SECT, narrow)
    _write(project, "draft.docx", _docx_bytes(document))
    result = _audit("baseline")
    assert result.status == "ok", result.error
    issues = result.payload["issues"]
    assert [row["code"] for row in issues] == ["margin_top_mismatch"]
    assert issues[0]["locator"] == "sect"
    assert "上边距" in issues[0]["detail"] and "37" in issues[0]["detail"]
    facts = {row["key"]: row["value"] for row in result.payload["facts"]}
    assert facts["margin_top"] == "20.0mm"


def test_body_rule_violations_aggregate_with_first_locator(tmp_path: Path, monkeypatch) -> None:
    project = _workspace(tmp_path, monkeypatch)
    document = (
        f"<w:document {_W}><w:body>{_title()}"
        '<w:p><w:pPr><w:spacing w:line="700" w:lineRule="exact"/>'
        '<w:ind w:firstLineChars="100"/></w:pPr>'
        '<w:r><w:rPr><w:rFonts w:eastAsia="宋体"/><w:sz w:val="24"/></w:rPr>'
        "<w:t>正文行距三十五磅缩进一字宋体小四。</w:t></w:r></w:p>"
        f"{_SECT}</w:body></w:document>"
    )
    _write(project, "draft.docx", _docx_bytes(document))
    result = _audit("baseline")
    assert result.status == "ok", result.error
    issues = {row["code"]: row for row in result.payload["issues"]}
    assert set(issues) == {
        "body_font_mismatch",
        "body_size_mismatch",
        "line_spacing_out_of_band",
        "first_line_indent_mismatch",
    }
    assert all(row["locator"] == "L2" for row in issues.values())
    assert "35.0" in issues["line_spacing_out_of_band"]["detail"]
    assert "宋体" in issues["body_font_mismatch"]["detail"]


def test_title_rule_violations_report_each_dimension(tmp_path: Path, monkeypatch) -> None:
    project = _workspace(tmp_path, monkeypatch)
    document = (
        f"<w:document {_W}><w:body>{_title(font='宋体', sz='36', jc='right')}"
        f"{_body()}{_SECT}</w:body></w:document>"
    )
    _write(project, "draft.docx", _docx_bytes(document))
    result = _audit("baseline")
    assert result.status == "ok", result.error
    issues = {row["code"]: row for row in result.payload["issues"]}
    assert set(issues) == {"title_font_mismatch", "title_size_mismatch", "title_not_centered"}
    assert all(row["locator"] == "L1" for row in issues.values())


def test_heading_font_violation_hits_level_counter(tmp_path: Path, monkeypatch) -> None:
    project = _workspace(tmp_path, monkeypatch)
    styles = _STYLES.replace('<w:rFonts w:eastAsia="黑体"/>', '<w:rFonts w:eastAsia="宋体"/>')
    document = _conformant_document()
    _write(project, "draft.docx", _docx_bytes(document, styles=styles))
    result = _audit("baseline")
    assert result.status == "ok", result.error
    issues = result.payload["issues"]
    assert [row["code"] for row in issues] == ["heading1_font_mismatch"]
    assert issues[0]["locator"] == "L3"
    assert "黑体" in issues[0]["detail"]


def test_unknown_fonts_land_in_unchecked_not_issues(tmp_path: Path, monkeypatch) -> None:
    project = _workspace(tmp_path, monkeypatch)
    # 无 styles.xml、段落无任何 rPr:字体与字号都不可得 → 未核,而不是"违规"。
    bare_styles = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"/>'
    )
    document = (
        f"<w:document {_W}><w:body>{_title()}{_body()}{_SECT}</w:body></w:document>"
    )
    _write(project, "draft.docx", _docx_bytes(document, styles=bare_styles))
    result = _audit("baseline")
    assert result.status == "ok", result.error
    payload = result.payload
    assert payload["issues"] == []
    codes = {row["code"] for row in payload["unchecked"]}
    assert {"body_font_unknown", "body_size_unknown", "line_unknown", "indent_unknown"} <= codes


def test_table_and_empty_paragraphs_keep_anchor_numbering(tmp_path: Path, monkeypatch) -> None:
    project = _workspace(tmp_path, monkeypatch)
    table = (
        "<w:tbl><w:tr><w:tc><w:p><w:r><w:rPr>"
        '<w:rFonts w:eastAsia="宋体"/><w:sz w:val="18"/></w:rPr>'
        "<w:t>表内段不参与正文口径</w:t></w:r></w:p></w:tc></w:tr></w:tbl>"
    )
    body_last = (
        '<w:p><w:pPr><w:spacing w:line="700" w:lineRule="exact"/></w:pPr>'
        "<w:r><w:t>表后正文。</w:t></w:r></w:p>"
    )
    document = f"<w:document {_W}><w:body>{_title()}<w:p/>{table}{body_last}{_SECT}</w:body></w:document>"
    _write(project, "draft.docx", _docx_bytes(document))
    result = _audit("baseline")
    assert result.status == "ok", result.error
    payload = result.payload
    assert payload["paragraphs_total"] == 4 and payload["paragraphs_checked"] == 4
    issues = {row["code"]: row for row in payload["issues"]}
    # 表内段只记段号(L3),不被判成正文违规;违规落在表后的正文段 L4。
    assert set(issues) == {"line_spacing_out_of_band"}
    assert issues["line_spacing_out_of_band"]["locator"] == "L4"

    # 与 P1 摄取编号交叉验证:analyze 的 items 编号与 audit 的 L{n} 一致。
    look = invoke("company_office_analyze", "lab", {"project": PROJECT, "path": "draft.docx"})
    assert look.status == "ok", look.error
    numbered = {item["index"]: item["text"] for item in look.payload["items"]}
    assert numbered[3] == "表内段不参与正文口径"
    assert numbered[4] == "表后正文。"
    assert 1 in numbered and 2 not in numbered  # 空段保留段号但不进条目


def test_imported_mode_describes_and_never_applies_baseline(tmp_path: Path, monkeypatch) -> None:
    project = _workspace(tmp_path, monkeypatch)
    narrow = _SECT.replace('w:top="2098"', 'w:top="1134"')
    document = _conformant_document().replace(_SECT, narrow)
    _write(project, "draft.docx", _docx_bytes(document))

    result = _audit("imported")
    assert result.status == "ok", result.error
    payload = result.payload
    assert payload["mode"] == "imported"
    # 外来件口径:20mm 上边距是"该文件自己的主流格式",不是违规。
    assert payload["issues"] == []
    facts = {row["key"]: row["value"] for row in payload["facts"]}
    assert facts["margin_top"] == "20.0mm"
    assert facts["body_font"] == "仿宋_GB2312" and facts["body_pt"] == "16.0pt"
    assert facts["line_pt"] == "28.0pt" and facts["indent_chars"] == "2.00字"
    unchecked = {row["code"] for row in payload["unchecked"]}
    assert "rule_table" in unchecked

    baseline = _audit("baseline")
    assert baseline.status == "ok", baseline.error
    assert any(row["code"] == "margin_top_mismatch" for row in baseline.payload["issues"])


def test_multiple_sections_flagged_in_both_modes(tmp_path: Path, monkeypatch) -> None:
    project = _workspace(tmp_path, monkeypatch)
    mid_sect = (
        '<w:p><w:pPr><w:sectPr><w:pgSz w:w="11906" w:h="16838"/></w:sectPr></w:pPr></w:p>'
    )
    document = _conformant_document().replace(_SECT, f"{mid_sect}{_SECT}")
    _write(project, "draft.docx", _docx_bytes(document))
    for mode in ("baseline", "imported"):
        result = _audit(mode)
        assert result.status == "ok", result.error
        issues = result.payload["issues"]
        assert issues[0]["code"] == "section_multiple" and issues[0]["locator"] == "sect"
        assert result.payload["sections"] == 2


def test_paragraph_cap_is_truncated_honestly(tmp_path: Path, monkeypatch) -> None:
    project = _workspace(tmp_path, monkeypatch)
    filler = "<w:p/>" * 5001
    document = f"<w:document {_W}><w:body>{filler}{_SECT}</w:body></w:document>"
    _write(project, "draft.docx", _docx_bytes(document))
    result = _audit("baseline")
    assert result.status == "ok", result.error
    payload = result.payload
    assert payload["paragraphs_total"] == 5001 and payload["paragraphs_checked"] == 5000
    assert payload["truncated"] is True
    unchecked = {row["code"]: row["detail"] for row in payload["unchecked"]}
    assert unchecked["paragraph_tail"] == "第 5001-5001 段超过检查上限:1 段未检查"
    assert any(row["code"] == "title_missing" for row in payload["issues"])


def test_suffix_and_package_failures_refuse(tmp_path: Path, monkeypatch) -> None:
    project = _workspace(tmp_path, monkeypatch)
    _write(project, "plain.txt", b"hello")
    _write(project, "broken.docx", b"PK\x03\x04 not a package")

    text = _audit("baseline", name="plain.txt")
    assert text.status == "error" and "只支持 .docx" in text.error

    corrupt = _audit("baseline", name="broken.docx")
    assert corrupt.status == "error" and "docx 数据包损坏" in corrupt.error
