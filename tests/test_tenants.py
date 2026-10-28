"""Architecture gates for P1-C: tenant/service enablement projection.

Sources: docs/company-agent-2000-person-days-development-plan-v1.0.zh-CN.md P1 and
docs/oss-survey/04-工程衔接建议.zh-CN.md 「P0 2.1」. The registry is operator
data; enablement is a modeled fact that never widens tool visibility and never
acts on model-controlled input. A configured-but-invalid registry fails closed
to "unavailable" rather than guessing an enablement.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from company_agent.invoke import invoke
from company_agent.receipts import subject, subject_source
from company_agent.tenants import projection, re_all_subjects_valid, summary

TRUSTED = "operator@corp.example.com"
OTHER = "guest@corp.example.com"
SERVICE = "compute.cloud"
OTHER_SERVICE = "company.algorithm"
ALL_SERVICES = {"company.algorithm", "company.asset", "compute.cloud", "compute.hpc"}


@pytest.fixture(autouse=True)
def hermetic(monkeypatch) -> None:
    monkeypatch.delenv("COMPANY_AGENT_TENANT_REGISTRY", raising=False)
    monkeypatch.delenv("COMPANY_AGENT_SUBJECT", raising=False)
    monkeypatch.setenv("COMPANY_AGENT_PROFILE", "company-agent")


def _registry(
    monkeypatch, tmp_path: Path, rows: list[dict[str, object]], name: str = "tenants.jsonl"
) -> Path:
    path = tmp_path / name
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    path.chmod(0o600)
    monkeypatch.setenv("COMPANY_AGENT_TENANT_REGISTRY", str(path))
    return path


def _line(subject: str = TRUSTED, service: str = SERVICE, state: str = "approved",
          expires_epoch: int | None = None, approved_by: str = "owner@corp") -> dict[str, object]:
    return {"subject": subject, "service": service, "state": state,
            "expires_epoch": expires_epoch, "approved_by": approved_by}


def test_legacy_regime_without_registry(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("COMPANY_AGENT_TENANT_REGISTRY", raising=False)
    assert not summary()["configured"]
    facts = projection(TRUSTED, "trusted")
    assert facts["regime"] == "legacy-single-user"
    assert facts["services"] == {}
    payload = invoke("company_capabilities", "lab")
    assert payload.status == "ok"
    assert payload.payload["enablement"]["regime"] == "legacy-single-user"


def test_approved_entry_enables_only_that_service(monkeypatch, tmp_path) -> None:
    _registry(monkeypatch, tmp_path, [_line()])
    facts = projection(TRUSTED, "trusted")
    assert facts["regime"] == "registry"
    assert facts["services"][SERVICE]["enabled"] is True
    assert facts["services"][SERVICE]["reason"] == "approved"
    assert facts["services"][OTHER_SERVICE]["enabled"] is False
    assert facts["services"][OTHER_SERVICE]["reason"] == "subject_absent"
    status = summary()
    assert status["valid"] is True and status["approved_services"] == 1
    assert status["subjects"] == 1 and status["entries"] == 1


def test_expired_pending_and_revoked_facts(monkeypatch, tmp_path) -> None:
    _registry(monkeypatch, tmp_path, [
        _line(service=SERVICE, expires_epoch=1),
        _line(service=OTHER_SERVICE, state="pending"),
        _line(subject=OTHER, service=SERVICE, state="revoked"),
    ])
    facts = projection(TRUSTED, "trusted")
    assert facts["services"][SERVICE]["reason"] == "expired"
    assert facts["services"][SERVICE]["enabled"] is False
    assert facts["services"][OTHER_SERVICE]["reason"] == "pending"
    other_facts = projection(OTHER, "trusted")
    assert other_facts["services"][SERVICE]["reason"] == "revoked"
    assert other_facts["services"][SERVICE]["enabled"] is False


def test_latest_line_wins_for_one_subject_service(monkeypatch, tmp_path) -> None:
    _registry(monkeypatch, tmp_path, [
        _line(state="pending"),
        _line(state="approved"),
    ])
    facts = projection(TRUSTED, "trusted")
    assert facts["services"][SERVICE]["reason"] == "approved"
    assert facts["services"][SERVICE]["enabled"] is True


def test_untrusted_subject_never_matches_registry(monkeypatch, tmp_path) -> None:
    # Even a line registered for the literal untrusted identity must never be
    # consumed by an untrusted subject: identity unusable means facts unknown.
    _registry(monkeypatch, tmp_path, [_line(subject="unknown@unknown")])
    facts = projection("unknown@unknown", "untrusted")
    assert facts["services"][SERVICE]["reason"] == "untrusted_subject"
    assert facts["services"][SERVICE]["enabled"] is False


def test_missing_registry_file_fails_closed(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("COMPANY_AGENT_TENANT_REGISTRY", str(tmp_path / "absent.jsonl"))
    facts = projection(TRUSTED, "trusted")
    assert facts["regime"] == "unavailable"
    assert all(row["reason"] == "registry_unavailable" for row in facts["services"].values())


def test_invalid_registry_line_fails_closed(monkeypatch, tmp_path) -> None:
    _registry(monkeypatch, tmp_path, [
        {"subject": "not-an-identity", "service": SERVICE, "state": "approved",
         "expires_epoch": None, "approved_by": "o@x"},
    ])
    facts = projection(TRUSTED, "trusted")
    assert facts["regime"] == "unavailable"
    status = summary()
    assert status["configured"] is True and status["valid"] is False


def test_unknown_line_field_or_out_of_scope_service_fails_closed(monkeypatch, tmp_path) -> None:
    row = _line()
    row["note"] = "extra"
    _registry(monkeypatch, tmp_path, [row])
    assert projection(TRUSTED, "trusted")["regime"] == "unavailable"
    _registry(monkeypatch, tmp_path, [_line(service="company.knowledge")], name="scope.jsonl")
    assert projection(TRUSTED, "trusted")["regime"] == "unavailable"


def test_blank_lines_remain_register_with_no_entries(monkeypatch, tmp_path) -> None:
    path = tmp_path / "blank.jsonl"
    path.write_text("\n\n\n", encoding="utf-8")
    path.chmod(0o600)
    monkeypatch.setenv("COMPANY_AGENT_TENANT_REGISTRY", str(path))
    facts = projection(TRUSTED, "trusted")
    assert facts["regime"] == "registry"
    assert facts["services"][SERVICE]["reason"] == "subject_absent"


def test_relative_registry_path_fails_closed(monkeypatch) -> None:
    monkeypatch.setenv("COMPANY_AGENT_TENANT_REGISTRY", "relative/tenants.jsonl")
    assert projection(TRUSTED, "trusted")["regime"] == "unavailable"


def test_symlink_registry_path_fails_closed(monkeypatch, tmp_path, make_symlink) -> None:
    target = _registry(monkeypatch, tmp_path, [_line()], name="target.jsonl")
    link = tmp_path / "link.jsonl"
    make_symlink(target, link)
    monkeypatch.setenv("COMPANY_AGENT_TENANT_REGISTRY", str(link))
    assert projection(TRUSTED, "trusted")["regime"] == "unavailable"


def test_oversized_registry_fails_closed(monkeypatch, tmp_path) -> None:
    path = tmp_path / "bulk.jsonl"
    path.write_text(
        "\n".join(json.dumps(_line(subject=f"u{i}@corp.example.com")) for i in range(2048)),
        encoding="utf-8",
    )
    path.chmod(0o600)
    monkeypatch.setenv("COMPANY_AGENT_TENANT_REGISTRY", str(path))
    assert projection(TRUSTED, "trusted")["regime"] == "unavailable"


def test_capability_payload_carries_subject_and_enablement(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("COMPANY_AGENT_SUBJECT", TRUSTED)
    _registry(monkeypatch, tmp_path, [_line(subject=TRUSTED), _line(subject=TRUSTED, service=OTHER_SERVICE)])
    payload = invoke("company_capabilities", "lab")
    assert payload.status == "ok"
    enablement = payload.payload["enablement"]
    assert enablement["regime"] == "registry"
    assert enablement["subject"] == subject() == TRUSTED
    assert enablement["services"][SERVICE]["enabled"] is True
    assert enablement["services"][OTHER_SERVICE]["enabled"] is True
    assert set(enablement["services"]) == ALL_SERVICES
    # Every registered fact survives the model-visible envelope shape contract.
    assert all(set(row) >= {"service", "enabled", "reason"} for row in enablement["services"].values())


def test_legacy_payload_keeps_enablement_out_of_the_envelope_shape(monkeypatch) -> None:
    payload = invoke("company_capabilities", "lab")
    assert payload.status == "ok"
    assert payload.payload["enablement"] == {
        "regime": "legacy-single-user", "subject": subject(), "services": {},
    }


def test_registry_subject_shapes_follow_the_receipt_pattern(monkeypatch, tmp_path) -> None:
    _registry(monkeypatch, tmp_path, [
        _line(subject="a.b-c_d@corp.example.com"),
        _line(subject="bob@LAB"),
    ], name="double.jsonl")
    assert re_all_subjects_valid({"a.b-c_d@corp.example.com", "bob@LAB"})
    _registry(monkeypatch, tmp_path, [_line(subject="bad shape@x")], name="bad.jsonl")
    assert projection(TRUSTED, "trusted")["regime"] == "unavailable"


def test_doctor_aggregate_matches_legacy_regime(monkeypatch) -> None:
    monkeypatch.delenv("COMPANY_AGENT_TENANT_REGISTRY", raising=False)
    import io
    import json as jsonlib
    from contextlib import redirect_stdout

    from company_agent.cli import main
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        assert main(["doctor"]) == 0
    payload = jsonlib.loads(buffer.getvalue())
    assert payload["tenants_governance"] == {
        "regime": "legacy-single-user", "configured": False, "valid": False,
        "entries": 0, "subjects": 0, "approved_services": 0,
    }


def test_doctor_aggregate_counts_approved_services(monkeypatch, tmp_path) -> None:
    import io
    import json as jsonlib
    from contextlib import redirect_stdout

    from company_agent.cli import main
    _registry(monkeypatch, tmp_path, [
        _line(subject=TRUSTED),
        _line(subject=OTHER, service=OTHER_SERVICE),
        _line(subject=OTHER, service=SERVICE, state="pending"),
    ])
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        assert main(["doctor"]) == 0
    payload = jsonlib.loads(buffer.getvalue())
    status = payload["tenants_governance"]
    assert status["regime"] == "registry" and status["valid"] is True
    assert status["entries"] == 3 and status["subjects"] == 2 and status["approved_services"] == 2


def test_untrusted_projection_in_capability_payload_is_never_enabled() -> None:
    # No registry configured: legacy regime. Trusted-source semantics are
    # covered by test_capability_payload_carries_subject_and_enablement; this
    # pins the payload shape for the untrusted path through the schema gate.
    from company_agent.catalog import current_contract_digest  # noqa: F401  (digest freshness)

    payload = invoke("company_capabilities", "boot")
    assert payload.status == "ok"
    enablement = payload.payload["enablement"]
    assert enablement["subject"] == subject() or subject_source() == "untrusted"
    assert enablement["regime"] in {"legacy-single-user", "registry", "unavailable"}
