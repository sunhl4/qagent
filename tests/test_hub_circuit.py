"""Hub catalog + three-input upload + circuit job FSM."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import traceback
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from qagent.adapters.docs import WiredDocs
from qagent.adapters.hub import NativeHub
from qagent.adapters.pin import pin_from_qasm
from qagent.entrypoints.shell_http import dispatch
from qagent.models.handles import HANDLE_CIRCUIT, HANDLE_TWIN
from qagent.services.circuit_job import public_job, start_job
from qagent.services.ingest_store import load_ingest
from qagent.services.policy import decide
from qagent.services.translate import ORIGIN_COMPANY, ORIGIN_NATIVE, ORIGIN_TRANSLATED, translate_config
from qagent.services.uploads import KIND_CIRCUIT, KIND_CONFIG, KIND_UNKNOWN, classify_upload, parse_config_text

_QASM = """OPENQASM 3.0;
include "stdgates.inc";
qubit[2] q;
h q[0];
cx q[0], q[1];
"""

_CONFIG = {
    "api_version": "hub/v1",
    "algorithm_id": "org.chem.vqe",
    "algorithm": {"native_format": "qchem-stack.scenario", "scenario": "minimal_vqe"},
}


def test_classify_three_modalities() -> None:
    assert classify_upload("ghz.qasm", _QASM) == KIND_CIRCUIT
    assert classify_upload("job.yaml", "algorithm_id: org.chem.vqe") == KIND_CONFIG
    assert classify_upload("job.json", json.dumps(_CONFIG)) == KIND_CONFIG
    assert classify_upload("h2.json", json.dumps({"molecule": "H2", "basis": "sto-3g"})) == KIND_CONFIG
    assert classify_upload("run.py", "from qiskit import QuantumCircuit") == KIND_UNKNOWN


def test_parse_config_yaml_subset() -> None:
    text = "api_version: hub/v1\nalgorithm_id: org.chem.vqe\nalgorithm:\n  native_format: qchem-stack.scenario\n"
    data = parse_config_text(text)
    assert data["api_version"] == "hub/v1"
    assert data["algorithm_id"] == "org.chem.vqe"
    assert data["algorithm"]["native_format"] == "qchem-stack.scenario"


_COMPANY_IDS = {
    "org.algo.qaoa.maxcut",
    "org.algo.qrc.mnist",
    "org.algo.trotter.first_order",
    "org.algo.vqe.hea",
    "org.chem.adapt",
    "org.chem.embed.dmet",
    "org.chem.excited.qse",
    "org.chem.excited.sceom",
    "org.chem.excited.vqd",
    "org.chem.gqe",
    "org.chem.iqeb",
    "org.chem.qpe",
    "org.chem.sa_vqe",
    "org.chem.sqd",
    "org.chem.tetris_adapt",
    "org.chem.vqe",
    "org.compiler.h2",
    "org.demo.uqcdemo",
    "org.runtime.iontrap-noise",
    "org.runtime.qiskit-uqc-sim",
    "org.runtime.uqc-cloud",
    "org.software.qchem-stack",
    "org.software.uqc-algorithm",
    "org.workflow.qccd",
}

_HUB_ENV = ("QAGENT_ALGO_HUB_HOME", "QAGENT_ALGO_HUB_URL")


def test_bundled_catalog_ships_company_face() -> None:
    previous = {key: os.environ.pop(key, None) for key in _HUB_ENV}
    try:
        text = (ROOT / "contracts" / "hub" / "catalog_face.json").read_text(encoding="utf-8")
        assert "192.168" not in text
        assert "gitlab" not in text.lower()
        assert "gitee" not in text.lower()
        listed = NativeHub().list_assets({})
        assert listed["source"] == "bundled"
        ids = {row["id"] for row in listed["assets"]}
        assert ids == _COMPANY_IDS
        assert listed["count"] == 24
        algorithms = NativeHub().list_assets({"kind": "algorithm"})
        assert algorithms["count"] == 12
        described = NativeHub().describe({"id": "org.chem.sqd"})
        assert described["id"] == "org.chem.sqd"
        assert described["selectable"] is True
        assert HANDLE_TWIN not in json.dumps(listed)
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def test_catalog_docs_hit_without_local_hub() -> None:
    previous = os.environ.pop("QAGENT_KNOWLEDGE_PATH", None)
    os.environ.pop("QAGENT_ALGO_HUB_HOME", None)
    try:
        hits = WiredDocs().search({"query": "公司算法目录"})
        paths = {item["path"].replace("\\", "/") for item in hits.get("hits") or []}
        assert "manuals/algo_catalog.md" in paths
        assert hits.get("empty") is False
    finally:
        if previous is None:
            os.environ.pop("QAGENT_KNOWLEDGE_PATH", None)
        else:
            os.environ["QAGENT_KNOWLEDGE_PATH"] = previous


def test_hub_choose_does_not_merge_vqe() -> None:
    hub = NativeHub()
    assert hub.choose({"has_molecule": True})["algorithm_id"] == "org.chem.vqe"
    assert hub.choose({"has_molecule": False})["algorithm_id"] == "org.algo.vqe.hea"
    listed = hub.list_assets({"kind": "algorithm"})
    assert listed["count"] >= 4
    assert HANDLE_TWIN not in listed
    described = hub.describe({"id": "org.chem.vqe"})
    assert described["id"] == "org.chem.vqe"
    assert HANDLE_TWIN not in described


def test_hub_validate_envelope() -> None:
    hub = NativeHub()
    ok = hub.validate({"config": _CONFIG})
    assert ok["ok"] is True
    bad = hub.validate({"config": {"api_version": "hub/v1", "algorithm_id": "org.chem.vqe"}})
    assert bad["ok"] is False


def test_hub_tools_are_allowed_on_lab() -> None:
    assert decide("qagent_hub_list", "lab", {}) == "allow"
    assert decide("qagent_hub_choose", "lab", {"has_molecule": True}) == "allow"
    assert decide("qagent_hub_translate", "lab", {"config": {"molecule": "H2"}}) == "allow"
    assert decide("qagent_hub_translate", "boot", {"config": {"molecule": "H2"}}) == "deny"
    assert decide("qagent_circuit_job", "lab", {}) == "allow"
    assert decide("qagent_circuit_job", "boot", {}) == "deny"
    assert decide("qagent_circuit_job", "algo", {}) == "deny"


def test_upload_config_and_circuit() -> None:
    folder = Path(tempfile.mkdtemp())
    pins = folder / "pins.json"
    jobs = folder / "assignments.jsonl"
    ingest = folder / "ingest.json"
    with patch("qagent.adapters.pin._STORE", pins), patch(
        "qagent.adapters.assignment_store._DEFAULT", jobs
    ), patch.dict(
        "os.environ",
        {"QAGENT_ASSIGNMENTS_FILE": str(jobs), "QAGENT_INGEST_FILE": str(ingest)},
        clear=False,
    ):
        code, row = dispatch(
            "POST",
            "/api/uploads",
            {"filename": "h2.yaml", "text": json.dumps(_CONFIG)},
        )
        assert code == 200
        assert isinstance(row, dict)
        assert row.get("kind") == KIND_CONFIG
        assert row.get("ok") is True
        assert row.get("algorithm_id") == "org.chem.vqe"
        assert row.get("origin") == ORIGIN_NATIVE
        assert HANDLE_TWIN not in row

        code, circ = dispatch("POST", "/api/uploads", {"filename": "ghz.qasm", "text": _QASM})
        assert code == 200
        assert isinstance(circ, dict)
        assert circ.get("kind") == KIND_CIRCUIT
        assert str((circ.get("circuit") or {}).get(HANDLE_CIRCUIT) or "").startswith("circ_")
        assert "qasm3" not in (circ.get("circuit") or {})
        job = circ.get("job") or {}
        assert job.get("workflow") == "circuit"
        assert job.get("stage") in {"estimate", "ask", "validate"}
        assert HANDLE_TWIN not in job


def test_circuit_job_asks_and_aer_has_no_twin() -> None:
    folder = Path(tempfile.mkdtemp())
    pins = folder / "pins.json"
    jobs = folder / "assignments.jsonl"
    with patch("qagent.adapters.pin._STORE", pins), patch.dict(
        "os.environ", {"QAGENT_ASSIGNMENTS_FILE": str(jobs)}, clear=False
    ):
        pinned = pin_from_qasm(_QASM)
        circuit_id = pinned[HANDLE_CIRCUIT]
        twin_job = start_job(circuit_id=circuit_id, backend="twin")
        face = public_job(twin_job)
        assert twin_job.status == "needs_ask"
        assert face["status"] == "needs_ask"
        assert "makespan_ns" in face
        assert HANDLE_TWIN not in face

        aer_job = start_job(circuit_id=circuit_id, backend="aer")
        aer_face = public_job(aer_job)
        assert HANDLE_TWIN not in aer_face
        assert aer_face.get("aer_provenance") in {None, "aer"} or aer_job.status in {"draft", "failed"}


def test_translate_company_and_foreign() -> None:
    company = translate_config({"id": "h2", "action": "build", "molecule": "H2", "basis": "sto-3g"})
    assert company["ok"] is True
    assert company["origin"] == ORIGIN_COMPANY
    assert company["from_kind"] == "company"
    assert company["algorithm_id"] == "org.chem.vqe"
    assert company["config"]["api_version"] == "hub/v1"
    assert "qasm3" not in company["config"]

    foreign = translate_config({"molecule": "H2", "geometry": "H 0 0 0; H 0 0 0.74", "basis": "sto-3g"})
    assert foreign["origin"] == ORIGIN_TRANSLATED
    assert foreign["from_kind"] == "molecule"
    assert foreign["algorithm_id"] == "org.chem.vqe"

    pauli = translate_config({"hamiltonian": {"terms": [{"coeff": 1.0, "ops": "ZZ"}]}})
    assert pauli["algorithm_id"] == "org.algo.vqe.hea"
    assert pauli["from_kind"] == "pauli"
    assert "pauli_terms" not in (pauli.get("config") or {})

    cut = translate_config({"problem": "maxcut", "edges": [[0, 1], [1, 2]]})
    assert cut["algorithm_id"] == "org.algo.qaoa.maxcut"
    assert cut["from_kind"] == "maxcut"

    qiskit = translate_config({"framework": "qiskit", "qasm3": _QASM})
    assert qiskit["ok"] is True
    assert qiskit["origin"] == ORIGIN_TRANSLATED
    assert qiskit["from_kind"] == "qiskit"
    assert qiskit["qasm"].startswith("OPENQASM")
    assert qiskit["algorithm_id"] == ""

    unread = translate_config({"foo": 1})
    assert unread["ok"] is False
    assert unread["errors"]


def test_hub_translate_face_is_slim() -> None:
    hub = NativeHub()
    face = hub.translate({"config": {"molecule": "H2", "basis": "sto-3g"}})
    assert face["ok"] is True
    assert face["algorithm_id"] == "org.chem.vqe"
    assert face["origin"] == ORIGIN_TRANSLATED
    assert "qasm3" not in face
    assert "config" not in face
    assert HANDLE_TWIN not in face


def test_upload_translates_and_pins_foreign_qasm() -> None:
    folder = Path(tempfile.mkdtemp())
    pins = folder / "pins.json"
    jobs = folder / "assignments.jsonl"
    ingest = folder / "ingest.json"
    with patch("qagent.adapters.pin._STORE", pins), patch(
        "qagent.adapters.assignment_store._DEFAULT", jobs
    ), patch.dict(
        "os.environ",
        {"QAGENT_ASSIGNMENTS_FILE": str(jobs), "QAGENT_INGEST_FILE": str(ingest)},
        clear=False,
    ):
        code, row = dispatch(
            "POST",
            "/api/uploads",
            {
                "filename": "ibm.json",
                "text": json.dumps({"backend": "ibm_brisbane", "qasm3": _QASM}),
            },
        )
        assert code == 200
        assert isinstance(row, dict)
        assert row.get("kind") == KIND_CONFIG
        assert row.get("ok") is True
        assert row.get("origin") == ORIGIN_TRANSLATED
        assert row.get("from_kind") == "ibm"
        assert "qasm3" not in row
        assert "qasm3" not in (row.get("circuit") or {})
        assert str((row.get("circuit") or {}).get(HANDLE_CIRCUIT) or "").startswith("circ_")
        job = row.get("job") or {}
        assert job.get("workflow") == "circuit"
        assert HANDLE_TWIN not in job
        saved = load_ingest("")
        assert saved.get("circuit_id", "").startswith("circ_")
        assert saved.get("origin") == ORIGIN_TRANSLATED

        code, pack = dispatch(
            "POST",
            "/api/uploads",
            {"filename": "h2.json", "text": json.dumps({"id": "h2", "action": "build", "molecule": "H2"})},
        )
        assert code == 200
        assert isinstance(pack, dict)
        assert pack.get("origin") == ORIGIN_COMPANY
        assert pack.get("algorithm_id") == "org.chem.vqe"
        assert pack.get("circuit") is None

        code, bad = dispatch("POST", "/api/uploads", {"filename": "run.py", "text": "print(1)"})
        assert code == 400
        assert isinstance(bad, dict)
        assert "脚本" in str(bad.get("error") or "")


def test_chat_http_does_not_echo_algorithm_id() -> None:
    with patch(
        "qagent.entrypoints.shell_http.turn",
        return_value={
            "reply": "先估计。",
            "awaiting": None,
            "ready": True,
            "open_settings": False,
            "via": "dsh-session",
            "session_id": "sess_hidden",
            "algorithm_id": "org.chem.vqe",
            "used_tools": ["qagent_hub_choose"],
        },
    ):
        code, face = dispatch(
            "POST",
            "/api/chat",
            {"message": "先估计", "algorithm_id": "org.chem.vqe"},
        )
    assert code == 200
    assert isinstance(face, dict)
    assert "algorithm_id" not in face
    assert "session_id" not in face
    assert HANDLE_TWIN not in face


def main() -> int:
    failed = 0
    for name, fn in (
        ("classify_three_modalities", test_classify_three_modalities),
        ("parse_config_yaml_subset", test_parse_config_yaml_subset),
        ("bundled_catalog_ships_company_face", test_bundled_catalog_ships_company_face),
        ("catalog_docs_hit_without_local_hub", test_catalog_docs_hit_without_local_hub),
        ("hub_choose_does_not_merge_vqe", test_hub_choose_does_not_merge_vqe),
        ("hub_validate_envelope", test_hub_validate_envelope),
        ("hub_tools_are_allowed_on_lab", test_hub_tools_are_allowed_on_lab),
        ("upload_config_and_circuit", test_upload_config_and_circuit),
        ("circuit_job_asks_and_aer_has_no_twin", test_circuit_job_asks_and_aer_has_no_twin),
        ("translate_company_and_foreign", test_translate_company_and_foreign),
        ("hub_translate_face_is_slim", test_hub_translate_face_is_slim),
        ("upload_translates_and_pins_foreign_qasm", test_upload_translates_and_pins_foreign_qasm),
        ("chat_http_does_not_echo_algorithm_id", test_chat_http_does_not_echo_algorithm_id),
    ):
        try:
            fn()
            print(f"ok  {name}")
        except Exception:
            failed += 1
            print(f"FAIL {name}")
            traceback.print_exc()
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
