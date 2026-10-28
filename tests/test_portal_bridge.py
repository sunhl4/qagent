"""Company.portal adapter gates: the cloud platform and HPC workspace pages are
reachable from the conversation only as kind+route facts; nothing here dispatches
network traffic, handles credentials or reads portal page content."""
from __future__ import annotations

import json
from typing import Any

import pytest

from company_agent.capabilities import list_capabilities
from company_agent.catalog import builtin_tools_for_preset, load_presets, load_tools
from company_agent.invoke import invoke, validate_invocation
from company_agent.policy import decide
from company_agent.portal import PortalError, load_portal_sources, open_portal

TOOL = "company_portal_open"
ROUTES = {
    "cloud": "/company-workspace/portal/cloud/",
    "hpc": "/company-workspace/portal/hpc/",
}
_NOTE = {kind: str(open_portal({"kind": kind})["note"]) for kind in ROUTES}


def test_contract_declares_exactly_one_open_fact_tool() -> None:
    row = load_tools()[TOOL]
    assert row["capability"] == "company.portal"
    assert row["operation"] == "portal.open"
    assert row["input_handles"] == [] and row["output_handles"] == []
    assert row["parameters"]["properties"].keys() == {"kind"}
    assert row["parameters"]["properties"]["kind"]["enum"] == ["cloud", "hpc"]
    assert row["output"]["properties"]["route"]["pattern"] == "^/company-workspace/portal/(cloud|hpc)/$"


def test_capability_is_local_only_and_never_billable() -> None:
    caps = {item.id: item for item in list_capabilities()}
    capability = caps["company.portal"]
    assert capability.kind == "portal"
    assert capability.provider == "company-portal"
    # The kind tokens live in the shared contract; portal is a pure local fact.
    assert capability.tools == (TOOL,)
    assert capability.handles == () and capability.approval == "none"
    sources = load_portal_sources()
    assert [(row["kind"], row["route"]) for row in sources["portals"]] == sorted(ROUTES.items())


def test_open_facts_are_bounded_and_never_urls() -> None:
    for kind, route in sorted(ROUTES.items()):
        invoked = invoke(TOOL, "lab", {"kind": kind})
        assert invoked.status == "ok", invoked.error
        payload: dict[str, Any] = invoked.payload  # type: ignore[assignment]
        assert payload == {
            "ok": True,
            "kind": kind,
            "route": route,
            "note": _NOTE[kind],
        }
        assert validate_invocation(TOOL, {"kind": kind}) is None
        assert validate_invocation(TOOL, {"kind": "outer"}) is not None
        encoded = json.dumps(payload, ensure_ascii=False)
        assert len(encoded) < 600
        assert "://" not in encoded, "open facts never carry absolute URLs"
        assert payload["route"].startswith("/company-workspace/")


def test_unknown_kind_fails_closed_without_dispatch() -> None:
    invoked = invoke(TOOL, "lab", {"kind": "dev"})
    assert invoked.status == "error"
    assert invoked.error and "kind" in str(invoked.error.lower())
    assert validate_invocation(TOOL, {"kind": "dev"}) != ""


def test_empty_arguments_fail_at_the_schema_gate() -> None:
    invoked = invoke(TOOL, "lab", {})
    assert invoked.status == "error"


def test_direct_open_portal_rejects_malformed_arguments() -> None:
    with pytest.raises(PortalError) as exc_info:
        open_portal({"kind": "hpc-dev"})
    assert "portal kind is unknown" in str(exc_info.value)
    with pytest.raises(PortalError):
        open_portal(None)
    with pytest.raises(PortalError):
        open_portal({"kind": ["cloud"]})


def test_portal_open_is_visible_in_boot_lab_algo_and_hidden_in_sign() -> None:
    by_preset = {preset: row["visible_tools"] for preset, row in load_presets()["presets"].items()}
    for preset in ("boot", "lab", "algo"):
        assert TOOL in by_preset[preset], preset
    assert TOOL not in by_preset["sign"]


def test_open_navigation_never_requires_approval_or_tenant_service() -> None:
    for preset in ("boot", "lab", "algo"):
        assert decide(TOOL, preset, {"kind": "cloud"}) == "allow"


def test_portal_tools_join_the_builtin_free_managed_roster() -> None:
    # Managed native builtins stay disjoint from capability tools; the four
    # profile probes keep the exact same expectation shape.
    builtins = set(builtin_tools_for_preset("lab"))
    assert TOOL not in builtins
    assert load_tools()[TOOL]["name"] == TOOL
