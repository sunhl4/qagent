from qagent.models.eln import EVENT_CLAIM_BLOCKED, EVENT_RECIPE_PIN, FORBIDDEN_ELN_KEYS
from qagent.services.eln import read_eln
from qagent.services.invoke import invoke


def test_denied_aer_claim_is_logged() -> None:
    invoke("qiskit_aer_run", "lab", {"circuit_id": "c1", "shots": 100, "claim_twin_id": True})
    events = [row for row in read_eln() if row.get("type") == EVENT_CLAIM_BLOCKED]
    assert events
    assert events[-1]["reason"] == "aer_claim_twin_id"
    assert not FORBIDDEN_ELN_KEYS & set(events[-1])


def test_allowed_recipe_pins_short_event() -> None:
    invoke("qdata_run_recipe", "lab", {"name": "a2_chem_pes", "shots": 128})
    events = [row for row in read_eln() if row.get("type") == EVENT_RECIPE_PIN]
    assert events
    assert events[-1]["recipe"] == "a2_chem_pes"
    assert "pauli_terms" not in events[-1]
