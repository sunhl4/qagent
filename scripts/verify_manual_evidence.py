#!/usr/bin/env python3
"""Validate deidentified, human-supervised acceptance evidence without asserting physical truth."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import math
import os
import re
import stat
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

FORMAT = "company-agent-manual-evidence/1"
ATTESTATION_FORMAT = "company-agent-evidence-attestation/1"
TRUST_FORMAT = "company-agent-evidence-trust/1"
SHA256 = re.compile(r"sha256:[0-9a-f]{64}\Z")
ID = re.compile(r"[A-Za-z][A-Za-z0-9_.:-]{0,127}\Z")
REQUEST_ID = re.compile(r"req_[0-9a-f]{32}\Z")
UTC_TIME = re.compile(r"20[0-9]{2}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z\Z")
OUTCOMES = {"rejected", "allowed", "unknown"}
MAX_JSON_BYTES = 1024 * 1024
MAX_JSON_DEPTH = 24
MAX_JSON_NODES = 20_000


class EvidenceError(RuntimeError):
    """Evidence is malformed, ambiguous, duplicated, or incorrectly linked."""


def _pairs_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise EvidenceError(f"duplicate JSON field: {key}")
        value[key] = item
    return value


def _validate_json(value: Any) -> None:
    """Reject unbounded structures and non-JSON or unsafe scalar values."""
    pending = [(value, 0)]
    nodes = 0
    while pending:
        item, depth = pending.pop()
        nodes += 1
        if nodes > MAX_JSON_NODES or depth > MAX_JSON_DEPTH:
            raise EvidenceError("JSON structure exceeds budget")
        if isinstance(item, dict):
            if any(not isinstance(key, str) for key in item):
                raise EvidenceError("JSON keys must be strings")
            pending.extend((entry, depth + 1) for pair in item.items() for entry in pair)
        elif isinstance(item, list):
            pending.extend((entry, depth + 1) for entry in item)
        elif isinstance(item, str):
            item.encode("utf-8", errors="strict")
        elif item is None or isinstance(item, bool):
            continue
        elif isinstance(item, (int, float)):
            if not math.isfinite(item) or abs(item) > 9_007_199_254_740_991:
                raise EvidenceError("invalid JSON number")
        else:
            raise EvidenceError("invalid JSON type")


def _reject_constant(_value: str) -> None:
    raise EvidenceError("nonfinite JSON number")


def load_json(path: Path) -> Any:
    """Read a bounded regular file without following a leaf symlink or waiting on a pipe."""
    try:
        path = Path(path)
        # O_NOFOLLOW and O_NONBLOCK do not exist on Windows; there the leaf-link
        # fence is the pre-open symlink check plus the regular-file fstat below.
        if not hasattr(os, "O_NOFOLLOW") and path.is_symlink():
            raise EvidenceError("invalid JSON file or structure budget")
        flags = os.O_RDONLY
        flags |= getattr(os, "O_BINARY", 0)
        flags |= getattr(os, "O_NONBLOCK", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "rb") as handle:
            info = os.fstat(handle.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_JSON_BYTES:
                raise EvidenceError("JSON file exceeds budget or is nonregular")
            raw = handle.read(MAX_JSON_BYTES + 1)
        if len(raw) > MAX_JSON_BYTES:
            raise EvidenceError("JSON file exceeds budget")
        value = json.loads(
            raw.decode("utf-8"), object_pairs_hook=_pairs_no_duplicates, parse_constant=_reject_constant
        )
        _validate_json(value)
        return value
    except (OSError, UnicodeError, ValueError, RecursionError, OverflowError, EvidenceError) as exc:
        raise EvidenceError("invalid JSON file or structure budget") from exc


def canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
        ).encode("ascii")
    except (TypeError, ValueError, RecursionError, OverflowError) as exc:
        raise EvidenceError("value is not canonical JSON") from exc


def sha256_json(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


def evidence_digest(bundle: dict[str, Any]) -> str:
    return sha256_json(bundle)


def _exact(value: Any, keys: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise EvidenceError(f"invalid {label} fields")
    return value


def _valid_id(value: Any, label: str) -> str:
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise EvidenceError(f"invalid {label}")
    return value


def _valid_digest(value: Any, label: str) -> str:
    if not isinstance(value, str) or not SHA256.fullmatch(value):
        raise EvidenceError(f"invalid {label}")
    return value


def _valid_time(value: Any, label: str) -> str:
    if not isinstance(value, str) or not UTC_TIME.fullmatch(value):
        raise EvidenceError(f"invalid {label}")
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise EvidenceError(f"invalid {label}") from exc
    return value


def _protected_file(path: Path, label: str, *, private: bool = False) -> Path:
    if not path.is_absolute() or path.is_symlink():
        raise EvidenceError(f"{label} path must be absolute and not a symlink")
    try:
        real = path.resolve(strict=True)
        info = real.lstat()
    except OSError as exc:
        raise EvidenceError(f"{label} is unavailable") from exc
    forbidden = 0o077 if private else 0o022
    if not stat.S_ISREG(info.st_mode) or info.st_mode & forbidden:
        raise EvidenceError(f"{label} must be a protected regular file")
    return real


def _parameters_digest(parameters: dict[str, Any]) -> str:
    _exact(parameters, {"circuit_id", "shots", "provider"}, "device parameters")
    circuit = parameters["circuit_id"]
    shots = parameters["shots"]
    if (
        not isinstance(circuit, str)
        or not re.fullmatch(r"circ_[A-Za-z0-9_-]{1,251}", circuit)
        or isinstance(shots, bool)
        or not isinstance(shots, int)
        or not 1 <= shots <= 1_000_000
        or parameters["provider"] != "ionstack-twinrun"
    ):
        raise EvidenceError("invalid device parameters")
    return sha256_json(parameters)


def _validate_case(case: Any, bundle_run_id: str, *, real: bool) -> dict[str, Any]:
    case = _exact(
        case,
        {
            "case_id",
            "run_id",
            "kind",
            "call_id",
            "approval_id",
            "approval_decision",
            "provider",
            "parameters",
            "approval_parameters_digest",
            "call_parameters_digest",
            "provider_parameters_digest",
            "request_id",
            "provider_request_id",
            "counter_before",
            "counter_after",
            "outcome",
            "automatic_retry_count",
            "reconciliation",
        },
        "evidence case",
    )
    for key in ("case_id", "call_id", "approval_id"):
        _valid_id(case[key], key)
    if case["run_id"] != bundle_run_id:
        raise EvidenceError("case run_id linkage mismatch")
    if not isinstance(case["kind"], str) or case["kind"] not in {"reject", "allow_once", "unknown"}:
        raise EvidenceError("invalid case kind")
    if (not isinstance(case["approval_decision"], str)
            or case["approval_decision"] not in {"rejected", "allowed-once"}):
        raise EvidenceError("invalid approval decision")
    if case["provider"] != "ionstack-twinrun":
        raise EvidenceError("invalid evidence provider")
    if not isinstance(case["parameters"], dict):
        raise EvidenceError("invalid parameters object")
    expected_digest = _parameters_digest(case["parameters"])
    digest_fields = ("approval_parameters_digest", "call_parameters_digest", "provider_parameters_digest")
    if any(case[field] != expected_digest for field in digest_fields):
        raise EvidenceError("approval, call, and provider parameters digest mismatch")
    request_id = case["request_id"]
    provider_request_id = case["provider_request_id"]
    for value in (request_id, provider_request_id):
        if value is not None and (not isinstance(value, str) or not REQUEST_ID.fullmatch(value)):
            raise EvidenceError("invalid request_id")
    if provider_request_id != request_id:
        raise EvidenceError("provider request_id linkage mismatch")
    before = case["counter_before"]
    after = case["counter_after"]
    if (
        isinstance(before, bool)
        or not isinstance(before, int)
        or before < 0
        or isinstance(after, bool)
        or not isinstance(after, int)
        or after < before
    ):
        raise EvidenceError("invalid server counters")
    if not isinstance(case["outcome"], str) or case["outcome"] not in OUTCOMES:
        raise EvidenceError("invalid evidence outcome")
    retries = case["automatic_retry_count"]
    if type(retries) is not int or retries != 0:
        raise EvidenceError("automatic retry count must be zero")
    reconciliation = case["reconciliation"]
    if case["kind"] == "reject":
        if (
            case["approval_decision"] != "rejected"
            or request_id is not None
            or after - before != 0
            or case["outcome"] != "rejected"
            or reconciliation is not None
        ):
            raise EvidenceError("reject case must prove zero provider calls")
    elif case["kind"] == "allow_once":
        if (
            case["approval_decision"] != "allowed-once"
            or request_id is None
            or after - before != 1
            or case["outcome"] != "allowed"
            or reconciliation is not None
        ):
            raise EvidenceError("allow-once case must prove exactly one provider call")
    else:
        if (
            case["approval_decision"] != "allowed-once"
            or request_id is None
            or after - before != 1
            or case["outcome"] != "unknown"
        ):
            raise EvidenceError("unknown case must bind one dispatched request")
        reconciliation = _exact(
            reconciliation,
            {"request_id", "checked_at", "status", "operator_record_id", "automatic_retry"},
            "reconciliation",
        )
        if (
            reconciliation["request_id"] != request_id
            or not isinstance(reconciliation["automatic_retry"], bool)
            or reconciliation["automatic_retry"]
            or not isinstance(reconciliation["status"], str)
            or reconciliation["status"] not in {"queued", "running", "completed", "failed", "not_found"}
        ):
            raise EvidenceError("unknown outcome reconciliation mismatch")
        _valid_time(reconciliation["checked_at"], "reconciliation checked_at")
        _valid_id(reconciliation["operator_record_id"], "operator record id")
    if real and case["parameters"]["circuit_id"].endswith("fixture"):
        raise EvidenceError("real evidence must not use a synthetic fixture circuit")
    return case


def validate_bundle(
    bundle: Any,
    *,
    expected_contract_digest: str | None = None,
    expected_lock_digest: str | None = None,
    expected_manifest_digest: str | None = None,
) -> dict[str, Any]:
    try:
        _validate_json(bundle)
    except (UnicodeError, OverflowError) as exc:
        raise EvidenceError("invalid JSON scalar") from exc
    bundle = _exact(
        bundle,
        {
            "format",
            "evidence_class",
            "run_id",
            "started_at",
            "ended_at",
            "contract_digest",
            "lock_digest",
            "release_manifest_digest",
            "environment_id",
            "deidentified",
            "contains_secrets",
            "collection_method",
            "cases",
        },
        "evidence bundle",
    )
    if bundle["format"] != FORMAT:
        raise EvidenceError("unsupported evidence format")
    if (not isinstance(bundle["evidence_class"], str)
            or bundle["evidence_class"] not in {"real", "synthetic"}):
        raise EvidenceError("invalid evidence class")
    real = bundle["evidence_class"] == "real"
    run_id = _valid_id(bundle["run_id"], "run_id")
    start = _valid_time(bundle["started_at"], "started_at")
    end = _valid_time(bundle["ended_at"], "ended_at")
    if end < start:
        raise EvidenceError("evidence time range is reversed")
    contract = _valid_digest(bundle["contract_digest"], "contract digest")
    lock = _valid_digest(bundle["lock_digest"], "lock digest")
    manifest = _valid_digest(bundle["release_manifest_digest"], "release manifest digest")
    _valid_id(bundle["environment_id"], "environment_id")
    if bundle["deidentified"] is not True or bundle["contains_secrets"] is not False:
        raise EvidenceError("evidence must be deidentified and secret-free")
    if bundle["collection_method"] != "human_supervised_external_observation":
        raise EvidenceError("evidence collection method is not independently supervised")
    for actual, expected, label in (
        (contract, expected_contract_digest, "contract"),
        (lock, expected_lock_digest, "lock"),
        (manifest, expected_manifest_digest, "release manifest"),
    ):
        if expected is not None and actual != expected:
            raise EvidenceError(f"{label} digest linkage mismatch")
    if not isinstance(bundle["cases"], list) or len(bundle["cases"]) < 3 or len(bundle["cases"]) > 32:
        raise EvidenceError("evidence must contain a bounded case list")
    cases = [_validate_case(case, run_id, real=real) for case in bundle["cases"]]
    for field in ("case_id", "call_id", "approval_id"):
        values = [case[field] for case in cases]
        if len(values) != len(set(values)):
            raise EvidenceError(f"duplicate {field}")
    requests = [case["request_id"] for case in cases if case["request_id"] is not None]
    if len(requests) != len(set(requests)):
        raise EvidenceError("duplicate request_id")
    kinds = {case["kind"] for case in cases}
    if not {"reject", "allow_once", "unknown"} <= kinds:
        raise EvidenceError("reject, allow-once, and unknown cases are all required")
    allow_cases = [case for case in cases if case["kind"] == "allow_once"]
    if len(allow_cases) < 2:
        raise EvidenceError("repeated calls require two separately approved allow-once cases")
    parameter_digests = {case["call_parameters_digest"] for case in allow_cases}
    if len(parameter_digests) != 1:
        raise EvidenceError("repeated-call parameter snapshots do not match")
    return bundle


def _secret(trust: dict[str, Any]) -> bytes:
    encoded = trust["hmac_sha256_key_hex"]
    if not isinstance(encoded, str) or not re.fullmatch(r"[0-9a-f]{64,256}", encoded) or len(encoded) % 2:
        raise EvidenceError("invalid evidence trust key")
    return bytes.fromhex(encoded)


def verify_attestation(bundle: dict[str, Any], attestation_path: Path, trust_path: Path) -> dict[str, Any]:
    attestation_path = _protected_file(attestation_path, "evidence attestation", private=True)
    trust_path = _protected_file(trust_path, "evidence trust config", private=True)
    trust = _exact(load_json(trust_path), {"format", "key_id", "hmac_sha256_key_hex"}, "trust config")
    if trust["format"] != TRUST_FORMAT:
        raise EvidenceError("unsupported evidence trust format")
    key_id = _valid_id(trust["key_id"], "trust key_id")
    attestation = _exact(
        load_json(attestation_path),
        {
            "format",
            "key_id",
            "evidence_sha256",
            "run_id",
            "contract_digest",
            "lock_digest",
            "release_manifest_digest",
            "attested_at",
            "signature",
        },
        "evidence attestation",
    )
    if (
        attestation["format"] != ATTESTATION_FORMAT
        or attestation["key_id"] != key_id
        or attestation["evidence_sha256"] != evidence_digest(bundle)
        or attestation["run_id"] != bundle["run_id"]
        or attestation["contract_digest"] != bundle["contract_digest"]
        or attestation["lock_digest"] != bundle["lock_digest"]
        or attestation["release_manifest_digest"] != bundle["release_manifest_digest"]
    ):
        raise EvidenceError("evidence attestation linkage mismatch")
    _valid_time(attestation["attested_at"], "attested_at")
    if not isinstance(attestation["signature"], str) or not re.fullmatch(
        r"hmac-sha256:[0-9a-f]{64}", attestation["signature"]
    ):
        raise EvidenceError("invalid evidence attestation signature")
    signed = {key: value for key, value in attestation.items() if key != "signature"}
    expected = "hmac-sha256:" + hmac.new(_secret(trust), canonical_bytes(signed), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, attestation["signature"]):
        raise EvidenceError("evidence attestation signature mismatch")
    return attestation


def verify_paths(
    evidence_path: Path,
    *,
    attestation_path: Path | None = None,
    trust_path: Path | None = None,
    expected_contract_digest: str | None = None,
    expected_lock_digest: str | None = None,
    expected_manifest_digest: str | None = None,
) -> dict[str, Any]:
    evidence_path = _protected_file(evidence_path, "evidence bundle")
    bundle = validate_bundle(
        load_json(evidence_path),
        expected_contract_digest=expected_contract_digest,
        expected_lock_digest=expected_lock_digest,
        expected_manifest_digest=expected_manifest_digest,
    )
    if (attestation_path is None) != (trust_path is None):
        raise EvidenceError("attestation and trust config must be supplied together")
    attested = False
    if attestation_path is not None:
        verify_attestation(bundle, attestation_path, trust_path)
        attested = True
    return {
        "status": "structurally_verified",
        "evidence_class": bundle["evidence_class"],
        "evidence_sha256": evidence_digest(bundle),
        "operator_attested": attested,
        "physical_truth_certified": False,
        "external_acceptance": "awaiting_human_attestation"
        if not attested
        else "awaiting_independent_review",
        "warning": (
            "JSON structure and provenance linkage do not certify physical events or self-reported counters"
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--attestation", type=Path)
    parser.add_argument("--trust-config", type=Path)
    parser.add_argument("--contract-digest")
    parser.add_argument("--lock-digest")
    parser.add_argument("--manifest-digest")
    args = parser.parse_args(argv)
    for value, label in (
        (args.contract_digest, "contract"),
        (args.lock_digest, "lock"),
        (args.manifest_digest, "manifest"),
    ):
        if value is not None and not SHA256.fullmatch(value):
            parser.error(f"invalid {label} digest")
    try:
        report = verify_paths(
            args.evidence,
            attestation_path=args.attestation,
            trust_path=args.trust_config,
            expected_contract_digest=args.contract_digest,
            expected_lock_digest=args.lock_digest,
            expected_manifest_digest=args.manifest_digest,
        )
    except (EvidenceError, OSError, RuntimeError, ValueError, TypeError):
        print("manual evidence verification failed: invalid or unavailable evidence", file=sys.stderr)
        return 1
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
