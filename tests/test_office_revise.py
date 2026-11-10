"""Window saves write cells and Word text back into the existing file."""
from __future__ import annotations

import io
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from company_agent.office_revise import OfficeReviseError, revise_docx, revise_sheet, view_docx, write_docx_blocks

WORKSPACE = "COMPANY_AGENT_TOOL_WORKSPACE"
MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


def _plain(block: dict) -> dict:
    return {key: value for key, value in block.items() if key not in {"kind", "mixed", "truncated"}}


def _mount(tmp_path: Path, monkeypatch) -> Path:
    root = tmp_path / "mount"
    root.mkdir()
    monkeypatch.setenv(WORKSPACE, str(root))
    return root


def _xlsx(root: Path) -> None:
    sheet = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<worksheet xmlns="{MAIN}">'
        '<sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>名称</t></is></c>'
        '<c r="B1"><f>SUM(1,2)</f><v>3</v></c></row></sheetData></worksheet>'
    )
    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<workbook xmlns="{MAIN}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="设备对照" sheetId="1" r:id="rId1"/></sheets></workbook>'
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
        '</Relationships>'
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as package:
        package.writestr("xl/workbook.xml", workbook)
        package.writestr("xl/_rels/workbook.xml.rels", rels)
        package.writestr("xl/worksheets/sheet1.xml", sheet)
        package.writestr("xl/styles.xml", f'<?xml version="1.0" encoding="UTF-8"?><styleSheet xmlns="{MAIN}"/>')
    (root / "对照.xlsx").write_bytes(buffer.getvalue())


def _text(path: Path, ref: str) -> str:
    with zipfile.ZipFile(path) as package:
        root = ET.fromstring(package.read("xl/worksheets/sheet1.xml"))
    for cell in root.iter(f"{{{MAIN}}}c"):
        if cell.get("r") == ref:
            return "".join(node.text or "" for node in cell.iter(f"{{{MAIN}}}t")) or "".join(node.text or "" for node in cell.iter(f"{{{MAIN}}}v"))
    return ""


def test_sheet_save_replaces_a_cell_and_keeps_the_formula(tmp_path: Path, monkeypatch) -> None:
    root = _mount(tmp_path, monkeypatch)
    _xlsx(root)
    revised = revise_sheet({
        "path": "对照.xlsx",
        "purpose": "窗口里修改表格",
        "sheets": [{"name": "设备对照", "cells": [
            {"cell": "A1", "value": "设备"},
            {"cell": "C1", "value": 8},
        ]}],
    })
    assert revised["saved"] is True
    assert revised["cells"] == 2
    assert _text(root / "对照.xlsx", "A1") == "设备"
    assert _text(root / "对照.xlsx", "C1") == "8"
    with zipfile.ZipFile(root / "对照.xlsx") as package:
        xml = package.read("xl/worksheets/sheet1.xml")
    assert b"SUM(1,2)" in xml


def test_sheet_save_refuses_a_formula_cell(tmp_path: Path, monkeypatch) -> None:
    root = _mount(tmp_path, monkeypatch)
    _xlsx(root)
    before = (root / "对照.xlsx").read_bytes()
    try:
        revise_sheet({
            "path": "对照.xlsx",
            "purpose": "窗口里修改表格",
            "sheets": [{"name": "设备对照", "cells": [{"cell": "B1", "value": "9"}]}],
        })
    except ValueError as exc:
        assert "公式" in str(exc)
    else:
        raise AssertionError("formula cell was written")
    assert (root / "对照.xlsx").read_bytes() == before


def test_sheet_save_rejects_a_path_outside_the_workspace(tmp_path: Path, monkeypatch) -> None:
    _mount(tmp_path, monkeypatch)
    try:
        revise_sheet({"path": "../对照.xlsx", "purpose": "窗口里修改表格", "sheets": [{"name": "设备对照", "cells": [{"cell": "A1", "value": "x"}]}]})
    except ValueError as exc:
        assert "invalid" in str(exc) or "路径" in str(exc)
    else:
        raise AssertionError("escaped path was accepted")


