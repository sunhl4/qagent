"""Copy company plugins and the Python kernel into a versioned install tree.

The desktop profile then points at that tree. It does not junction back to the
git checkout.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

VERSION = "0.2.1-company.1"
ROOT = Path(__file__).resolve().parents[1]
PACKAGES = (
    "company-agent-core",
    "company-agent-policy",
    "company-agent-quantum",
    "company-agent-hpc",
    "company-agent-device",
    "company-agent-latex",
    "company-agent-office",
    "company-agent-plan",
    "company-agent-research",
)
PRESET = ROOT / "desktop" / "company-agent-preset"
LOCAL = Path(os.environ["LOCALAPPDATA"]) / "UnitQC" / "company-agent"
PLUGIN_DEST = LOCAL / "plugins" / VERSION
RUNTIME_DEST = LOCAL / "runtime"
PROFILE = Path(os.environ["USERPROFILE"]) / ".dsh" / "profiles" / "desktop" / "package.json"
PROFILE_MODULES = Path(os.environ["USERPROFILE"]) / ".dsh" / "profiles" / "desktop" / "node_modules" / "@unitqc"


def _ignore(directory: str, names: list[str]) -> set[str]:
    skipped = {"node_modules", "__pycache__", ".pytest_cache", ".git"}
    return {name for name in names if name in skipped or name.endswith(".pyc")}


def _junction(link: Path, target: Path) -> None:
    if link.exists() or link.is_symlink():
        if link.is_dir() and not link.is_symlink():
            # A junction is a directory. Remove it without deleting the target.
            subprocess.check_call(["cmd", "/c", "rmdir", str(link)])
        else:
            link.unlink()
    subprocess.check_call(["cmd", "/c", "mklink", "/J", str(link), str(target)])


def _copy_package(source: Path, dest_root: Path) -> Path:
    dest = dest_root / source.name
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(source, dest, ignore=_ignore)
    manifest = dest / "package.json"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["version"] = VERSION
    manifest.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return dest


def stage_plugins() -> Path:
    if PLUGIN_DEST.exists():
        shutil.rmtree(PLUGIN_DEST)
    PLUGIN_DEST.mkdir(parents=True)
    staged: dict[str, Path] = {}
    for name in PACKAGES:
        staged[name] = _copy_package(ROOT / "packages" / name, PLUGIN_DEST)
    staged["company-agent-preset"] = _copy_package(PRESET, PLUGIN_DEST)
    core = staged["company-agent-core"]
    for name, path in staged.items():
        if name == "company-agent-core":
            continue
        manifest = json.loads((path / "package.json").read_text(encoding="utf-8"))
        if "@unitqc/company-agent-core" not in manifest.get("dependencies", {}):
            continue
        link = path / "node_modules" / "@unitqc" / "company-agent-core"
        link.parent.mkdir(parents=True, exist_ok=True)
        _junction(link, core)
    (PLUGIN_DEST / "manifest.json").write_text(
        json.dumps({"version": VERSION, "packages": sorted(staged)}, indent=2) + "\n",
        encoding="utf-8",
    )
    return PLUGIN_DEST


def stage_runtime() -> None:
    for name in ("src", "contracts"):
        dest = RUNTIME_DEST / name
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(ROOT / name, dest, ignore=_ignore)
    python = r"C:\Users\Administrator\anaconda3\envs\qc_chem\python.exe"
    (RUNTIME_DEST / "environment.json").write_text(
        json.dumps({"python": python, "dsh": "0.2.1-rc.5"}, indent=2) + "\n",
        encoding="utf-8",
    )


def retarget_profile(plugin_root: Path) -> None:
    payload = json.loads(PROFILE.read_text(encoding="utf-8"))
    dependencies = payload.setdefault("dependencies", {})
    names = [*(PACKAGES), "company-agent-preset"]
    for name in names:
        dependencies[f"@unitqc/{name}"] = "file:" + (plugin_root / name).as_posix()
    PROFILE.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    for name in names:
        _junction(PROFILE_MODULES / name, plugin_root / name)


def main() -> None:
    plugins = stage_plugins()
    stage_runtime()
    retarget_profile(plugins)
    print(plugins)
    print(RUNTIME_DEST)


if __name__ == "__main__":
    main()
