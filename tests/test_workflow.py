import pytest

from company_agent.workflow import validate


def test_workflow_rejects_unknown_top_level_fields() -> None:
    with pytest.raises(ValueError, match="workflow has unknown fields"):
        validate({"steps": [], "legacy": True})


def test_valid_quantum_workflow() -> None:
    result = validate(
        {
            "steps": [
                {
                    "id": "algorithm",
                    "capability": "company.algorithm",
                    "tool": "quantum_algorithm_run",
                    "produces": ["asset_id"],
                    "arguments": {
                        "catalog_version": "cat_fixture",
                        "component_version": "1.0",
                        "algorithm": "vqe",
                    },
                },
                {
                    "id": "circuit",
                    "capability": "company.asset",
                    "tool": "quantum_circuit_export",
                    "needs": ["asset_id"],
                    "produces": ["circuit_id"],
                },
                {
                    "id": "estimate",
                    "capability": "quantum.compilation",
                    "tool": "quantum_compile_estimate",
                    "needs": ["circuit_id"],
                },
                {
                    "id": "device",
                    "capability": "quantum.device",
                    "tool": "quantum_device_run",
                    "needs": ["circuit_id"],
                    "produces": ["twin_id"],
                    "arguments": {"shots": 8},
                },
            ]
        }
    )
    assert result["valid"] is True
    assert result["steps"][-1]["approval"] == "human"


def test_algorithm_catalog_step_has_no_handles() -> None:
    result = validate(
        {
            "steps": [
                {
                    "id": "catalog",
                    "capability": "company.algorithm",
                    "tool": "quantum_algorithm_catalog",
                    "arguments": {"query": "vqe", "limit": 8},
                },
                {
                    "id": "algorithm",
                    "capability": "company.algorithm",
                    "tool": "quantum_algorithm_run",
                    "produces": ["asset_id"],
                    "arguments": {
                        "catalog_version": "cat_fixture",
                        "component_version": "1.0",
                        "algorithm": "vqe",
                    },
                },
            ]
        }
    )
    assert result["valid"] is True
    assert result["steps"][0]["produces"] == []


def test_algorithm_catalog_cannot_declare_handles() -> None:
    with pytest.raises(ValueError, match="cannot produce handles"):
        validate(
            {
                "steps": [
                    {
                        "id": "catalog",
                        "capability": "company.algorithm",
                        "tool": "quantum_algorithm_catalog",
                        "produces": ["asset_id"],
                    }
                ]
            }
        )


def test_algorithm_run_rejects_discovery_sentinel() -> None:
    with pytest.raises(ValueError, match="quantum_algorithm_catalog"):
        validate(
            {
                "steps": [
                    {
                        "id": "algorithm",
                        "capability": "company.algorithm",
                        "tool": "quantum_algorithm_run",
                        "produces": ["asset_id"],
                        "arguments": {
                            "catalog_version": "cat_fixture",
                            "component_version": "1.0",
                            "algorithm": "__list_algorithms__",
                        },
                    }
                ]
            }
        )


def test_no_fourth_handle() -> None:
    with pytest.raises(ValueError, match="unknown handles"):
        validate(
            {
                "steps": [
                    {
                        "id": "bad",
                        "capability": "company.algorithm",
                        "tool": "quantum_algorithm_run",
                        "produces": ["illegal_handle"],
                    }
                ]
            }
        )


def algorithm_step(name):
    return {
        "id": name,
        "capability": "company.algorithm",
        "tool": "quantum_algorithm_run",
        "produces": ["asset_id", "circuit_id"],
        "arguments": {"catalog_version": "cat_fixture", "component_version": "1.0", "algorithm": "vqe"},
    }


def simulation_step(binding=None):
    step = {
        "id": "simulate",
        "capability": "quantum.simulation",
        "tool": "quantum_simulate",
        "needs": ["circuit_id"],
        "arguments": {"shots": 8},
    }
    if binding is not None:
        step["bindings"] = binding
    return step


def test_multiple_producers_resolve_explicit_branch() -> None:
    binding = {"circuit_id": {"step": "first", "output": "circuit_id"}}
    result = validate(
        {"steps": [algorithm_step("first"), algorithm_step("second"), simulation_step(binding)]}
    )
    assert result["valid"] is True
    assert result["validation_scope"] == "structure_and_arguments_only"
    assert result["steps"][-1]["bindings"] == binding
    assert result["produces"] == ["asset_id", "circuit_id"]


