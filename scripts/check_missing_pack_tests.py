#!/usr/bin/env python3
"""L1-04c CI gate: fail if missing_pack_tests(Path("tests")) is nonempty."""

from __future__ import annotations

from pathlib import Path

from qagent.services.benchmark import missing_pack_tests


def main() -> int:
    missing = missing_pack_tests(Path("tests"))
    print("missing_pack_tests", missing)
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
