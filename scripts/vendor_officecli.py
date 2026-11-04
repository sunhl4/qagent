"""Copy a pinned OfficeCLI build into resources/officecli/<platform>/.

The pin is 1.0.149. Pass ``--bin`` to install a local binary. ``--fetch``
downloads the release asset and fails honestly if the URL does not answer.
The binary is not committed by this script's mere presence.
"""
from __future__ import annotations

import argparse
import platform
import shutil
import sys
import urllib.request
from pathlib import Path

PIN = "1.0.149"
ROOT = Path(__file__).resolve().parents[1]


def platform_tag() -> str:
    system = {"win32": "win32", "darwin": "darwin", "linux": "linux"}.get(sys.platform, sys.platform)
    machine = platform.machine().lower()
    arch = "x64" if machine in {"amd64", "x86_64"} else machine or "x64"
    return f"{system}-{arch}"


def destination(tag: str) -> Path:
    name = "officecli.exe" if tag.startswith("win32") else "officecli"
    return ROOT / "resources" / "officecli" / tag / name


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", default=PIN)
    parser.add_argument("--bin")
    parser.add_argument("--fetch", action="store_true")
    parser.add_argument(
        "--url",
        default=f"https://github.com/iOfficeAI/OfficeCLI/releases/download/v{PIN}/officecli",
    )
    args = parser.parse_args()
    if args.version != PIN:
        print(f"refusing version {args.version}; pin is {PIN}", file=sys.stderr)
        return 2
    target = destination(platform_tag())
    target.parent.mkdir(parents=True, exist_ok=True)
    if args.bin:
        shutil.copyfile(args.bin, target)
    elif args.fetch:
        urllib.request.urlretrieve(args.url, target)  # noqa: S310 -- operator-supplied pin URL
    else:
        print(f"pass --bin or --fetch; destination would be {target}")
        return 2
    notice = target.parent / "NOTICE"
    if not notice.exists():
        notice.write_text(f"OfficeCLI {PIN}\n", encoding="utf-8")
    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
