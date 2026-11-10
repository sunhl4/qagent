"""Durable dispatch receipts: the reconcile-before-retry boundary for external jobs.

The receipt store is a local, append-only JSONL ledger kept outside the DSH
workspace. It records exactly the allowlisted metadata produced by the provider
diagnostics channel plus, for successful binding submissions only, one short
contract-declared platform reference (``business_ref``: ``cloud_task``, ``slurm_number``/
``job_name`` or ``twin_id``) so an operator can correlate a request with the
platform-side job — never tool arguments, never scientific results, never
credentials — and separates two record kinds:

- ``dispatch``: written before the request is sent. For the binding operations
  (``device.run``, ``hpc.submit``, ``cloud.submit``) this record is mandatory:
  if it cannot be persisted, the request must not be sent, because an unknown
  outcome would otherwise have no durable locator.
- ``outcome``: written once the invocation resolves (``ok``/``completed``, or
  ``error`` whose execution state stayed ``unknown``). Best effort; a
  persistence failure never overrides or reinterprets the actual result.

Retention is bounded by the contract: files roll at ``max_file_bytes`` and at
most ``max_files`` files are kept. The platform (cloud/HPC/QPU) stays the
authoritative fact source; receipts only provide request locators so the
operator can reconcile ``unknown`` outcomes against platform facts.
"""

from __future__ import annotations

import datetime
import getpass
import json
import os
import re
import socket
import time
from pathlib import Path
from typing import Any

from company_agent.catalog import load_result_policy
from company_agent.jsonutil import loads as strict_json_loads

_SUBJECT_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,62}@[A-Za-z0-9][A-Za-z0-9.-]{0,52}")
_REQUEST_ID_PATTERN = re.compile(r"req_[0-9a-f]{32}")
_DIGEST_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")
_OPERATION_PATTERN = re.compile(r"[a-z]+(?:\.[a-z-]+)+")
_TOOL_PATTERN = re.compile(r"(?:quantum|hpc)_[a-z_]{1,125}")
# Union of the contract-declared platform receipt shapes: cloud_task
# (``[A-Za-z0-9_.:-]``), slurm_number/job_name (``[A-Za-z0-9_.-]``) and twin_id
# (``twin_`` + ``[A-Za-z0-9_-]``). One conservative class, validated in the
# contract, never a free-form mirror of provider output.
_REF_PATTERN = re.compile(r"[A-Za-z0-9_.:-]{1,256}")


class ReceiptError(RuntimeError):
    """The receipt contract or store is unusable for a dispatch-bound record."""


def _policy() -> dict[str, Any]:
    receipts = load_result_policy()["receipts"]
    if not isinstance(receipts, dict):
        raise RuntimeError("invalid Company Agent receipt contract")
    return receipts


def requires_dispatch_record(operation: object) -> bool:
    """True when the operation must persist a dispatch record before sending."""

    if not isinstance(operation, str):
        return False
    binding = _policy()["binding_operations"]
    return isinstance(binding, list) and operation in binding


def business_ref_from_result(operation: object, result: object) -> str:
    """Extract the contract-declared business reference from a delivered result.

    Only the first candidate field named by the contract ``ref_rules`` for this
    operation is used, and only when it is a schema-valid string. Everything
    else — refused answers, lost responses, operations without ref rules —
    extracts the empty reference: receipts record references only for facts
    the platform actually delivered, never for guesses.
    """


    policy = _policy()
    rules = policy.get("ref_rules")
    limit = int(str(policy.get("ref_max_bytes", 256)))
    if not isinstance(rules, dict) or not isinstance(operation, str):
        return ""
    names = rules.get(operation)
    if not isinstance(names, list) or not isinstance(result, dict):
        return ""
    for name in names:
        value = result.get(name)
        if not isinstance(value, str):
            continue
        try:
            size = len(value.encode("utf-8"))
        except UnicodeError:
            continue
        if 0 < size <= limit and _REF_PATTERN.fullmatch(value):
            return value
    return ""


def _root() -> Path:
    raw = str(os.environ.get(str(_policy()["dir_env"])) or "").strip()
    root = Path(raw) if raw else Path.home() / ".local" / "state" / "company-agent" / "receipts"
    if not root.is_absolute() or root == Path(root.anchor):
        raise ReceiptError("receipt store path is invalid")
    for part in root.parts[1:]:
        if part in {"", ".", ".."}:
            raise ReceiptError("receipt store path is invalid")
    return root


