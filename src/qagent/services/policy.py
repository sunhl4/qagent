from __future__ import annotations

from typing import Any

from qagent.adapters.contracts import load_policy, load_presets
from qagent.models.types import Decision


def _is_hidden(presets: dict[str, Any], preset: str, tool: str) -> bool:
    block = presets["presets"][preset]
    hidden = set(block.get("hidden_tools") or [])
    visible = set(block.get("visible_tools") or [])
    if tool in hidden:
        return True
    if visible and tool not in visible:
        return True
    return False


def _ref(policy: dict[str, Any], name: str) -> Any:
    return policy[name]


def _when_match(
    when: dict[str, Any] | None,
    *,
    policy: dict[str, Any],
    presets: dict[str, Any],
    tool: str,
    preset: str,
    args: dict[str, Any],
) -> bool:
    if not when:
        return True
    if when.get("tool_in_ref"):
        return tool in set(_ref(policy, when["tool_in_ref"]))
    if when.get("tool_hidden_in_preset"):
        return _is_hidden(presets, preset, tool)
    if "arg_not_in" in when:
        field, ref = next(iter(when["arg_not_in"].items()))
        value = args.get(field)
        allowed = set(_ref(policy, ref))
        return value is None or value not in allowed
    if "arg_gte" in when:
        field, ref = next(iter(when["arg_gte"].items()))
        raw = args.get(field)
        if raw is None:
            return False
        return float(raw) >= float(_ref(policy, ref))
    if "arg_eq" in when:
        return all(args.get(k) == v for k, v in when["arg_eq"].items())
    return False


def decide(tool: str, preset: str, args: dict[str, Any] | None = None) -> Decision:
    """First matching rule wins. No match → deny (fail closed)."""
    policy = load_policy()
    presets = load_presets()
    args = args or {}
    if preset not in presets["presets"]:
        return "deny"
    for rule in policy["rules"]:
        tools = rule["tools"]
        if "*" not in tools and tool not in tools:
            continue
        if preset not in rule["presets"]:
            continue
        if not _when_match(
            rule.get("when"),
            policy=policy,
            presets=presets,
            tool=tool,
            preset=preset,
            args=args,
        ):
            continue
        decision = rule["decision"]
        if decision not in ("allow", "deny", "ask"):
            return "deny"
        return decision
    return "deny"
