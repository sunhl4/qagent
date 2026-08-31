from qagent.services.policy import decide


def test_unknown_recipe_denied() -> None:
    assert decide("qdata_run_recipe", "lab", {"name": "foo_bar"}) == "deny"


def test_allowlisted_recipe_allowed() -> None:
    assert decide("qdata_run_recipe", "lab", {"name": "a2_chem_pes"}) == "allow"


def test_huge_shots_asks() -> None:
    assert decide("ionstack_twin_run", "lab", {"shots": 10_000_000}) == "ask"


def test_twin_run_asks_on_lab() -> None:
    assert decide("ionstack_twin_run", "lab", {"shots": 1000}) == "ask"


def test_twin_run_denied_on_algo() -> None:
    assert decide("ionstack_twin_run", "algo", {"shots": 1000}) == "deny"


def test_cal_tool_denied() -> None:
    assert decide("cal_edit", "lab", {}) == "deny"


def test_force_quantum_wins_denied() -> None:
    assert decide("qdata_dequant_gate", "lab", {"force_verdict": "quantum_wins"}) == "deny"


def test_identity_allowed() -> None:
    assert decide("ionstack_twin_identity", "lab", {}) == "allow"


def test_codex_hidden_on_lab() -> None:
    assert decide("subagent_codex", "lab", {}) == "deny"


def test_codex_allowed_on_algo() -> None:
    assert decide("subagent_codex", "algo", {}) == "allow"


def test_unknown_preset_denied() -> None:
    assert decide("qdata_run_recipe", "customer", {}) == "deny"


def test_list_engines_allowed() -> None:
    assert decide("qagent_list_engines", "lab", {}) == "allow"


def test_aer_cannot_claim_twin() -> None:
    assert decide("qiskit_aer_run", "lab", {"claim_twin_id": True}) == "deny"


def test_ibm_run_denied() -> None:
    assert decide("qiskit_ibm_run", "lab", {}) == "deny"
