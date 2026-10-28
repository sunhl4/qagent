"""Rebuild a private test environment from hash-locked wheels already in pip's local cache."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from email.parser import BytesParser
from pathlib import Path

from packaging.tags import parse_tag, sys_tags
from packaging.utils import canonicalize_name, parse_wheel_filename

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = Path(__file__).resolve().parent
LOCK = ROOT / "runtime/python-dev.lock"
CACHE = Path.home() / ".cache/pip/http-v2"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--venv", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if not args.venv.is_absolute() or args.venv.exists():
        parser.error("venv must be a new absolute path")
    target = args.report
    if target.exists():
        parser.error("evidence already exists")
    lock = LOCK.read_bytes()
    entries = re.findall(r"^([\w.-]+)==([^\s\\]+)(.*?)(?=^\w[\w.-]*==|\Z)",
                         lock.decode(), re.MULTILINE | re.DOTALL)
    pins = {canonicalize_name(name): {"version": version, "hashes": set(re.findall(
        r"--hash=sha256:([a-f0-9]{64})", body))} for name, version, body in entries}
    tags = set(sys_tags())
    matches = {}
    for body in sorted(CACHE.rglob("*.body")):
        with body.open("rb") as handle:
            if handle.read(4) != b"PK\x03\x04":
                continue
        try:
            with zipfile.ZipFile(body) as archive:
                metadata = [name for name in archive.namelist()
                            if name.endswith(".dist-info/METADATA") and len(name.split("/")) == 2]
                if len(metadata) != 1:
                    continue
                meta = BytesParser().parsebytes(archive.read(metadata[0]))
                name = canonicalize_name(meta["Name"])
                if name not in pins or name in matches or meta["Version"] != pins[name]["version"]:
                    continue
                wheel = BytesParser().parsebytes(archive.read(metadata[0].removesuffix("METADATA") + "WHEEL"))
                wheel_tags = wheel.get_all("Tag", [])
                compatible = [tag for tag in wheel_tags if parse_tag(tag) & tags]
                if not compatible:
                    continue
                filename = f"{name.replace('-', '_')}-{meta['Version']}-{compatible[0]}.whl"
                if not (parse_wheel_filename(filename)[3] & tags):
                    continue
            digest = hashlib.sha256(body.read_bytes()).hexdigest()
            if digest in pins[name]["hashes"]:
                matches[name] = {"version": meta["Version"], "sha256": digest,
                                 "cache": str(body), "filename": filename}
        except (zipfile.BadZipFile, KeyError, ValueError):
            continue
    report = {"format": "company-agent-offline-environment/1", "network_used": False,
              "lock_sha256": hashlib.sha256(lock).hexdigest(), "wheels": matches,
              "missing": sorted(set(pins) - set(matches)), "venv": str(args.venv)}
    commands = []
    report["commands"] = commands
    if report["missing"]:
        report["status"] = "blocked"
    else:
        wheelhouse = args.venv.parent / (args.venv.name + "-wheelhouse")
        wheelhouse.mkdir(mode=0o700)
        for row in matches.values():
            destination = wheelhouse / row["filename"]
            shutil.copyfile(row["cache"], destination)
            assert hashlib.sha256(destination.read_bytes()).hexdigest() == row["sha256"]
        env = {"PATH": "/usr/bin:/bin", "HOME": str(Path.home()), "LANG": "C.UTF-8",
               "PIP_NO_INDEX": "1", "PIP_DISABLE_PIP_VERSION_CHECK": "1",
               "PIP_CONFIG_FILE": os.devnull, "PYTHONDONTWRITEBYTECODE": "1"}
        for command in (
            ["/usr/bin/python3", "-I", "-m", "venv", str(args.venv)],
            [str(args.venv / "bin/python"), "-I", "-m", "pip", "install", "--no-index",
             "--only-binary=:all:", "--require-hashes", "--find-links", str(wheelhouse), "-r", str(LOCK)],
            [str(args.venv / "bin/python"), "-I", "-m", "pip", "check"],
            [str(args.venv / "bin/python"), "-I", "-m", "pip", "freeze", "--all"],
        ):
            result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=180, check=False)
            commands.append({"command": command, "exit_code": result.returncode,
                             "stdout": result.stdout, "stderr": result.stderr})
            if result.returncode:
                break
        report["status"] = "passed" if len(commands) == 4 and not commands[-1]["exit_code"] else "failed"
    with target.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print(json.dumps({"status": report["status"], "missing": report["missing"],
                      "verified_wheels": len(matches), "venv": str(args.venv)}))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