def test_docx_save_tracks_one_paragraph(tmp_path: Path, monkeypatch) -> None:
    root = _mount(tmp_path, monkeypatch)
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:body><w:p><w:r><w:t>量子设备在线</w:t></w:r></w:p></w:body></w:document>'
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        '</Types>'
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as package:
        package.writestr("[Content_Types].xml", content_types)
        package.writestr("word/document.xml", document)
    (root / "说明.docx").write_bytes(buffer.getvalue())
    revised = revise_docx({"path": "说明.docx", "purpose": "窗口里修订正文", "find": "在线", "replace": "离线"})
    assert revised["saved"] is True
    assert revised["edited"] == 1
    with zipfile.ZipFile(root / "说明.docx") as package:
        xml = package.read("word/document.xml")
    assert "离线".encode() in xml
    assert b"w:ins" in xml or "w:ins".encode() in xml


def test_sheet_save_writes_bold_into_the_stylesheet(tmp_path: Path, monkeypatch) -> None:
    root = _mount(tmp_path, monkeypatch)
    _xlsx(root)
    revised = revise_sheet({
        "path": "对照.xlsx",
        "purpose": "窗口里修改表格",
        "sheets": [{"name": "设备对照", "cells": [{"cell": "A1", "value": "名称", "style": {"bold": True, "size": 14, "align": "center"}}]}],
    })
    assert revised["saved"] is True
    with zipfile.ZipFile(root / "对照.xlsx") as package:
        sheet = package.read("xl/worksheets/sheet1.xml")
        styles = package.read("xl/styles.xml")
    assert b'r="A1"' in sheet and b's="' in sheet
    assert b"<b" in styles or b":b" in styles
    assert b'val="14"' in styles


def test_docx_page_reads_and_writes_a_paragraph_and_a_table(tmp_path: Path, monkeypatch) -> None:
    root = _mount(tmp_path, monkeypatch)
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body><w:p><w:r><w:t>通知</w:t></w:r></w:p>"
        "<w:tbl><w:tr><w:tc><w:p><w:r><w:t>名称</w:t></w:r></w:p></w:tc>"
        "<w:tc><w:p><w:r><w:t>离子阱</w:t></w:r></w:p></w:tc></w:tr></w:tbl>"
        "</w:body></w:document>"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as package:
        package.writestr("word/document.xml", document)
    (root / "通知.docx").write_bytes(buffer.getvalue())
    viewed = view_docx({"path": "通知.docx", "purpose": "窗口里打开文档"})
    assert viewed["blocks"][0]["text"] == "通知"
    assert viewed["blocks"][1]["rows"][0][1]["paragraphs"][0]["text"] == "离子阱"
    cell = _plain(viewed["blocks"][1]["rows"][0][1]["paragraphs"][0])
    cell["text"] = "超导"
    cell["bold"] = True
    written = write_docx_blocks({"path": "通知.docx", "purpose": "窗口里修改文档", "blocks": [cell]})
    assert written["saved"] is True
    assert written["edited"] == 1
    again = view_docx({"path": "通知.docx", "purpose": "窗口里打开文档"})
    saved = again["blocks"][1]["rows"][0][1]["paragraphs"][0]
    assert saved["text"] == "超导"
    assert saved["bold"] is True
    assert again["blocks"][0]["text"] == "通知"


def test_docx_page_replaces_a_tracked_change(tmp_path: Path, monkeypatch) -> None:
    root = _mount(tmp_path, monkeypatch)
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body><w:p><w:r><w:t>量子设备</w:t></w:r>"
        '<w:del w:id="1"><w:r><w:delText>在线</w:delText></w:r></w:del>'
        '<w:ins w:id="2"><w:r><w:t>离线</w:t></w:r></w:ins></w:p></w:body></w:document>'
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as package:
        package.writestr("word/document.xml", document)
    (root / "窗口修订.docx").write_bytes(buffer.getvalue())
    viewed = view_docx({"path": "窗口修订.docx", "purpose": "窗口里打开文档"})
    block = _plain(viewed["blocks"][0])
    assert block["text"] == "量子设备离线"
    block["text"] = "量子设备检修"
    block["bold"] = True
    written = write_docx_blocks({"path": "窗口修订.docx", "purpose": "窗口里修改文档", "blocks": [block]})
    assert written["saved"] is True
    again = view_docx({"path": "窗口修订.docx", "purpose": "窗口里打开文档"})
    assert again["blocks"][0]["text"] == "量子设备检修"
    assert again["blocks"][0]["bold"] is True


def _docx(root: Path, name: str, body: str) -> None:
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{body}</w:body></w:document>"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as package:
        package.writestr("word/document.xml", document)
    (root / name).write_bytes(buffer.getvalue())


