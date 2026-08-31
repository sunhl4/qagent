#!/usr/bin/env python3
"""Stdlib-only verifier for qagent.receipt/v1. No qagent imports."""
from __future__ import annotations

import hashlib
import json
import sys


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def content_address(value: object) -> str:
    digest = hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()
    return "sha256:" + digest


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: verify_receipt.py receipt.json", file=sys.stderr)
        return 2
    payload = json.loads(open(argv[1], encoding="utf-8").read())
    if payload.get("schema") != "qagent.receipt/v1":
        print("FAIL schema")
        return 1
    given = payload.get("receipt_hash")
    body = {key: payload[key] for key in payload if key != "receipt_hash"}
    expected = content_address(body)
    if given != expected:
        print(f"FAIL hash given={given} expected={expected}")
        return 1
    if payload.get("signed") or payload.get("status") == "signed":
        handles = payload.get("handles") if isinstance(payload.get("handles"), dict) else {}
        sources = payload.get("sources") if isinstance(payload.get("sources"), list) else []
        if "qccd-twin" not in sources or not handles.get("twin_id"):
            print("FAIL unsigned cannot look signed")
            return 1
    print(f"PASS {expected}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
