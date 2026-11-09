from __future__ import annotations

import json
import math
import os
import time
from collections.abc import Mapping
from typing import Any

from company_agent import analysis as _analysis_module
from company_agent import budget
from company_agent import latex_workspace as _latex_workspace
from company_agent import office_audit as _office_audit
from company_agent import office_chart as _office_chart
from company_agent import office_compare as _office_compare
from company_agent import office_compute as _office_compute
from company_agent import office_convert as _office_convert
from company_agent import office_create as _office_create
from company_agent import office_deliver as _office_deliver
from company_agent import office_edit as _office_edit
from company_agent import office_files as _office_files
from company_agent import office_fix as _office_fix
from company_agent import office_ingest as _office_ingest
from company_agent import office_matter as _office_matter
from company_agent import office_open as _office_open
from company_agent import office_pptx as _office_pptx
from company_agent import office_review as _office_review
from company_agent import office_surface as _office_surface
from company_agent import office_validate as _office_validate
from company_agent import plan_hub as _plan_hub
from company_agent import portal as _portal
from company_agent import research_clock as _research_clock
from company_agent import table_profile as _table_profile
from company_agent import work_items as _work_items
from company_agent import workspace_reference as _workspace_reference
from company_agent.capabilities import capability
from company_agent.catalog import contract_snapshot, load_presets, load_result_policy, load_tools
from company_agent.contracts import HANDLE_PREFIXES, HANDLES, Invocation
from company_agent.diagnostics import emit, invocation_events
from company_agent.knowledge import search
from company_agent.policy import decide
from company_agent.providers import ProviderError, client_by_provider
from company_agent.sanitize import validate_output_content, validate_result_size
from company_agent.schema import SchemaError, validate_json_schema
from company_agent.webfetch import fetch as _webfetch_fetch
from company_agent.workflow import validate


def _capability_payload(preset: str) -> dict[str, Any]:
    from company_agent.capabilities import list_capabilities
    from company_agent.receipts import evidence
    from company_agent.receipts import subject as receipt_subject
    from company_agent.receipts import subject_source as receipt_subject_source
    from company_agent.tenants import projection as tenants_projection

    visible = set(load_presets()["presets"][preset]["visible_tools"])

    def provider_state(item):
        if item.kind in {"knowledge", "workflow", "document", "plan", "portal", "research"}:
            return "local"
        return "configured_unverified" if client_by_provider(item.provider).configured() else "unconfigured"

    def layer(item):
        try:
            return evidence(item.tools)
        except (KeyError, TypeError, ValueError, OSError, RuntimeError):
            return {
                "state": "unavailable", "tool": "", "request_id": "",
                "age_seconds": 0, "digest_match": "unavailable",
            }

    profile = str(os.environ.get("COMPANY_AGENT_PROFILE") or "").strip()
    if profile not in {"company-agent", "company-agent-minimal"}:
        profile = "unknown"
    approvals: list[str] = []
    for name in sorted(visible):
        try:
            if decide(name, preset, {}) == "ask":
                approvals.append(name)
        except (KeyError, TypeError, ValueError, RuntimeError):
            continue

    return {
        "preset": preset,
        "identity": {
            "subject": receipt_subject(),
            "subject_source": receipt_subject_source(),
            "profile": profile,
        },
        "enablement": tenants_projection(receipt_subject(), receipt_subject_source()),
        "approvals": approvals,
        "capabilities": [
            {
                "id": item.id,
                "kind": item.kind,
                "provider": item.provider,
                "contract_version": item.contract_version,
                "tools": list(item.tools),
                "visible_tools": [name for name in item.tools if name in visible],
                "provider_state": provider_state(item),
                "approval": item.approval,
                "evidence": layer(item),
            }
            for item in list_capabilities()
        ],
    }


