from __future__ import annotations

import copy
import hashlib
import hmac
import importlib.util
import json
import sys
from argparse import Namespace
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str):
    path = ROOT / f"scripts/{name}.py"
    spec = importlib.util.spec_from_file_location(f"test_{name}_module", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


EVIDENCE = load_script("verify_manual_evidence")
ACCEPTANCE = load_script("verify_acceptance")
D0 = "sha256:" + "0" * 64
D1 = "sha256:" + "1" * 64
D2 = "sha256:" + "2" * 64
PARAMETERS = {"circuit_id": "circ_synthetic", "shots": 1, "provider": "ionstack-twinrun"}
PARAMETERS_DIGEST = EVIDENCE.sha256_json(PARAMETERS)


def case(kind: str, index: int) -> dict:
    dispatched = kind != "reject"
    request_id = f"req_{index:032x}" if dispatched else None
    approval = "rejected" if kind == "reject" else "allowed-once"
    outcome = {"reject": "rejected", "allow_once": "allowed", "unknown": "unknown"}[kind]
    reconciliation = None
    if kind == "unknown":
        reconciliation = {
            "request_id": request_id,
            "checked_at": "2026-10-08T07:02:00Z",
            "status": "completed",
            "operator_record_id": f"reconcile-{index}",
            "automatic_retry": False,
        }
    return {
        "case_id": f"case-{index}",
        "run_id": "run-synthetic-1",
        "kind": kind,
        "call_id": f"call-{index}",
        "approval_id": f"approval-{index}",
        "approval_decision": approval,
        "provider": "ionstack-twinrun",
        "parameters": copy.deepcopy(PARAMETERS),
        "approval_parameters_digest": PARAMETERS_DIGEST,
        "call_parameters_digest": PARAMETERS_DIGEST,
        "provider_parameters_digest": PARAMETERS_DIGEST,
        "request_id": request_id,
        "provider_request_id": request_id,
        "counter_before": index,
        "counter_after": index + int(dispatched),
        "outcome": outcome,
        "automatic_retry_count": 0,
        "reconciliation": reconciliation,
    }


def bundle() -> dict:
    return {
        "format": EVIDENCE.FORMAT,
        "evidence_class": "synthetic",
        "run_id": "run-synthetic-1",
        "started_at": "2026-10-08T07:00:00Z",
        "ended_at": "2026-10-08T07:03:00Z",
        "contract_digest": D0,
        "lock_digest": D1,
        "release_manifest_digest": D2,
        "environment_id": "isolated-synthetic-env",
        "deidentified": True,
        "contains_secrets": False,
        "collection_method": "human_supervised_external_observation",
        "cases": [case("reject", 1), case("allow_once", 2), case("allow_once", 3), case("unknown", 4)],
    }


def write_json(path: Path, value: dict, mode: int = 0o600) -> Path:
    path.write_text(json.dumps(value), encoding="utf-8")
    path.chmod(mode)
    return path


@pytest.mark.posix_permissions  # evidence protection needs POSIX chmod bits
def test_structural_evidence_never_certifies_physical_truth(tmp_path: Path) -> None:
    evidence_path = write_json(tmp_path / "evidence.json", bundle())
    report = EVIDENCE.verify_paths(
        evidence_path,
        expected_contract_digest=D0,
        expected_lock_digest=D1,
        expected_manifest_digest=D2,
    )
    assert report["status"] == "structurally_verified"
    assert report["evidence_class"] == "synthetic"
    assert report["physical_truth_certified"] is False
    assert report["external_acceptance"] == "awaiting_human_attestation"


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda value: value["cases"][0].update(counter_after=2), "zero provider calls"),
        (lambda value: value["cases"][1].update(counter_after=4), "exactly one provider call"),
        (lambda value: value["cases"][1].update(call_parameters_digest=D0), "parameters digest mismatch"),
        (lambda value: value["cases"][1].update(provider_request_id="req_" + "f" * 32), "request_id linkage"),
        (lambda value: value["cases"][2].update(approval_id="approval-2"), "duplicate approval_id"),
        (lambda value: value["cases"][2].update(request_id="req_" + f"{2:032x}",
                                                 provider_request_id="req_" + f"{2:032x}"),
         "duplicate request_id"),
        (lambda value: value["cases"][3].update(reconciliation=None), "reconciliation"),
        (lambda value: value["cases"][3]["reconciliation"].update(automatic_retry=True), "reconciliation"),
    ],
)
def test_evidence_rejects_forged_or_inconsistent_linkage(mutation, message) -> None:
    value = bundle()
    mutation(value)
    with pytest.raises(EVIDENCE.EvidenceError, match=message):
        EVIDENCE.validate_bundle(value)


def test_missing_case_and_missing_field_fail_closed() -> None:
    value = bundle()
    value["cases"] = [row for row in value["cases"] if row["kind"] != "reject"]
    with pytest.raises(EVIDENCE.EvidenceError, match="required"):
        EVIDENCE.validate_bundle(value)
    value = bundle()
    del value["cases"][0]["approval_id"]
    with pytest.raises(EVIDENCE.EvidenceError, match="fields"):
        EVIDENCE.validate_bundle(value)


def test_duplicate_json_fields_are_rejected(tmp_path: Path) -> None:
    path = tmp_path / "duplicate.json"
    path.write_text('{"format":"one","format":"two"}', encoding="utf-8")
    path.chmod(0o600)
    with pytest.raises(EVIDENCE.EvidenceError, match="invalid JSON"):
        EVIDENCE.load_json(path)


