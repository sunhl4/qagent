from __future__ import annotations

from typing import Any, Mapping

from qagent.models.fill import fill

Args = Mapping[str, Any]
Result = Mapping[str, Any]


def _reserve(slot_id: str, where: str):
    def _call(_self: object, _args: Args) -> Result:
        fill(slot_id, where)

    return _call


class ReservedQData:
    list_providers = _reserve("S-QDATA-07", "QDataPort.list_providers")
    run_recipe = _reserve("S-QDATA-04", "QDataPort.run_recipe")
    submit_job = _reserve("S-QDATA-08", "QDataPort.submit_job")
    get_job = _reserve("S-QDATA-03", "QDataPort.get_job")
    list_assets = _reserve("S-QDATA-08", "QDataPort.list_assets")
    get_run_record = _reserve("S-QDATA-05", "QDataPort.get_run_record")
    dequant_gate = _reserve("S-QDATA-06", "QDataPort.dequant_gate")
    sandbox_exec = _reserve("S-SAND-01", "QDataPort.sandbox_exec")


class ReservedQChem:
    run = _reserve("S-QCHEM-01", "QChemPort.run")
    export_parity = _reserve("S-QCHEM-02", "QChemPort.export_parity")


class ReservedIonstack:
    twin_identity = _reserve("S-TWIN-01", "IonstackPort.twin_identity")
    twin_run = _reserve("S-TWIN-02", "IonstackPort.twin_run")
    compile_estimate = _reserve("S-TWIN-03", "IonstackPort.compile_estimate")


class ReservedRoute:
    compile_estimate = _reserve("S-ROUTE-01", "RoutePort.compile_estimate")


class ReservedQiskit:
    import_circuit = _reserve("S-QISKIT-01", "QiskitPort.import_circuit")
    export_circuit = _reserve("S-QISKIT-02", "QiskitPort.export_circuit")
    transpile = _reserve("S-QISKIT-03", "QiskitPort.transpile")
    aer_run = _reserve("S-QISKIT-04", "QiskitPort.aer_run")
    ibm_run = _reserve("S-QISKIT-05", "QiskitPort.ibm_run")


class ReservedCirq:
    import_circuit = _reserve("S-CIRQ-01", "CirqPort.import_circuit")
    export_circuit = _reserve("S-CIRQ-02", "CirqPort.export_circuit")
    simulator_run = _reserve("S-CIRQ-03", "CirqPort.simulator_run")


class ReservedPennylane:
    import_circuit = _reserve("S-PL-01", "PennylanePort.import_circuit")
    export_circuit = _reserve("S-PL-02", "PennylanePort.export_circuit")
    simulator_run = _reserve("S-PL-03", "PennylanePort.simulator_run")


class ReservedDocs:
    search = _reserve("S-DOCS-01", "DocsPort.search")


class ReservedCodex:
    oneshot = _reserve("S-CODEX-01", "CodexPort.oneshot")
    attended = _reserve("S-CODEX-02", "CodexPort.attended")