def _resolve_subject() -> tuple[str, str]:
    """Return (subject, source) where source is trusted, derived or untrusted.

    The trusted value comes only from the contract-declared launcher
    environment variable, which the host sets after server-side
    authentication — never from model context, tool arguments or session
    state. An untrusted value silently reverting to a derived OS identity
    would misattribute work in a multi-user environment, so any rejected
    trusted value or unusable OS identity resolves to ``unknown@unknown``
    with source ``untrusted`` instead.
    """

    limit = int(str(_policy()["subject_max_bytes"]))
    trusted_env = str(_policy().get("trusted_subject_env") or "")
    if trusted_env:
        trusted = str(os.environ.get(trusted_env) or "").strip()
        if (
            trusted
            and len(trusted.encode("utf-8")) <= limit
            and _SUBJECT_PATTERN.fullmatch(trusted)
        ):
            return trusted, "trusted"
    try:
        raw = f"{getpass.getuser()}@{socket.gethostname()}"
    except (ImportError, KeyError, OSError, ValueError):
        raw = "unknown@unknown"
    if trusted_env and os.environ.get(trusted_env, "").strip():
        # A configured trusted value that failed validation must never be
        # replaced by the derived OS identity (which could be another user).
        return "unknown@unknown", "untrusted"
    raw = "".join(character for character in raw if ord(character) >= 32 and ord(character) != 127)
    if len(raw.encode("utf-8")) > limit or not _SUBJECT_PATTERN.fullmatch(raw):
        return "unknown@unknown", "untrusted"
    return raw, "derived"


def subject() -> str:
    """Attribution identity for receipts and capability layering; never a credential."""

    return _resolve_subject()[0]


def subject_source() -> str:
    """Where the attribution identity came from: trusted, derived or untrusted."""

    return _resolve_subject()[1]


