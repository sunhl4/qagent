#!/usr/bin/env python3
"""H-01a live probe. Prints codes only. Does not mint twin_id. Does not print secrets."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from qagent.adapters.dsh_session import DshSessionClient, DshSessionError, dsh_base_url


def main() -> int:
    client = DshSessionClient(timeout=5.0)
    print(f"base {dsh_base_url()}")
    try:
        listed = client.rpc("session.list", {})
        print("session.list ok items", len(listed.get("items") or []))
    except DshSessionError as exc:
        print("session.list", exc.code, str(exc).splitlines()[0])
        return 1
    try:
        session_id = client.create()
        print("session.create ok", session_id[:16])
        return 0
    except DshSessionError as exc:
        print("session.create", exc.code)
        print(str(exc).splitlines()[0])
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
