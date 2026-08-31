from __future__ import annotations

import argparse
import json
from dataclasses import asdict

from qagent.adapters.preset import active_preset
from qagent.services.invoke import invoke
from qagent.services.policy import decide


def _args(raw: str) -> dict:
    if not raw:
        return {}
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("args must be a JSON object")
    return parsed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="qagent-invoke")
    parser.add_argument("action", choices=("decide", "invoke"))
    parser.add_argument("--tool", required=True)
    parser.add_argument("--preset", default=active_preset())
    parser.add_argument("--args", default="{}")
    parser.add_argument("--approved", action="store_true")
    ns = parser.parse_args(argv)
    args = _args(ns.args)
    if ns.action == "decide":
        print(json.dumps({"decision": decide(ns.tool, ns.preset, args)}))
        return 0
    result = invoke(ns.tool, ns.preset, args, approved=ns.approved)
    payload = asdict(result)
    print(json.dumps(payload, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
