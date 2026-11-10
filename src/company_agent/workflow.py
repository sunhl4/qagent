from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from company_agent.capabilities import capability
from company_agent.catalog import load_tools
from company_agent.contracts import HANDLES, WorkflowStep
from company_agent.schema import SchemaError, validate_json_schema


def validate(args: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(args, Mapping):
        raise TypeError("workflow arguments must be an object")
    if not isinstance(args, dict):
        raise TypeError("workflow arguments must be a JSON object")
    unknown_top = set(args) - {"steps", "inputs", "record", "tenant_id"}
    if unknown_top:
        raise ValueError(f"workflow has unknown fields: {sorted(unknown_top)}")
    raw_steps = args.get("steps")
    if not isinstance(raw_steps, list) or not raw_steps:
        raise ValueError("steps must be a non-empty list")
    if len(raw_steps) > 64:
        raise ValueError("steps must contain at most 64 items")
    known_ids: set[str] = set()
    produced: set[str] = set()
    producers: dict[str, list[str]] = {handle: [] for handle in HANDLES}
    outputs_by_step: dict[str, set[str]] = {}
    steps: list[WorkflowStep] = []
    tools = load_tools()
    validate_json_schema(
        args.get("inputs", []), tools["company_workflow_validate"]["parameters"]["properties"]["inputs"]
    )
    external = {item["id"]: item for item in args.get("inputs", [])}
    if len(external) != len(args.get("inputs", [])):
        raise ValueError("workflow has duplicate input identifiers")
    from company_agent.contracts import HANDLE_PREFIXES

    for item in external.values():
        if not item["value"].startswith(HANDLE_PREFIXES[item["handle"]]):
            raise ValueError("workflow input handle does not match its declared type")
    available = {item["handle"] for item in external.values()}
    no_handle_tools = {
        "company_capabilities",
        "company_knowledge_search",
        "company_workflow_validate",
        "quantum_algorithm_catalog",
        "quantum_asset_list",
        "quantum_device_identity",
    }
    for index, raw in enumerate(raw_steps):
        if not isinstance(raw, dict):
            raise ValueError(f"step {index} must be an object")
        step_id_value = raw.get("id")
        capability_value = raw.get("capability")
        tool_value = raw.get("tool")
        if not all(isinstance(value, str) for value in (step_id_value, capability_value, tool_value)):
            raise ValueError(f"step {index} id, capability, and tool must be strings")
        step_id = step_id_value.strip()
        capability_id = capability_value.strip()
        tool = tool_value.strip()
        unknown_fields = set(raw) - {
            "id",
            "capability",
            "tool",
            "needs",
            "produces",
            "approval",
            "arguments",
            "bindings",
        }
        if unknown_fields:
            raise ValueError(f"step {index} has unknown fields: {sorted(unknown_fields)}")
        if not step_id or step_id in known_ids or step_id in external:
            raise ValueError(f"step {index} has an empty or duplicate id")
        valid_step_id = all(
            character.isascii() and (character.isalnum() or character in "_.-") for character in step_id
        )
        if not valid_step_id:
            raise ValueError(f"step {index} id has an invalid format")
        if len(step_id) > 128:
            raise ValueError(f"step {index} id is too long")
        if not capability_id or len(capability_id) > 128:
            raise ValueError(f"step {index} has an invalid capability")
        valid_capability = all(
            character.isascii() and (character.isalnum() or character in ".-") for character in capability_id
        )
        if not valid_capability:
            raise ValueError(f"step {index} has an invalid capability")
        if not tool or len(tool) > 128:
            raise ValueError(f"step {index} has an invalid tool")
        valid_tool = all(
            character.isascii() and (character.isalnum() or character == "_") for character in tool
        )
        if not valid_tool:
            raise ValueError(f"step {index} has an invalid tool")
        try:
            spec = capability(capability_id)
        except KeyError as exc:
            raise ValueError(f"step {index} references an unknown capability") from exc
        if tool not in spec.tools:
            raise ValueError(f"{tool!r} is not provided by {capability_id!r}")
        tool_contract = tools.get(tool)
        if not isinstance(tool_contract, dict):
            raise ValueError(f"step {index} references an unknown tool")
        input_handles = set(tool_contract.get("input_handles") or ())
        output_handles = set(tool_contract.get("output_handles") or ())
        raw_needs = raw.get("needs", [])
        raw_creates = raw.get("produces", [])
        if not isinstance(raw_needs, list) or not isinstance(raw_creates, list):
            raise ValueError(f"step {step_id} handles must be arrays")
        if not all(isinstance(item, str) for item in (*raw_needs, *raw_creates)):
            raise ValueError(f"step {step_id} handles must be strings")
        needs = tuple(raw_needs)
        creates = tuple(raw_creates)
        explicit_approval = raw.get("approval")
        if explicit_approval not in {None, "none", "human"}:
            raise ValueError(f"step {step_id} has an invalid approval")
        if explicit_approval is not None and not isinstance(explicit_approval, str):
            raise ValueError(f"step {step_id} has an invalid approval")
        if set(needs) & set(creates):
            raise ValueError(f"step {step_id} cannot consume and produce the same handle")
        if len(needs) != len(set(needs)) or len(creates) != len(set(creates)):
            raise ValueError(f"step {step_id} repeats a handle")
        unknown_handles = (set(needs) | set(creates)) - set(HANDLES)
        if unknown_handles:
            raise ValueError(f"unknown handles: {sorted(unknown_handles)}")
        unexpected_inputs = set(needs) - input_handles
        if unexpected_inputs:
            raise ValueError(f"tool {tool} cannot consume handles: {sorted(unexpected_inputs)}")
        missing = set(needs) - produced - available
        if missing:
            raise ValueError(f"step {step_id} needs unavailable handles: {sorted(missing)}")
        if "twin_id" in creates and tool != "quantum_device_run":
            raise ValueError("only quantum_device_run may produce twin_id")
        bindings = raw.get("bindings", {})
        if not isinstance(bindings, dict) or set(bindings) - set(needs):
            raise ValueError(f"step {step_id} bindings must reference declared needs")
        resolved_bindings: dict[str, dict[str, str]] = {}
        for handle in needs:
            reference = bindings.get(handle)
            if reference is None and handle in bindings:
                raise ValueError(f"step {step_id} has an invalid binding")
            if reference is None:
                candidates = [{"step": source, "output": handle} for source in producers[handle]]
                candidates.extend(
                    {"input": name, "output": handle}
                    for name, item in external.items()
                    if item["handle"] == handle
                )
                if len(candidates) != 1:
                    raise ValueError(f"step {step_id} has ambiguous {handle}; explicit binding required")
                reference = candidates[0]
            if not isinstance(reference, dict) or reference.get("output") != handle:
                raise ValueError(f"step {step_id} has an invalid binding")
            if set(reference) == {"input", "output"}:
                source = external.get(reference["input"])
                if source is None or source["handle"] != handle:
                    raise ValueError(f"step {step_id} binding must reference a matching external input")
            elif (
                set(reference) != {"step", "output"}
                or not isinstance(reference.get("step"), str)
                or handle not in outputs_by_step.get(reference["step"], set())
            ):
                raise ValueError(f"step {step_id} binding must reference a matching earlier output")
            resolved_bindings[handle] = dict(reference)
        if "twin_id" in creates and spec.provider != "ionstack-twinrun":
            raise ValueError("twin_id requires the ionstack-twinrun provider")
        allowed_outputs = output_handles
        unowned_outputs = set(creates) - allowed_outputs
        if unowned_outputs:
            raise ValueError(f"tool {tool} cannot produce handles: {sorted(unowned_outputs)}")
        if tool == "quantum_simulate" and "circuit_id" not in needs:
            raise ValueError("quantum_simulate must declare circuit_id in needs")
        if tool == "quantum_compile_estimate" and "circuit_id" not in needs:
            raise ValueError("quantum_compile_estimate must declare circuit_id in needs")
        if tool == "quantum_device_run" and explicit_approval not in {None, "human"}:
            raise ValueError("quantum_device_run requires human approval")
        if set(needs) != input_handles:
            missing_inputs = input_handles - set(needs)
            if missing_inputs:
                raise ValueError(f"tool {tool} requires handles: {sorted(missing_inputs)}")
        if tool == "quantum_circuit_export" and "asset_id" not in needs:
            raise ValueError("quantum_circuit_export must declare asset_id in needs")
        if tool == "quantum_circuit_export" and set(creates) != {"circuit_id"}:
            raise ValueError("quantum_circuit_export must produce exactly circuit_id")
        if tool == "quantum_device_run" and "circuit_id" not in needs:
            raise ValueError("quantum_device_run must declare circuit_id in needs")
        if tool == "quantum_device_run" and set(creates) != {"twin_id"}:
            raise ValueError("quantum_device_run must produce exactly twin_id")
        if tool == "quantum_algorithm_run" and not set(creates) <= {"asset_id", "circuit_id"}:
            raise ValueError("quantum_algorithm_run declared invalid produced handles")
        if tool in {"quantum_simulate", "quantum_compile_estimate", "quantum_asset_get"} and creates:
            raise ValueError(f"tool {tool} must not declare produced handles")
        if tool in no_handle_tools and (needs or creates):
            raise ValueError(f"tool {tool} must not declare workflow handles")
        if tool != "quantum_device_run" and explicit_approval == "human":
            raise ValueError(f"step {step_id} cannot request device approval")
        arguments = raw.get("arguments")
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            raise ValueError(f"step {step_id} arguments must be an object")
        if set(arguments) & set(creates):
            raise ValueError(f"step {step_id} cannot provide produced handles as arguments")
        undeclared_handles = (set(arguments) & set(HANDLES)) - set(needs)
        if undeclared_handles:
            raise ValueError(
                f"step {step_id} must declare argument handles in needs: {sorted(undeclared_handles)}"
            )
        parameter_schema = tool_contract.get("parameters") or {}
        properties = parameter_schema.get("properties") or {}
        unknown_arguments = set(arguments) - set(properties)
        if unknown_arguments and parameter_schema.get("additionalProperties") is not True:
            raise ValueError(f"step {step_id} has unknown arguments: {sorted(unknown_arguments)}")
        static_arguments = dict(arguments)
        for handle in needs:
            if handle in static_arguments:
                raise ValueError(f"step {step_id} must declare handle {handle} only in needs")
            static_arguments[handle] = {
                "asset_id": "asset_workflow",
                "circuit_id": "circ_workflow",
                "twin_id": "twin_workflow",
            }[handle]
        if tool == "quantum_algorithm_run" and arguments.get("algorithm") == "__list_algorithms__":
            raise ValueError(f"step {step_id} must use quantum_algorithm_catalog for discovery")
        try:
            validate_json_schema(static_arguments, parameter_schema, path=f"step {step_id} arguments")
        except SchemaError as exc:
            raise ValueError(str(exc)) from exc
        approval = "human" if tool == "quantum_device_run" else "none"
        if explicit_approval not in {None, approval}:
            raise ValueError(f"step {step_id} approval contradicts the tool contract")
        steps.append(
            WorkflowStep(
                step_id,
                capability_id,
                tool,
                needs,
                creates,
                approval,
                arguments,
                resolved_bindings,
            )
        )
        outputs_by_step[step_id] = set(creates)
        for handle in creates:
            producers[handle].append(step_id)
        produced.update(creates)
        known_ids.add(step_id)
    result = {
        "valid": True,
        "validation_scope": "structure_and_arguments_only",
        "steps": [
            {
                "id": step.id,
                "capability": step.capability,
                "tool": step.tool,
                "needs": list(step.needs),
                "produces": list(step.produces),
                "approval": step.approval,
                "bindings": dict(step.bindings),
            }
            for step in steps
        ],
        "produces": sorted(produced),
    }
    record = args.get("record", False)
    if not isinstance(record, bool):
        raise ValueError("record must be a boolean")
    if record:
        from company_agent.work_items import WorkItemError, WorkItemStore
        try:
            with WorkItemStore() as store:
                attached = store.attach_plan(args.get("tenant_id"), [step.tool for step in steps])
        except WorkItemError as exc:
            raise ValueError(str(exc)) from exc
        result["plan_hash"] = attached["plan_hash"]
    return result
