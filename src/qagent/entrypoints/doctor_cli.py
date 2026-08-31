from __future__ import annotations

import argparse
import json
import sys

from qagent.services.doctor import probe


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="qagent-doctor")
    parser.add_argument("--store", action="store_true", help="also scan ELN / assignments")
    ns = parser.parse_args(argv)
    report = probe(scan_store=ns.store)
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
