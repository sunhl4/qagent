"""P1 WPS-suite ingestion gate: bounded, honest, fail-closed office reads.

Spec source: ``WPS-SUITE-PORTING`` L1/pedido slice — 模型拿到的正文与肉眼一致;
20MB/32 sheet/5000 行上限如约截断并明示; 未接入的能力(OCR/.doc/pptx)明确拒绝。
"""
from __future__ import annotations

import hashlib
import io
import zipfile
from pathlib import Path

import pytest

from company_agent.invoke import invoke
from company_agent.office_ingest import (
    MAX_FILE_BYTES,
    MAX_ITEM_TEXT_CHARS,
    MAX_ROWS_PER_SHEET,
    MAX_SHEETS,
    OfficeIngestError,
)

_W = b'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
_M = b'xmlns:m="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
_R = b'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'

WORKSPACE_ROOT_ENV = "COMPANY_AGENT_TOOL_WORKSPACE"
PROJECT = "legal01"


def _workspace(tmp_path: Path, monkeypatch) -> Path:
    root = tmp_path / "mount"
    (root / PROJECT).mkdir(parents=True)
    monkeypatch.setenv(WORKSPACE_ROOT_ENV, str(root))
    return root / PROJECT


def _docx_bytes(paragraphs: list[str]) -> bytes:
    body = []
    for text in paragraphs:
        if text:
            body.append(f"<w:p><w:r><w:t>{text}</w:t></w:r></w:p>".encode())
        else:
            body.append(b"<w:p/>")
    xml = (
        b'<w:document ' + _W + b'><w:body>'
        + b"".join(body)
        + b"</w:body></w:document>"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as package:
        package.writestr("word/document.xml", xml)
    return buffer.getvalue()


def _xlsx_bytes(sheets: list[tuple[str, list[list[str]]]], shared: list[str] | None = None) -> bytes:
    shared = shared or []
    declarations = "".join(
        f'<m:sheet name="{name}" sheetId="{index}" r:id="rId{index}"/>'
        for index, (name, _) in enumerate(sheets, start=1)
    )
    relations = "".join(
        f'<Relationship Id="rId{index}" Target="worksheets/sheet{index}.xml"/>'
        for index in range(1, len(sheets) + 1)
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as package:
        package.writestr(
            "xl/workbook.xml",
            b'<m:workbook ' + _M + b' ' + _R + b'><m:sheets>'
            + declarations.encode()
            + b'</m:sheets></m:workbook>',
        )
        package.writestr(
            "xl/_rels/workbook.xml.rels",
            b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            + relations.encode()
            + b"</Relationships>",
        )
        for index, (_, rows) in enumerate(sheets, start=1):
            body = []
            for row_number, row in enumerate(rows, start=1):
                cells = "".join(
                    _cell(cell, column, shared) for column, cell in enumerate(row, start=1)
                )
                body.append(f'<m:row r="{row_number}">{cells}</m:row>'.encode())
            package.writestr(
                f"xl/worksheets/sheet{index}.xml",
                b'<m:worksheet ' + _M + b'><m:sheetData>'
                + b"".join(body)
                + b'</m:sheetData></m:worksheet>',
            )
        if shared:
            # Write sharedStrings AFTER cell expansion: _cell() grows `shared`
            # while materialising the sheet XML above.
            shared_xml = (
                '<m:sst xmlns:m="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                + "".join(f"<m:si><m:t>{item}</m:t></m:si>" for item in shared)
                + "</m:sst>"
            )
            package.writestr("xl/sharedStrings.xml", shared_xml.encode())
    return buffer.getvalue()


def _cell(value: str, column: int, shared: list[str]) -> str:
    letter = chr(64 + column)
    try:
        shared_index = shared.index(value)
    except ValueError:
        shared.append(value)
        shared_index = len(shared) - 1
    return f'<m:c r="{letter}1" t="s"><m:v>{shared_index}</m:v></m:c>'


def test_docx_paragraph_text_is_paged_and_resumable(tmp_path: Path, monkeypatch) -> None:
    project = _workspace(tmp_path, monkeypatch)
    paragraphs = [("" if number % 7 == 0 else f"第 {number} 段内容") for number in range(1, 211)]
    (project / "report.docx").write_bytes(_docx_bytes(paragraphs))
    result = invoke("company_office_analyze", "lab", {"project": PROJECT, "path": "report.docx"})
    assert result.status == "ok", result.error
    payload = result.payload
    assert payload["kind"] == "docx"
    assert payload["path"] == f"{PROJECT}/report.docx"
    assert payload["total_units"] == 210
    assert payload["sha256"] == hashlib.sha256((project / "report.docx").read_bytes()).hexdigest()
    assert payload["bytes"] == (project / "report.docx").stat().st_size
    assert payload["trust"] == "untrusted_reference_data"
    assert payload["offset"] == 0
    # 210 paragraphs fit one page (items cap 256 + budget); nothing truncated.
    assert payload["truncated"] is False
    assert payload["items"] and payload["items"][0] == {"index": 1, "text": "第 1 段内容"}
    seen: dict[int, str] = {item["index"]: item["text"] for item in payload["items"]}
    assert set(seen) == {number for number in range(1, 211) if number % 7 != 0}
    assert seen[3] == "第 3 段内容"
    assert seen[209] == "第 209 段内容"
    # offset pages are 0-based unit indexes: 209 continues after unit 209.
    following = invoke(
        "company_office_analyze",
        "lab",
        {"project": PROJECT, "path": "report.docx", "offset": 209},
    )
    assert following.status == "ok"
    assert following.payload["items"] == []


def test_docx_empty_document_has_zero_units(tmp_path: Path, monkeypatch) -> None:
    project = _workspace(tmp_path, monkeypatch)
    (project / "empty.docx").write_bytes(_docx_bytes([]))
    result = invoke("company_office_analyze", "lab", {"project": PROJECT, "path": "empty.docx"})
    assert result.status == "ok"
    payload = result.payload
    assert payload["total_units"] == 0
    assert payload["items"] == []
    assert payload["truncated"] is False


def test_xlsx_sheets_rows_and_row_cap_are_marked(tmp_path: Path, monkeypatch) -> None:
    project = _workspace(tmp_path, monkeypatch)
    shared: list[str] = []
    wide_rows = [["甲", "乙", "丙", "丁"] for _ in range(MAX_ROWS_PER_SHEET + 7)]
    (project / "book.xlsx").write_bytes(
        _xlsx_bytes([("总表", wide_rows), ("第二张", [[" Only", "两列"]])], shared=shared)
    )
    result = invoke("company_office_analyze", "lab", {"project": PROJECT, "path": "book.xlsx"})
    assert result.status == "ok", result.error
    payload = result.payload
    assert payload["kind"] == "xlsx"
    assert payload["total_units"] == 2
    assert payload["truncated"] is False
    first, second = payload["items"]
    assert first["index"] == 1 and first["label"] == "总表"
    lines = first["text"].splitlines()
    assert lines[0] == f"rows={MAX_ROWS_PER_SHEET + 7} columns=4"
    assert len(lines) - 1 == 8 + 2  # 8 preview rows + 预览省略 + 行上限 markers
    assert "行超出 5000 行上限:第 5001-5007 行未读取" in first["text"]
    assert "[预览仅展示前 8 行" in first["text"]
    assert second["label"] == "第二张"
    assert "Only\t两列" in second["text"]
    first_cell_only = first["text"].splitlines()[1]
    assert first_cell_only.split("\t")[0] == "甲"


def test_xlsx_sheet_cap_is_truncated_explicitly(tmp_path: Path, monkeypatch) -> None:
    project = _workspace(tmp_path, monkeypatch)
    sheets = [(f"S{number}", [[str(number)]]) for number in range(1, MAX_SHEETS + 5)]
    (project / "wide.xlsx").write_bytes(_xlsx_bytes(sheets))
    result = invoke("company_office_analyze", "lab", {"project": PROJECT, "path": "wide.xlsx"})
    assert result.status == "ok"
    payload = result.payload
    assert payload["total_units"] == MAX_SHEETS
    assert payload["truncated"] is True
    joined = "\n".join(item["text"] for item in payload["items"])
    assert f"表页超出 32 张上限:第 {MAX_SHEETS + 1}-{MAX_SHEETS + 4} 张未读取" in joined


def test_xlsx_offset_pages_by_sheet(tmp_path: Path, monkeypatch) -> None:
    project = _workspace(tmp_path, monkeypatch)
    sheets = [(f"S{number}", [[str(number)]]) for number in range(1, 4)]
    (project / "three.xlsx").write_bytes(_xlsx_bytes(sheets))
    skipped = invoke("company_office_analyze", "lab", {"project": PROJECT, "path": "three.xlsx", "offset": 1})
    assert skipped.status == "ok"
    payload = skipped.payload
    assert [item["index"] for item in payload["items"]] == [2, 3]
    assert payload["items"][0]["label"] == "S2"
    assert payload["truncated"] is False


def test_pdf_text_layer_pages(tmp_path: Path, monkeypatch) -> None:
    pytest.importorskip("pypdf")
    project = _workspace(tmp_path, monkeypatch)
    pdf = _minimal_pdf_bytes()
    (project / "doc.pdf").write_bytes(pdf)
    from pypdf import PdfReader

    assert len(PdfReader(io.BytesIO(pdf)).pages) == 2
    result = invoke("company_office_analyze", "lab", {"project": PROJECT, "path": "doc.pdf"})
    assert result.status == "ok", result.error
    payload = result.payload
    assert payload["kind"] == "pdf"
    assert payload["total_units"] == 2
    assert payload["truncated"] is False
    assert "Page one body" in payload["items"][0]["text"]
    assert "Page two body" in payload["items"][1]["text"]


def test_pdf_without_engine_fails_closed(tmp_path: Path, monkeypatch) -> None:
    project = _workspace(tmp_path, monkeypatch)
    (project / "doc.pdf").write_bytes(b"%PDF-1.4\n")
    monkeypatch.setitem(__import__("sys").modules, "pypdf", None)
    result = invoke("company_office_analyze", "lab", {"project": PROJECT, "path": "doc.pdf"})
    assert result.status == "error"
    assert "pypdf" in result.error and "拒绝" in result.error


INLINE_MARK = "…[行内截断]"


def test_text_lines_page_with_inline_truncation(tmp_path: Path, monkeypatch) -> None:
    project = _workspace(tmp_path, monkeypatch)
    long_line = "长" * (MAX_ITEM_TEXT_CHARS + 500)
    content = "\n".join(["首行", long_line, "末行"])
    (project / "notes.txt").write_text(content, encoding="utf-8")
    result = invoke("company_office_analyze", "lab", {"project": PROJECT, "path": "notes.txt"})
    assert result.status == "ok"
    payload = result.payload
    assert payload["kind"] == "text"
    assert payload["total_units"] == 3
    expected = "长" * (MAX_ITEM_TEXT_CHARS - len(INLINE_MARK)) + INLINE_MARK
    assert payload["items"][1]["text"] == expected
    assert payload["items"][2]["text"] == "末行"
    assert payload["truncated"] is False


def test_text_paging_within_result_budget(tmp_path: Path, monkeypatch) -> None:
    project = _workspace(tmp_path, monkeypatch)
    content = "\n".join(f"行{number}" for number in range(1, 40_001))
    (project / "long.txt").write_text(content, encoding="utf-8")
    result = invoke("company_office_analyze", "lab", {"project": PROJECT, "path": "long.txt"})
    assert result.status == "ok"
    payload = result.payload
    assert payload["total_units"] == 40_000
    assert payload["truncated"] is True
    assert payload["items"]
    last_page_bytes = len(
        __import__("json").dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    )
    assert last_page_bytes < 64_000, "每个工具结果都必须在 results.json 预算内"
    cursor = payload["items"][-1]["index"]
    following = invoke(
        "company_office_analyze",
        "lab",
        {"project": PROJECT, "path": "long.txt", "offset": cursor},
    )
    assert following.status == "ok"
    assert following.payload["items"], "翻页必须继续"
    assert following.payload["items"][0]["index"] == cursor + 1


def test_refusals_are_honest_fail_closed(tmp_path: Path, monkeypatch) -> None:
    project = _workspace(tmp_path, monkeypatch)
    legacy = {
        "old.doc": b"\xd0\xcf\x11\xe0legacy",
        "book.xls": b"\xd0\xcf\x11\xe0xls",
        "slid.ppt": b"\xd0\xcf\x11\xe0ppt",
        "deck.pptx": b"PK",
        "photo.png": b"\x89PNG",
        "archive.zip": b"PK\x03\x04",
    }
    for name, marker in legacy.items():
        (project / name).write_bytes(marker)
    for name in legacy:
        result = invoke("company_office_analyze", "lab", {"project": PROJECT, "path": name})
        assert result.status == "error", name
    doc = invoke("company_office_analyze", "lab", {"project": PROJECT, "path": "old.doc"})
    assert "另存为" in doc.error
    png = invoke("company_office_analyze", "lab", {"project": PROJECT, "path": "photo.png"})
    assert "OCR 未接入" in png.error
    pptx = invoke("company_office_analyze", "lab", {"project": PROJECT, "path": "deck.pptx"})
    # .pptx 属合同声明的支持类型(逐片文本层);坏包必须按"损坏"fail-closed,
    # 而不能退回"未接入"的通用话术。
    assert "数据包损坏" in pptx.error


def test_over_twenty_mb_file_is_refused_not_truncated(tmp_path: Path, monkeypatch) -> None:
    project = _workspace(tmp_path, monkeypatch)
    (project / "huge.txt").write_bytes(b"x" * (MAX_FILE_BYTES + 1))
    result = invoke("company_office_analyze", "lab", {"project": PROJECT, "path": "huge.txt"})
    assert result.status == "error"
    assert "20MB" in result.error and "拒绝" in result.error


def test_non_utf8_text_refused(tmp_path: Path, monkeypatch) -> None:
    project = _workspace(tmp_path, monkeypatch)
    (project / "gbk.txt").write_bytes("中文".encode("gbk"))
    result = invoke("company_office_analyze", "lab", {"project": PROJECT, "path": "gbk.txt"})
    assert result.status == "error"
    assert "UTF-8" in result.error


def test_workspace_escape_and_missing_paths_fail_closed(tmp_path: Path, monkeypatch) -> None:
    _workspace(tmp_path, monkeypatch)
    for args in (
        {"project": PROJECT, "path": "../outside.txt"},
        {"project": PROJECT, "path": "missing.docx"},
        {"project": "", "path": "x.docx"},
        {"project": PROJECT, "path": ""},
        {"project": PROJECT, "path": "x.docx", "offset": -1},
    ):
        result = invoke("company_office_analyze", "lab", args)
        assert result.status in {"denied", "error"}, args
        assert result.status == "error" or result.decision == "deny"


def test_sign_preset_cannot_see_office_tool(tmp_path: Path, monkeypatch) -> None:
    project = _workspace(tmp_path, monkeypatch)
    (project / "notes.txt").write_text("hello", encoding="utf-8")
    denied = invoke("company_office_analyze", "sign", {"project": PROJECT, "path": "notes.txt"})
    assert denied.decision == "deny" and denied.status == "denied"


def test_module_level_error_fails_without_external_paths(tmp_path: Path, monkeypatch) -> None:
    project = _workspace(tmp_path, monkeypatch)
    (project / "broken.docx").write_bytes(b"not a zip")
    from company_agent.office_ingest import analyze

    with pytest.raises(OfficeIngestError) as caught:
        analyze({"project": PROJECT, "path": "broken.docx"})
    assert "docx" in str(caught.value)


def _minimal_pdf_bytes() -> bytes:
    # Honest ASCII-safe two-page body: the cap/read gate does not need CJK
    # glyphs inside a hand-built PDF; the real acceptance case is a real
    # PDF file, covered in the manual matrix later.
    page1 = b"BT /F1 12 Tf 72 720 Td (Page one body) Tj ET"
    page2 = b"BT /F1 12 Tf 72 720 Td (Page two body) Tj ET"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R 4 0 R] /Count 2 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 6 0 R >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 7 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length %d >>\nstream\n%s\nendstream" % (len(page1), page1),
        b"<< /Length %d >>\nstream\n%s\nendstream" % (len(page2), page2),
    ]
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    position = out.tell()
    for number, body in enumerate(objects, start=1):
        offsets.append(position)
        out.write(f"{number} 0 obj\n".encode() + body + b"\nendobj\n")
        position = out.tell()
    xref_at = out.tell()
    out.write(f"xref\n0 {len(objects) + 1}\n".encode())
    out.write(b"0000000000 65535 f \n")
    for offset in offsets:
        out.write(f"{offset:010d} 00000 n \n".encode())
    out.write(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF\n".encode())
    return out.getvalue()
