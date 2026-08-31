from __future__ import annotations

from typing import Any, Mapping

from qagent.adapters.support import new_id, try_http_json_url

_PERMISSION_NEVER = "never"


def _task_of(args: Mapping[str, Any]) -> str:
    return str(args.get("task") or "spi")


def _is_approved(args: Mapping[str, Any]) -> bool:
    return bool(args.get("approved") or args.get("approve"))


def _documented_app_server() -> str | None:
    """Official Codex is `app-server --stdio` via the dsh plugin. No HTTP URL is documented."""
    return None


def _oneshot_via_app_server(task: str, endpoint: str) -> dict[str, Any] | None:
    live = try_http_json_url(
        endpoint.rstrip("/"),
        "POST",
        {
            "task": task,
            "inherits_parent_context": False,
            "permission_mode": _PERMISSION_NEVER,
        },
    )
    if not live:
        return None
    text = live.get("text")
    if not isinstance(text, str) or not text:
        return None
    return {
        "text": text,
        "tests_green": bool(live.get("tests_green")),
        "tools_called": list(live.get("tools_called") or []),
        "needs_app_server": False,
        "not_wired": False,
        "inherits_parent_context": False,
        "permission_mode": _PERMISSION_NEVER,
    }


def _oneshot_not_wired(task: str) -> dict[str, Any]:
    return {
        "text": f"oneshot not wired for {task}; needs_app_server",
        "tests_green": False,
        "tools_called": [],
        "needs_app_server": True,
        "not_wired": True,
        "inherits_parent_context": False,
        "permission_mode": _PERMISSION_NEVER,
    }


def _file_change_descriptor(args: Mapping[str, Any]) -> dict[str, Any]:
    path = args.get("path") or args.get("file")
    item: dict[str, Any] = {
        "item": "fileChange",
        "status": "pending",
        "applied": False,
    }
    if isinstance(path, str) and path:
        item["path"] = path
    return item


class WiredCodex:
    """algo-only seams. Official one-shot never inherits parent context."""

    def oneshot(self, args: Mapping[str, Any]) -> dict[str, Any]:
        task = _task_of(args)
        endpoint = _documented_app_server()
        live = _oneshot_via_app_server(task, endpoint) if endpoint else None
        if live is not None:
            return live
        return _oneshot_not_wired(task)

    def attended(self, args: Mapping[str, Any]) -> dict[str, Any]:
        approved = _is_approved(args)
        payload: dict[str, Any] = {
            "thread_id": str(args.get("thread_id") or new_id("thr")),
            "status": "pending_file_change" if approved else "needs_approval",
            "approval_item": "fileChange",
            "applied": False,
            "diff": None,
            "inherits_parent_context": False,
            "no_diff_until_approved": not approved,
            "permission_mode": _PERMISSION_NEVER,
            "needs_app_server": True,
        }
        if approved:
            payload["file_change"] = _file_change_descriptor(args)
        return payload
