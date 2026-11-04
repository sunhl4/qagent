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
        "company_office_create", "lab", {"purpose": "测试写入",
            "project": PROJECT, "path": path, "content": {"text": content}}
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
        {"purpose": "测试写入", "project": PROJECT, "path": "old.docx", "content": {"blocks": [
            {"kind": "paragraph", "text": "共同开头。"},
            {"kind": "paragraph", "text": "旧句甲。"},
        ]}},
    )
    invoke(
        "company_office_create", "lab",
        {"purpose": "测试写入", "project": PROJECT, "path": "new.docx", "content": {"blocks": [
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
        {"purpose": "测试写入", "project": PROJECT, "path": "a.xlsx", "content": {"sheets": [
            {"name": "表1", "rows": [["头"], ["值"]]}
        ]}},
    )
    _text("b.md", "x")
    result = _compare("a.xlsx", "b.md")
    assert result.status == "error"
    assert "混合类型" in (result.error or "")
    (tmp_path / "mount" / PROJECT / "old.ppt").write_bytes(b"ppt")
    refused = _compare("old.ppt", "old.ppt")
    assert refused.status == "error"
    assert "不支持" in (refused.error or "")


def test_xlsx_rows_and_doc_text_compare(tmp_path: Path, monkeypatch) -> None:
    import struct

    from company_agent.office_binary import compound_file

    project = _workspace(tmp_path, monkeypatch)
    for name, value in (("a.xlsx", "甲"), ("b.xlsx", "乙")):
        made = invoke(
            "company_office_create", "lab",
            {"purpose": "测试写入", "project": PROJECT, "path": name, "content": {
                "sheets": [{"name": "表", "rows": [["列"], [value]]}]
            }},
        )
        assert made.status == "ok", made.error
    sheet = _compare("a.xlsx", "b.xlsx")
    assert sheet.status == "ok", sheet.error
    assert sheet.payload["kind"] == "xlsx"
    assert sheet.payload["identical"] is False

    def word(text: str) -> bytes:
        body = text + "\r"
        encoded = body.encode("utf-16-le")
        blob = bytearray(0x800 + len(encoded))
        struct.pack_into("<HH", blob, 0, 0xA5EC, 0x00C1)
        struct.pack_into("<H", blob, 0x0A, 0x0200)
        struct.pack_into("<I", blob, 0x4C, len(body))
        blob[0x800 : 0x800 + len(encoded)] = encoded
        plc = struct.pack("<II", 0, len(body)) + struct.pack("<HIH", 0, 0x800, 0)
        clx = bytes([0x02]) + struct.pack("<I", len(plc)) + plc
        table = bytearray(0x20 + len(clx))
        table[0x20 : 0x20 + len(clx)] = clx
        struct.pack_into("<II", blob, 0x1A2, 0x20, len(clx))
        return compound_file({"WordDocument": bytes(blob), "1Table": bytes(table)})

    (project / "a.doc").write_bytes(word("原文甲"))
    (project / "b.doc").write_bytes(word("原文乙"))
    binary = _compare("a.doc", "b.doc")
    assert binary.status == "ok", binary.error
    assert binary.payload["kind"] == "doc"
    assert binary.payload["identical"] is False


def test_empty_pdf_without_ocr_is_refused(tmp_path: Path, monkeypatch) -> None:
    pytest = __import__("pytest")
    pytest.importorskip("pypdf")
    project = _workspace(tmp_path, monkeypatch)
    page = b"BT ET"
    body = b"<< /Length %d >>\nstream\n%s\nendstream" % (len(page), page)
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R >>",
        body,
    ]
    out = __import__("io").BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for number, item in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(f"{number} 0 obj\n".encode() + item + b"\nendobj\n")
    xref = out.tell()
    out.write(f"xref\n0 {len(objects) + 1}\n".encode())
    out.write(b"0000000000 65535 f \n")
    for offset in offsets:
        out.write(f"{offset:010d} 00000 n \n".encode())
    out.write(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    (project / "blank.pdf").write_bytes(out.getvalue())
    (project / "blank-b.pdf").write_bytes(out.getvalue())
    result = invoke(
        "company_office_compare", "lab",
        {"project": PROJECT, "file_a": "blank.pdf", "file_b": "blank-b.pdf", "ocr_mode": "off"},
    )
    assert result.status == "error"
    assert "ocr_mode=off" in (result.error or "")
