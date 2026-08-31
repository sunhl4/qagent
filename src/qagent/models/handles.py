from __future__ import annotations

from typing import Literal

HANDLE_CIRCUIT = "circuit_id"
HANDLE_ASSET = "asset_id"
HANDLE_TWIN = "twin_id"
HANDLES = (HANDLE_CIRCUIT, HANDLE_ASSET, HANDLE_TWIN)

PROVENANCE_QCCD_TWIN = "qccd-twin"
PROVENANCE_AER = "aer"
PROVENANCE_IBM = "ibm"
PROVENANCE_CIRQ = "cirq"
FOREIGN_PROVENANCE = frozenset({PROVENANCE_AER, PROVENANCE_IBM, PROVENANCE_CIRQ})

TWIN_ISSUER_ENGINE = "ionstack"

B3_QUANTUM_WINS = "quantum_wins"
B3_CLASSICAL_WINS = "classical_wins"
B3_INCONCLUSIVE = "inconclusive"
B3Verdict = Literal["quantum_wins", "classical_wins", "inconclusive"]
B3_VERDICTS = (B3_QUANTUM_WINS, B3_CLASSICAL_WINS, B3_INCONCLUSIVE)

FORBIDDEN_IMPORT_ROOTS = ("qdata", "ionstack", "qchem", "qcchem", "qiskit")


def may_emit_twin_id(engine_id: str) -> bool:
    return engine_id == TWIN_ISSUER_ENGINE