def test_real_label_rejects_synthetic_fixture_identifiers() -> None:
    value = bundle()
    value["evidence_class"] = "real"
    for row in value["cases"]:
        row["parameters"]["circuit_id"] = "circ_fixture"
        digest = EVIDENCE.sha256_json(row["parameters"])
        row["approval_parameters_digest"] = digest
        row["call_parameters_digest"] = digest
        row["provider_parameters_digest"] = digest
    with pytest.raises(EVIDENCE.EvidenceError, match="synthetic fixture"):
        EVIDENCE.validate_bundle(value)


@pytest.mark.posix_permissions  # evidence protection needs POSIX chmod bits
def test_external_attestation_binds_run_contract_lock_and_release(tmp_path: Path) -> None:
    value = bundle()
    evidence_path = write_json(tmp_path / "evidence.json", value)
    key = bytes.fromhex("33" * 32)
    trust = {"format": EVIDENCE.TRUST_FORMAT, "key_id": "human-operator", "hmac_sha256_key_hex": key.hex()}
    trust_path = write_json(tmp_path / "trust.json", trust)
    signed = {
        "format": EVIDENCE.ATTESTATION_FORMAT,
        "key_id": "human-operator",
        "evidence_sha256": EVIDENCE.evidence_digest(value),
        "run_id": value["run_id"],
        "contract_digest": value["contract_digest"],
        "lock_digest": value["lock_digest"],
        "release_manifest_digest": value["release_manifest_digest"],
        "attested_at": "2026-10-08T07:04:00Z",
    }
    attestation = {
        **signed,
        "signature": "hmac-sha256:" + hmac.new(
            key, EVIDENCE.canonical_bytes(signed), hashlib.sha256
        ).hexdigest(),
    }
    attestation_path = write_json(tmp_path / "attestation.json", attestation)
    report = EVIDENCE.verify_paths(
        evidence_path, attestation_path=attestation_path, trust_path=trust_path
    )
    assert report["operator_attested"] is True
    assert report["physical_truth_certified"] is False
    assert report["external_acceptance"] == "awaiting_independent_review"
    attestation["run_id"] = "forged-run"
    write_json(attestation_path, attestation)
    with pytest.raises(EVIDENCE.EvidenceError, match="linkage"):
        EVIDENCE.verify_paths(
            evidence_path, attestation_path=attestation_path, trust_path=trust_path
        )


@pytest.mark.posix_permissions  # evidence protection needs POSIX chmod bits
def test_acceptance_import_stays_blocked_even_when_structurally_valid(tmp_path: Path) -> None:
    evidence_path = write_json(tmp_path / "evidence.json", bundle())
    args = Namespace(
        evidence=evidence_path,
        evidence_attestation=None,
        evidence_trust_config=None,
        contract_digest=D0,
        lock_digest=D1,
        release_manifest_digest=D2,
    )
    row = ACCEPTANCE.evidence_check(args)
    assert row["status"] == "blocked"
    assert row["structural_status"] == "structurally_verified"
    assert row["physical_truth_certified"] is False
    assert row["reason"] == "awaiting_human_attestation"


@pytest.mark.parametrize("date", ["2026-02-30T07:00:00Z", "2026-13-01T07:00:00Z",
                                  "2026-10-08T25:00:00Z", "2026-10-08", [], None])
def test_evidence_requires_real_utc_dates(date):
    value = bundle()
    value["started_at"] = date
    with pytest.raises(EVIDENCE.EvidenceError, match="started_at"):
        EVIDENCE.validate_bundle(value)


@pytest.mark.parametrize("field", ["counter_before", "counter_after", "automatic_retry_count"])
@pytest.mark.parametrize("invalid", [False, 0.0, "0", [], 9_007_199_254_740_992])
def test_evidence_counters_and_retry_are_safe_integers(field, invalid):
    value = bundle()
    value["cases"][0][field] = invalid
    with pytest.raises(EVIDENCE.EvidenceError):
        EVIDENCE.validate_bundle(value)


@pytest.mark.parametrize("field", ["kind", "approval_decision", "outcome"])
@pytest.mark.parametrize("invalid", [[], {}])
def test_case_enum_wrong_types_are_domain_errors(field, invalid):
    value = bundle()
    value["cases"][0][field] = invalid
    with pytest.raises(EVIDENCE.EvidenceError):
        EVIDENCE.validate_bundle(value)


def test_bundle_and_reconciliation_wrong_types_are_domain_errors():
    value = bundle()
    value["evidence_class"] = []
    with pytest.raises(EVIDENCE.EvidenceError):
        EVIDENCE.validate_bundle(value)
    value = bundle()
    value["cases"][-1]["reconciliation"]["status"] = {}
    with pytest.raises(EVIDENCE.EvidenceError):
        EVIDENCE.validate_bundle(value)
    value = bundle()
    value["cases"][-1]["reconciliation"]["checked_at"] = "2026-02-30T00:00:00Z"
    with pytest.raises(EVIDENCE.EvidenceError):
        EVIDENCE.validate_bundle(value)


def test_acceptance_missing_and_invalid_evidence_do_not_pass(tmp_path: Path) -> None:
    args = Namespace(
        evidence=None, evidence_attestation=None, evidence_trust_config=None,
        contract_digest=None, lock_digest=None, release_manifest_digest=None,
    )
    assert ACCEPTANCE.evidence_check(args)["reason"] == "evidence_missing"
    args.evidence = write_json(tmp_path / "bad.json", {"self_reported_counter": 1})
    row = ACCEPTANCE.evidence_check(args)
    assert row["status"] == "failed"
    assert row["physical_truth_certified"] is False
