from company_agent.capabilities import list_capabilities
from company_agent.catalog import (
    load_capabilities,
    load_policy,
    load_presets,
    load_providers,
    load_tools,
)
from company_agent.contracts import HANDLE_PREFIXES, HANDLES, PROVIDER_PROTOCOL


def test_contract_top_level_shapes_are_exact() -> None:
    tools = load_tools()
    capabilities = load_capabilities()
    providers = load_providers()
    presets = load_presets()
    assert set(capabilities) == {"version", "capabilities"}
    assert set(providers) == {"protocol", "providers"}
    assert set(presets) == {"version", "presets"}
    assert capabilities["version"] == "1.0.0"
    assert presets["version"] == "1.0.0"
    assert tools


def test_duplicate_capability_ids_are_rejected(monkeypatch) -> None:
    row = {
        "id": "duplicate",
        "kind": "workflow",
        "provider": "company-agent",
        "contract_version": "1",
        "tools": [],
    }
    monkeypatch.setattr(
        "company_agent.capabilities.load_capabilities",
        lambda: {"capabilities": [row, row]},
    )
    try:
        list_capabilities()
    except RuntimeError as exc:
        assert "capability contract is invalid" in str(exc)
    else:
        raise AssertionError("duplicate capabilities were accepted")


def test_capability_and_tool_catalogs_are_consistent() -> None:
    capabilities = {item.id: item for item in list_capabilities()}
    tools = load_tools()
    assert tuple(HANDLES) == ("asset_id", "circuit_id", "twin_id")
    assert HANDLE_PREFIXES == {
        "asset_id": "asset_",
        "circuit_id": "circ_",
        "twin_id": "twin_",
    }
    assert {
        "company.algorithm",
        "company.asset",
        "quantum.simulation",
        "quantum.compilation",
        "quantum.device",
        "compute.cloud",
        "compute.hpc",
        "company.knowledge",
        "company.workflow",
        "company.latex",
        "company.office",
        "company.plan",
        "company.portal",
        "company.research",
    } == set(capabilities)
    for name, row in tools.items():
        assert row["capability"] in capabilities, name
        assert name in capabilities[row["capability"]].tools, name
        assert set(row["input_handles"]) <= set(HANDLES)
        assert set(row["output_handles"]) <= set(HANDLES)
        assert set(row["input_handles"]).isdisjoint(row["output_handles"])
        assert set(row["input_handles"]) | set(row["output_handles"]) <= set(
            capabilities[row["capability"]].handles
        )
        required_arguments = set(row["parameters"].get("required") or ())
        assert set(row["input_handles"]) <= required_arguments
        parameters = row["parameters"]
        assert parameters["type"] == "object"
        assert parameters["additionalProperties"] is False
        assert set(parameters.get("required") or ()) <= set(parameters.get("properties") or {})
        schema = row["output"]
        assert schema["type"] == "object"
        assert schema["additionalProperties"] is False
        assert set(schema.get("required") or ()) <= set(schema.get("properties") or {})
        assert set(row["output_handles"]) <= set(schema.get("properties") or {})
        for handle in row["output_handles"]:
            assert handle in set(schema.get("required") or ()) or name == "quantum_algorithm_run"


def test_nested_object_contracts_declare_properties_explicitly() -> None:
    def check(schema: dict) -> None:
        if schema.get("type") == "object":
            assert isinstance(schema.get("properties"), dict), schema
            assert "additionalProperties" in schema
            for child in schema["properties"].values():
                check(child)
            additional = schema["additionalProperties"]
            if isinstance(additional, dict):
                check(additional)
        if schema.get("type") == "array":
            check(schema["items"])

    for row in load_tools().values():
        check(row["parameters"])
        check(row["output"])


def test_contract_graph_is_closed_and_unique() -> None:
    tools = load_tools()
    capabilities = {item.id: item for item in list_capabilities()}
    providers = load_providers()
    provider_rows = providers["providers"]
    provider_by_id = {row["id"]: row for row in provider_rows}
    expected_provider_ids = {
        "uniqon",
        "independent-simulator",
        "independent-compiler",
        "ionstack-twinrun",
        "uqc-cloud",
        "hpc-slurm-ssh",
    }
    assert set(provider_by_id) == expected_provider_ids
    provider_operations: list[tuple[str, str]] = [
        (str(row["id"]), str(operation)) for row in provider_rows for operation in row["operations"]
    ]
    assert providers["protocol"] == PROVIDER_PROTOCOL
    assert len(provider_by_id) == len(provider_rows)
    assert len(provider_operations) == len(set(provider_operations))
    assert len(tools) == len(set(tools))
    referenced_tools: set[str] = set()
    referenced_operations: set[tuple[str, str]] = set()
    for capability in capabilities.values():
        assert len(capability.tools) == len(set(capability.tools))
        referenced_tools.update(capability.tools)
        for tool in capability.tools:
            assert tools[tool]["capability"] == capability.id
        if capability.kind in {"platform", "simulator", "compiler", "device", "compute", "cloud"}:
            assert capability.provider in provider_by_id
            allowed_operations = set(provider_by_id[capability.provider]["operations"])
            operations = {tools[tool]["operation"] for tool in capability.tools}
            assert operations <= allowed_operations
            referenced_operations.update((capability.provider, operation) for operation in operations)
    assert referenced_tools == set(tools)
    assert referenced_operations == set(provider_operations)


