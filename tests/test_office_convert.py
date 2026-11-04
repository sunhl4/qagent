"""Exit slice gate: local conversion with lease + three-way verification.

Spec source: ``WPS-SUITE-PORTING`` §4.6/§4.7 (L6) — no engine is a hard
honest failure, never a stand-in artifact; the child runs minimal-env arrayed
arguments; products must exist, be non-empty and carry the right magic.
The fake runner here writes a real-shaped artifact, so the verification
path is exercised end to end without LibreOffice installed.
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

from company_agent import office_convert
from company_agent.invoke import invoke

WORKSPACE_ROOT_ENV = "COMPANY_AGENT_TOOL_WORKSPACE"
PROJECT = "ship01"
SOFFICE_ENV = "COMPANY_AGENT_SOFFICE"


def _workspace(tmp_path: Path, monkeypatch) -> Path:
    root = tmp_path / "mount"
    project = root / PROJECT
    project.mkdir(parents=True)
    monkeypatch.setenv(WORKSPACE_ROOT_ENV, str(root))
    monkeypatch.delenv("COMPANY_AGENT_WORD_CMD", raising=False)
    monkeypatch.delenv(SOFFICE_ENV, raising=False)
    monkeypatch.setattr(office_convert, "_com_progid", lambda: None)
    return project


def test_darwin_save_as_script_uses_the_word_container(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(office_convert, "_platform", lambda: "darwin")
    monkeypatch.delenv("COMPANY_AGENT_WORD_CMD", raising=False)
    engine, kind = office_convert._resolve_engine()
    assert engine == "osascript" and kind == "apple"
    script = office_convert._apple_script(Path("a.doc"), Path("staging"), "docx")
    assert "~/Library/Containers/com.microsoft.Word/Data/Documents" in script
    assert "display alerts" in script
    assert "activate" not in script
    word = tmp_path / "word-cmd"
    word.write_bytes(b"stub")
    monkeypatch.setenv("COMPANY_AGENT_WORD_CMD", str(word))
    assert office_convert._resolve_engine()[1] == "word"


def _fake_engine(tmp_path: Path, monkeypatch) -> Path:
    """Configure COMPANY_AGENT_SOFFICE at a fake (but existing) engine path."""
    phony = tmp_path / "soffice-stub.uqt"
    phony.write_bytes(b"stub")
    monkeypatch.setenv(SOFFICE_ENV, str(phony))
    return phony


def _fake_runner(magic: bytes | None):
    def runner(command: list[str], cwd: str) -> tuple[int, bytes]:
        # command: [engine, --headless, --nologo, --nolockcheck,
        #           --convert-to, <fmt>, --outdir, <dir>, <source>]
        fmt = command[5]
        source = Path(command[8])
        stem = source.stem
        if fmt == "pdf":
            if magic is not None:
                (Path(cwd) / (stem + ".pdf")).write_bytes(magic + b"fake pdf body")
            return 0, b""
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as package:
            package.writestr(
                "word/document.xml",
                '<?xml version="1.0"?>'
                '<w:document xmlns:w="http://schemas.openxmlformats.org'
                "/wordprocessingml/2006/main\"><w:body/></w:document>",
            )
        Path(cwd).joinpath(stem + ".docx").write_bytes(buffer.getvalue())
        return 0, b""

    return runner


def _docx_bytes() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as package:
        package.writestr(
            "word/document.xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org'
            '/wordprocessingml/2006/main"><w:body/></w:document>',
        )
    return buffer.getvalue()


def test_docx_goes_to_pdf_with_configured_engine(tmp_path: Path, monkeypatch) -> None:
    project = _workspace(tmp_path, monkeypatch)
    (project / "report.docx").write_bytes(_docx_bytes())
    _fake_engine(tmp_path, monkeypatch)
    monkeypatch.setattr(office_convert, "_run", _fake_runner(b"%PDF-1.4 "))

    result = invoke("company_office_convert", "lab", {"purpose": "测试写入",
        "project": PROJECT, "path": "report.docx"})
    assert result.status == "ok", result.error
    payload = result.payload
    assert payload["convert"] == "pdf"
    assert payload["source"] == "ship01/report.docx"
    assert payload["path"] == "ship01/report.pdf"
    assert payload["engine"] == "soffice-stub.uqt"
    assert payload["overwrote"] is False
    assert (project / "report.pdf").read_bytes().startswith(b"%PDF-1.4 ")


def test_doc_goes_to_docx_and_is_verified_as_package(tmp_path: Path, monkeypatch) -> None:
    project = _workspace(tmp_path, monkeypatch)
    (project / "legacy.doc").write_bytes(b"\xd0\xcf\x11\xe0OLE-MASTER")
    _fake_engine(tmp_path, monkeypatch)
    monkeypatch.setattr(office_convert, "_run", _fake_runner(None))

    result = invoke("company_office_convert", "lab", {"purpose": "测试写入",
        "project": PROJECT, "path": "legacy.doc"})
    assert result.status == "ok", result.error
    assert result.payload["convert"] == "docx"
    assert result.payload["path"] == "ship01/legacy.docx"
    with zipfile.ZipFile(project / "legacy.docx") as package:
        _ = package.read("word/document.xml")


def test_auto_suffix_avoids_overwriting(tmp_path: Path, monkeypatch) -> None:
    project = _workspace(tmp_path, monkeypatch)
    (project / "old.pdf").write_bytes(b"%PDF-EXISTS")
    (project / "old.docx").write_bytes(_docx_bytes())
    _fake_engine(tmp_path, monkeypatch)
    monkeypatch.setattr(office_convert, "_run", _fake_runner(b"%PDF-1.4 "))

    result = invoke("company_office_convert", "lab", {"purpose": "测试写入",
        "project": PROJECT, "path": "old.docx"})
    assert result.status == "ok", result.error
    assert result.payload["path"] == "ship01/old_01.pdf"
    assert (project / "old.pdf").read_bytes() == b"%PDF-EXISTS"  # 原有产物未被破坏

    forced = invoke(
        "company_office_convert", "lab", {"purpose": "测试写入",
            "project": PROJECT, "path": "old.docx", "overwrite": True}
    )
    assert forced.status == "ok", forced.error
    assert forced.payload["path"] == "ship01/old.pdf"
    assert forced.payload["overwrote"] is True
    assert (project / "old.pdf").read_bytes().startswith(b"%PDF-1.4 ")


def test_missing_engine_is_a_named_hard_failure(tmp_path: Path, monkeypatch) -> None:
    project = _workspace(tmp_path, monkeypatch)
    (project / "report.docx").write_bytes(_docx_bytes())
    monkeypatch.delenv(SOFFICE_ENV, raising=False)
    monkeypatch.setattr(office_convert, "_which", lambda name: None)

    result = invoke("company_office_convert", "lab", {"purpose": "测试写入",
        "project": PROJECT, "path": "report.docx"})
    assert result.status == "error"
    assert "未找到无头转换引擎" in result.error
    assert (project / "report.pdf").exists() is False


def test_source_magic_and_suffix_guards(tmp_path: Path, monkeypatch) -> None:
    project = _workspace(tmp_path, monkeypatch)
    (project / "liar.docx").write_bytes(b"plain text, not a zip")
    (project / "sheet.xls").write_bytes(b"\xd0\xcf\x11\xe0")

    notzip = invoke("company_office_convert", "lab", {"purpose": "测试写入",
        "project": PROJECT, "path": "liar.docx"})
    assert notzip.status == "error" and "字节与其扩展名不符" in notzip.error

    unsupported = invoke("company_office_convert", "lab", {"purpose": "测试写入",
        "project": PROJECT, "path": "sheet.xls"})
    assert unsupported.status == "error" and "不是可转换类型" in unsupported.error


def test_failed_engine_run_refuses(tmp_path: Path, monkeypatch) -> None:
    project = _workspace(tmp_path, monkeypatch)
    (project / "report.docx").write_bytes(_docx_bytes())
    _fake_engine(tmp_path, monkeypatch)

    def failing_run(command: list[str], cwd: str) -> tuple[int, bytes]:
        return 3, b"soffice says no"

    monkeypatch.setattr(office_convert, "_run", failing_run)
    result = invoke("company_office_convert", "lab", {"purpose": "测试写入",
        "project": PROJECT, "path": "report.docx"})
    assert result.status == "error" and "退出码 3" in result.error
    assert (project / "report.pdf").exists() is False


def test_registered_word_save_as_beats_soffice(tmp_path: Path, monkeypatch) -> None:
    project = _workspace(tmp_path, monkeypatch)
    (project / "legacy.doc").write_bytes(b"\xd0\xcf\x11\xe0OLE-MASTER")
    _fake_engine(tmp_path, monkeypatch)
    monkeypatch.setattr(office_convert, "_com_progid", lambda: "Word.Application")

    def save(progid: str, source: Path, staging: Path, fmt: str) -> None:
        assert progid == "Word.Application"
        assert fmt == "docx"
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as package:
            package.writestr("word/document.xml", "<w:document/>")
        (staging / f"{source.stem}.docx").write_bytes(buffer.getvalue())

    monkeypatch.setattr(office_convert, "_com_save", save)
    result = invoke(
        "company_office_convert",
        "lab",
        {"purpose": "测试写入", "project": PROJECT, "path": "legacy.doc"},
    )
    assert result.status == "ok", result.error
    assert result.payload["engine"] == "Word.Application"
    assert result.payload["convert"] == "docx"
