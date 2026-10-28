#!/usr/bin/env python3
"""Read-only acceptance probe for the company Overleaf git-bridge.

The adapter ships ``company_latex_overleaf_pull`` / ``push`` / ``status``
under the ``COMPANY_AGENT_OVERLEAF_*`` environment contract; this probe lets
deployment verify that contract against the real instance without touching
any project file:

1. config_shape - base URL, credential and optional project allowlist parse
   exactly as the adapter's ``_configured`` requires;
2. authentication - ``git ls-remote`` against the derived bridge URL succeeds
   (live; the fixed username ``git`` plus token authenticate);
3. branch_present - the requested branch exists on the online head (live);
4. refs_shape - the online ref list stays bounded and well formed (live).

Credential contract: the token is read from the adapter's
``COMPANY_AGENT_OVERLEAF_GIT_TOKEN`` environment variable; the optional
``COMPANY_AGENT_OVERLEAF_PROJECT_ALLOWLIST`` limits which projects the
adapter may touch (an empty variable means every project is allowed).

Rules (same spirit as probe_model_service):
- offline by default: without ``--live`` nothing is sent; the evidence file
  records ``executed: false``;
- read-only transport: only ``ls-remote`` runs; no clone, fetch, push or any
  project mutation is attempted; the workspace is never read;
- the token exists only in memory as child-process URL userinfo; every
  evidence field is scrubbed against the token and the base URL;
- the online head SHA is recorded as an observable fact. Prompts, file
  contents, whole ref listings and any credential never enter the evidence.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from company_agent.overleaf_sync import (  # noqa: E402
    PlanError,
    _configured,
    _remote_url,
    _run_git,
    _scrub,
)

FORMAT = "company-overleaf-git-probe/1.0"
MAX_REFS = 1000


def _ls_remote_ref_listing(remote: str, *, token: str, base_url: str) -> list[tuple[str, str]]:
    """One bounded read-only ``ls-remote``; returns (sha, ref) pairs."""
    stdout = _run_git(["ls-remote", "--heads", remote], token=token, base=base_url)
    rows: list[tuple[str, str]] = []
    for line in _scrub(stdout, token, base_url).splitlines():
        parts = line.strip().split("\t", 2)
        ref = parts[1].strip() if len(parts) >= 2 else ""
        if (
            ref.startswith("refs/heads/")
            and len(parts[0]) == 40
            and all(character in "0123456789abcdef" for character in parts[0])
            and (parts[0], ref) not in rows
        ):
            rows.append((parts[0], ref))
    if len(rows) > MAX_REFS:
        raise PlanError("overleaf project ref listing exceeds the bounded size")
    return rows


def _ls_remote(base_url: str, token: str, project_id: str) -> list[tuple[str, str]]:
    remote = _remote_url(base_url, token, project_id)
    return _ls_remote_ref_listing(remote, token=token, base_url=base_url)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="probe_overleaf_git")
    parser.add_argument("--base-url", required=True,
                        help="self-hosted Overleaf base url, same as COMPANY_AGENT_OVERLEAF_GIT_BASE")
    parser.add_argument("--project-id", required=True,
                        help="hex project id whose git bridge is probed")
    parser.add_argument("--branch", default="main")
    parser.add_argument("--provider", default="ayakaleaf")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--output", default=str(ROOT / "docs" / "evidence" / "overleaf-git-probe.json"))
    args = parser.parse_args(argv)

    checks: list[dict[str, object]] = []
    executed = args.live
    config: dict[str, object] = {}
    try:
        base, token, allowed = _configured_with_base(args)
        config = {
            "base_host": _safe_host(base),
            "allowlist_projects": len(allowed),
            "allowlist_unlimited": not allowed,
            "project_in_allowlist": not allowed or args.project_id in allowed,
        }
        checks.append({
            "check": "config_shape",
            "ok": config["project_in_allowlist"] is True,
            "detail": "configuration parses and the probe project is allowed by the allowlist",
        })
    except PlanError as exc:
        config = {}
        checks.append({
            "check": "config_shape",
            "ok": False,
            "detail": f"configuration rejected: {str(exc)[:120]}",
        })
        base = token = ""

    if executed:
        if not base or not token:
            checks.append({
                "check": "authentication",
                "ok": False,
                "detail": "skipped: configuration rejected",
            })
        else:
            try:
                rows = _ls_remote(base, token, args.project_id)
                heads = {ref: sha for sha, ref in rows if ref == f"refs/heads/{args.branch}"}
                checks.append({
                    "check": "authentication",
                    "ok": True,
                    "detail": f"ls-remote returned {len(rows)} bounded refs",
                })
                checks.append({
                    "check": "branch_present",
                    "ok": bool(heads),
                    "detail": (f"branch {args.branch!r} present" if heads
                               else f"branch {args.branch!r} absent from the online head"),
                    "head_sha": heads.get(f"refs/heads/{args.branch}", ""),
                })
                checks.append({
                    "check": "refs_shape",
                    "ok": all(
                        ref.startswith("refs/heads/") and len(sha) == 40
                        for sha, ref in rows
                    ),
                    "detail": "ref list well formed",
                })
            except PlanError as exc:
                message = str(exc)[:200]
                checks.append({
                    "check": "authentication",
                    "ok": False,
                    "detail": f"ls-remote refused: {message}",
                })
    else:
        checks.append({"check": "authentication", "ok": False, "detail": "not executed (offline without --live)"})
        checks.append({"check": "branch_present", "ok": False, "detail": "not executed (offline without --live)"})
        checks.append({"check": "refs_shape", "ok": False, "detail": "not executed (offline without --live)"})

    ok = executed and bool(base and token) and all(check["ok"] for check in checks)
    payload = {
        "evidence": FORMAT,
        "provider": args.provider,
        "executed": executed,
        "project_id": args.project_id,
        "branch": args.branch,
        "config": config,
        "checks": checks,
        "ok": ok,
        "note": "本探针只做只读 ls-remote；证据不包含令牌、URL、项目文件或完整引用列表。",
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"ok": payload["ok"], "executed": executed, "output": str(output)}))
    return 0 if payload["ok"] or (not executed and checks[0]["ok"]) else 1


def _configured_with_base(args: argparse.Namespace) -> tuple[str, str, tuple[str, ...]]:
    """Reuse the adapter's ``_configured`` with the probe's explicit base URL."""
    import os

    previous = os.environ.get("COMPANY_AGENT_OVERLEAF_GIT_BASE")
    os.environ["COMPANY_AGENT_OVERLEAF_GIT_BASE"] = args.base_url
    try:
        return _configured()
    finally:
        if previous is None:
            os.environ.pop("COMPANY_AGENT_OVERLEAF_GIT_BASE", None)
        else:
            os.environ["COMPANY_AGENT_OVERLEAF_GIT_BASE"] = previous


def _safe_host(base: str) -> str:
    import urllib.parse

    parsed = urllib.parse.urlsplit(base)
    host = parsed.hostname or ""
    return f"{parsed.scheme}://{host}" + (f":{parsed.port}" if parsed.port is not None else "")


if __name__ == "__main__":
    raise SystemExit(main())
