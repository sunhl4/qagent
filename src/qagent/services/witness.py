from __future__ import annotations

from typing import Any, Mapping

from qagent.models.gov import (
    KIND_FOREIGN_TWIN,
    KIND_FORGED_TWIN,
    KIND_LEAK,
    KIND_NO_EVIDENCE,
    Finding,
    b3_block,
    foreign_provenance,
    leak_paths,
    may_carry_twin,
    payload_has_twin,
)
from qagent.models.handles import B3_QUANTUM_WINS, HANDLE_TWIN, PROVENANCE_QCCD_TWIN


def scan_payload(tool: str, payload: Mapping[str, Any] | None) -> tuple[Finding, ...]:
    """Posterior checks. Empty tuple means honest. Not an agent loop."""
    if not payload:
        return ()
    found: list[Finding] = []
    provenance = payload.get("provenance")
    if payload_has_twin(payload) and not may_carry_twin(tool):
        found.append(
            Finding(
                kind=KIND_FORGED_TWIN,
                path=HANDLE_TWIN,
                message="twin_id is only issued by ionstack_twin_run",
                pool="handles",
            )
        )
    if provenance == PROVENANCE_QCCD_TWIN and not may_carry_twin(tool):
        found.append(
            Finding(
                kind=KIND_FOREIGN_TWIN,
                path="provenance",
                message="qccd-twin is only legal on ionstack_twin_run",
                pool="provenance",
            )
        )
    if foreign_provenance(provenance) and (
        payload_has_twin(payload) or provenance == PROVENANCE_QCCD_TWIN
    ):
        found.append(
            Finding(
                kind=KIND_FORGED_TWIN,
                path="provenance",
                message="foreign provenance cannot wear qccd-twin or twin_id",
                pool="provenance",
            )
        )
    block = b3_block(payload)
    if block.get("verdict") == B3_QUANTUM_WINS and not block.get("qem_contract_ok"):
        found.append(
            Finding(
                kind=KIND_NO_EVIDENCE,
                path="b3.verdict",
                message="quantum_wins requires qem_contract_ok",
                pool="b3",
            )
        )
    for path in leak_paths(payload):
        found.append(
            Finding(
                kind=KIND_LEAK,
                path=path,
                message=f"leaked {path}",
                pool="short_output",
            )
        )
    return tuple(found)


def first_finding(tool: str, payload: Mapping[str, Any] | None) -> Finding | None:
    hits = scan_payload(tool, payload)
    return hits[0] if hits else None
