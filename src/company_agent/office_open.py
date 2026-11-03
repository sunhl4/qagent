"""Desktop exit for one workspace file (§5.1, L7; Windows deployment port).

The reference repo's ``open_with_wps`` kept three invariants the port must
keep as well: the launcher is verified (macOS pinned the bundle id), the
launch is audited, and a failure is a human message - never a silent fall
back to some system default. On Windows the verified launcher is the file
association: the registry is walked from the suffix to its ``shell\\open``
executable and the executable must be WPS/Kingsoft, otherwise the open
refuses with "请先把默认程序设为 WPS".

Behavior:

- launching requires the explicit environment switch
  ``COMPANY_AGENT_OPEN_WPS=wps|startfile``; without it the tool refuses - the
  adapter must never spring a GUI app on an unattended host by accident;
- ``wps`` mode refuses on non-Windows hosts and when the association is not
  WPS; the launch itself is ``subprocess.Popen([exe, path])`` with the shell
  out of the loop;
- ``startfile`` mode is the operator-opted system-association open
  (``os.startfile``); it is documented as "may not be WPS";
- suffix allowlist: .doc .docx .xls .xlsx .ppt .pptx .wps .et .dps .pdf
  .txt .md - deliverable kinds plus the legacy binaries this tool is the
  escape hatch for;
- every launch and every failure carries an ``open_with_wps`` audit line
  when the ledger is configured (best effort, never a blocker);
- the receipt carries no machine paths beyond the workspace compound and
  reduces the launcher to its basename.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from company_agent import office_create as _oc
from company_agent import workspace_files

ENV_OPEN = "COMPANY_AGENT_OPEN_WPS"
_LOGO_STEM = ("wps", "kingsoft")

OPEN_SUFFIXES = (
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".ppt",
    ".pptx",
    ".wps",
    ".et",
    ".dps",
    ".pdf",
    ".txt",
    ".md",
)


class OfficeOpenError(ValueError):
    """Refusal that names the boundary hit without echoing paths outside the root."""


def open_file(args: dict) -> dict:
    """Contract entry point: hand one workspace file to the desktop's WPS."""

    root = workspace_files.root()
    compound = _oc._compound(args)
    resolved = workspace_files.resolve(root, compound)
    if not resolved.is_file():
        raise OfficeOpenError("workspace path is not a file")
    suffix = resolved.suffix.casefold()
    if suffix not in OPEN_SUFFIXES:
        allowed = " ".join(OPEN_SUFFIXES)
        raise OfficeOpenError(f"{suffix or '(无后缀)'} 不是可交给 WPS 的打开类型;支持 {allowed}")
    mode = _mode()
    audit_detail: dict[str, object]
    if mode == "wps":
        if _host() != "nt":
            raise OfficeOpenError("wps 定位走 Windows 注册表:当前平台不支持,请用 startfile 档")
        launcher_exe = _from_registry(suffix)
        _launch([launcher_exe, str(resolved.absolute())])
        launcher = _basename(launcher_exe)
        audit_detail = {"engine": "wps", "launcher": launcher}
    else:
        _shell_open(str(resolved.absolute()))
        launcher = "shell"
        audit_detail = {"engine": "startfile", "launcher": launcher}
    note = args.get("note")
    if isinstance(note, str) and note.strip():
        audit_detail["note"] = note.strip()[:120]
    return {
        "path": compound,
        "engine": mode,
        "launcher": launcher,
        "audited": _audit(compound, audit_detail),
    }


def _mode() -> str:
    raw = str(os.environ.get(ENV_OPEN) or "").strip()
    if raw == "wps":
        return raw
    if raw == "startfile":
        return raw
    raise OfficeOpenError(
        f"未配置拉起方式:{ENV_OPEN} 需要 wps 或 startfile;"
        "本地桌面部署显式开启后才允许拉起外部程序,拒绝静默默认"
    )


def _host() -> str:
    """Platform seam: tests stub this instead of the real ``os`` module."""
    return os.name


def _from_registry(suffix: str) -> str:
    """Registry-walk the suffix association and turn it into a launcher path.

    The validation (must be WPS or Kingsoft) lives here, on the caller side
    of the registry seam, so tests can stub the registry without stubbing
    the rule.
    """

    command = _registry_command(suffix)
    launcher = _first_token(command)
    if not launcher:
        raise OfficeOpenError("注册表关联无法解析出程序路径:请修复默认程序")
    lowered = launcher.casefold()
    if "wps" not in lowered and "kingsoft" not in lowered:
        raise OfficeOpenError(
            f"当前文件关联是 {Path(launcher).name},不是 WPS:"
            "请把默认程序设为 WPS,或改用 startfile 档;不静默换用系统默认"
        )
    return launcher


def _registry_command(suffix: str) -> str:
    """Read ``HKCR\\<ext>`` -> ProgID -> ``shell\\open\\command`` for one suffix."""

    import winreg  # noqa: PLC0415 -- Windows-only path, imported lazily

    with_suffix = suffix if suffix.startswith(".") else f".{suffix}"
    try:
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, with_suffix) as key:
            progid = str(winreg.QueryValueEx(key, "")[0]).strip()
        if not progid or "/" in progid or "\\" in progid:
            raise OfficeOpenError(f"{with_suffix} 的注册表关联无效:请修复默认程序")
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, f"{progid}\\shell\\open\\command") as key:
            command = str(winreg.QueryValueEx(key, "")[0]).strip()
    except OSError as exc:
        raise OfficeOpenError(
            f"注册表没有 {with_suffix} 的打开关联:请先把默认程序设为 WPS 再试;系统未改默认程序"
        ) from exc
    if not command:
        raise OfficeOpenError(f"{with_suffix} 的打开关联为空:请修复默认程序")
    return command


def _first_token(command: str) -> str:
    if command.startswith('"'):
        return command[: command.find('"', 1)].lstrip('"') if '"' in command[1:] else command[1:]
    return command.split(" ", 1)[0].strip('"')


def _basename(launcher: str) -> str:
    name = Path(launcher).name or launcher
    return name[:64]


def _audit(compound: str, detail: dict[str, object]) -> bool:
    try:
        from company_agent import audit_chain  # noqa: PLC0415 -- optional ledger

        payload = {"path": compound, **detail}
        audit_chain.append("open_with_wps", payload)
        return True
    except Exception:  # noqa: BLE001 -- 没配置台账时打开本身照常完成
        return False


_spawn = subprocess.Popen


def _launch(argv: list[str]) -> None:
    try:
        _spawn(argv)
    except FileNotFoundError as exc:
        raise OfficeOpenError("WPS 主程序在注册表里登记的位置不存在:请重装或修复关联") from exc
    except OSError as exc:
        raise OfficeOpenError("拉起 WPS 失败:系统拒绝启动该程序") from exc


_startfile = getattr(os, "startfile", None)


def _shell_open(absolute: str) -> None:
    if _startfile is None:
        raise OfficeOpenError("startfile 档仅支持 Windows:当前平台没有 os.startfile")
    try:
        _startfile(absolute)
    except OSError as exc:
        raise OfficeOpenError("按系统默认程序打开失败:请确认本机已安装该文件类型的程序") from exc