def test_legacy_needs_resolves_only_unique_upstream() -> None:
    result = validate({"steps": [algorithm_step("first"), simulation_step()]})
    assert result["steps"][-1]["bindings"] == {
        "circuit_id": {"step": "first", "output": "circuit_id"},
    }
    with pytest.raises(ValueError, match="ambiguous"):
        validate({"steps": [algorithm_step("first"), algorithm_step("second"), simulation_step()]})


@pytest.mark.parametrize(
    "binding",
    [
        {"circuit_id": {"step": "simulate", "output": "circuit_id"}},
        {"circuit_id": {"step": "future", "output": "circuit_id"}},
        {"circuit_id": {"step": "missing", "output": "circuit_id"}},
        {"circuit_id": {"step": "first", "output": "asset_id"}},
        {"circuit_id": {"step": "first", "output": "circuit_id", "extra": 1}},
        {"circuit_id": None},
        {"asset_id": {"step": "first", "output": "asset_id"}},
    ],
)
def test_bindings_reject_invalid_sources(binding) -> None:
    with pytest.raises(ValueError, match="binding"):
        validate({"steps": [algorithm_step("first"), simulation_step(binding), algorithm_step("future")]})


def test_binding_cannot_reference_undeclared_optional_output() -> None:
    first = algorithm_step("first")
    first["produces"] = ["asset_id"]
    binding = {"circuit_id": {"step": "first", "output": "circuit_id"}}
    with pytest.raises(ValueError, match="binding"):
        validate({"steps": [first, algorithm_step("second"), simulation_step(binding)]})


def test_workflow_validation_never_calls_provider(monkeypatch) -> None:
    monkeypatch.setattr(
        "company_agent.providers.ProviderClient.invoke",
        lambda *args: pytest.fail("static validation invoked a provider"),
    )
    assert validate({"steps": [algorithm_step("first"), simulation_step()]})["valid"]


def test_workflow_step_arguments_reject_unknown_fields() -> None:
    with pytest.raises(ValueError, match="unknown arguments"):
        validate(
            {
                "steps": [
                    {
                        "id": "algorithm",
                        "capability": "company.algorithm",
                        "tool": "quantum_algorithm_run",
                        "arguments": {"legacy": True},
                    }
                ]
            }
        )


def test_workflow_rejects_missing_required_static_argument() -> None:
    with pytest.raises(ValueError, match="algorithm is required"):
        validate(
            {
                "steps": [
                    {
                        "id": "algorithm",
                        "capability": "company.algorithm",
                        "tool": "quantum_algorithm_run",
                        "produces": ["asset_id"],
                    }
                ]
            }
        )


def test_workflow_rejects_invalid_static_argument() -> None:
    with pytest.raises(ValueError, match="shots must be >= 1"):
        validate(
            {
                "steps": [
                    {
                        "id": "algorithm",
                        "capability": "company.algorithm",
                        "tool": "quantum_algorithm_run",
                        "produces": ["circuit_id"],
                        "arguments": {
                            "catalog_version": "cat_fixture",
                            "component_version": "1.0",
                            "algorithm": "vqe",
                        },
                    },
                    {
                        "id": "device",
                        "capability": "quantum.device",
                        "tool": "quantum_device_run",
                        "needs": ["circuit_id"],
                        "produces": ["twin_id"],
                        "arguments": {"shots": 0},
                    },
                ]
            }
        )


def test_step_arguments_must_be_an_object() -> None:
    with pytest.raises(ValueError, match="arguments must be an object"):
        validate(
            {
                "steps": [
                    {
                        "id": "bad",
                        "capability": "company.algorithm",
                        "tool": "quantum_algorithm_run",
                        "arguments": [],
                    }
                ]
            }
        )


def test_step_unknown_fields_fail_closed() -> None:
    with pytest.raises(ValueError, match="unknown fields"):
        validate(
            {
                "steps": [
                    {
                        "id": "bad",
                        "capability": "company.workflow",
                        "tool": "company_capabilities",
                        "legacy_mode": True,
                    }
                ]
            }
        )