_LOCAL_TOOLS = {
    "company_capabilities": _capability_payload,
    "company_knowledge_search": search,
    "company_fetch": _webfetch_fetch,
    "company_table_profile": _table_profile.profile,
    "company_workspace_reference": _workspace_reference.reference,
    "company_analysis_render": _analysis_module.render,
    "company_office_analyze": _office_ingest.analyze,
    "company_office_create": _office_create.create,
    "company_office_compare": _office_compare.compare,
    "company_office_edit": _office_edit.edit,
    "company_office_validate": _office_validate.validate,
    "company_office_chart": _office_chart.chart,
    "company_office_matter": _office_matter.matter,
    "company_office_audit": _office_audit.audit,
    "company_office_pptx": _office_pptx.pptx,
    "company_office_convert": _office_convert.convert,
    "company_office_open": _office_open.open_file,
    "company_office_compute": _office_compute.compute,
    "company_office_deliver": _office_deliver.deliver,
    "company_office_review_table": _office_review.review_table,
    "company_office_files": _office_files.files,
    "company_office_fix": _office_fix.fix,
    "company_office_surface": _office_surface.surface,
    "company_workflow_validate": validate,
    "company_latex_structure": _latex_workspace.structure,
    "company_latex_read": _latex_workspace.read_window,
    "company_latex_edit": _latex_workspace.edit,
    "company_latex_batch_edit": _latex_workspace.batch_edit,
    "company_latex_check": _latex_workspace.check,
    "company_latex_compile": _latex_workspace.compile,
    "company_latex_diff": _latex_workspace.diff,
    "company_latex_checkpoint": _latex_workspace.checkpoint,
    "company_latex_revert": _latex_workspace.revert,
    "company_latex_pull": _latex_workspace.pull,
    "company_latex_push": _latex_workspace.push,
    "company_latex_overleaf_pull": _latex_workspace.overleaf_pull,
    "company_latex_overleaf_push": _latex_workspace.overleaf_push,
    "company_latex_overleaf_status": _latex_workspace.overleaf_status,
    "company_latex_issue_note": _latex_workspace.issue_pdf_note,
    "company_plan_projects": _plan_hub.projects,
    "company_plan_issues": _plan_hub.issues,
    "company_plan_issue_get": _plan_hub.issue_get,
    "company_plan_issue_create": _plan_hub.issue_create,
    "company_plan_mrs": _plan_hub.mrs,
    "company_plan_note_create": _plan_hub.note_create,
    "company_plan_issue_write": _plan_hub.issue_write,
    "company_plan_milestones": _plan_hub.milestones,
    "company_plan_milestone_create": _plan_hub.milestone_create,
    "company_work_item": _work_items.work_item,
    "company_portal_open": _portal.open_portal,
    "company_research_compile": _research_clock.compile_spec,
    "company_research_run": _research_clock.run_spec,
    "company_research_status": _research_clock.read_status,
    "company_research_digest": _research_clock.read_digest,
}


def _provider_tools() -> dict[str, tuple[str, str]]:
    try:
        return {
            name: (str(row["capability"]), str(row["operation"]))
            for name, row in load_tools().items()
            if name not in _LOCAL_TOOLS
        }
    except (KeyError, TypeError, ValueError) as exc:
        raise ProviderError("tool provider mapping contract is invalid") from exc


_MAX_ARGUMENT_BYTES = 256_000
_MAX_ARGUMENT_DEPTH = 24
_MAX_ARGUMENT_COLLECTION_ITEMS = 10_000
_MAX_PUBLIC_ERROR_CHARS = 500
_SENSITIVE_ERROR_MARKERS = ("token", "secret", "api_key", "password", "authorization")


def _safe_error_message(error: object, fallback: str) -> str:
    message = str(error or "").strip()
    folded = message.casefold()
    if (
        not message
        or len(message) > _MAX_PUBLIC_ERROR_CHARS
        or any(marker in folded for marker in _SENSITIVE_ERROR_MARKERS)
        or "http://" in folded
        or "https://" in folded
        or "/mnt/" in folded
        or "/home/" in folded
    ):
        return fallback
    try:
        validate_output_content(message, reference=True)
    except (ValueError, RuntimeError, OverflowError):
        return fallback
    return message