def test_docx_page_keeps_an_untouched_mixed_paragraph(tmp_path: Path, monkeypatch) -> None:
    root = _mount(tmp_path, monkeypatch)
    _docx(root, "说明.docx", (
        "<w:p><w:r><w:rPr><w:b/></w:rPr><w:t>粗</w:t></w:r>"
        '<w:r><w:rPr><w:sz w:val="28"/></w:rPr><w:t>细</w:t></w:r></w:p>'
        "<w:p><w:r><w:t>下一句</w:t></w:r></w:p>"
    ))
    viewed = view_docx({"path": "说明.docx", "purpose": "窗口里打开文档"})
    assert viewed["blocks"][0]["mixed"] is True
    assert viewed["blocks"][1]["mixed"] is False
    before = (root / "说明.docx").read_bytes()
    try:
        write_docx_blocks({"path": "说明.docx", "purpose": "窗口里修改文档", "blocks": [_plain(viewed["blocks"][0])]})
    except OfficeReviseError as exc:
        assert "没有需要保存的修改" in str(exc)
    else:
        raise AssertionError("unchanged paragraph was written")
    assert (root / "说明.docx").read_bytes() == before
    second = _plain(viewed["blocks"][1])
    second["text"] = "下一句改"
    written = write_docx_blocks({
        "path": "说明.docx", "purpose": "窗口里修改文档",
        "blocks": [_plain(viewed["blocks"][0]), second],
    })
    assert written["edited"] == 1
    again = view_docx({"path": "说明.docx", "purpose": "窗口里打开文档"})
    assert again["blocks"][0]["text"] == "粗细"
    assert again["blocks"][0]["mixed"] is True
    assert again["blocks"][1]["text"] == "下一句改"


def test_docx_page_refuses_a_truncated_paragraph(tmp_path: Path, monkeypatch) -> None:
    root = _mount(tmp_path, monkeypatch)
    _docx(root, "长文.docx", f"<w:p><w:r><w:t>{'字' * 1501}</w:t></w:r></w:p>")
    before = (root / "长文.docx").read_bytes()
    viewed = view_docx({"path": "长文.docx", "purpose": "窗口里打开文档"})
    assert viewed["blocks"][0]["truncated"] is True
    assert len(viewed["blocks"][0]["text"]) == 1500
    try:
        write_docx_blocks({"path": "长文.docx", "purpose": "窗口里修改文档", "blocks": [_plain(viewed["blocks"][0])]})
    except OfficeReviseError as exc:
        assert "1500" in str(exc)
    else:
        raise AssertionError("truncated paragraph was written")
    assert (root / "长文.docx").read_bytes() == before


def test_docx_page_reads_every_paragraph_in_a_cell(tmp_path: Path, monkeypatch) -> None:
    root = _mount(tmp_path, monkeypatch)
    _docx(root, "表.docx", (
        "<w:tbl><w:tr><w:tc>"
        "<w:p><w:r><w:t>上</w:t></w:r></w:p><w:p><w:r><w:t>下</w:t></w:r></w:p>"
        "</w:tc></w:tr></w:tbl>"
    ))
    viewed = view_docx({"path": "表.docx", "purpose": "窗口里打开文档"})
    paragraphs = viewed["blocks"][0]["rows"][0][0]["paragraphs"]
    assert [item["text"] for item in paragraphs] == ["上", "下"]
    lower = _plain(paragraphs[1])
    lower["text"] = "下改"
    written = write_docx_blocks({"path": "表.docx", "purpose": "窗口里修改文档", "blocks": [lower]})
    assert written["edited"] == 1
    again = view_docx({"path": "表.docx", "purpose": "窗口里打开文档"})
    assert [item["text"] for item in again["blocks"][0]["rows"][0][0]["paragraphs"]] == ["上", "下改"]


