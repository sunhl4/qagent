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
    "approved": {"subject": SUBJECT, "class": "internal", "service": "compute.cloud",
                 "state": "approved", "expires_epoch": None, "approved_by": "owner"},
    "revoked": {"subject": SUBJECT, "class": "internal", "service": "compute.cloud",
                "state": "revoked", "expires_epoch": None, "approved_by": "owner"},
    "other": {"subject": SUBJECT, "class": "internal", "service": "compute.hpc",
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

    _write(registry, [LINES["approved"], LINES["revoked"]])
    second = projection(SUBJECT, TRUSTED)
    assert second["services"]["compute.cloud"]["enabled"] is False
    assert second["services"]["compute.cloud"]["reason"] == "revoked"

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

    monkeypatch.delenv("COMPANY_AGENT_SUBJECT", raising=False)
    degraded_receipts = ("unknown@unknown", "untrusted")
    monkeypatch.setattr("company_agent.receipts.subject", lambda: degraded_receipts[0])
    monkeypatch.setattr("company_agent.receipts.subject_source", lambda: degraded_receipts[1])
    after = projection(degraded_receipts[0], degraded_receipts[1])
    assert all(row["enabled"] is False for row in after["services"].values())
    assert after["regime"] != "registry" or all(
        row["reason"] != "approved" for row in after["services"].values()
    )


def test_receipt_store_hides_other_subjects(tmp_path, monkeypatch) -> None:
    from company_agent import receipts

    store = tmp_path / "receipts"
    store.mkdir()
    monkeypatch.setenv("COMPANY_AGENT_RECEIPT_DIR", str(store))
    monkeypatch.setenv("COMPANY_AGENT_SUBJECT", "current@corp.example.com")
    event = {
        "version": "1.2", "record": "dispatch", "tool": "hpc_submit", "operation": "hpc.submit",
        "request_id": "req_" + "a" * 32, "contract_digest": "sha256:" + "0" * 64,
        "elapsed_ms": 0, "status": "dispatched", "error_category": "none",
        "execution_state": "dispatched", "timestamp": 1,
        "business_ref": "", "subject": "current@corp.example.com",
    }
    path = store / "receipts-20990101-0001.jsonl"
    path.write_text(
        json.dumps({**event, "subject": "other@corp.example.com"}) + "\n"
        + json.dumps({**event, "request_id": "req_" + "b" * 32, "subject": "current@corp.example.com"}) + "\n",
        encoding="utf-8",
    )
    rows = receipts.load_records(limit=10)
    assert [row["request_id"] for row in rows] == ["req_" + "b" * 32]
    assert receipts.reconcile(limit=10)["unknown"][0]["request_id"] == "req_" + "b" * 32