def _validate_json_value(value: Any, *, depth: int = 0) -> None:
    if depth > _MAX_ARGUMENT_DEPTH:
        raise ValueError("arguments exceed maximum nesting depth")
    if isinstance(value, str):
        if len(value.encode("utf-8")) > 100_000:
            raise ValueError("arguments contain an oversized string")
        return
    if value is None or isinstance(value, bool):
        return
    if isinstance(value, int):
        if abs(value) > 9007199254740991:
            raise ValueError("arguments contain an unsafe integer")
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("arguments contain a non-finite number")
        if value.is_integer() and abs(value) > 9007199254740991:
            raise ValueError("arguments contain an unsafe integer")
        if value == 0.0 and math.copysign(1.0, value) < 0:
            raise ValueError("arguments contain negative zero")
        return
    if isinstance(value, list):
        if len(value) > _MAX_ARGUMENT_COLLECTION_ITEMS:
            raise ValueError("arguments contain an oversized list")
        for item in value:
            _validate_json_value(item, depth=depth + 1)
        return
    if isinstance(value, dict):
        if len(value) > _MAX_ARGUMENT_COLLECTION_ITEMS:
            raise ValueError("arguments contain an oversized object")
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("argument object keys must be strings")
            if len(key.encode("utf-8")) > 512:
                raise ValueError("arguments contain an oversized object key")
            _validate_json_value(item, depth=depth + 1)
        return
    raise TypeError(f"arguments contain unsupported type {type(value).__name__}")