def test_step_handles_must_be_string_arrays() -> None:
    with pytest.raises(ValueError, match="handles must be strings"):
        validate(
            {
                "steps": [
                    {
                        "id": "bad",
                        "capability": "company.algorithm",
                        "tool": "quantum_algorithm_run",
                        "produces": [1],
                    }
                ]
            }
        )


def test_device_step_cannot_disable_human_approval() -> None:
    with pytest.raises(ValueError, match="requires human approval"):
        validate(
            {
                "steps": [
                    {
                        "id": "device",
                        "capability": "quantum.device",
                        "tool": "quantum_device_run",
                        "produces": ["twin_id"],
                        "approval": "none",
                    }
                ]
            }
        )


def test_only_device_run_can_produce_twin() -> None:
    with pytest.raises(ValueError, match="only quantum_device_run"):
        validate(
            {
                "steps": [
                    {
                        "id": "bad",
                        "capability": "quantum.simulation",
                        "tool": "quantum_simulate",
                        "produces": ["twin_id"],
                    }
                ]
            }
        )


def test_device_step_requires_available_circuit() -> None:
    with pytest.raises(ValueError, match="requires handles"):
        validate(
            {
                "steps": [
                    {
                        "id": "device",
                        "capability": "quantum.device",
                        "tool": "quantum_device_run",
                        "produces": ["twin_id"],
                        "arguments": {"shots": 8},
                    }
                ]
            }
        )


def test_workflow_handle_cannot_be_duplicated_in_arguments() -> None:
    with pytest.raises(ValueError, match="only in needs"):
        validate(
            {
                "steps": [
                    {
                        "id": "algorithm",
                        "capability": "company.algorithm",
                        "tool": "quantum_algorithm_run",
                        "produces": ["circuit_id"],
                        "arguments": {
                            "catalog_version": "cat_fixture",
                            "component_version": "1.0",
                            "algorithm": "vqe",
                        },
                    },
                    {
                        "id": "simulate",
                        "capability": "quantum.simulation",
                        "tool": "quantum_simulate",
                        "needs": ["circuit_id"],
                        "arguments": {"circuit_id": "circ_other", "shots": 8},
                    },
                ]
            }
        )


def test_tool_cannot_claim_handle_owned_by_another_capability() -> None:
    with pytest.raises(ValueError, match="cannot produce handles"):
        validate(
            {
                "steps": [
                    {
                        "id": "bad",
                        "capability": "quantum.compilation",
                        "tool": "quantum_compile_estimate",
                        "produces": ["asset_id"],
                    }
                ]
            }
        )


def test_tool_cannot_claim_sibling_tool_output() -> None:
    with pytest.raises(ValueError, match="cannot produce handles"):
        validate(
            {
                "steps": [
                    {
                        "id": "bad",
                        "capability": "company.asset",
                        "tool": "quantum_asset_get",
                        "produces": ["circuit_id"],
                    }
                ]
            }
        )


def test_tool_cannot_consume_unowned_handle() -> None:
    with pytest.raises(ValueError, match="cannot consume handles"):
        validate(
            {
                "steps": [
                    {
                        "id": "algorithm",
                        "capability": "company.algorithm",
                        "tool": "quantum_algorithm_run",
                        "produces": ["asset_id"],
                        "arguments": {
                            "catalog_version": "cat_fixture",
                            "component_version": "1.0",
                            "algorithm": "vqe",
                        },
                    },
                    {
                        "id": "bad",
                        "capability": "quantum.compilation",
                        "tool": "quantum_compile_estimate",
                        "needs": ["asset_id"],
                    },
                ]
            }
        )


def test_consumed_handle_cannot_be_redeclared_as_output() -> None:
    with pytest.raises(ValueError, match="cannot consume and produce the same handle"):
        validate(
            {
                "steps": [
                    {
                        "id": "algorithm",
                        "capability": "company.algorithm",
                        "tool": "quantum_algorithm_run",
                        "produces": ["asset_id", "circuit_id"],
                        "arguments": {
                            "catalog_version": "cat_fixture",
                            "component_version": "1.0",
                            "algorithm": "vqe",
                        },
                    },
                    {
                        "id": "simulate",
                        "capability": "quantum.simulation",
                        "tool": "quantum_simulate",
                        "needs": ["circuit_id"],
                        "produces": ["circuit_id"],
                    },
                ]
            }
        )
