from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import asdict
from typing import Any

from company_agent.capabilities import list_capabilities
from company_agent.catalog import load_managed_builtins, load_tools, load_tools_for_preset
from company_agent.invoke import invoke, validate_invocation
from company_agent.jsonutil import loads as strict_json_loads
from company_agent.policy import decide
from company_agent.providers import clients
from company_agent.receipts import reconcile as receipt_reconcile

_MAX_STDIN_ARGUMENT_BYTES = 256_000


def _argument_text(raw: str) -> str:
    if raw != "-":
        if len(raw.encode("utf-8")) > _MAX_STDIN_ARGUMENT_BYTES:
            raise ValueError("arguments exceed maximum size")
        return raw
    data = sys.stdin.buffer.read(_MAX_STDIN_ARGUMENT_BYTES + 1)
    if len(data) > _MAX_STDIN_ARGUMENT_BYTES:
        raise ValueError("standard-input arguments exceed maximum size")
    try:
        return data.decode("utf-8")
    except UnicodeError as exc:
        raise ValueError("standard-input arguments must be UTF-8 JSON") from exc


def _safe_contract_error(exc: object, fallback: str) -> str:
    message = str(exc or "").strip()
    unsafe = any(marker in message.casefold() for marker in ("/", "\\", "token", "secret"))
    if not message or len(message) > 240 or unsafe:
        return fallback
    return message


def _dump(value: Any) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("CLI response is not valid JSON") from exc


def _knowledge_governance() -> dict[str, object]:
    """Registry status over the builtin knowledge root; booleans and counts only."""

    try:
        from company_agent.jsonutil import loads as strict_load
        from company_agent.knowledge import registry_status, roots

        builtin = next((root for root_id, root in roots() if root_id == "builtin"), None)
        if builtin is None:
            return {"present": False, "valid": False, "entries": 0}
        status = registry_status(builtin)
        entries = 0
        if status["present"] and status["valid"]:
            try:
                payload = strict_load((builtin / "registry.json").read_text(encoding="utf-8"))
                rows = payload.get("entries") if isinstance(payload, dict) else None
                entries = len(rows) if isinstance(rows, list) else -1
            except (OSError, ValueError, TypeError, RuntimeError):
                entries = -1
        return {"present": bool(status["present"]), "valid": bool(status["valid"]), "entries": entries}
    except (RuntimeError, OSError, ValueError, StopIteration):
        return {"present": False, "valid": False, "entries": 0}


def _tenants_governance() -> dict[str, object]:
    """Tenant registry facts; regime and counts only, never subjects or paths."""

    try:
        from company_agent.tenants import summary

        return dict(summary())
    except (RuntimeError, OSError, ValueError, TypeError, KeyError):
        return {"regime": "unavailable", "configured": True, "valid": False,
                "entries": 0, "subjects": 0, "approved_services": 0}


def _skills_governance() -> dict[str, object]:
    """Admission registry facts; the mount root never enters model-visible output."""

    try:
        from company_agent.catalog import load_skills

        rows = load_skills()
    except (RuntimeError, KeyError, TypeError, ValueError):
        return {"present": False, "valid": False}
    env_root = str(os.environ.get("COMPANY_AGENT_SKILL_ROOT") or "").strip()
    return {
        "present": True,
        "valid": True,
        "skills": len(rows),
        "revoked": sum(1 for row in rows.values() if row["revoked"]),
        "mount_root_configured": bool(env_root),
        "scripts_registered": sum(len(row["scripts"]) for row in rows.values()),
    }


