"""Tenant/service enablement facts: the registry is operator-managed data, never model input.

Survey source: docs/oss-survey/04-工程衔接建议.zh-CN.md 「P1」 and the delivery-plan P1
phase. The registry is a JSONL ledger of ``{subject, class, service, state,
expires_epoch, approved_by}`` lines kept outside ``contracts/``. ``class`` is
``internal`` or ``external`` and must agree for every line of one subject.
``approved`` means the operator bound that subject to that capability, with
optional expiry. An invalid registry, a missing class, or two classes for one
subject fails closed. An unset registry stays the single-user seat and does
not consult this ledger. A configured registry can narrow a preset; it never
widens one. The model cannot supply the class or the allow-list.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

from company_agent.catalog import load_tenants
from company_agent.jsonutil import loads as strict_json_loads
from company_agent.receipts import _SUBJECT_PATTERN, subject, subject_source

_SERVICES: tuple[str, ...] | None = None


class TenantRegistryError(RuntimeError):
    """The configured tenant registry is unusable; enterprise facts stay unknown."""


def _model() -> dict[str, Any]:
    return load_tenants()


def _services() -> tuple[str, ...]:
    global _SERVICES
    if _SERVICES is None:
        _SERVICES = tuple(str(item) for item in _model()["services"])
    return _SERVICES


def _disabled(service: str, reason: str) -> dict[str, Any]:
    item: dict[str, Any] = {"service": service, "enabled": False, "reason": reason}
    # The contract keeps approved_by/expires_epoch optional and non-null: keys
    # are omitted instead of carrying nulls through the model-visible envelope.
    return item


def _empty_legacy(subject_value: str) -> dict[str, Any]:
    return {"regime": "legacy-single-user", "subject": subject_value, "class": "", "services": {}}


def _unavailable(subject_value: str) -> dict[str, Any]:
    return {
        "regime": "unavailable",
        "subject": subject_value,
        "class": "",
        "services": {service: _disabled(service, "registry_unavailable") for service in _services()},
    }


def _account_class(entries: list[dict[str, Any]], subject_value: str) -> str:
    found = {str(row["class"]) for row in entries if row["subject"] == subject_value}
    if len(found) != 1:
        return ""
    return next(iter(found))


def _registry_path() -> Path | None:
    """Resolve the configured registry path; None means legacy single-user regime."""

    configured = str(os.environ.get(str(_model()["registry_env"])) or "").strip()
    if not configured:
        return None
    path = Path(configured)
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise TenantRegistryError("tenant registry path is invalid")
    if len(path.parts) <= 1 or any(part in {"", ".", ".."} for part in path.parts[1:]):
        raise TenantRegistryError("tenant registry path is invalid")
    model = _model()
    path_bytes = path.stat().st_size
    if path_bytes > int(model["max_registry_bytes"]):
        raise TenantRegistryError("tenant registry exceeds contract size")
    return path


def _parse_entries(path: Path) -> list[dict[str, Any]]:
    """Strict per-line ledger parse; any invalid line invalidates the registry."""

    model = _model()
    fields = set(str(item) for item in model["line_fields"])
    services = set(_services())
    classes = set(str(item) for item in model["classes"])
    states = set(str(item) for item in model["states"])
    approved_limit = int(model["approved_by_max_bytes"])
    subject_limit = int(model["subject_max_bytes"])
    max_lines = int(model["max_lines"])
    text = path.read_text(encoding="utf-8")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) > max_lines:
        raise TenantRegistryError("tenant registry exceeds contract line budget")
    entries: list[dict[str, Any]] = []
    for line in lines:
        try:
            row = strict_json_loads(line)
        except (ValueError, TypeError):
            raise TenantRegistryError("tenant registry line is invalid") from None
        if not isinstance(row, dict) or set(row) != fields:
            raise TenantRegistryError("tenant registry line is invalid")
        subject = row["subject"]
        account_class = row["class"]
        service = row["service"]
        state = row["state"]
        expires = row["expires_epoch"]
        approved_by = row["approved_by"]
        if (
            not isinstance(subject, str)
            or len(subject.encode("utf-8")) > subject_limit
            or not _SUBJECT_PATTERN.fullmatch(subject)
            or not isinstance(account_class, str)
            or account_class not in classes
            or not isinstance(service, str)
            or service not in services
            or not isinstance(state, str)
            or state not in states
            or not isinstance(approved_by, str)
            or not approved_by
            or len(approved_by.encode("utf-8")) > approved_limit
        ):
            raise TenantRegistryError("tenant registry line is invalid")
        expires = row["expires_epoch"]
        if expires is not None and (
            not isinstance(expires, int) or isinstance(expires, bool)
            or not 0 <= expires <= 9007199254740991
        ):
            raise TenantRegistryError("tenant registry line is invalid")
        entries.append({
            "subject": subject, "class": account_class, "service": service, "state": state,
            "expires_epoch": expires, "approved_by": approved_by,
        })
    seen_class: dict[str, str] = {}
    for entry in entries:
        prior = seen_class.get(entry["subject"])
        if prior is not None and prior != entry["class"]:
            raise TenantRegistryError("tenant registry line is invalid")
        seen_class[entry["subject"]] = entry["class"]
    return entries


def summary() -> dict[str, Any]:
    """Doctor/status facts: booleans and counts only, no paths and no subjects."""

    configured = bool(str(os.environ.get(str(_model()["registry_env"])) or "").strip())
    if not configured:
        return {"regime": "legacy-single-user", "configured": False, "valid": False,
                "entries": 0, "subjects": 0, "approved_services": 0}
    try:
        entries = _parse_entries(_registry_path())
    except (TenantRegistryError, OSError, ValueError, TypeError):
        return {"regime": "unavailable", "configured": True, "valid": False,
                "entries": 0, "subjects": 0, "approved_services": 0}
    subjects = {row["subject"] for row in entries}
    now = int(time.time())
    approved = {
        (row["subject"], row["service"])
        for row in entries
        if row["state"] == "approved" and (row["expires_epoch"] is None or row["expires_epoch"] > now)
    }
    return {"regime": "registry", "configured": True, "valid": True,
            "entries": len(entries), "subjects": len(subjects),
            "approved_services": len(approved)}


def projection(subject_value: str, source: str) -> dict[str, Any]:
    """Per-subject enablement facts for the capability payload; facts, not grants."""

    if (
        not isinstance(subject_value, str)
        or not subject_value
        or len(subject_value.encode("utf-8")) > int(_model()["subject_max_bytes"])
    ):
        return _empty_legacy(subject_value if isinstance(subject_value, str) else "")
    if not str(os.environ.get(str(_model()["registry_env"])) or "").strip():
        return _empty_legacy(subject_value)
    reason = "untrusted_subject" if source == "untrusted" else "subject_absent"
    if source == "untrusted":
        # Fail closed for an unusable identity: registered lines must never be
        # matched by whatever a misconfigured host's derived identity appears to be.
        return {
            "regime": "registry", "subject": subject_value, "class": "",
            "services": {service: _disabled(service, reason) for service in _services()},
        }
    try:
        entries = _parse_entries(_registry_path())
    except (TenantRegistryError, OSError, ValueError, TypeError):
        return _unavailable(subject_value)
    services: dict[str, Any] = {}
    now = int(time.time())
    for service in _services():
        latest = next(
            (
                row
                for row in reversed(entries)
                if row["subject"] == subject_value and row["service"] == service
            ),
            None,
        )
        if latest is None:
            services[service] = _disabled(service, reason)
            continue
        decision: dict[str, Any] = {"service": service, "enabled": False,
                                    "reason": "revoked" if latest["state"] == "revoked" else latest["state"]}
        decision["approved_by"] = latest["approved_by"]
        if latest["expires_epoch"] is not None:
            decision["expires_epoch"] = int(latest["expires_epoch"])
        if latest["state"] == "approved":
            # Unified boundary with the knowledge registry: the recorded
            # expires_epoch itself is still valid; the next epoch is not.
            if latest["expires_epoch"] is None or now <= latest["expires_epoch"]:
                decision = {"service": service, "enabled": True, "reason": "approved",
                            "approved_by": latest["approved_by"]}
                if latest["expires_epoch"] is not None:
                    decision["expires_epoch"] = int(latest["expires_epoch"])
            else:
                decision["reason"] = "expired"
        elif latest["state"] == "pending":
            decision["reason"] = "pending"
        services[service] = decision
    return {
        "regime": "registry",
        "subject": subject_value,
        "class": _account_class(entries, subject_value),
        "services": services,
    }


def account_allows(capability: str) -> bool:
    """True when this seat may use the capability.

    An unset registry is the single-user seat, so the preset remains the only
    gate. A configured registry allows the capability only when the subject has
    one class and an approved, unexpired line. A session grant cannot call this
    true, and a preset denial is applied by the caller before this result.
    """

    if not isinstance(capability, str) or not capability:
        return False
    facts = projection(subject(), subject_source())
    if facts.get("regime") == "legacy-single-user":
        return True
    if facts.get("regime") != "registry" or facts.get("class") not in {"internal", "external"}:
        return False
    services = facts.get("services")
    if not isinstance(services, dict):
        return False
    row = services.get(capability)
    return isinstance(row, dict) and row.get("enabled") is True


def re_all_subjects_valid(subjects: set[str]) -> bool:
    """Shared-shape check so every registered subject follows the receipts pattern."""

    return all(_SUBJECT_PATTERN.fullmatch(value) for value in subjects)