def _validate_argument_envelope(arguments: Mapping[str, Any]) -> None:
    _validate_json_value(dict(arguments))
    try:
        encoded = json.dumps(arguments, ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise TypeError("arguments must be JSON serializable") from exc
    if len(encoded) > _MAX_ARGUMENT_BYTES:
        raise ValueError("arguments exceed maximum encoded size")


def _validate_arguments(tool: str, arguments: Mapping[str, Any]) -> None:
    if tool == "quantum_algorithm_run" and arguments.get("algorithm") == "__list_algorithms__":
        raise ValueError("use quantum_algorithm_catalog for algorithm discovery")
    schema = load_tools()[tool].get("parameters") or {}
    try:
        validate_json_schema(dict(arguments), schema, path="")
    except SchemaError as exc:
        message = str(exc)
        normalized = message.lstrip()
        if normalized.startswith("has unknown fields:"):
            message = "unknown arguments:" + normalized.removeprefix("has unknown fields:")
        if tool == "hpc_submit" and message.startswith("script has an invalid format"):
            message = (
                "script must be an absolute POSIX path (starting with /) to a batch script "
                "that already exists on the authorized HPC gateway; ~ paths, relative "
                "paths, Windows drive paths, spaces and inline script text are rejected; "
                "verify the file first with hpc_script_check"
            )
        raise ValueError(message) from exc


def _validate_handle_value(name: str, value: object, *, provider_output: bool) -> None:
    prefix = HANDLE_PREFIXES[name]
    suffix = value[len(prefix) :] if isinstance(value, str) and value.startswith(prefix) else ""
    valid_chars = suffix and all(
        character.isascii() and (character.isalnum() or character in "_-") for character in suffix
    )
    if not isinstance(value, str) or not valid_chars:
        message = f"{name} has an invalid format"
    elif len(value) > 256:
        message = f"{name} is too long"
    else:
        return
    if provider_output:
        raise ProviderError(message)
    raise ValueError(message)


def _validate_input_handles(tool: str, arguments: Mapping[str, Any]) -> None:
    for name in load_tools()[tool].get("input_handles") or ():
        _validate_handle_value(str(name), arguments.get(name), provider_output=False)


def _validate_output(tool: str, payload: Mapping[str, Any]) -> None:
    schema = load_tools()[tool].get("output")
    if not isinstance(schema, Mapping):
        raise ProviderError(f"tool {tool} has no output contract")
    try:
        validate_json_schema(dict(payload), schema, path="result")
    except SchemaError as exc:
        message = str(exc)
        if "has unknown fields:" in message:
            message = message.split("has unknown fields:", 1)[0] + "has unknown fields"
        raise ProviderError(message) from exc
    metrics = payload.get("summary", {}).get("metrics")
    if metrics is not None:
        names = set()
        for item in metrics["items"]:
            name, kind, value, unit = (item[key] for key in ("name", "kind", "value", "unit"))
            if name in names:
                raise ProviderError("scientific metric names must be unique")
            names.add(name)
            if kind == "uncertainty" and value < 0:
                raise ProviderError("scientific uncertainty must be non-negative")
            if kind == "probability" and (unit != "dimensionless" or not 0 <= value <= 1):
                raise ProviderError("scientific probability has invalid unit or range")
            if kind == "count" and (unit != "count" or value < 0 or int(value) != value):
                raise ProviderError("scientific count has invalid unit or value")
            if kind != "count" and unit == "count":
                raise ProviderError("scientific metric kind does not match count unit")


def _validate_handles(
    tool: str,
    payload: Mapping[str, Any],
    arguments: Mapping[str, Any] | None = None,
) -> None:
    contract = load_tools()[tool]
    allowed_outputs = set(contract.get("output_handles") or ())
    extra = set(payload).intersection(HANDLES)
    unexpected = extra - allowed_outputs
    if unexpected:
        raise ProviderError(f"tool {tool} returned unowned handles: {sorted(unexpected)}")
    for name in extra:
        _validate_handle_value(name, payload[name], provider_output=True)
    if "twin_id" in extra and tool != "quantum_device_run":
        raise ProviderError("only quantum_device_run may return twin_id")
    if tool == "quantum_asset_list":
        assets = payload.get("assets")
        if isinstance(assets, list):
            for asset in assets:
                if isinstance(asset, dict) and "asset_id" in asset:
                    _validate_handle_value("asset_id", asset["asset_id"], provider_output=True)
    if tool == "quantum_algorithm_catalog":
        if payload.get("provider") != "uniqon":
            raise ProviderError("algorithm catalog returned an invalid provider")
        algorithms = payload.get("algorithms")
        if not isinstance(algorithms, list):
            raise ProviderError("algorithm catalog must contain an algorithms list")
        identifiers = [(row.get("id"), row.get("version")) for row in algorithms if isinstance(row, dict)]
        if (
            len(identifiers) != len(algorithms)
            or any(not isinstance(part, str) for identity in identifiers for part in identity)
            or len(identifiers) != len(set(identifiers))
        ):
            raise ProviderError("algorithm catalog contains duplicate or invalid identifiers")
        if identifiers != sorted(identifiers):
            raise ProviderError("algorithm catalog must use deterministic identifier order")
        from company_agent.schema import validate_schema_definition

        for row in algorithms:
            if "input_schema" in row:
                validate_schema_definition(row["input_schema"])
                if (
                    row["input_schema"].get("type") != "object"
                    or row["input_schema"].get("additionalProperties") is not False
                ):
                    raise ProviderError("algorithm input schema must be a closed object")
        if payload.get("complete") is True and "next_cursor" in payload:
            raise ProviderError("complete algorithm catalog must not include next_cursor")
        if payload.get("complete") is False and not payload.get("next_cursor"):
            raise ProviderError("partial algorithm catalog must include next_cursor")
    if tool == "quantum_algorithm_run" and payload.get("asset_id") is None:
        raise ProviderError("algorithm result must contain asset_id")
    if tool == "quantum_circuit_export" and payload.get("circuit_id") is None:
        raise ProviderError("circuit export must contain circuit_id")
    if tool == "quantum_simulate":
        provenance = payload.get("provenance")
        if provenance != "independent-simulator":
            raise ProviderError("simulator result has invalid provenance")
        if payload.get("shots_actual") is not None:
            shots_actual = payload["shots_actual"]
            requested_shots = (arguments or {}).get("shots")
            if shots_actual > requested_shots:
                raise ProviderError("simulator result exceeds requested shots")
    if tool == "quantum_compile_estimate":
        if payload.get("provenance") != "independent-compiler":
            raise ProviderError("compiler result has invalid provenance")
        makespan = payload.get("makespan_ns")
        if (
            not isinstance(makespan, (int, float))
            or isinstance(makespan, bool)
            or not math.isfinite(makespan)
            or makespan < 0
        ):
            raise ProviderError("compiler result must contain a finite non-negative makespan_ns")
    if tool == "quantum_device_identity":
        if "twin_id" in payload:
            raise ProviderError("device identity must not return twin_id")
        if payload.get("provider") is not None and payload.get("provider") != "ionstack-twinrun":
            raise ProviderError("device identity returned an invalid provider")
    if tool == "quantum_device_run" and (
        payload.get("twin_id") is None or payload.get("provenance") != "qccd-twin"
    ):
        raise ProviderError("device result must contain twin_id and qccd-twin provenance")
    if tool == "quantum_device_run" and set(payload).intersection(HANDLES) != {"twin_id"}:
        raise ProviderError("device result must contain only the twin_id handle")
    if tool == "quantum_device_run" and payload.get("shots_actual") is not None:
        shots_actual = payload["shots_actual"]
        requested_shots = (arguments or {}).get("shots")
        if (
            not isinstance(shots_actual, int)
            or isinstance(shots_actual, bool)
            or shots_actual < 1
            or shots_actual > requested_shots
        ):
            raise ProviderError("device result has invalid shots_actual")
    if tool != "quantum_device_run" and payload.get("provenance") == "qccd-twin":
        raise ProviderError("non-device provider returned qccd-twin provenance")


def validate_invocation(tool: str, args: Mapping[str, Any] | None = None) -> str | None:
    """Return a safe validation error without invoking policy or a provider."""

    if args is not None and not isinstance(args, Mapping):
        return "args must be an object"
    if args is not None and not isinstance(args, dict):
        return "args must be a JSON object"
    if not isinstance(tool, str) or not tool or len(tool) > 128:
        return "invalid tool name"
    if not all(character.isascii() and (character.isalnum() or character == "_") for character in tool):
        return "invalid tool name"
    try:
        tools = load_tools()
    except (KeyError, TypeError, ValueError, RuntimeError):
        return "invalid tool contract"
    if tool not in tools:
        return "unknown tool"
    arguments = dict(args or {})
    try:
        _validate_argument_envelope(arguments)
        _validate_input_handles(tool, arguments)
        _validate_arguments(tool, arguments)
    except (KeyError, TypeError, ValueError, RuntimeError) as exc:
        return _safe_error_message(exc, "invalid tool arguments")
    return None


def invoke(
    tool: str, preset: str, args: Mapping[str, Any] | None = None, *, approved: bool = False
) -> Invocation:
    start = time.monotonic()
    try:
        with contract_snapshot() as snapshot, invocation_events() as provider_event:
            result = _invoke(tool, preset, args, approved=approved)
            row = load_tools().get(tool) if isinstance(tool, str) else None
            # Exactly one final invocation event; only provider events count dispatches.
            emit(
                {
                    "version": "1.0",
                    "event": "invocation",
                    "tool": tool if row else "unknown",
                    "operation": row["operation"] if row else "unknown",
                    "request_id": provider_event.get("request_id", ""),
                    "contract_digest": snapshot.digest,
                    "elapsed_ms": max(0, int((time.monotonic() - start) * 1000)),
                    "status": result.status,
                    "error_category": provider_event.get(
                        "error_category", "validation" if result.status in {"error", "denied"} else "none"
                    ),
                    "execution_state": provider_event.get(
                        "execution_state", "completed" if result.status == "ok" else "not_dispatched"
                    ),
                }
            )
            return result
    except (ValueError, TypeError, KeyError, RuntimeError):
        return Invocation(tool, "deny", "error", error="invalid tool contract")


def _invoke(
    tool: str, preset: str, args: Mapping[str, Any] | None = None, *, approved: bool = False
) -> Invocation:
    if not isinstance(approved, bool):
        return Invocation(tool, "deny", "error", error="approved must be a boolean")
    validation_error = validate_invocation(tool, args)
    if validation_error is not None:
        status = "denied" if validation_error in {"unknown tool", "invalid tool name"} else "error"
        return Invocation(tool, "deny", status, error=validation_error)
    arguments = dict(args or {})
    try:
        decision = decide(tool, preset, arguments)
        if decision not in {"allow", "ask", "deny"}:
            return Invocation(tool, "deny", "error", error="invalid policy decision")
    except (KeyError, TypeError, ValueError, RuntimeError):
        return Invocation(tool, "deny", "error", error="invalid policy contract")
    if decision == "deny":
        return Invocation(tool, decision, "denied", error="policy denied")
    if decision == "ask" and not approved:
        try:
            budget.precheck(tool, wait=True)
        except budget.BudgetError as exc:
            return Invocation(tool, decision, "error", error=str(exc))
        budget.charge_approval_wait()
        return Invocation(tool, decision, "needs_ask")
    started_ns = time.monotonic_ns()
    try:
        load_result_policy()
        budget.precheck(tool)
        if tool in _LOCAL_TOOLS:
            if tool == "company_capabilities":
                payload = _LOCAL_TOOLS[tool](preset)
            elif tool == "company_knowledge_search":
                payload = _LOCAL_TOOLS[tool](arguments, preset=preset)
            else:
                payload = _LOCAL_TOOLS[tool](arguments)
            if not isinstance(payload, dict):
                raise ValueError(f"local tool {tool} returned a non-object result")
        else:
            provider_spec = _provider_tools().get(tool)
            if provider_spec is None:
                raise ProviderError(f"tool {tool} has no provider mapping")
            capability_id, operation = provider_spec
            expected_provider = capability(capability_id).provider
            if tool == "quantum_device_run" and expected_provider != "ionstack-twinrun":
                raise ProviderError("quantum_device_run is not bound to ionstack-twinrun")
            if (
                tool != "quantum_device_run"
                and expected_provider == "ionstack-twinrun"
                and operation == "device.run"
            ):
                raise ProviderError("only quantum_device_run may invoke device.run")
            client = client_by_provider(expected_provider)
            payload = client.invoke(operation, arguments)
        if not isinstance(payload, Mapping):
            raise ProviderError(f"tool {tool} returned a non-object payload")
        payload = dict(payload)
        validate_output_content(
            payload,
            allow_twin_id=tool == "quantum_device_run",
            reference=tool in _LOCAL_TOOLS,
        )
        _validate_handles(tool, payload, arguments)
        _validate_output(tool, payload)
        validate_result_size(payload)
        budget.charge(tool, elapsed_ms=int((time.monotonic_ns() - started_ns) // 1_000_000))
        return Invocation(tool, decision, "ok", payload=payload)
    except (KeyError, TypeError, ValueError, ProviderError) as exc:
        budget.charge(tool, elapsed_ms=int((time.monotonic_ns() - started_ns) // 1_000_000))
        fallback = (
            "provider or tool result validation failed"
            if tool not in _LOCAL_TOOLS
            else "local tool validation failed"
        )
        return Invocation(tool, decision, "error", error=_safe_error_message(exc, fallback))
    except RuntimeError:
        budget.charge(tool, elapsed_ms=int((time.monotonic_ns() - started_ns) // 1_000_000))
        return Invocation(tool, decision, "error", error="internal tool failure")
    except Exception:
        budget.charge(tool, elapsed_ms=int((time.monotonic_ns() - started_ns) // 1_000_000))
        return Invocation(tool, decision, "error", error="internal tool failure")
