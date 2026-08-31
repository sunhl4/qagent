from __future__ import annotations

import argparse
import json
import sys

from qagent.services.handoff import HandoffError, create_handoff, list_handoffs
from qagent.services.knowledge import lookup
from qagent.services.replay import replay
from qagent.services.savepoint import enter_safe_mode, restore, snapshot
from qagent.services.usage import usage_summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="qagent-gov")
    parser.add_argument("cmd", choices=("handoff", "replay", "savepoint", "safe-mode", "usage", "knowledge"))
    parser.add_argument("--source", default="lab")
    parser.add_argument("--target", default="lab")
    parser.add_argument("--handles", default="{}")
    parser.add_argument("--intent", default="")
    parser.add_argument("--assignment", default="")
    parser.add_argument("--note", default="")
    parser.add_argument("--id", default="")
    parser.add_argument("--query", default="")
    ns = parser.parse_args(argv)
    try:
        if ns.cmd == "handoff":
            if ns.handles == "{}" and not ns.intent:
                payload = {"handoffs": list_handoffs()}
            else:
                payload = create_handoff(
                    source_preset=ns.source,
                    target_preset=ns.target,
                    handles=json.loads(ns.handles),
                    intent=ns.intent,
                ).to_public()
        elif ns.cmd == "replay":
            payload = replay(ns.assignment)
        elif ns.cmd == "savepoint":
            payload = restore(ns.id) if ns.id else snapshot(ns.note)
        elif ns.cmd == "safe-mode":
            payload = enter_safe_mode()
        elif ns.cmd == "knowledge":
            payload = lookup(ns.query)
        else:
            payload = usage_summary()
    except (HandoffError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
