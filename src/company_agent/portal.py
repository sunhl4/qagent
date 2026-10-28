"""Company portal open facts: the workspace decides rendering, the model never fetches.

The only surface the agent carries for the cloud platform and HPC portals is the
same-origin relative route of the server-managed proxy (host.mjs:
``/company-workspace/portal/<kind>/``). This module holds that constant map and a
fail-closed open fact. Navigation is a workspace concern here; no page content,
absolute URL, credential or dispatch re-enters the model cycle — the contract
declares this capability read-only with zero network activity by construction.
"""

from __future__ import annotations

MAX_NOTE_CHARS = 120

_PORTALS: dict[str, dict[str, str]] = {
    "cloud": {
        "route": "/company-workspace/portal/cloud/",
        "title": "云平台",
        "note": "云平台门户由服务端代理承载；登录在页面内完成，作业事实仍走平台工具与回执。",
    },
    "hpc": {
        "route": "/company-workspace/portal/hpc/",
        "title": "超算",
        "note": "超算门户由服务端代理承载；页面登录与作业导航在门户内完成。",
    },
}


class PortalError(ValueError):
    """Invalid portal reference: nothing is opened and no request is made."""


def load_portal_sources() -> dict[str, object]:
    """Contract-facing source facts; constants only, so answers never fabricate."""
    return {
        "version": "1.0.0",
        "portals": [
            {"kind": kind, "title": row["title"], "route": row["route"]}
            for kind, row in _PORTALS.items()
        ],
    }


def _bounded_note(kind: str) -> str:
    return _PORTALS[kind]["note"][:MAX_NOTE_CHARS]


def open_portal(arguments: object) -> dict[str, object]:
    """Deliver one open fact: kind plus the proxied relative route.

    No dispatch happens here or anywhere in this capability; the kind gate is the
    only path, unknown kinds fail closed with a short generic error, and page
    health itself is honestly rendered by the workspace at the proxy route.
    """
    data = arguments if isinstance(arguments, dict) else {}
    kind = data.get("kind")
    row = _PORTALS.get(kind) if isinstance(kind, str) else None
    if row is None:
        raise PortalError("portal kind is unknown")
    return {"ok": True, "kind": kind, "route": row["route"], "note": _bounded_note(kind)}
