"""G-01 governance pack: boot, witness, handoff, doctor, savepoint. Not a loop."""

from __future__ import annotations

import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from qagent.adapters.preset import PRESET_BOOT, PRESETS, active_preset, set_active_preset
from qagent.entrypoints.shell_http import dispatch
from qagent.models.gov import GOV_EVAL_IDS, KIND_FORGED_TWIN, KIND_NO_EVIDENCE, extra_handle_keys
from qagent.services.eval_run import run_evals
from qagent.services.handoff import HandoffError, create_handoff
from qagent.services.invoke import invoke
from qagent.services.knowledge import lookup
from qagent.services.policy import decide
from qagent.services.savepoint import enter_safe_mode, safe_mode_on, snapshot
from qagent.services.witness import first_finding

_ENV_KEYS = (
    "QAGENT_USAGE_FILE",
    "QAGENT_ASKS_FILE",
    "QAGENT_HANDOFF_DIR",
    "QAGENT_SAVEPOINT_DIR",
    "QAGENT_SAFE_MODE_FILE",
    "QAGENT_PRESET_FILE",
    "QAGENT_PRESET",
    "QAGENT_WORKPLACE_FILE",
    "QAGENT_SECRETS_FILE",
    "QAGENT_DSH_ENV_FILE",
    "QAGENT_ASSIGNMENTS_FILE",
    "QAGENT_ELN_FILE",
)


@contextmanager
def isolated() -> Iterator[Path]:
    previous = {key: os.environ.get(key) for key in _ENV_KEYS}
    tmp = tempfile.TemporaryDirectory()
    try:
        folder = Path(tmp.name)
        os.environ["QAGENT_USAGE_FILE"] = str(folder / "usage.jsonl")
        os.environ["QAGENT_ASKS_FILE"] = str(folder / "asks.jsonl")
        os.environ["QAGENT_HANDOFF_DIR"] = str(folder / "handoffs")
        os.environ["QAGENT_SAVEPOINT_DIR"] = str(folder / "savepoints")
        os.environ["QAGENT_SAFE_MODE_FILE"] = str(folder / "safe_mode")
        os.environ["QAGENT_PRESET_FILE"] = str(folder / "active_preset")
        os.environ.pop("QAGENT_PRESET", None)
        os.environ["QAGENT_WORKPLACE_FILE"] = str(folder / "workplace.json")
        os.environ["QAGENT_SECRETS_FILE"] = str(folder / "secrets.json")
        os.environ["QAGENT_DSH_ENV_FILE"] = str(folder / "dsh.env")
        os.environ["QAGENT_ASSIGNMENTS_FILE"] = str(folder / "assignments.jsonl")
        os.environ["QAGENT_ELN_FILE"] = str(folder / "eln.jsonl")
        yield folder
    finally:
        tmp.cleanup()
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def test_boot_rails() -> None:
    assert PRESET_BOOT in PRESETS
    assert decide("qagent_list_engines", "boot", {}) == "allow"
    assert decide("qagent_pin_circuit", "boot", {}) == "allow"
    assert decide("ionstack_twin_run", "boot", {"shots": 8}) == "deny"
    assert decide("qdata_run_recipe", "boot", {"name": "a2_chem_pes"}) == "deny"
    assert decide("qiskit_aer_run", "boot", {"circuit_id": "c1", "shots": 8}) == "deny"


def test_witness_gates() -> None:
    miss = first_finding(
        "qdata_dequant_gate",
        {"b3": {"verdict": "quantum_wins", "qem_contract_ok": False}},
    )
    assert miss is not None and miss.kind == KIND_NO_EVIDENCE
    forged = first_finding(
        "qiskit_aer_run",
        {"provenance": "qccd-twin", "twin_id": "x"},
    )
    assert forged is not None and forged.kind == KIND_FORGED_TWIN
    honest = first_finding("qiskit_aer_run", {"provenance": "aer", "counts": {"00": 1}})
    assert honest is None
    live = first_finding(
        "ionstack_twin_run",
        {"provenance": "qccd-twin", "twin_id": "twin_honest", "counts": {"00": 1}},
    )
    assert live is None


def test_handoff_schema() -> None:
    with isolated():
        row = create_handoff(
            source_preset="lab",
            target_preset="sign",
            handles={"circuit_id": "circ_1"},
            intent="  keep going  ",
        )
        assert row.handles == {"circuit_id": "circ_1"}
        assert extra_handle_keys({"circuit_id": "c", "foo": "x"}) == ("foo",)
        try:
            create_handoff(source_preset="lab", target_preset="lab", handles={"foo": "x"})
        except HandoffError:
            pass
        else:
            raise AssertionError("extra handle must fail")


def test_safe_mode_is_boot() -> None:
    with isolated():
        set_active_preset("lab")
        snap = snapshot("gov-test")
        assert snap["workplace"].get("llm_api_key") is None
        out = enter_safe_mode()
        assert out["preset"] == PRESET_BOOT
        assert safe_mode_on()
        assert active_preset() == PRESET_BOOT


def test_eval_gov_pool() -> None:
    with isolated():
        rows = run_evals(*GOV_EVAL_IDS)
        failed = [row for row in rows if not row.ok]
        assert not failed, failed


def test_gov_http_face() -> None:
    with isolated():
        code, payload = dispatch("GET", "/api/gov/face", {})
        assert code == 200
        assert payload["has_twin"] is False
        assert "twin_id" not in json.dumps(payload)
        denied = dispatch("POST", "/api/safe-mode", {}, {})
        assert denied[0] == 403
        doctor = dispatch("GET", "/api/doctor", {})
        assert doctor[0] == 200
        assert doctor[1]["ok"] is True


def test_knowledge_hits_orange_book() -> None:
    hits = lookup("boot preset orange-book")
    assert hits["hits"]


def test_invoke_records_ask() -> None:
    with isolated():
        asked = invoke("ionstack_twin_run", "lab", {"shots": 32})
        assert asked.status == "needs_ask"
        lines = Path(os.environ["QAGENT_ASKS_FILE"]).read_text(encoding="utf-8")
        assert "ionstack_twin_run" in lines
        usage = Path(os.environ["QAGENT_USAGE_FILE"]).read_text(encoding="utf-8")
        assert "needs_ask" in usage
