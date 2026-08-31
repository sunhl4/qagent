import os

from qagent.models.handles import HANDLE_TWIN
from qagent.services.eval_run import DEFAULT_CIRCUIT
from qagent.services.invoke import invoke


def test_get_job_is_truncated() -> None:
    previous = os.environ.pop("QAGENT_QDATA_URL", None)
    try:
        submitted = invoke("qdata_submit_job", "lab", {"kind": "surrogate", "payload": {}})
        job = invoke("qdata_get_job", "lab", {"job_id": submitted.payload["job_id"]})
    finally:
        if previous is None:
            os.environ.pop("QAGENT_QDATA_URL", None)
        else:
            os.environ["QAGENT_QDATA_URL"] = previous
    assert job.status == "ok"
    assert set(job.payload) <= {"status", "summary", "asset_id"}
    assert "bitstrings" not in job.payload


def test_aer_has_no_twin_id() -> None:
    imported = invoke("qiskit_import_circuit", "lab", {})
    aer = invoke("qiskit_aer_run", "lab", {"circuit_id": imported.payload["circuit_id"], "shots": 16})
    assert aer.status == "ok"
    assert aer.payload["provenance"] == "aer"
    assert HANDLE_TWIN not in aer.payload


def test_approved_twin_run_does_not_mint_local_twin_id() -> None:
    previous = os.environ.get("QAGENT_TWIN_URL")
    os.environ["QAGENT_TWIN_URL"] = "http://127.0.0.1:1"
    try:
        result = invoke(
            "ionstack_twin_run",
            "lab",
            {
                "mode": "signoff",
                "shots": 32,
                "circuit": DEFAULT_CIRCUIT,
            },
            approved=True,
        )
    finally:
        if previous is None:
            os.environ.pop("QAGENT_TWIN_URL", None)
        else:
            os.environ["QAGENT_TWIN_URL"] = previous
    assert result.status == "error"
    assert HANDLE_TWIN not in (result.payload or {})
