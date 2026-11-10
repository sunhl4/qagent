from __future__ import annotations

import json
import math
import os
import re
import unicodedata
from typing import Any

from company_agent.catalog import load_providers, load_result_policy

_HANDLES = frozenset({"asset_id", "circuit_id", "twin_id"})


def _allowed_handle(
    key: str,
    path: tuple[str | int, ...],
    *,
    allow_twin_id: bool,
    allow_asset_list: bool,
) -> bool:
    if key not in _HANDLES:
        return True
    if not path:
        return key != "twin_id" or allow_twin_id
    return (
        allow_asset_list
        and len(path) == 2
        and path[0] == "assets"
        and isinstance(path[1], int)
        and key == "asset_id"
    )


def _key_parts(key: object) -> frozenset[str]:
    normalized = unicodedata.normalize("NFKC", str(key))
    normalized = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", normalized)
    normalized = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", normalized)
    return frozenset(part for part in re.split(r"[^a-z0-9]+", normalized.casefold()) if part)


def _is_forbidden_output_key(key: object, forbidden: set[str]) -> bool:
    folded = unicodedata.normalize("NFKC", str(key)).casefold()
    compact = re.sub(r"[^a-z0-9]", "", folded)
    parts = _key_parts(key)
    return (
        folded in forbidden
        or compact in {re.sub(r"[^a-z0-9]", "", item) for item in forbidden}
        or (compact in {"assetid", "circuitid", "twinid"} and key not in _HANDLES)
        or any(term in compact for term in ("calibration", "shuttle", "bitstring", "pauli"))
        or "qasm" in compact
        or bool(parts & {"cal", "token", "secret", "password", "authorization", "credential"})
        or {"api", "key"} <= parts
    )


def _forbidden_text(value: str, path: tuple[str | int, ...], allow_twin_id: bool) -> bool:
    if "qccd-twin" in value.casefold() and not (
        allow_twin_id and path == ("provenance",) and value == "qccd-twin"
    ):
        return True
    return bool(re.search(r"OPENQASM\s+[23](?:\.\d+)?|-----BEGIN [A-Z ]*PRIVATE KEY-----", value))


def validate_output_content(value: Any, *, allow_twin_id: bool = False, reference: bool = False) -> None:
    """Apply a common content boundary without interpreting local binding metadata as handles.

    Known credential matching is defense in depth, not detection of every secret.
    Authorized reference prose may mention provenance, but never contain science bodies.
    """
    names = {row["token_env"] for row in load_providers()["providers"]}
    names.update({"DEEPSEEK_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "UQC_CLOUD_API_KEY",
                  "HPC_TOKEN", "COMPANY_RELAY_API_KEY", "COMPANY_AGENT_LOCAL_MODEL_TOKEN",
                  "COMPANY_AGENT_GITLAB_TOKEN", "COMPANY_DINGTALK_APP_KEY",
                  "COMPANY_DINGTALK_APP_SECRET", "COMPANY_DINGTALK_ROBOT_CODE"})
    credentials = tuple({os.environ[name].strip() for name in names if os.environ.get(name, "").strip()})

    def visit(item: Any, path: tuple[str | int, ...] = ()) -> None:
        if len(path) > 24:
            raise ValueError("tool result exceeds content nesting limit")
        if isinstance(item, str):
            if any(secret in item for secret in credentials):
                raise ValueError("tool result contains forbidden content")
            body = bool(
                re.search(
                    r"OPENQASM\s+[23](?:\.\d+)?|-----BEGIN [A-Z ]*PRIVATE KEY-----",
                    item,
                    flags=re.IGNORECASE,
                )
            )
            if body or (not reference and _forbidden_text(item, path, allow_twin_id)):
                raise ValueError("tool result contains forbidden content")
        elif isinstance(item, dict):
            for key, child in item.items():
                visit(key, (*path, "key"))
                visit(child, (*path, key))
        elif isinstance(item, list):
            for index, child in enumerate(item):
                visit(child, (*path, index))
        elif isinstance(item, (int, float)) and not isinstance(item, bool):
            if (
                not math.isfinite(item)
                or (float(item).is_integer() and abs(item) > 9007199254740991)
                or (isinstance(item, float) and item == 0 and math.copysign(1, item) < 0)
            ):
                raise ValueError("tool result contains an unsafe number")

    visit(value)


def validate_result_size(value: Any, policy: dict[str, Any] | None = None) -> None:
    policy = load_result_policy() if policy is None else policy
    try:
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode(
            "utf-8"
        )
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise ValueError("tool result must be bounded UTF-8 JSON") from exc
    if len(encoded) > policy["max_result_bytes"]:
        raise ValueError("tool result exceeds maximum encoded size")


def has_forbidden_output(value: Any, *, allow_twin_id: bool = False, allow_asset_list: bool = False) -> bool:
    """Reject unsafe provider data rather than silently truncate scientific results."""

    policy = load_result_policy()
    limits = policy["provider_result"]
    forbidden = set(limits["forbidden_keys"])

    def contains(item: Any, path: tuple[str | int, ...] = ()) -> bool:
        if len(path) > limits["max_depth"]:
            return True
        if isinstance(item, dict):
            if len(item) > limits["max_mapping_items"]:
                return True
            for key, child in item.items():
                if (
                    not isinstance(key, str)
                    or _is_forbidden_output_key(key, forbidden)
                    or not _allowed_handle(
                        key, path, allow_twin_id=allow_twin_id, allow_asset_list=allow_asset_list
                    )
                    or contains(child, (*path, key))
                ):
                    return True
            return False
        if isinstance(item, list):
            return len(item) > limits["max_list_items"] or any(
                contains(child, (*path, index)) for index, child in enumerate(item)
            )
        if isinstance(item, str):
            return len(item.encode("utf-8")) > limits["max_string_bytes"] or _forbidden_text(
                item, path, allow_twin_id
            )
        if isinstance(item, float):
            return not math.isfinite(item) or (item == 0.0 and math.copysign(1.0, item) < 0)
        return not (item is None or isinstance(item, (bool, int)))

    try:
        if contains(value):
            return True
        validate_result_size(value, policy)
    except (ValueError, UnicodeError, RecursionError):
        return True
    return False


def short_result(value: Any, *, allow_twin_id: bool = False, allow_asset_list: bool = False) -> Any:
    """Defensive redaction helper; provider calls first reject any lossy input."""

    policy = load_result_policy()
    limits = policy["provider_result"]
    forbidden = set(limits["forbidden_keys"])

    def shorten(item: Any, path: tuple[str | int, ...] = ()) -> Any:
        if len(path) > limits["max_depth"]:
            return "[truncated]"
        if isinstance(item, dict):
            return {
                str(key): shorten(child, (*path, str(key)))
                for key, child in list(item.items())[: limits["max_mapping_items"]]
                if not _is_forbidden_output_key(key, forbidden)
                and _allowed_handle(
                    str(key), path, allow_twin_id=allow_twin_id, allow_asset_list=allow_asset_list
                )
            }
        if isinstance(item, list):
            return [
                shorten(child, (*path, index)) for index, child in enumerate(item[: limits["max_list_items"]])
            ]
        if isinstance(item, str):
            if _forbidden_text(item, path, allow_twin_id):
                return "[redacted]"
            return item.encode("utf-8")[: limits["max_string_bytes"]].decode("utf-8", errors="ignore")
        if isinstance(item, float) and not math.isfinite(item):
            return None
        if item is None or isinstance(item, (bool, int, float)):
            return item
        return "[unsupported]"

    result = shorten(value)
    validate_result_size(result, policy)
    return result
