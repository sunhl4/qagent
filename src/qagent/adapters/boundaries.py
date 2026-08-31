from __future__ import annotations

from pathlib import Path

from qagent.adapters.contracts import ROOT

_SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "wrappers", ".qagent", "apps"}
_SUFFIXES = {".py", ".ts", ".tsx", ".js"}


def _is_forbidden_line(line: str, roots: tuple[str, ...]) -> bool:
    stripped = line.split("#", 1)[0]
    stripped = stripped.split("//", 1)[0].strip()
    if not stripped:
        return False
    for root in roots:
        if stripped == f"import {root}" or stripped.startswith(f"import {root}."):
            return True
        if stripped.startswith(f"from {root} ") or stripped.startswith(f"from {root}."):
            return True
    return False


def scan_import_lines(*, root: Path, forbidden: tuple[str, ...]) -> list[str]:
    hits: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix not in _SUFFIXES:
            continue
        if any(part in _SKIP_DIRS for part in path.parts):
            continue
        rel = path.relative_to(root)
        if rel.parts[0] == "contracts":
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if _is_forbidden_line(line, forbidden):
                hits.append(f"{rel}:{lineno}:{line.strip()}")
    return hits