def test_sheet_save_keeps_unrelated_markup(tmp_path: Path, monkeypatch) -> None:
    root = _mount(tmp_path, monkeypatch)
    _xlsx(root)
    marked = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<worksheet xmlns="{MAIN}" xmlns:x14ac="http://schemas.microsoft.com/office/spreadsheetml/2009/9/ac" x14ac:keep="yes">'
        '<sheetData><row r="1" x14ac:dyDescent="0.25">'
        '<c r="A1" t="inlineStr"><is><t>名称</t></is></c>'
        '<c r="B1"><f>SUM(1,2)</f><v>3</v></c></row></sheetData></worksheet>'
    )
    original = (root / "对照.xlsx").read_bytes()
    buffer = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(original)) as source, zipfile.ZipFile(buffer, "w") as dest:
        for info in source.infolist():
            payload = marked.encode() if info.filename == "xl/worksheets/sheet1.xml" else source.read(info.filename)
            dest.writestr(info, payload)
    (root / "对照.xlsx").write_bytes(buffer.getvalue())
    styles_before = zipfile.ZipFile(root / "对照.xlsx").read("xl/styles.xml")
    revised = revise_sheet({
        "path": "对照.xlsx", "purpose": "窗口里修改表格",
        "sheets": [{"name": "设备对照", "cells": [{"cell": "A1", "value": "设备"}]}],
    })
    assert revised["saved"] is True
    with zipfile.ZipFile(root / "对照.xlsx") as package:
        xml = package.read("xl/worksheets/sheet1.xml")
        styles_after = package.read("xl/styles.xml")
    assert styles_after == styles_before
    assert b'x14ac:keep="yes"' in xml
    assert b'x14ac:dyDescent="0.25"' in xml
    assert b"SUM(1,2)" in xml
    assert "设备".encode() in xml


def test_docx_text_edit_keeps_font_color_and_the_other_paragraph(tmp_path: Path, monkeypatch) -> None:
    root = _mount(tmp_path, monkeypatch)
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
        ' xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml">'
        '<w:body>'
        '<w:p w14:paraId="AAA"><w:pPr><w:spacing w:after="200"/></w:pPr>'
        '<w:bookmarkStart w:id="0" w:name="title"/>'
        '<w:r><w:rPr><w:rFonts w:ascii="宋体"/><w:color w:val="FF0000"/><w:sz w:val="21"/></w:rPr><w:t>甲</w:t></w:r>'
        '<w:bookmarkEnd w:id="0"/></w:p>'
        '<w:p w14:paraId="BBB"><w:r><w:t>乙</w:t></w:r><w:r><w:pict>keep-shape</w:pict></w:r></w:p>'
        '</w:body></w:document>'
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as package:
        package.writestr("word/document.xml", document)
    (root / "说明.docx").write_bytes(buffer.getvalue())
    original = zipfile.ZipFile(root / "说明.docx").read("word/document.xml").decode()
    viewed = view_docx({"path": "说明.docx", "purpose": "窗口里打开文档"})
    first = _plain(viewed["blocks"][0])
    first["text"] = "甲改"
    written = write_docx_blocks({"path": "说明.docx", "purpose": "窗口里修改文档", "blocks": [first]})
    assert written["edited"] == 1
    updated = zipfile.ZipFile(root / "说明.docx").read("word/document.xml").decode()
    marker = 'w14:paraId="BBB"'
    assert original[:original.index(marker)] != updated[:updated.index(marker)]
    assert updated[updated.index(marker):] == original[original.index(marker):]
    assert "宋体" in updated and "FF0000" in updated and "bookmarkStart" in updated
    assert "keep-shape" in updated and "甲改" in updated
    assert "<w:jc" not in updated
    again = view_docx({"path": "说明.docx", "purpose": "窗口里打开文档"})
    assert again["blocks"][0]["text"] == "甲改"
    assert again["blocks"][0]["size"] == 21
    bold = _plain(again["blocks"][0])
    bold["bold"] = True
    write_docx_blocks({"path": "说明.docx", "purpose": "窗口里修改文档", "blocks": [bold]})
    styled = zipfile.ZipFile(root / "说明.docx").read("word/document.xml").decode()
    assert "宋体" in styled and "FF0000" in styled and "<w:b/>" in styled
    assert styled[styled.index(marker):] == original[original.index(marker):]


def test_encrypted_docx_names_the_lock(tmp_path: Path, monkeypatch) -> None:
    root = _mount(tmp_path, monkeypatch)
    (root / "加密.docx").write_bytes(b"\xe0\xa8\x91\xe7" + b"\x00" * 40 + b"Esafenet")
    try:
        view_docx({"path": "加密.docx", "purpose": "窗口里打开文档"})
    except OfficeReviseError as exc:
        assert "亿赛通" in str(exc)
    else:
        raise AssertionError("encrypted docx was opened")
