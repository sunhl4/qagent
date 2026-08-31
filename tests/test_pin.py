from qagent.models.handles import HANDLE_CIRCUIT
from qagent.services.invoke import invoke


def test_pin_returns_circuit_id_without_body() -> None:
    result = invoke(
        "qagent_pin_circuit",
        "lab",
        {"source": "qasm3", "qasm3": "OPENQASM 3.0; qubit q;"},
    )
    assert result.status == "ok"
    assert result.payload is not None
    assert result.payload[HANDLE_CIRCUIT].startswith("circ_")
    assert "qasm3" not in result.payload
    assert "twin_id" not in result.payload
