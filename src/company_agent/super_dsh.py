from __future__ import annotations

from datetime import datetime
from typing import Mapping

from company_agent.catalog import _load_object
from company_agent.work_items import WorkItemStore

_CLOCKS = ("agent", "platform")
_PLANES = ("control", "execution", "platform")
_SIGNAL_TYPES = (
    "experiment.completed.v1",
    "lease.changed.v1",
    "budget.exhausted.v1",
)
_FLOW_FOUNDATION = {
    "owner_when_locked": "upstream-super-agent",
    "stand_in": "local-control-plane",
    "company_keeps": ["tool-pack", "policy", "platform-clock"],
    "required_upstream": ["router", "subscription", "attention"],
    "replaced_when_locked": ["stand-in-ticket-store", "stand-in-thread-binding"],
    "unattended": {
        "entry": "source-event",
        "opens_ticket_when": "written-rule",
        "default_until_rule": "observe",
        "company_policy_still_applies": True,
    },
}
_FORBIDDEN = ("secret", "token", "password", "prompt", "credential", "api_key")
_EVENT_FIELDS = (
    "schema_version", "tenant_id", "source", "idempotency_key",
    "subject_id", "mandate", "policy_version",
)


class SuperDshError(ValueError):
    """Raised when the company Super DSH architecture contract is invalid."""


def _architecture() -> dict:
    contract = _load_object("superagent.json")
    architecture = contract.get("architecture")
    framework = contract.get("framework")
    clocks = architecture.get("clocks") if isinstance(architecture, dict) else None
    planes = architecture.get("planes") if isinstance(architecture, dict) else None
    channels = architecture.get("channels") if isinstance(architecture, dict) else None
    watchdog = architecture.get("watchdog") if isinstance(architecture, dict) else None
    control = contract.get("control_plane") if isinstance(contract, dict) else None
    if (
        contract.get("version") != "1.3.0"
        or not isinstance(control, dict)
        or control.get("schema_version") != "1"
        or control.get("event_fields") != list(_EVENT_FIELDS)
        or control.get("unknown_retryable") is not False
        or control.get("company_fact_store") is not False
        or control.get("cross_tenant_read") != "deny"
        or control.get("ledger_role") != "local-control-plane"
        or not isinstance(architecture, dict)
        or architecture.get("name") != "company-super-dsh"
        or architecture.get("audience") != "company"
        or architecture.get("second_runtime") is not False
        or not isinstance(clocks, dict)
        or set(clocks) != set(_CLOCKS)
        or clocks["agent"].get("owner") != "control"
        or clocks["agent"].get("fact_store") != "local-control-plane"
        or control.get("open_sources") != ["company", "workspace", "research"]
        or control.get("execution_fields") != ["session_ref", "tool_pack"]
        or control.get("recover_fields") != [
            "assignment_id", "ticket_id", "execution_state", "session_ref", "tool_pack", "thread_key",
        ]
        or control.get("ticket_rule") != {"mode": "auto", "strength": "explicit"}
        or control.get("reconcile_rule") != {
            "from_execution": "unknown",
            "to_execution": "ended",
            "to_ticket": "ended",
        }
        or clocks["platform"].get("owner") != "research-layer"
        or not isinstance(planes, dict)
        or set(planes) != set(_PLANES)
        or any(planes[name].get("starts_model_loop") is not False for name in _PLANES)
        or planes["execution"].get("executor") != "existing-dsh-session"
        or planes["platform"].get("enters_as") != "research-trigger"
        or not isinstance(channels, dict)
        or channels.get("github") is not False
        or channels.get("feishu") is not False
        or channels.get("research") is not True
        or not isinstance(watchdog, dict)
        or watchdog.get("may_open_ticket") is not False
        or watchdog.get("may_change_policy") is not False
        or watchdog.get("may_retry_unknown") is not False
        or architecture.get("signal_types") != list(_SIGNAL_TYPES)
        or architecture.get("flow_foundation") != _FLOW_FOUNDATION
        or not isinstance(framework, dict)
        or framework.get("runtime") != "deepseek-harness"
        or framework.get("executor") != "existing-dsh-session"
        or "research" not in contract.get("source_kinds", [])
    ):
        raise SuperDshError("super-dsh architecture is invalid")
    return architecture


