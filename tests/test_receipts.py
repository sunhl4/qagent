"""Architecture gates for the oss-survey P0 items: durable receipts and layered capability verdicts.

Sources: docs/oss-survey/04-工程衔接建议.zh-CN.md 「P0」 and 03-本地架构对照与工程边界.zh-CN.md §2、§5、§6.
The counter-examples demanded there must fail closed here:

- a submission that cannot leave a durable receipt must never leave the
  machine (P0 2.3);
- ``unknown`` platform outcomes are facts of uncertainty, never silent
  failures to replay (P0 2.3, results.json device_execution);
- decisive provider refusals are never disguised as unknown results;
- capability verdicts keep the identity/credential/session/approval/probe
  layers apart so no layer may fake another (P0 2.1).
"""

from __future__ import annotations

import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from company_agent.catalog import current_contract_digest
from company_agent.invoke import invoke
from company_agent.receipts import (
    ReceiptError,
    evidence,
    load_records,
    reconcile,
    record_dispatch,
    record_outcome,
    requires_dispatch_record,
    subject,
)
from company_agent.receipts import (
    subject_source as receipts_subject_source,
)


@pytest.fixture(autouse=True)
def store(tmp_path, monkeypatch) -> str:
    store = tmp_path / "receipts"
    store.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("COMPANY_AGENT_RECEIPT_DIR", str(store))
    monkeypatch.setenv("COMPANY_AGENT_PROFILE", "company-agent")
    # Hermetic provider layering: developer shells may carry live provider
    # config; the capability verdicts in this file must not depend on it.
    for name in (
        "COMPANY_QUANTUM_PLATFORM_INVOKE_URL", "COMPANY_QUANTUM_PLATFORM_TOKEN",
        "COMPANY_AGENT_SIMULATOR_INVOKE_URL", "COMPANY_AGENT_SIMULATOR_TOKEN",
        "COMPANY_AGENT_COMPILER_INVOKE_URL", "COMPANY_AGENT_COMPILER_TOKEN",
        "COMPANY_AGENT_DEVICE_INVOKE_URL", "COMPANY_AGENT_DEVICE_TOKEN",
        "COMPANY_AGENT_CLOUD_INVOKE_URL", "COMPANY_AGENT_CLOUD_TOKEN",
        "COMPANY_AGENT_HPC_INVOKE_URL", "COMPANY_AGENT_HPC_TOKEN",
    ):
        monkeypatch.delenv(name, raising=False)
    return str(store)


def _event(
    *,
    tool: str = "quantum_device_run",
    operation: str = "device.run",
    status: str = "dispatched",
    execution_state: str = "dispatched",
    request_id: str = "req_" + "a" * 32,
    digest: str | None = None,
    timestamp: int | None = None,
    elapsed_ms: int = 12,
    error_category: str = "none",
) -> dict[str, object]:
    return {
        "version": "1.0", "event": "provider", "tool": tool, "operation": operation,
        "request_id": request_id, "contract_digest": digest or current_contract_digest(),
        "elapsed_ms": elapsed_ms, "status": status, "error_category": error_category,
        "execution_state": execution_state,
        "timestamp": time.time() if timestamp is None else timestamp,
    }


class DeviceHandler(BaseHTTPRequestHandler):
    provider = "ionstack-twinrun"
    result: dict = {
        "twin_id": "twin_fixture", "provenance": "qccd-twin", "shots_actual": 1,
        "summary": {"status": "completed", "duration_ms": 1},
    }
    requests: list[dict] = []
    response_status = 200
    response_json: dict | None = None

    def do_POST(self) -> None:  # noqa: N802
        request = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
        self.__class__.requests.append(request)
        if self.__class__.response_json is not None:
            response = dict(self.__class__.response_json)
            if response.get("request_id") == "echo":
                response["request_id"] = request["request_id"]
            status = 200
        elif self.__class__.response_status != 200:
            response = {"error": "internal server error"}
            status = self.__class__.response_status
        else:
            response = {
                "protocol": "company-agent-provider/1.0", "ok": True,
                "provider": self.provider, "request_id": request["request_id"],
                "result": self.result,
            }
            status = 200
        raw = json.dumps(response).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *_args) -> None:
        return

    def handle(self) -> None:
        try:
            super().handle()
        except (BrokenPipeError, ConnectionResetError):
            return


