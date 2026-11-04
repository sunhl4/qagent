"""Delivery naming gate: title/date/sequence discipline, never overwriting.

Spec source: ``WPS-SUITE-PORTING`` §3.7/§4.3 — the MeWork ``标题_YYYYMMDD_NN``
delivery naming, sequenced and non-overwriting, workspace-fenced.
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

from company_agent.invoke import invoke

WORKSPACE_ROOT_ENV = "COMPANY_AGENT_TOOL_WORKSPACE"
PROJECT = "dil01"


def _workspace(tmp_path: Path, monkeypatch) -> Path:
    root = tmp_path / "mount"
    project = root / PROJECT
    project.mkdir(parents=True)
    monkeypatch.setenv(WORKSPACE_ROOT_ENV, str(root))
    return project


def _docx_bytes(text: str = "交付正文") -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as package:
        package.writestr(
            "word/document.xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org'
            '/wordprocessingml/2006/main"><w:body/></w:document>',
        )
    return buffer.getvalue()


def _deliver(name: str, **extra):
    args = {"project": PROJECT, "path": name, "purpose": "测试写入"}
    args.update(extra)
    return invoke("company_office_deliver", "lab", args)


def test_default_title_and_sequence(tmp_path: Path, monkeypatch) -> None:
    project = _workspace(tmp_path, monkeypatch)
    (project / "演练报告_20260101.docx").write_bytes(_docx_bytes())

    first = _deliver("演练报告_20260101.docx")
    assert first.status == "ok", first.error
    payload = first.payload
    # 旧日期戳默认剥除:标题 = "演练报告"
    assert payload["source"] == "dil01/演练报告_20260101.docx"
    assert payload["path"].startswith("dil01/deliverables/演练报告_")
    assert payload["path"].endswith("_01.docx")
    assert payload["sequence"] == 1
    assert payload["bytes"] > 0 and len(payload["sha256"]) == 64

    second = _deliver("演练报告_20260101.docx")
    assert second.status == "ok", second.error
    assert second.payload["sequence"] == 2
    assert second.payload["path"].endswith("_02.docx")
    # 源文件未被触碰
    assert (project / "演练报告_20260101.docx").is_file()


def test_explicit_title_fills_the_name(tmp_path: Path, monkeypatch) -> None:
    project = _workspace(tmp_path, monkeypatch)
    (project / "draft.docx").write_bytes(_docx_bytes())

    result = _deliver("draft.docx", title="合规整改报告")
    assert result.status == "ok", result.error
    assert "/deliverables/" in result.payload["path"]
    assert "合规整改报告_" in result.payload["path"] and result.payload["path"].endswith(".docx")


def test_suffix_guard_and_missing_file(tmp_path: Path, monkeypatch) -> None:
    project = _workspace(tmp_path, monkeypatch)
    (project / "evil.exe").write_bytes(b"MZ")
    bad = _deliver("evil.exe")
    assert bad.status == "error" and "不是交付类型" in bad.error

    missing = _deliver("nowhere.docx")
    assert missing.status == "error" and "workspace file" in missing.error
    assert "尚未同步" in missing.error


def test_preview_does_not_copy(tmp_path: Path, monkeypatch) -> None:
    project = _workspace(tmp_path, monkeypatch)
    (project / "draft.docx").write_bytes(_docx_bytes())
    result = _deliver("draft.docx", mode="preview")
    assert result.status == "ok", result.error
    assert result.payload["mode"] == "preview"
    assert result.payload["sequence"] == 0
    assert result.payload["path"] == result.payload["source"]
    assert not (project / "deliverables").exists()


def test_title_allows_one_hundred_sixty_characters(tmp_path: Path, monkeypatch) -> None:
    project = _workspace(tmp_path, monkeypatch)
    (project / "draft.docx").write_bytes(_docx_bytes())
    title = "A" * 160
    result = _deliver("draft.docx", title=title)
    assert result.status == "ok", result.error
    assert title in result.payload["path"]
    too_long = _deliver("draft.docx", title="B" * 161)
    assert too_long.status == "error"


def test_title_rejects_path_separator(tmp_path: Path, monkeypatch) -> None:
    project = _workspace(tmp_path, monkeypatch)
    (project / "draft.docx").write_bytes(_docx_bytes())
    result = _deliver("draft.docx", title="../逃逸")
    assert result.status == "error" and "路径分隔符" in result.error