def _safe_int(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        return 0
    return max(0, min(value, 2**53 - 1))


def _encode(
    event: dict[str, Any], *, record: str, status: str, execution_state: str | None = None,
    business_ref: str = "",
) -> str:
    policy = _policy()
    fields = set(str(item) for item in policy["fields"])
    unexpected = set(event) - fields - {"version", "event", "business_ref"}
    if unexpected:
        raise ValueError("receipt source event carries unexpected fields")
    elapsed = event.get("elapsed_ms")
    timestamp = event.get("timestamp")
    if not isinstance(elapsed, int) or isinstance(elapsed, bool):
        elapsed = 0
    if not isinstance(timestamp, int) or isinstance(timestamp, bool):
        import time

        timestamp = int(time.time())
    plain = {key: str(event.get(key) or "") for key in (
        "tool", "operation", "request_id", "contract_digest", "error_category", "execution_state")}
    encoded_state = (
        str(event.get("execution_state") or "") if execution_state is None else execution_state
    )
    reference = business_ref if isinstance(business_ref, str) else ""
    value: dict[str, Any] = {
        "version": str(policy["version"]),
        "record": record,
        "tool": plain["tool"],
        "operation": plain["operation"],
        "request_id": plain["request_id"],
        "contract_digest": plain["contract_digest"],
        "subject": subject(),
        "elapsed_ms": _safe_int(elapsed),
        "timestamp": _safe_int(timestamp),
        "status": status,
        "error_category": plain["error_category"],
        "execution_state": encoded_state,
        "business_ref": reference,
    }
    if value["record"] not in set(str(item) for item in policy["records"]):
        raise ValueError("receipt record kind is invalid")
    if value["status"] not in set(str(item) for item in policy["statuses"]):
        raise ValueError("receipt status is invalid")
    if value["execution_state"] not in set(str(item) for item in policy["execution_states"]):
        raise ValueError("receipt execution state is invalid")
    if not _TOOL_PATTERN.fullmatch(value["tool"]):
        raise ValueError("receipt tool name is invalid")
    if not _OPERATION_PATTERN.fullmatch(value["operation"]) or len(value["operation"]) > 128:
        raise ValueError("receipt operation name is invalid")
    if not _REQUEST_ID_PATTERN.fullmatch(value["request_id"]):
        raise ValueError("receipt request id is invalid")
    if not _DIGEST_PATTERN.fullmatch(value["contract_digest"]):
        raise ValueError("receipt contract digest is invalid")
    if value["record"] == "dispatch":
        if value["status"] != "dispatched" or value["execution_state"] != "dispatched":
            raise ValueError("dispatch record must carry the plain dispatched state")
        if value["error_category"] != "none":
            raise ValueError("dispatch record is written before any error exists")
    elif value["status"] == "ok" and value["execution_state"] != "completed":
        raise ValueError("successful outcome must be completed")
    elif value["status"] == "refused":
        # A refusal is the platform answering "no" decisively; the attempt was
        # sent and never left the confirmation boundary, so keep the record
        # tied to the dispatched state instead of inventing an outcome.
        if value["execution_state"] != "dispatched" or value["error_category"] not in {
            "remote", "authentication",
        }:
            raise ValueError("refused outcome must record a decisive provider answer")
    elif value["status"] == "error":
        if value["execution_state"] != "unknown":
            raise ValueError("failed outcome must stay unknown until reconciled")
    if reference:
        limit = int(str(policy.get("ref_max_bytes", 256)))
        rules = policy.get("ref_rules")
        allowed_ref_operations = (
            set(str(item) for item in rules) if isinstance(rules, dict) else set()
        )
        # A business reference certifies a fact the platform delivered: only a
        # successful outcome of a contract-declared binding operation may bind
        # one, so dispatches, refusals and unknown outcomes never qualify.
        if (
            not _REF_PATTERN.fullmatch(reference)
            or len(reference.encode("utf-8")) > limit
            or value["record"] != "outcome"
            or value["status"] != "ok"
            or value["operation"] not in allowed_ref_operations
        ):
            raise ValueError("receipt business reference is not bindable to this record")
    raw = json.dumps(value, separators=(",", ":"), ensure_ascii=True)
    if len(raw.encode("utf-8")) > int(str(policy["max_record_bytes"])):
        raise ValueError("receipt record is oversized")
    return raw


def _files(root: Path, *, reverse: bool = False) -> list[Path]:
    try:
        found = [
            item for item in root.iterdir()
            if item.is_file() and item.name.startswith("receipts-") and item.name.endswith(".jsonl")
        ]
    except FileNotFoundError:
        return []
    return sorted(found, key=lambda item: item.name, reverse=reverse)


def _next_file(root: Path) -> Path:
    today = datetime.datetime.now(datetime.UTC).strftime("%Y%m%d")
    head = f"receipts-{today}-"
    last = 0
    for item in _files(root):
        suffix = item.name[len(head):].removesuffix(".jsonl")
        if item.name.startswith(head) and suffix.isdigit():
            last = max(last, int(suffix))
    return root / f"{head}{last + 1:04d}.jsonl"


def _persist(line: str) -> None:
    policy = _policy()
    max_files = max(1, int(str(policy["max_files"])))
    max_file_bytes = int(str(policy["max_file_bytes"]))
    root = _root()
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    existing = _files(root)
    target = None
    if existing:
        newest = existing[-1]
        try:
            fits = newest.stat().st_size + len(line.encode("utf-8")) + 1 <= max_file_bytes
        except OSError:
            fits = False
        if fits:
            target = newest
    if target is None:
        # A new file takes one slot: evict the oldest files to stay within budget.
        while len(existing) + 1 > max_files:
            item = existing.pop(0)
            try:
                item.unlink()
            except OSError:
                return
        target = _next_file(root)
    payload = (line + "\n").encode("utf-8")
    handle = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        os.write(handle, payload)
    finally:
        os.close(handle)


def record_dispatch(event: dict[str, Any]) -> None:
    """Persist a dispatch record before the network request is actually sent.

    Only the metadata already produced by the provider diagnostics channel is
    written. Failure raises :class:`ReceiptError`; the caller must refuse to
    dispatch a binding submission (device/HPC/cloud) without a persisted locator.
    """

    try:
        _persist(_encode(event, record="dispatch", status="dispatched"))
    except (OSError, RuntimeError, ValueError, TypeError) as exc:
        raise ReceiptError("receipt persistence unavailable before dispatch") from exc


def record_outcome(
    event: dict[str, Any], *, refused: bool = False, business_ref: str = "",
) -> None:
    """Best-effort terminal record; never overrides the real result.

    ``refused`` means the provider authoritatively answered an error (HTTP 4xx
    or a protocol refusal): the platform said no, so the operation did not
    happen and re-querying is optional. ``error`` with an ``unknown`` execution
    state means the attempt was sent but never confirmed: the next step is
    platform reconciliation, never a silent resubmission. ``business_ref`` is
    the contract-declared platform receipt (``cloud_task``/``slurm_number``/
    ``job_name``/``twin_id``) extracted from a delivered result; successful
    outcomes bind it permanently, and every other state keeps it empty because
    no platform fact is known.
    """

    try:
        if event.get("status") == "ok":
            status: str = "ok"
            state = "completed"
        elif refused:
            status = "refused"
            state = "dispatched"
        else:
            # Sent but never confirmed: the platform truth stays explicitly open.
            status = "error"
            state = "unknown"
        _persist(_encode(
            event, record="outcome", status=status, execution_state=state,
            business_ref=business_ref,
        ))
    except (OSError, RuntimeError, ValueError, TypeError):
        return


def load_records(*, limit: int = 24) -> list[dict[str, Any]]:
    """Newest-first bounded read, scoped to the current subject."""

    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 400:
        raise ValueError("receipt read limit is invalid")
    subject_value = subject()
    if not isinstance(subject_value, str) or not _SUBJECT_PATTERN.fullmatch(subject_value):
        raise ValueError("receipt subject filter is invalid")
    policy = _policy()
    fields = set(str(item) for item in policy["fields"])
    max_record_bytes = int(str(policy["max_record_bytes"]))
    files = _files(_root(), reverse=True)[: max(1, int(str(policy["max_files"])))]
    records: list[dict[str, Any]] = []
    for item in files:
        if len(records) >= limit:
            break
        try:
            data = item.read_text(encoding="utf-8")
        except OSError:
            continue
        for raw in reversed(data.splitlines()):
            if len(records) >= limit:
                break
            raw = raw.strip()
            if not raw or len(raw.encode("utf-8")) > max_record_bytes:
                continue
            try:
                record = strict_json_loads(raw)
            except (json.JSONDecodeError, ValueError, TypeError, UnicodeError):
                continue
            if not isinstance(record, dict) or set(record) != fields:
                continue
            if record.get("subject") != subject_value:
                continue
            if not all(isinstance(record[key], str) for key in fields - {"elapsed_ms", "timestamp"}):
                continue
            if any(
                not isinstance(record[key], int) or isinstance(record[key], bool)
                for key in ("elapsed_ms", "timestamp")
            ):
                continue
            if not _TOOL_PATTERN.fullmatch(str(record["tool"])):
                continue
            if not _OPERATION_PATTERN.fullmatch(str(record["operation"])):
                continue
            record_ref = str(record["business_ref"])
            if record_ref and not _REF_PATTERN.fullmatch(record_ref):
                continue
            records.append(record)
    return records


def _load_subject_records(subject_value: str, *, limit: int = 400) -> list[dict[str, Any]]:
    if not isinstance(subject_value, str) or not _SUBJECT_PATTERN.fullmatch(subject_value):
        raise ValueError("receipt subject filter is invalid")
    policy = _policy()
    fields = set(str(item) for item in policy["fields"])
    max_record_bytes = int(str(policy["max_record_bytes"]))
    files = _files(_root(), reverse=True)[: max(1, int(str(policy["max_files"])))]
    records: list[dict[str, Any]] = []
    for item in files:
        if len(records) >= limit:
            break
        try:
            data = item.read_text(encoding="utf-8")
        except OSError:
            continue
        for raw in reversed(data.splitlines()):
            if len(records) >= limit:
                break
            raw = raw.strip()
            if not raw or len(raw.encode("utf-8")) > max_record_bytes:
                continue
            try:
                record = strict_json_loads(raw)
            except (json.JSONDecodeError, ValueError, TypeError, UnicodeError):
                continue
            if not isinstance(record, dict) or set(record) != fields or record.get("subject") != subject_value:
                continue
            if not all(isinstance(record[key], str) for key in fields - {"elapsed_ms", "timestamp"}):
                continue
            if any(not isinstance(record[key], int) or isinstance(record[key], bool) for key in ("elapsed_ms", "timestamp")):
                continue
            if not _TOOL_PATTERN.fullmatch(str(record["tool"])) or not _OPERATION_PATTERN.fullmatch(str(record["operation"])):
                continue
            record_ref = str(record["business_ref"])
            if record_ref and not _REF_PATTERN.fullmatch(record_ref):
                continue
            records.append(record)
    return records


def _current_digest() -> str:
    from company_agent.catalog import current_contract_digest

    digest = current_contract_digest()
    return str(digest) if digest else ""


def evidence(tool_names: object) -> dict[str, Any]:
    """Fresh execution evidence for one capability, derived from the receipt store.

    ``state`` is ``ok`` for a recent successful run under the current contract
    digest, ``stale`` when the best record is older than
    ``evidence_max_age_seconds`` or was produced under a different digest,
    ``failure`` for the latest recorded error, ``none`` when the store holds no
    record for the capability, and ``unavailable`` when the store itself cannot
    be read. Evidence never substitutes for the provider ``configured()`` state
    and never claims a service is offline just because receipts are missing.
    """

    if not isinstance(tool_names, (tuple, list, frozenset)) or len(tool_names) > 32:
        raise ValueError("evidence tool list is invalid")
    names = frozenset(str(item) for item in tool_names)
    try:
        records = load_records(limit=400)
        policy = _policy()
        digest = _current_digest()
    except (OSError, ReceiptError, RuntimeError, ValueError):
        return {
            "state": "unavailable", "tool": "", "request_id": "",
            "age_seconds": 0, "digest_match": "unavailable",
        }
    best: dict[str, Any] | None = None
    for record in records:
        if str(record["tool"]) in names and (
            best is None or int(record["timestamp"]) > int(best["timestamp"])
        ):
            best = record
    if best is None:
        return {
            "state": "none", "tool": "", "request_id": "",
            "age_seconds": 0, "digest_match": "current" if digest else "unavailable",
        }
    digest_match = "current" if str(best["contract_digest"]) == digest else "stale"
    age = max(0, int(time.time()) - int(best["timestamp"]))
    state = str(best["status"])
    if state == "ok":
        state = "stale" if (
            age > int(str(policy["evidence_max_age_seconds"])) or digest_match == "stale"
        ) else "ok"
    else:
        state = "failure"
    request = str(best["request_id"])
    if not _REQUEST_ID_PATTERN.fullmatch(request):
        request = ""
    return {
        "state": state,
        "tool": str(best["tool"])[:128],
        "request_id": request,
        "age_seconds": age,
        "digest_match": digest_match,
    }


def reconcile(*, limit: int = 24, subject_value: str | None = None) -> dict[str, Any]:
    """Bounded reconciliation summary over the current subject's receipt store.

    Unknown outcomes are reported as facts, not failures: the operation may
    already have run on the platform, so the next step is always to re-query
    platform status with the original business context and never to resubmit.
    """

    try:
        records = _load_subject_records(subject_value or subject(), limit=400)
        policy = _policy()
    except (OSError, ReceiptError, RuntimeError, ValueError):
        return {
            "version": "1.0", "available": False, "unknown": [], "recent": [],
            "note": "receipt store unreadable; platform facts stay authoritative",
        }
    binding = set(str(value) for value in policy["binding_operations"])
    outcomes: dict[str, dict[str, Any]] = {}
    dispatches: dict[str, dict[str, Any]] = {}
    for record in records:
        request = str(record["request_id"])
        if record["record"] == "dispatch":
            dispatches.setdefault(request, record)
        else:
            outcomes.setdefault(request, record)
    flagged: list[dict[str, Any]] = []
    for request in sorted(dispatches, reverse=True):
        dispatch = dispatches[request]
        if dispatch.get("operation") not in binding:
            continue
        outcome = outcomes.get(request)
        if outcome is None or (
            outcome.get("status") == "error" and outcome.get("execution_state") == "unknown"
        ):
            flagged.append(dispatch if outcome is None else outcome)
    flagged = flagged[: max(1, min(limit, 400))]
    return {
        "version": "1.0",
        "available": True,
        "unknown": flagged,
        "recent": records[: max(0, min(limit, 400))],
        "note": (
            "unknown outcomes require platform reconciliation: re-query with the "
            "original business context; never resubmit automatically"
        ),
    }


def unknown_submissions() -> list[dict[str, str]]:
    """Short unknown cloud, HPC, and device outcomes. Empty when the store cannot be read."""
    try:
        records = load_records(limit=200)
    except (OSError, ReceiptError, RuntimeError, ValueError, TypeError):
        return []
    found: list[dict[str, str]] = []
    for record in records:
        if record.get("record") != "outcome" or record.get("execution_state") != "unknown":
            continue
        if record.get("operation") not in {"cloud.submit", "hpc.submit", "device.run"}:
            continue
        found.append({"tool": str(record["tool"]), "business_ref": str(record.get("business_ref") or "")})
        if len(found) == 8:
            break
    return found


def identity_age_seconds() -> int | None:
    """Age of the newest successful device identity receipt, or None when absent."""
    try:
        records = load_records(limit=200)
    except (OSError, ReceiptError, RuntimeError, ValueError, TypeError):
        return None
    now = int(time.time())
    for record in records:
        if record.get("tool") != "quantum_device_identity" or record.get("status") != "ok":
            continue
        stamp = record.get("timestamp")
        if isinstance(stamp, int) and not isinstance(stamp, bool):
            return max(0, now - stamp)
    return None
