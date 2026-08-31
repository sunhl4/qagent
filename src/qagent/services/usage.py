from __future__ import annotations

from typing import Any, Mapping

from qagent.adapters.gov_store import append_jsonl, now_iso, read_jsonl, usage_path


def record_usage(
    *,
    tool: str,
    preset: str,
    status: str,
    decision: str,
) -> None:
    """Counts only. Never stores payload, args, or secrets. Must not break invoke."""
    try:
        append_jsonl(
            usage_path(),
            {
                "ts": now_iso(),
                "tool": tool,
                "preset": preset,
                "status": status,
                "decision": decision,
            },
        )
    except OSError:
        return


def list_usage() -> list[dict[str, Any]]:
    return read_jsonl(usage_path())


def usage_summary() -> dict[str, Any]:
    rows = list_usage()
    by_tool: dict[str, int] = {}
    by_status: dict[str, int] = {}
    for row in rows:
        tool = str(row.get("tool") or "")
        status = str(row.get("status") or "")
        by_tool[tool] = by_tool.get(tool, 0) + 1
        by_status[status] = by_status.get(status, 0) + 1
    return {"count": len(rows), "by_tool": by_tool, "by_status": by_status}


def usage_face() -> dict[str, Any]:
    summary = usage_summary()
    return {"count": summary["count"], "by_status": summary["by_status"]}
