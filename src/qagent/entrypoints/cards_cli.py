from __future__ import annotations

import argparse
import json

from qagent.services.cards import pes_card, signoff_card


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="qagent-cards")
    parser.add_argument("kind", choices=("pes", "signoff"))
    ns = parser.parse_args(argv)
    payload = pes_card() if ns.kind == "pes" else signoff_card()
    print(json.dumps(payload, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
