"""P8-A1 governance immediacy: survey H03 pinned for the tenants registry.

The plan's H03 acceptance behavior demands「撤权即时生效且有跨实例反例」. The
tenant registry is the shared durable instance medium: every projection call
re-reads it, so a row rewritten between two calls (by the operator, another
process, or the demo approval writer) binds the very next fact. The default
approval posture (H02) is already triple-pinned (CLI gating, DSH runtime,
release manifest) and is not repeated here beyond the direct API surface.
"""

from __future__ import annotations

import json

from company_agent.tenants import projection

SUBJECT = "operator@corp.example.com"
TRUSTED = "trusted"

LINES = {
    "approved": {"subject": SUBJECT, "service": "compute.cloud",
                 "state": "approved", "expires_epoch": None, "approved_by": "owner"},
    "revoked": {"subject": SUBJECT, "service": "compute.cloud",
                "state": "revoked", "expires_epoch": None, "approved_by": "owner"},
    "other": {"subject": SUBJECT, "service": "compute.hpc",
              "state": "approved", "expires_epoch": None, "approved_by": "owner"},
}


def _write(path, lines: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(row) + "\n" for row in lines), encoding="utf-8",
    )


def test_revocation_applies_on_the_next_projection_mid_process(tmp_path, monkeypatch) -> None:
    registry = tmp_path / "tenants.jsonl"
    _write(registry, [LINES["approved"]])
    monkeypatch.setenv("COMPANY_AGENT_TENANT_REGISTRY", str(registry))
    monkeypatch.setenv("COMPANY_AGENT_SUBJECT", SUBJECT)
    monkeypatch.setattr("company_agent.receipts.subject", lambda: SUBJECT)
    monkeypatch.setattr("company_agent.receipts.subject_source", lambda: TRUSTED)

    first = projection(SUBJECT, TRUSTED)
    assert first["regime"] == "registry"
    assert first["services"]["compute.cloud"]["enabled"] is True

    # The operator (or any other instance bound to the same durable file)
    # revokes the row; the very next projection must bind the new fact.
    _write(registry, [LINES["approved"], LINES["revoked"]])
    second = projection(SUBJECT, TRUSTED)
    assert second["services"]["compute.cloud"]["enabled"] is False
    assert second["services"]["compute.cloud"]["reason"] == "revoked"

    # Removing the row and re-approving again is equally immediate.
    _write(registry, [LINES["other"], LINES["approved"]])
    third = projection(SUBJECT, TRUSTED)
    assert third["services"]["compute.cloud"]["enabled"] is True
    assert third["services"]["compute.cloud"]["reason"] == "approved"


def test_expiry_cut_applies_immediately_mid_process(tmp_path, monkeypatch) -> None:
    """Same H03 semantics for the validity window: rows bind fresh facts."""

    import time as time_module

    facts = tmp_path / "tenants.jsonl"
    monkeypatch.setenv("COMPANY_AGENT_TENANT_REGISTRY", str(facts))
    monkeypatch.setenv("COMPANY_AGENT_SUBJECT", SUBJECT)
    monkeypatch.setattr("company_agent.receipts.subject", lambda: SUBJECT)
    monkeypatch.setattr("company_agent.receipts.subject_source", lambda: TRUSTED)

    frozen = {"now": int(time_module.time()) + 3}
    monkeypatch.setattr("company_agent.tenants.time.time", lambda: frozen["now"])
    _write(facts, [{**LINES["approved"], "expires_epoch": frozen["now"]}])
    first = projection(SUBJECT, TRUSTED)
    assert first["services"]["compute.cloud"]["enabled"] is True

    # Unified boundary with the knowledge registry: the recorded epoch itself
    # is still valid; the next epoch is gone (strict ``now > expires``).
    frozen["now"] += 2
    second = projection(SUBJECT, TRUSTED)
    assert second["services"]["compute.cloud"]["enabled"] is False
    assert second["services"]["compute.cloud"]["reason"] == "expired"


def test_registry_file_removal_degrades_immediately(tmp_path, monkeypatch) -> None:
    registry = tmp_path / "tenants.jsonl"
    _write(registry, [LINES["approved"]])
    monkeypatch.setenv("COMPANY_AGENT_TENANT_REGISTRY", str(registry))
    monkeypatch.setenv("COMPANY_AGENT_SUBJECT", SUBJECT)
    monkeypatch.setattr("company_agent.receipts.subject", lambda: SUBJECT)
    monkeypatch.setattr("company_agent.receipts.subject_source", lambda: TRUSTED)
    assert projection(SUBJECT, TRUSTED)["regime"] == "registry"

    # A vanished registry cannot silently become legacy-with-facts: the
    # configured regime degrades to unavailable (fail closed), which is the
    # cross-instance "the medium itself went away" counterexample.
    registry.unlink()
    assert not registry.exists()
    after = projection(SUBJECT, TRUSTED)
    assert after["regime"] == "unavailable"
    assert all(
        row["enabled"] is False and row["reason"] == "registry_unavailable"
        for row in after["services"].values()
    )


def test_untrusted_subject_stops_consuming_rows_immediately(tmp_path, monkeypatch) -> None:
    registry = tmp_path / "tenants.jsonl"
    _write(registry, [LINES["approved"]])
    monkeypatch.setenv("COMPANY_AGENT_TENANT_REGISTRY", str(registry))
    monkeypatch.setenv("COMPANY_AGENT_SUBJECT", SUBJECT)
    monkeypatch.setattr("company_agent.receipts.subject", lambda: SUBJECT)
    monkeypatch.setattr("company_agent.receipts.subject_source", lambda: TRUSTED)
    assert projection(SUBJECT, TRUSTED)["services"]["compute.cloud"]["enabled"] is True

    # The subject source degrades to untrusted mid-process (the trusted env
    # disappears): the registry must never be consulted for such subjects.
    monkeypatch.delenv("COMPANY_AGENT_SUBJECT", raising=False)
    degraded_receipts = ("unknown@unknown", "untrusted")
    monkeypatch.setattr(
        "company_agent.receipts.subject", lambda: degraded_receipts[0],
    )
    monkeypatch.setattr(
        "company_agent.receipts.subject_source", lambda: degraded_receipts[1],
    )
    after = projection(degraded_receipts[0], degraded_receipts[1])
    assert all(row["enabled"] is False for row in after["services"].values())
    assert after["regime"] != "registry" or all(
        row["reason"] != "approved" for row in after["services"].values()
    )