def test_presets_reference_only_known_tools() -> None:
    tools = set(load_tools())
    presets = load_presets()["presets"]
    assert set(presets) == {"boot", "lab", "algo", "sign"}
    visible_union: set[str] = set()
    for row in presets.values():
        visible = row["visible_tools"]
        assert len(visible) == len(set(visible))
        assert set(visible) <= tools
        visible_union.update(visible)
    assert visible_union == tools
    assert "quantum_device_run" not in presets["boot"]["visible_tools"]
    assert "quantum_device_run" not in presets["algo"]["visible_tools"]
    assert "quantum_device_run" in presets["lab"]["visible_tools"]
    assert "quantum_device_run" in presets["sign"]["visible_tools"]


def test_policy_device_identity_matches_capability_contract() -> None:
    policy = load_policy()
    assert policy["version"] == "1.0.0"
    assert set(policy) == {
        "version",
        "fail_closed",
        "forbidden_tools",
        "device_tool",
        "device_provider",
        "device_provenance",
        "device_ask_presets",
        "device_deny_presets",
        "hpc_submit_tool",
        "hpc_submit_provider",
        "hpc_submit_ask_presets",
        "hpc_submit_deny_presets",
        "hpc_file_write_tool",
        "hpc_file_write_provider",
        "hpc_file_write_ask_presets",
        "hpc_file_write_deny_presets",
        "hpc_job_cancel_tool",
        "hpc_job_cancel_provider",
        "hpc_job_cancel_ask_presets",
        "hpc_job_cancel_deny_presets",
        "cloud_submit_tool",
        "cloud_submit_provider",
        "cloud_submit_ask_presets",
        "cloud_submit_deny_presets",
        "cloud_submission",
        "latex_write_tools",
        "latex_write_provider",
        "latex_write_ask_presets",
        "latex_write_deny_presets",
        "plan_write_tools",
        "plan_write_provider",
        "plan_write_ask_presets",
        "plan_write_deny_presets",
        "research_run_tool",
        "research_run_provider",
        "research_run_ask_presets",
        "research_run_deny_presets",
    }
    device = next(item for item in list_capabilities() if item.id == "quantum.device")
    assert policy["fail_closed"] is True
    assert policy["device_tool"] == "quantum_device_run"
    assert policy["device_provider"] == device.provider
    assert policy["device_provenance"] == device.provenance
    assert set(policy["device_ask_presets"]) == {"lab", "sign"}
    assert set(policy["device_deny_presets"]) == {"boot", "algo"}
    assert set(policy["device_ask_presets"]).isdisjoint(policy["device_deny_presets"])
    assert set(policy["device_ask_presets"]) | set(policy["device_deny_presets"]) == set(
        load_presets()["presets"]
    )
    hpc = next(item for item in list_capabilities() if item.id == "compute.hpc")
    assert policy["hpc_submit_tool"] == "hpc_submit"
    assert policy["hpc_submit_provider"] == hpc.provider
    assert set(policy["hpc_submit_ask_presets"]) == {"lab", "sign"}
    assert set(policy["hpc_submit_deny_presets"]) == {"boot", "algo"}
    assert set(policy["hpc_submit_ask_presets"]).isdisjoint(policy["hpc_submit_deny_presets"])
    assert set(policy["hpc_submit_ask_presets"]) | set(policy["hpc_submit_deny_presets"]) == set(
        load_presets()["presets"]
    )
    assert policy["hpc_file_write_tool"] == "hpc_stage_file"
    assert policy["hpc_file_write_provider"] == hpc.provider
    assert set(policy["hpc_file_write_ask_presets"]) == {"lab", "sign"}
    assert set(policy["hpc_file_write_deny_presets"]) == {"boot", "algo"}
    assert set(policy["hpc_file_write_ask_presets"]).isdisjoint(policy["hpc_file_write_deny_presets"])
    assert set(policy["hpc_file_write_ask_presets"]) | set(policy["hpc_file_write_deny_presets"]) == set(
        load_presets()["presets"]
    )
    cloud = next(item for item in list_capabilities() if item.id == "compute.cloud")
    assert policy["cloud_submit_tool"] == "quantum_cloud_submit"
    assert policy["cloud_submit_provider"] == cloud.provider
    assert set(policy["cloud_submit_ask_presets"]) == {"lab", "sign"}
    assert set(policy["cloud_submit_deny_presets"]) == {"boot", "algo"}
    assert set(policy["cloud_submit_ask_presets"]).isdisjoint(policy["cloud_submit_deny_presets"])
    assert set(policy["cloud_submit_ask_presets"]) | set(policy["cloud_submit_deny_presets"]) == set(
        load_presets()["presets"]
    )
    assert policy["cloud_submission"] == {
        "target_scope": "simulators_only", "artifact_scope": "workspace_openqasm_file",
        "automatic_retries": 0,
    }
    assert policy["hpc_job_cancel_tool"] == "hpc_job_cancel"
    assert policy["hpc_job_cancel_provider"] == hpc.provider
    assert set(policy["hpc_job_cancel_ask_presets"]) == {"lab", "sign"}
    assert set(policy["hpc_job_cancel_deny_presets"]) == {"boot", "algo"}
    assert set(policy["hpc_job_cancel_ask_presets"]).isdisjoint(policy["hpc_job_cancel_deny_presets"])
    assert set(policy["hpc_job_cancel_ask_presets"]) | set(policy["hpc_job_cancel_deny_presets"]) == set(
        load_presets()["presets"]
    )
    research = next(item for item in list_capabilities() if item.id == "company.research")
    assert policy["research_run_tool"] == "company_research_run"
    assert policy["research_run_provider"] == research.provider
    assert policy["research_run_ask_presets"] == ["lab"]
    assert policy["research_run_deny_presets"] == ["boot", "algo", "sign"]
    assert set(policy["research_run_ask_presets"]).isdisjoint(policy["research_run_deny_presets"])
    assert set(policy["research_run_ask_presets"]) | set(policy["research_run_deny_presets"]) == set(
        load_presets()["presets"]
    )