def topology() -> dict:
    """Return the company-wide Super DSH shape without session or science data."""
    architecture = _architecture()
    return {
        "name": architecture["name"],
        "audience": architecture["audience"],
        "runtime": "deepseek-harness",
        "second_runtime": False,
        "clocks": list(_CLOCKS),
        "planes": list(_PLANES),
        "executor": "existing-dsh-session",
        "platform_entry": "research-trigger",
        "channels": dict(architecture["channels"]),
        "watchdog": {
            "may_open_ticket": False,
            "may_change_policy": False,
            "may_retry_unknown": False,
        },
        "signal_types": list(_SIGNAL_TYPES),
        "flow_foundation": dict(architecture["flow_foundation"]),
        "schema_version": "1",
        "unknown_retryable": False,
        "company_fact_store": False,
        "execution_fields": ["session_ref", "tool_pack"],
        "recover_fields": [
            "assignment_id", "ticket_id", "execution_state", "session_ref", "tool_pack", "thread_key",
        ],
    }


def _bounded_identifier(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SuperDshError(f"{field} is invalid")
    text = value.strip()
    if any(marker in text.casefold() for marker in _FORBIDDEN):
        raise SuperDshError(f"{field} is invalid")
    if len(text.encode("utf-8")) > 80:
        raise SuperDshError(f"{field} is too long")
    return text


_HANDOFF_FIELDS = ("tenant_id", "request_id", "idempotency_key", "mandate", "tool")


def record_device_handoff(store: WorkItemStore, payload: Mapping[str, object]) -> dict:
    """Record a QPU request as a device-approval candidate. Do not open a ticket or call a device."""
    _architecture()
    if set(payload) != set(_HANDOFF_FIELDS):
        raise SuperDshError("device handoff has an unknown field")
    if payload.get("mandate") != "lab" or payload.get("tool") != "quantum_device_run":
        raise SuperDshError("device handoff is invalid")
    tenant_id = _bounded_identifier(payload.get("tenant_id"), "tenant_id")
    request_id = _bounded_identifier(payload.get("request_id"), "request_id")
    idempotency_key = payload.get("idempotency_key")
    if not isinstance(idempotency_key, str) or not idempotency_key.strip():
        raise SuperDshError("idempotency_key is invalid")
    if any(marker in idempotency_key.casefold() for marker in _FORBIDDEN):
        raise SuperDshError("idempotency_key is invalid")
    text = f"device-approval {request_id}"
    row = store.receive(
        "research", request_id, tenant_id, text, human=False,
        tenant_id=tenant_id, idempotency_key=idempotency_key, subject_id=tenant_id,
    )
    return {
        "authority": "candidate",
        "trigger_id": row["trigger_id"],
        "ticket_id": "",
        "mandate": "lab",
        "tool": "quantum_device_run",
    }


def ingest_platform_signal(store: WorkItemStore, payload: Mapping[str, object]) -> dict:
    """Record one research-layer fact as a Super DSH trigger. Do not open a ticket."""
    architecture = _architecture()
    allowed = set(payload)
    if not allowed <= {
        "signal_type", "tenant_id", "project_id", "resource_id", "resource_version", "time",
    }:
        raise SuperDshError("platform signal has an unknown field")
    signal_type = payload.get("signal_type")
    if signal_type not in architecture["signal_types"]:
        raise SuperDshError("platform signal type is invalid")
    tenant_id = _bounded_identifier(payload.get("tenant_id"), "tenant_id")
    resource_id = _bounded_identifier(payload.get("resource_id"), "resource_id")
    project = payload.get("project_id")
    if project is not None:
        project = _bounded_identifier(project, "project_id")
    version = payload.get("resource_version")
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise SuperDshError("resource version is invalid")
    stamp = payload.get("time")
    if not isinstance(stamp, str):
        raise SuperDshError("signal time is invalid")
    try:
        datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SuperDshError("signal time is invalid") from exc
    thread_id = f"{tenant_id}:{resource_id}"
    text = f"{signal_type} {resource_id} v{version}"
    if project is not None:
        text = f"{text} project {project}"
    idempotency_key = f"{signal_type}:{tenant_id}:{resource_id}:{version}"
    row = store.receive(
        "research", thread_id, tenant_id, text, human=False, addressed=None,
        tenant_id=tenant_id, idempotency_key=idempotency_key, subject_id=tenant_id,
    )
    return {
        "source": "research",
        "clock": "platform",
        "authority": "candidate",
        "trigger_id": row["trigger_id"],
        "thread_key": row["thread_key"],
        "ticket_id": "",
    }
