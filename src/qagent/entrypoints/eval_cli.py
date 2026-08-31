from __future__ import annotations

import argparse
import sys

from qagent.services.eval_run import DEFAULT_EVAL_IDS, run_evals


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="qagent-eval")
    parser.add_argument(
        "--ids",
        default=",".join(DEFAULT_EVAL_IDS),
    )
    ns = parser.parse_args(argv)
    ids = [part.strip() for part in ns.ids.split(",") if part.strip()]
    failed = 0
    for result in run_evals(*ids):
        mark = "ok" if result.ok else "FAIL"
        extra = f"  {result.detail}" if result.detail else ""
        print(f"{mark}  {result.id}{extra}")
        if not result.ok:
            failed += 1
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