def _receipt_summary() -> dict[str, object]:
    """Bounded reconciliation counts for cross-client state projection."""

    try:
        from company_agent.receipts import load_records, reconcile

        listed = reconcile(limit=200)
        if not listed.get("available"):
            return {"available": False, "unknown_outcomes": 0}
        unknown = len(listed.get("unknown") or [])
        return {
            "available": True,
            "unknown_outcomes": min(unknown, 200),
            "records_visible": len(load_records(limit=200)),
        }
    except (RuntimeError, OSError, ValueError, TypeError):
        return {"available": False, "unknown_outcomes": 0}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="company-agent")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("capabilities")
    tools_cmd = sub.add_parser("tools")
    tools_cmd.add_argument("--preset")
    sub.add_parser("doctor")
    reconcile_cmd = sub.add_parser("reconcile")
    reconcile_cmd.add_argument("--request-id", default="")
    reconcile_cmd.add_argument("--limit", type=int, default=24)
    decide_cmd = sub.add_parser("decide")
    authorize_cmd = sub.add_parser("authorize")
    validate_cmd = sub.add_parser("validate")
    invoke_cmd = sub.add_parser("invoke")
    for cmd in (decide_cmd, authorize_cmd, validate_cmd, invoke_cmd):
        cmd.add_argument("--tool", required=True)
        cmd.add_argument("--preset", default="lab")
        cmd.add_argument("--args", default="{}")
    invoke_cmd.add_argument("--approved", action="store_true")
    ns = parser.parse_args(argv)
    if ns.command == "invoke" and ns.approved and os.environ.get("COMPANY_AGENT_APPROVAL_CONTEXT") != "dsh":
        parser.error("--approved is reserved for the DSH approval lifecycle")
    if ns.command == "invoke" and ns.approved and os.environ.get("COMPANY_AGENT_PROFILE") != "company-agent":
        parser.error("--approved is only valid in the full company-agent profile")
    if ns.command == "invoke" and not ns.approved and os.environ.get("COMPANY_AGENT_APPROVAL_CONTEXT"):
        parser.error("approval context requires --approved")
    if ns.command != "invoke" and os.environ.get("COMPANY_AGENT_APPROVAL_CONTEXT"):
        parser.error("approval context is only valid for invoke")
    if ns.command == "capabilities":
        try:
            payload = [asdict(item) for item in list_capabilities()]
        except RuntimeError:
            print(_dump({"error": "capability contract is invalid"}))
            return 1
        print(_dump(payload))
        return 0
    if ns.command == "reconcile":
        if ns.request_id and not re.fullmatch(r"req_[0-9a-f]{32}", ns.request_id):
            parser.error("--request-id must match req_[32 lowercase hex chars]")
        if not 1 <= ns.limit <= 400:
            parser.error("--limit must be between 1 and 400")
        try:
            payload = receipt_reconcile(limit=ns.limit)
        except (RuntimeError, ValueError, TypeError, OSError):
            print(_dump({"error": "receipt contract is invalid"}))
            return 1
        if ns.request_id:
            matches = [
                row for row in payload["recent"] if row.get("request_id") == ns.request_id
            ] or [
                row for row in payload["unknown"] if row.get("request_id") == ns.request_id
            ]
            payload = {
                "version": "1.0",
                "available": payload["available"],
                "unknown": matches,
                "note": payload["note"],
            }
        print(_dump(payload))
        return 0 if payload["available"] else 1
    if ns.command == "tools":
        try:
            tools = load_tools_for_preset(ns.preset) if ns.preset else load_tools()
        except (KeyError, RuntimeError) as exc:
            parser.error(_safe_contract_error(exc, "tool contract is invalid"))
        print(_dump(list(tools.values())))
        return 0
    if ns.command == "doctor":
        try:
            provider_clients = clients()
        except (RuntimeError, ValueError, TypeError):
            print(_dump({"error": "provider contract is invalid"}))
            return 1
        payload = {
            client.id: {
                "configured": client.configured(),
                "env": client.url_env,
                "token_env": client.token_env,
            }
            for client in provider_clients
        }
        try:
            builtin_count = len(load_managed_builtins())
        except (RuntimeError, ValueError, TypeError):
            print(_dump({"error": "tool contract is invalid"}))
            return 1
        payload["model"] = {
            "configured": bool(os.environ.get("DEEPSEEK_API_KEY", "").strip()),
            "env": "DEEPSEEK_API_KEY",
        }
        payload["managed_builtins"] = {"enabled": True, "count": builtin_count}
        payload["local_model_route"] = {
            "token_env": "COMPANY_AGENT_LOCAL_MODEL_TOKEN",
            "token_configured": bool(os.environ.get("COMPANY_AGENT_LOCAL_MODEL_TOKEN", "").strip()),
        }
        payload["relay_model_route"] = {
            "token_env": "COMPANY_RELAY_API_KEY",
            "token_configured": bool(os.environ.get("COMPANY_RELAY_API_KEY", "").strip()),
        }
        payload["knowledge_governance"] = _knowledge_governance()
        payload["skills_governance"] = _skills_governance()
        payload["tenants_governance"] = _tenants_governance()
        payload["receipts"] = _receipt_summary()
        print(_dump(payload))
        return 0
    try:
        raw_arguments = _argument_text(ns.args)
        arguments = strict_json_loads(raw_arguments)
    except json.JSONDecodeError as exc:
        parser.error(f"--args must be valid JSON: {exc.msg}")
    except ValueError as exc:
        parser.error(str(exc))
    if not isinstance(arguments, dict):
        parser.error("--args must hold a JSON object")
    if ns.command == "validate":
        error = validate_invocation(ns.tool, arguments)
        print(_dump({"valid": error is None, "error": error}))
        return 0 if error is None else 1
    if ns.command == "authorize":
        error = validate_invocation(ns.tool, arguments)
        try:
            decision = "deny" if error is not None else decide(ns.tool, ns.preset, arguments)
        except (KeyError, TypeError, ValueError, RuntimeError):
            decision = "deny"
            error = "invalid policy contract"
        print(_dump({"decision": decision, "error": error}))
        return 0
    if ns.command == "decide":
        try:
            decision = decide(ns.tool, ns.preset, arguments)
        except (KeyError, TypeError, ValueError, RuntimeError):
            decision = "deny"
        print(_dump({"decision": decision}))
        return 0
    try:
        result = invoke(ns.tool, ns.preset, arguments, approved=ns.approved)
        encoded = _dump(asdict(result))
    except (TypeError, ValueError):
        result = None
        encoded = _dump(
            {
                "tool": ns.tool,
                "decision": "deny",
                "status": "error",
                "payload": None,
                "error": "serialization failure",
            }
        )
    print(encoded)
    if result is None:
        return 1
    return 0 if result.status in {"ok", "needs_ask", "denied"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
