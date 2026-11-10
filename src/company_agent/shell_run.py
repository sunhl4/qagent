"""Workspace-jailed local commands. No host shell, no grant, no remote submit."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

_ALLOWED = {"python", "pytest", "git", "node", "npm", "pnpm"}
_GIT = {"status", "diff", "log", "show", "add", "commit"}
_NPM = {"test", "run", "--version", "-v"}
_META = set("&|;<>`$\n\r")
_DENIED_WORDS = {"ssh", "scp", "curl", "wget", "powershell", "cmd", "wsl", "bash", "pwsh", "push"}
_SECRET_PARTS = ("TOKEN", "SECRET", "PASSWORD", "KEY", "CREDENTIAL", "AUTHORIZATION")
_AGENT_ENV = {
    "SSH_AUTH_SOCK",
    "SSH_AGENT_PID",
    "SSH_ASKPASS",
    "GIT_ASKPASS",
    "GIT_SSH",
    "GIT_SSH_COMMAND",
    "KRB5CCNAME",
}
_VERSION_FLAGS = {
    "python": {"--version", "-V"},
    "node": {"--version", "-v"},
    "pytest": {"--version"},
}
_SCRIPT_SUFFIXES = {
    "python": (".py",),
    "pytest": (".py",),
    "node": (".js", ".mjs", ".cjs"),
}
_NPM_PLACE = {"--prefix", "--dir", "-C"}
_GIT_CONFIG = {"-c", "--config", "--exec-path", "--no-index"}


class ShellError(ValueError):
    """The command is outside the local allowlist or the workspace."""


def _workspace() -> Path:
    raw = str(os.environ.get("COMPANY_AGENT_TOOL_WORKSPACE") or "").strip()
    root = Path(raw)
    if not raw or not root.is_absolute() or not root.is_dir():
        raise ShellError("workspace unavailable")
    return root.resolve()


def _name(token: str) -> str:
    base = Path(token).name.lower()
    if base.endswith(".exe"):
        base = base[:-4]
    return base


def _reject_text(token: str) -> None:
    if any(character in _META for character in token) or "\\" in token:
        raise ShellError("command metacharacters are refused")
    if ".." in Path(token).parts:
        raise ShellError("command path is refused")


def _cwd(root: Path, relative: str | None) -> Path:
    if not relative:
        return root
    _reject_text(relative)
    if relative.startswith("/") or (len(relative) > 1 and relative[1] == ":"):
        raise ShellError("command path is refused")
    target = (root / relative).resolve()
    if target != root and root not in target.parents:
        raise ShellError("command path is refused")
    if not target.is_dir():
        raise ShellError("command directory is unavailable")
    return target


def _environment() -> dict[str, str]:
    cleaned: dict[str, str] = {}
    for name, value in os.environ.items():
        upper = name.upper()
        if (
            upper.startswith("COMPANY_")
            or upper in _AGENT_ENV
            or any(part in upper for part in _SECRET_PARTS)
        ):
            continue
        cleaned[name] = value
    return cleaned


def _executable(root: Path, name: str) -> str:
    resolved = shutil.which(name)
    if not resolved:
        raise ShellError("command is not available")
    path = Path(resolved).resolve()
    if path == root or root in path.parents:
        raise ShellError("command is not available")
    return str(path)


def _outside(token: str) -> bool:
    return token.startswith("/") or token.startswith("\\") or ":" in token


def _inside(root: Path, relative: str) -> None:
    if _outside(relative):
        raise ShellError("command path is refused")
    target = (root / relative).resolve()
    if target != root and root not in target.parents:
        raise ShellError("command path is refused")


def _check(argv: list[str], root: Path) -> str:
    if not argv or any(not isinstance(item, str) or not item for item in argv):
        raise ShellError("command is not allowed")
    for item in argv:
        _reject_text(item)
    exe = _name(argv[0])
    if exe not in _ALLOWED or any(separator in argv[0] for separator in ("/", "\\")) or _outside(argv[0]):
        raise ShellError("command is not allowed")
    for item in argv[1:]:
        if _outside(item):
            raise ShellError("command path is refused")
    if exe == "git":
        if len(argv) < 2 or argv[1] not in _GIT or any(_name(item) in _DENIED_WORDS for item in argv[1:]):
            raise ShellError("git command is not allowed")
        for item in argv[2:]:
            flag = item.split("=", 1)[0]
            if flag in _GIT_CONFIG or flag.startswith("--exec-path") or flag.startswith("--config"):
                raise ShellError("git command is not allowed")
            if not item.startswith("-"):
                _inside(root, item)
    elif exe in {"npm", "pnpm"}:
        if len(argv) < 2 or argv[1] not in _NPM:
            raise ShellError("command is not allowed")
        for item in argv[2:]:
            flag = item.split("=", 1)[0]
            if flag in _NPM_PLACE:
                raise ShellError("command is not allowed")
            if not item.startswith("-"):
                _inside(root, item)
    elif exe in _SCRIPT_SUFFIXES:
        suffixes = _SCRIPT_SUFFIXES[exe]
        for item in argv[1:]:
            if item in _VERSION_FLAGS[exe]:
                continue
            if item.startswith("-") or not item.endswith(suffixes):
                raise ShellError("command is not allowed")
            _inside(root, item)
    return exe


def _clip(text: str, limit: int) -> tuple[str, bool]:
    encoded = text.encode("utf-8")
    if len(encoded) <= limit and len(text) <= limit:
        return text, False
    clipped = encoded[:limit].decode("utf-8", errors="ignore")
    return clipped[:limit], True


def run(arguments: dict) -> dict:
    argv = list(arguments["argv"])
    root = _workspace()
    exe = _check(argv, root)
    directory = _cwd(root, arguments.get("cwd"))
    timeout = arguments.get("timeout_seconds", 30)
    if isinstance(timeout, bool) or not isinstance(timeout, int) or not 1 <= timeout <= 60:
        raise ShellError("command timeout is invalid")
    command = [_executable(root, exe), *argv[1:]]
    try:
        completed = subprocess.run(
            command,
            cwd=directory,
            env=_environment(),
            shell=False,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        stdout, out_cut = _clip((exc.stdout or b"").decode("utf-8", errors="replace"), 16000)
        stderr, err_cut = _clip((exc.stderr or b"").decode("utf-8", errors="replace") + "\ntimeout", 4000)
        return {
            "ok": False,
            "exit_code": 124,
            "stdout": stdout,
            "stderr": stderr[:4000],
            "truncated": True or out_cut or err_cut,
        }
    except OSError as exc:
        raise ShellError("command is not available") from exc
    stdout, out_cut = _clip(completed.stdout.decode("utf-8", errors="replace"), 16000)
    stderr, err_cut = _clip(completed.stderr.decode("utf-8", errors="replace"), 4000)
    code = completed.returncode if 0 <= completed.returncode <= 255 else 1
    return {
        "ok": code == 0,
        "exit_code": code,
        "stdout": stdout,
        "stderr": stderr,
        "truncated": out_cut or err_cut,
    }
