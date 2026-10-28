#!/usr/bin/env python3
"""Check all managed Python, JavaScript and Shell files, excluding installed dependencies."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sources(directory: Path):
    for base, directories, files in os.walk(directory):
        directories[:] = [name for name in directories if name not in {"node_modules", "__pycache__"}]
        for name in sorted(files):
            yield Path(base) / name


def main() -> int:
    subprocess.run([sys.executable, "-m", "ruff", "check", "--no-cache", "src", "tests", "scripts"],
                   cwd=ROOT, check=True)
    runtime = Path(os.environ.get("COMPANY_AGENT_RUNTIME_DIR",
                   Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
                   / "unitqc-company-agent/dsh-runtime"))
    node = os.environ.get("COMPANY_AGENT_NODE", str(runtime / "node_modules/node/bin/node"))
    count = 0
    for root in ("src", "packages", "profiles", "scripts", "tests"):
        for path in sources(ROOT / root):
            if path.suffix == ".py":
                compile(path.read_bytes(), str(path.relative_to(ROOT)), "exec")
            elif path.suffix in {".js", ".mjs"}:
                subprocess.run([node, "--check", str(path)], check=True, capture_output=True)
            elif path.suffix == ".sh":
                subprocess.run(["bash", "-n", str(path)], check=True, capture_output=True)
            else:
                continue
            count += 1
    print(f"static checks passed: {count} managed source files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
