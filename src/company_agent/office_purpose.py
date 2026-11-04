"""Required purpose line for office write tools.

The sentence is recorded on the existing HMAC audit chain together with a
short argument summary. An unconfigured ledger skips the line.
"""

from __future__ import annotations


def take(args: dict) -> str:
    """Return the required purpose, or refuse when it is missing or too long."""

    raw = args.get("purpose")
    if not isinstance(raw, str) or not raw.strip() or len(raw) > 80:
        raise ValueError("purpose 必须是 1..80 字的一句说明")
    return raw.strip()


def audit(event: str, purpose: str, summary: dict) -> None:
    """Best-effort ledger line. A missing ledger does not change the write."""

    try:
        from company_agent import audit_chain  # noqa: PLC0415 -- optional ledger

        audit_chain.append(event, {"purpose": purpose, **summary})
    except Exception:  # noqa: BLE001 -- documented best-effort boundary
        return