@pytest.fixture
def provider_url(monkeypatch) -> str:
    server = ThreadingHTTPServer(("127.0.0.1", 0), DeviceHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv(
        "COMPANY_AGENT_DEVICE_INVOKE_URL", f"http://127.0.0.1:{server.server_port}/invoke",
    )
    monkeypatch.setenv("COMPANY_AGENT_DEVICE_TOKEN", "local-fixture")
    DeviceHandler.requests = []
    DeviceHandler.response_json = None
    DeviceHandler.response_status = 200
    try:
        yield f"http://127.0.0.1:{server.server_port}/invoke"
    finally:
        server.shutdown()
        thread.join(timeout=2)


@pytest.fixture
def device_call(monkeypatch) -> object:
    monkeypatch.setenv("COMPANY_AGENT_APPROVAL_CONTEXT", "dsh")

    def run() -> object:
        return invoke(
            "quantum_device_run", "lab", {"circuit_id": "circ_fixture", "shots": 1}, approved=True,
        )

    return run


# ---------------------------------------------------------------- receipts --


def test_dispatch_needs_receipt_contract_binding() -> None:
    for operation in ("device.run", "hpc.submit", "cloud.submit"):
        assert requires_dispatch_record(operation) is True
    for operation in ("device.identity", "hpc.queue", "cloud.devices", "asset.list"):
        assert requires_dispatch_record(operation) is False
    assert requires_dispatch_record(None) is False


def test_dispatch_and_outcome_roundtrip_records_subject_and_plain_metadata(
    store, tmp_path, monkeypatch,
) -> None:
    record_dispatch(_event())
    record_outcome(_event(status="ok", execution_state="completed", elapsed_ms=45))
    records = load_records(limit=10)
    assert [row["record"] for row in records] == ["outcome", "dispatch"]
    assert [row["execution_state"] for row in records] == ["completed", "dispatched"]
    assert all(row["subject"] == subject() and row["subject"] for row in records)
    assert records[0]["elapsed_ms"] == 45
    (payload_file,) = [name for name in os.listdir(store) if name.endswith(".jsonl")]
    if os.name == "posix":
        assert os.stat(os.path.join(store, payload_file)).st_mode & 0o077 == 0
    # A store directory the runtime created itself is private (0700).
    fresh = tmp_path / "runtime-made-receipts"
    monkeypatch.setenv("COMPANY_AGENT_RECEIPT_DIR", str(fresh))
    record_dispatch(_event(request_id="req_" + "9" * 32))
    if os.name == "posix":
        assert os.stat(fresh).st_mode & 0o777 == 0o700
    monkeypatch.setenv("COMPANY_AGENT_RECEIPT_DIR", store)


def test_unexpected_source_fields_or_bad_names_never_reach_the_store(store) -> None:
    event = _event()
    event["bogus"] = "field"
    record_outcome(_event(status="ok", execution_state="completed"))
    record_outcome(event)
    record_outcome({"**event": "forged-tool-name", **_event(), "tool": "concise"})
    records = load_records(limit=10)
    assert len(records) == 1
    assert records[0]["record"] == "outcome"


def test_failed_dispatch_without_receipt_never_sends(
    store, provider_url, device_call, monkeypatch,
) -> None:
    from company_agent import receipts

    def refuse(_line: str) -> None:
        raise OSError("disk unavailable")

    monkeypatch.setattr(receipts, "_persist", refuse)
    result = device_call()
    assert result.status == "error"
    assert DeviceHandler.requests == []
    assert "receipt" in result.error


def test_provider_refusal_is_decisive_and_not_unknown(store, provider_url, device_call) -> None:
    DeviceHandler.response_json = {
        "protocol": "company-agent-provider/1.0", "ok": False,
        "provider": "ionstack-twinrun", "request_id": "echo",
        "error": "provider refused the submission",
    }
    result = device_call()
    assert result.status == "error"
    assert "failed" in result.error and "unknown" not in result.error
    records = load_records(limit=10)
    assert [row["record"] for row in records] == ["outcome", "dispatch"]
    assert records[0]["status"] == "refused" and records[1]["status"] == "dispatched"
    assert records[0]["error_category"] == "remote"
    assert records[0]["business_ref"] == "" and records[1]["business_ref"] == ""
    listed = reconcile(limit=40)
    assert listed["available"] is True
    assert listed["unknown"] == [], "a decisive refusal needs no reconciliation"
    assert [row["status"] for row in listed["recent"]] == ["refused", "dispatched"]


def test_response_loss_records_unknown_for_reconciliation(
    store, provider_url, device_call,
) -> None:
    DeviceHandler.response_status = 500
    result = device_call()
    assert result.status == "error"
    assert "outcome unknown" in result.error
    listed = reconcile(limit=40)
    assert len(listed["unknown"]) == 1
    row = listed["unknown"][0]
    assert row["record"] == "outcome" and row["execution_state"] == "unknown"
    assert row["operation"] == "device.run" and row["request_id"].startswith("req_")
    assert row["tool"] == "quantum_device_run" and row["status"] == "error"
    assert row["business_ref"] == "", "a lost response binds no platform fact"
    assert "re-query" in listed["note"] and "resubmit" in listed["note"]


def test_unconfirmed_dispatch_only_is_flagged_as_unknown(store) -> None:
    record_dispatch(_event(request_id="req_" + "c" * 32))
    listed = reconcile(limit=10)
    assert [row["request_id"] for row in listed["unknown"]] == ["req_" + "c" * 32]


def test_resolved_outcome_is_not_reconciliation_work(store) -> None:
    record_dispatch(_event())
    record_outcome(_event(status="ok", execution_state="completed"))
    listed = reconcile(limit=10)
    assert listed["unknown"] == []
    assert [row["record"] for row in listed["recent"]] == ["outcome", "dispatch"]


def test_business_ref_extraction_follows_the_contract_rules(store) -> None:
    from company_agent.receipts import business_ref_from_result as extract

    assert extract("cloud.submit", {"cloud_task": "task-7", "state": "submitted"}) == "task-7"
    # slurm_number is preferred; an empty first candidate falls to job_name.
    assert extract("hpc.submit", {"slurm_number": "", "job_name": "demo"}) == "demo"
    assert extract("device.run", {"twin_id": "twin_a1"}) == "twin_a1"
    # Read-only operations have no ref rule; malformed values never bind.
    assert extract("cloud.status", {"cloud_task": "task-7"}) == ""
    assert extract("device.identity", {"twin_id": "twin_a1"}) == ""
    assert extract("hpc.submit", {"slurm_number": "not allowed!"}) == ""
    assert extract("device.run", {"twin_id": None}) == ""
    assert extract("device.run", "twin_a1") == ""
    assert extract(None, {"twin_id": "twin_a1"}) == ""


def test_ok_outcome_binds_business_ref_but_dispatch_stays_empty(store) -> None:
    record_dispatch(_event())
    record_outcome(
        _event(status="ok", execution_state="completed", elapsed_ms=9),
        business_ref="twin_ok1",
    )
    records = load_records(limit=10)
    assert [row["record"] for row in records] == ["outcome", "dispatch"]
    assert [row["business_ref"] for row in records] == ["twin_ok1", ""]
    listed = reconcile(limit=10)
    assert [row["business_ref"] for row in listed["recent"]] == ["twin_ok1", ""]


def test_business_ref_never_binds_outside_a_binding_success(store) -> None:
    from company_agent import receipts

    reference = "twin_ok1"
    # Unknown outcome: no platform fact is known, so nothing may be bound.
    record_outcome(
        _event(status="error", execution_state="unknown", error_category="transport"),
        business_ref=reference,
    )
    # Decisive refusal: the platform said no, nothing reached it.
    record_outcome(
        _event(
            request_id="req_" + "b" * 32, status="error", error_category="authentication",
        ),
        refused=True, business_ref=reference,
    )
    # Successful outcome of an operation without a ref rule.
    record_outcome(
        _event(
            tool="hpc_queue", operation="hpc.queue",
            request_id="req_" + "c" * 32, status="ok", execution_state="completed",
        ),
        business_ref=reference,
    )
    # References with credential-ish or free-form characters never enter the store.
    record_outcome(
        _event(request_id="req_" + "d" * 32, status="ok", execution_state="completed"),
        business_ref="Bearer abc+/secret",
    )
    assert load_records(limit=10) == []
    # A forged event-carried reference stays untrusted: only the explicit
    # extraction argument binds one, and dispatch records never bind at all.
    receipts.record_dispatch({**_event(), "business_ref": reference})
    (dispatch,) = load_records(limit=10)
    assert dispatch["business_ref"] == ""


def test_provider_success_binds_the_delivered_platform_reference(
    store, provider_url, device_call,
) -> None:
    result = device_call()
    assert result.status == "ok"
    records = load_records(limit=10)
    outcome = next(row for row in records if row["record"] == "outcome")
    dispatch = next(row for row in records if row["record"] == "dispatch")
    assert outcome["business_ref"] == DeviceHandler.result["twin_id"]
    assert dispatch["business_ref"] == ""
    listed = reconcile(limit=10)
    assert listed["unknown"] == []
    assert [row["business_ref"] for row in listed["recent"]] == [
        DeviceHandler.result["twin_id"], "",
    ]


def test_load_records_skips_torn_or_malformed_lines(store) -> None:
    record_dispatch(_event())
    (name,) = [name for name in os.listdir(store) if name.endswith(".jsonl")]
    path = os.path.join(store, name)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write('{"version":"1.0","record":"dispa\n')
        handle.write("not json at all\n")
        handle.write('{"version":"1.0","record":"dispatch","tool":"forged_tool"}\n')
    record_outcome(_event(status="ok", execution_state="completed"))
    records = load_records(limit=10)
    assert [row["record"] for row in records] == ["outcome", "dispatch"]


def test_receipt_store_env_must_be_absolute(store, monkeypatch) -> None:
    monkeypatch.setenv("COMPANY_AGENT_RECEIPT_DIR", "relative/path")
    with pytest.raises(ReceiptError):
        record_dispatch(_event())
    monkeypatch.setenv("COMPANY_AGENT_RECEIPT_DIR", "/")
    with pytest.raises(ReceiptError):
        record_dispatch(_event())


def test_rolls_files_when_the_current_file_is_full(store) -> None:
    record_dispatch(_event())
    store_path = os.environ["COMPANY_AGENT_RECEIPT_DIR"]
    (target,) = [name for name in os.listdir(store_path) if name.endswith(".jsonl")]
    with open(os.path.join(store_path, target), "wb") as handle:
        handle.write(b"\x00" * 263_000)
    record_dispatch(_event(request_id="req_" + "d" * 32))
    names = sorted(name for name in os.listdir(store_path) if name.endswith(".jsonl"))
    assert len(names) == 2
    assert names[0] == target


def test_prunes_beyond_the_contract_file_budget(store) -> None:
    from company_agent.catalog import load_result_policy

    store_path = os.environ["COMPANY_AGENT_RECEIPT_DIR"]
    max_files = load_result_policy()["receipts"]["max_files"]
    for index in range(max_files + 2):
        stale = os.path.join(store_path, f"receipts-19991231-{index:04d}.jsonl")
        with open(stale, "w", encoding="utf-8") as handle:
            handle.write("")
    # The most recent file is full, so a new roll must evict the oldest files.
    with open(
        os.path.join(store_path, f"receipts-29991231-{max_files + 1:04d}.jsonl"), "wb",
    ) as handle:
        handle.write(b"\x00" * 263_000)
    record_dispatch(_event(request_id="req_" + "e" * 32))
    kept = [name for name in os.listdir(store_path) if name.endswith(".jsonl")]
    assert len(kept) <= max_files


def test_subject_falls_back_when_identifiers_look_wrong(store, monkeypatch) -> None:
    from company_agent import receipts

    monkeypatch.setattr(receipts.socket, "gethostname", lambda: "")
    resolved = receipts.subject()  # exercise the shared resolver once
    assert resolved == "unknown@unknown"
    assert receipts.subject_source() == "untrusted"


def test_capability_identity_reports_the_subject_source(store) -> None:
    result = invoke("company_capabilities", "lab")
    assert result.status == "ok"
    identity = result.payload["identity"]
    assert set(identity) == {"subject", "subject_source", "profile"}
    assert identity["subject"] == subject()
    assert identity["subject_source"] == receipts_subject_source()
    assert identity["subject_source"] in {"trusted", "derived", "untrusted"}


def test_trusted_subject_env_binds_capability_and_receipts(store, monkeypatch) -> None:
    from company_agent import receipts

    trusted = "operator@corp.example.com"
    monkeypatch.setenv(receipts._policy()["trusted_subject_env"], trusted)

    assert subject() == trusted and receipts.subject_source() == "trusted"
    result = invoke("company_capabilities", "lab")
    assert result.status == "ok"
    assert result.payload["identity"] == {
        "subject": trusted, "subject_source": "trusted", "profile": "company-agent",
    }

    # The same trusted identity must land in the durable receipts store.
    event = _event(request_id="req_" + "7" * 32)
    record_dispatch(event)
    records = [row["subject"] for row in load_records()]
    assert trusted in records


def test_invalid_trusted_subject_is_never_silently_replaced(store, monkeypatch) -> None:
    from company_agent import receipts

    # A host misconfiguration must fail closed to "unknown", not to the
    # derived OS identity, which may belong to a different user entirely.
    monkeypatch.setenv(receipts._policy()["trusted_subject_env"], "op;rm -rf /")
    assert subject() == "unknown@unknown"
    assert receipts.subject_source() == "untrusted"

    # ...and an oversized trusted value is rejected for the same reason.
    monkeypatch.setenv(receipts._policy()["trusted_subject_env"], "a" * 300 + "@corp.example.com")
    assert subject() == "unknown@unknown" and receipts.subject_source() == "untrusted"


# ------------------------------------------------------- capability layer --



def test_capability_layers_stay_apart(store) -> None:
    result = invoke("company_capabilities", "lab")
    assert result.status == "ok"
    payload = result.payload
    assert payload["identity"] == {
        "subject": subject(), "subject_source": receipts_subject_source(), "profile": "company-agent",
    }
    assert payload["approvals"] == [
        "company_latex_batch_edit", "company_latex_edit", "company_latex_issue_note",
        "company_latex_overleaf_push", "company_latex_push", "company_latex_revert",
        "company_plan_issue_create", "company_plan_issue_write",
        "company_plan_milestone_create", "company_plan_note_create",
        "hpc_dir_create", "hpc_file_remove",
        "hpc_job_cancel", "hpc_stage_file", "hpc_submit",
        "quantum_cloud_submit", "quantum_device_run",
    ]
    rows = {row["id"]: row for row in payload["capabilities"]}
    assert all(
        rows[name]["provider_state"] == "local" and rows[name]["evidence"]["state"] == "none"
        for name in ("company.knowledge", "company.workflow")
    )
    digest_state = "current" if current_contract_digest() else "unavailable"
    assert rows["company.algorithm"]["evidence"] == {
        "state": "none", "tool": "", "request_id": "",
        "age_seconds": 0, "digest_match": digest_state,
    }
    # Credential presence must never be reported as a verified connection.
    assert rows["company.algorithm"]["provider_state"] == "unconfigured"
    assert rows["company.algorithm"]["evidence"]["state"] == "none"


def test_boot_preset_cannot_upgrade_read_only_visibility(store) -> None:
    result = invoke("company_capabilities", "boot")
    assert result.status == "ok"
    assert result.payload["approvals"] == []
    rows = {row["id"]: row for row in result.payload["capabilities"]}
    # boot exposes no HPC submission tool at all; the policy denies even the
    # queue probe for boot, and there is nothing to approve execution grants for.
    assert rows["compute.hpc"]["visible_tools"] == []


def test_injected_credentials_stay_configured_unverified(store, provider_url) -> None:
    result = invoke("company_capabilities", "lab")
    rows = {row["id"]: row for row in result.payload["capabilities"]}
    assert rows["quantum.device"]["provider_state"] == "configured_unverified"
    assert rows["quantum.device"]["evidence"]["state"] == "none"


def test_success_receipt_builds_current_evidence(store, provider_url, device_call) -> None:
    result = device_call()
    assert result.status == "ok"
    (dispatch,) = [row for row in load_records(limit=10) if row["record"] == "dispatch"]
    capabilities = invoke("company_capabilities", "lab")
    rows = {row["id"]: row for row in capabilities.payload["capabilities"]}
    device = rows["quantum.device"]
    assert device["evidence"]["state"] == "ok"
    assert device["evidence"]["tool"] == "quantum_device_run"
    assert device["evidence"]["request_id"] == dispatch["request_id"]
    assert device["evidence"]["digest_match"] == "current"
    assert 0 <= device["evidence"]["age_seconds"] <= 5


def test_digest_or_age_expiry_grows_stale(store) -> None:
    # Age expiry: newest record made with the current digest 7200 seconds ago.
    record_outcome(_event(
        status="ok", execution_state="completed", timestamp=int(time.time()) - 7200,
    ))
    aged = evidence(("quantum_device_run",))
    assert aged["state"] == "stale" and aged["age_seconds"] >= 3600
    assert aged["digest_match"] == "current"
    # Digest expiry: a newer record made under a different contract digest.
    record_outcome(_event(status="ok", execution_state="completed", digest="sha256:" + "0" * 64))
    refreshed = evidence(("quantum_device_run",))
    assert refreshed["state"] == "stale" and refreshed["digest_match"] == "stale"


def test_failure_and_refusal_evidence_reports_observed_failure(store) -> None:
    from company_agent import receipts

    record_outcome(
        _event(status="error", execution_state="unknown", error_category="timeout"), refused=False,
    )
    assert evidence(("quantum_device_run",))["state"] == "failure"
    record_outcome(
        _event(request_id="req_" + "f" * 32, status="error", error_category="authentication"),
        refused=True,
    )
    refreshed = evidence(("quantum_device_run",))
    assert refreshed["state"] == "failure"
    del receipts


def test_evidence_unavailable_when_store_unreadable(store, monkeypatch) -> None:
    from company_agent import receipts

    def broken_root():
        raise ReceiptError("receipt store path is invalid")

    monkeypatch.setattr(receipts, "_root", broken_root)
    assert evidence(("quantum_device_run",)) == {
        "state": "unavailable", "tool": "", "request_id": "",
        "age_seconds": 0, "digest_match": "unavailable",
    }


def test_unavailable_store_never_breaks_capability_listing(store, monkeypatch) -> None:
    from company_agent import receipts

    def broken_root():
        raise ReceiptError("receipt store path is invalid")

    monkeypatch.setattr(receipts, "_root", broken_root)
    result = invoke("company_capabilities", "sign")
    assert result.status == "ok"
    rows = {row["id"]: row for row in result.payload["capabilities"]}
    assert rows["quantum.device"]["evidence"]["state"] == "unavailable"


def test_receipt_contract_gate_rejects_broken_definitions(store, monkeypatch) -> None:
    from company_agent import catalog, receipts

    original = catalog._load_object

    def broken(name: str) -> dict:
        payload = dict(original(name))
        if name == "results.json":
            payload["receipts"] = {**payload["receipts"], "max_files": 9999}
        return payload

    monkeypatch.setattr(catalog, "_load_object", broken)
    with pytest.raises((RuntimeError, ReceiptError), match="receipt"):
        receipts.record_dispatch(_event())
    # Reading side stays observational: a broken contract is never evidence of
    # a platform fact, so evidence degrades to "unavailable" rather than lying.
    assert receipts.evidence(("quantum_device_run",))["state"] == "unavailable"
