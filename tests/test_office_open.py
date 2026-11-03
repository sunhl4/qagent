"""Desktop exit gate: open_in_wps modes, association check, audit line.

Spec source: ``WPS-SUITE-PORTING`` §5.1 (L7) — verified launcher, audit line,
human failure text, no silent fallback; launching is opt-in at the machine
level. The registry and the launch seams are monkeypatched, so the tests run
without WPS installed and without touching the real file associations.
"""
from __future__ import annotations

from pathlib import Path

from company_agent import office_open
from company_agent.invoke import invoke

WORKSPACE_ROOT_ENV = "COMPANY_AGENT_TOOL_WORKSPACE"
PROJECT = "desk01"
OPEN_ENV = "COMPANY_AGENT_OPEN_WPS"
AUDIT_LOG_ENV = "COMPANY_AGENT_AUDIT_LOG"
AUDIT_KEY_ENV = "COMPANY_AGENT_AUDIT_KEY"


def _workspace(tmp_path: Path, monkeypatch) -> Path:
    root = tmp_path / "mount"
    project = root / PROJECT
    project.mkdir(parents=True)
    monkeypatch.setenv(WORKSPACE_ROOT_ENV, str(root))
    return project


def _audit(tmp_path: Path, monkeypatch) -> Path:
    ledger = tmp_path / "audit.jsonl"
    monkeypatch.setenv(AUDIT_LOG_ENV, str(ledger))
    monkeypatch.setenv(AUDIT_KEY_ENV, "k" * 48)
    return ledger


def test_unset_mode_refuses_before_anything(tmp_path: Path, monkeypatch) -> None:
    project = _workspace(tmp_path, monkeypatch)
    (project / "draft.docx").write_bytes(b"PK\x03\x04")
    monkeypatch.delenv(OPEN_ENV, raising=False)

    result = invoke("company_office_open", "lab", {"project": PROJECT, "path": "draft.docx"})
    assert result.status == "error"
    assert "未配置拉起方式" in result.error and OPEN_ENV in result.error


def test_wps_mode_launches_registry_verified_launcher(tmp_path: Path, monkeypatch) -> None:
    project = _workspace(tmp_path, monkeypatch)
    ledger = _audit(tmp_path, monkeypatch)
    (project / "draft.docx").write_bytes(b"PK\x03\x04")
    monkeypatch.setenv(OPEN_ENV, "wps")
    monkeypatch.setattr(
        office_open,
        "_registry_command",
        lambda suffix: r'"C:\WPS Office\wps.exe" /prom "%1"',
    )
    launched: list[list[str]] = []
    monkeypatch.setattr(office_open, "_spawn", lambda argv: launched.append(argv) or object())

    result = invoke(
        "company_office_open",
        "lab",
        {"project": PROJECT, "path": "draft.docx", "note": "交付给法务"},
    )
    assert result.status == "ok", result.error
    payload = result.payload
    assert payload["engine"] == "wps"
    assert payload["launcher"] == "wps.exe"  # 机器路径不回显,只回 basename
    assert payload["path"] == "desk01/draft.docx"
    assert payload["audited"] is True
    assert launched and launched[0][0].endswith("wps.exe")
    assert launched[0][1].endswith("draft.docx")
    assert ledger.is_file()

    rows = [row for row in ledger.read_text(encoding="utf-8").splitlines() if row]
    assert any("open_with_wps" in row for row in rows)


def test_non_wps_association_refuses_instead_of_fallback(tmp_path: Path, monkeypatch) -> None:
    project = _workspace(tmp_path, monkeypatch)
    _audit(tmp_path, monkeypatch)
    (project / "sheet.xlsx").write_bytes(b"PK\x03\x04")
    monkeypatch.setenv(OPEN_ENV, "wps")
    monkeypatch.setattr(
        office_open,
        "_registry_command",
        lambda suffix: r'"C:\Programs\excel.exe" "%1"',
    )
    launched: list[list[str]] = []
    monkeypatch.setattr(office_open, "_spawn", lambda argv: launched.append(argv) or object())

    result = invoke("company_office_open", "lab", {"project": PROJECT, "path": "sheet.xlsx"})
    assert result.status == "error"
    assert "不是 WPS" in result.error and "不静默换用系统默认" in result.error
    assert launched == []


def test_missing_association_names_the_registry(tmp_path: Path, monkeypatch) -> None:
    project = _workspace(tmp_path, monkeypatch)
    (project / "draft.docx").write_bytes(b"PK\x03\x04")
    monkeypatch.setenv(OPEN_ENV, "wps")
    import winreg

    def missing(*key: object):
        raise OSError("registry absent")

    monkeypatch.setattr(winreg, "OpenKey", missing)
    result = invoke("company_office_open", "lab", {"project": PROJECT, "path": "draft.docx"})
    assert result.status == "error"
    assert "注册表没有" in result.error


def test_wps_mode_requires_windows_host(tmp_path: Path, monkeypatch) -> None:
    project = _workspace(tmp_path, monkeypatch)
    (project / "draft.docx").write_bytes(b"PK\x03\x04")
    monkeypatch.setenv(OPEN_ENV, "wps")
    # 平台接缝:stub _host(),不动全局 os 模块(pytest 自己也要用它)。
    monkeypatch.setattr(office_open, "_host", lambda: "posix")

    result = invoke("company_office_open", "lab", {"project": PROJECT, "path": "draft.docx"})
    assert result.status == "error" and "Windows 注册表" in result.error


def test_startfile_mode_uses_system_association_and_says_so(tmp_path: Path, monkeypatch) -> None:
    project = _workspace(tmp_path, monkeypatch)
    (project / "note.md").write_bytes(b"# hi")
    ledger = _audit(tmp_path, monkeypatch)
    monkeypatch.setenv(OPEN_ENV, "startfile")
    opened: list[str] = []
    monkeypatch.setattr(office_open, "_startfile", lambda path: opened.append(path))

    result = invoke("company_office_open", "lab", {"project": PROJECT, "path": "note.md"})
    assert result.status == "ok", result.error
    payload = result.payload
    assert payload["engine"] == "startfile"
    assert payload["launcher"] == "shell"
    assert payload["audited"] is True
    assert opened and opened[0].endswith("note.md")
    assert ledger.is_file()


def test_suffix_allowlist_and_missing_file(tmp_path: Path, monkeypatch) -> None:
    project = _workspace(tmp_path, monkeypatch)
    (project / "evil.exe").write_bytes(b"MZ")
    (project / "gone.docx").write_bytes(b"")

    monkeypatch.setenv(OPEN_ENV, "startfile")
    bad_kind = invoke("company_office_open", "lab", {"project": PROJECT, "path": "evil.exe"})
    assert bad_kind.status == "error" and "不是可交给 WPS 的打开类型" in bad_kind.error

    missing = invoke("company_office_open", "lab", {"project": PROJECT, "path": "nowhere.docx"})
    assert missing.status == "error" and "workspace file" in missing.error


def test_audit_failure_does_not_block_the_open(tmp_path: Path, monkeypatch) -> None:
    project = _workspace(tmp_path, monkeypatch)
    (project / "note.md").write_bytes(b"# hi")
    monkeypatch.setenv(OPEN_ENV, "startfile")
    monkeypatch.delenv(AUDIT_LOG_ENV, raising=False)
    monkeypatch.setattr(office_open, "_startfile", lambda path: None)

    result = invoke("company_office_open", "lab", {"project": PROJECT, "path": "note.md"})
    assert result.status == "ok", result.error
    assert result.payload["audited"] is False
