"""Host the real platform adapter with inert executors for cross-repository tests."""
from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

from uniqon.adapters.company_agent_provider import (
    AssetStore,
    CompanyAgentProvider,
    ExecutionBudget,
    ExecutionOutcome,
    ParameterDescription,
    StaticBearerAuthenticator,
    TrustedExecutionRegistration,
    create_loopback_server,
)
from uniqon.descriptors import Capability, ComponentDescriptor

SCHEMA = {
    "type": "object", "properties": {"count": {"type": "integer", "minimum": 1, "maximum": 4}},
    "required": ["count"], "additionalProperties": False, "maxProperties": 1,
}


def main() -> None:
    """Serve one subprocess-local fixture and report only bounded counters."""
    calls = []
    authorizations = []

    def execute(parameters):
        calls.append(dict(parameters))
        return ExecutionOutcome(b"synthetic-opaque-result", {
            "status": "completed", "qubits": 2, "gate_count": 3,
            "metrics": {"schema_version": "scientific-metrics/1.0", "items": [
                {"name": "samples", "kind": "count", "value": parameters["count"], "unit": "count"},
            ]},
        }, b"synthetic-opaque-circuit")

    def authorize(context):
        authorizations.append(context.principal)
        return context.principal == "fixture-owner-a"

    identities = (("external.agent-contract-fixture", "1.0"),
                  ("external.agent-contract-fixture", "2.0"),
                  ("external.agent-contract-added", "1.0"))
    extensions = tuple(Capability(ComponentDescriptor(
        identity, version, "solver", "fixture/1.0", maturity="experimental",
        scientific_scope="Synthetic adapter contract only; no scientific execution.",
        input_schema="registered JSON schema",
    ), "S2", "fixture.inert", ()) for identity, version in identities)
    registrations = tuple(TrustedExecutionRegistration(
        identity, version, SCHEMA,
        (ParameterDescription("count", "integer", True, "Bounded fixture count."),),
        execute, lambda _parameters, _budget: True, ExecutionBudget(),
        f"fixture-registration-{identity}", "fixture-trust-1",
    ) for identity, version in identities if version == "1.0")
    path = Path(sys.argv[1])
    store = AssetStore(path)
    service = CompanyAgentProvider(
        store, StaticBearerAuthenticator({
            "synthetic-agent-contract-token-a": "fixture-owner-a",
            "synthetic-agent-contract-token-b": "fixture-owner-b",
        }), authorize=authorize, registrations=registrations, extensions=extensions,
    )
    server = create_loopback_server(service)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print(json.dumps({"url": f"http://127.0.0.1:{server.server_port}/invoke"}), flush=True)
    try:
        sys.stdin.readline()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
        before = [row.asset_id for row in store.list("fixture-owner-a")]
        store.close()
    reopened = AssetStore(path)
    try:
        persisted = [row.asset_id for row in reopened.list("fixture-owner-a")]
    finally:
        reopened.close()
    print(json.dumps({"executions": len(calls), "authorizations": len(authorizations),
                      "persisted": len(persisted), "reopen_matches": before == persisted}), flush=True)


if __name__ == "__main__":
    main()
