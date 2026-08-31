from qagent.services.invoke import invoke

_FIVE = ["qdata", "qchem", "ionstack", "route", "qiskit"]


def test_list_engines_is_native() -> None:
    result = invoke("qagent_list_engines", "lab", {})
    assert result.status == "ok"
    assert result.decision == "allow"
    assert result.payload is not None
    ids = [row["id"] for row in result.payload["engines"]]
    assert ids[:5] == _FIVE
    assert set(_FIVE) <= set(ids)


def test_allowed_recipe_is_not_wired() -> None:
    result = invoke("qdata_run_recipe", "lab", {"name": "a2_chem_pes"})
    assert result.decision == "allow"
    assert result.status == "not_wired"
    assert result.slot_id == "S-QDATA-04"
    assert result.payload is None


def test_twin_run_asks_before_port() -> None:
    result = invoke("ionstack_twin_run", "lab", {"shots": 1000, "mode": "signoff"})
    assert result.decision == "ask"
    assert result.status == "needs_ask"
    assert result.payload is None


def test_aer_claim_twin_denied() -> None:
    result = invoke("qiskit_aer_run", "lab", {"circuit_id": "c1", "shots": 100, "claim_twin_id": True})
    assert result.status == "denied"


def test_ibm_run_denied() -> None:
    result = invoke("qiskit_ibm_run", "lab", {"circuit_id": "c1", "shots": 100})
    assert result.status == "denied"


def test_unknown_tool_denied() -> None:
    result = invoke("cal_edit", "lab", {})
    assert result.status == "denied"