def test_only_device_capability_can_produce_twin_id() -> None:
    producers = [item.id for item in list_capabilities() if "twin_id" in item.handles]
    assert producers == ["quantum.device"]


def test_algorithm_catalog_is_owned_by_platform() -> None:
    row = load_tools()["quantum_algorithm_catalog"]
    assert row["capability"] == "company.algorithm"
    assert row["operation"] == "algorithm.catalog"
    assert row["input_handles"] == []
    assert row["output_handles"] == []
    assert row["output"]["properties"]["provider"]["const"] == "uniqon"
    providers = {item["id"]: item for item in load_providers()["providers"]}
    assert "algorithm.catalog" in providers["uniqon"]["operations"]
    presets = load_presets()["presets"]
    assert "quantum_algorithm_catalog" in presets["lab"]["visible_tools"]
    assert "quantum_algorithm_catalog" in presets["algo"]["visible_tools"]
    assert "quantum_algorithm_catalog" not in presets["boot"]["visible_tools"]
    assert "quantum_algorithm_catalog" not in presets["sign"]["visible_tools"]
    algorithm = next(item for item in list_capabilities() if item.id == "company.algorithm")
    assert algorithm.provider == "uniqon"
    assert algorithm.tools == ("quantum_algorithm_catalog", "quantum_algorithm_run")
    assert algorithm.contract_version == "company.algorithm/2.0"


def test_asset_list_only_exposes_bounded_existing_asset_references() -> None:
    row = load_tools()["quantum_asset_list"]
    assert row["operation"] == "asset.list"
    assert row["output_handles"] == []
    assets = row["output"]["properties"]["assets"]
    assert assets["maxItems"] == 32
    assert assets["items"]["required"] == ["asset_id"]
    assert set(assets["items"]["properties"]) == {"asset_id", "kind", "label", "status"}
    assert assets["items"]["additionalProperties"] is False


def test_tool_registration_is_exactly_once_across_company_plugins() -> None:
    capabilities_by_package = {
        "core": {"company.workflow", "company.knowledge", "company.portal"},
        "quantum": {
            "company.algorithm",
            "company.asset",
            "quantum.simulation",
            "quantum.compilation",
            "compute.cloud",
        },
        "device": {"quantum.device"},
        "hpc": {"compute.hpc"},
        "latex": {"company.latex"},
        "office": {"company.office"},
        "plan": {"company.plan"},
        "research": {"company.research"},
    }
    registered: list[str] = []
    capabilities = {item.id: item for item in list_capabilities()}
    for package_capabilities in capabilities_by_package.values():
        for capability_id in package_capabilities:
            registered.extend(capabilities[capability_id].tools)
    assert len(registered) == len(set(registered))
    assert set(registered) == set(load_tools())
