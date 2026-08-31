from __future__ import annotations

import os
from typing import Any, Mapping

from qagent.adapters.assignment_store import AssignmentStore
from qagent.adapters.eln import NativeEln
from qagent.models.gov import Finding
from qagent.models.handles import PROVENANCE_QCCD_TWIN
from qagent.services.health import health_lamps, science_health
from qagent.services.savepoint import safe_mode_on
from qagent.services.witness import scan_payload


def _finding_face(item: Finding) -> dict[str, str]:
    return {"kind": item.kind, "path": item.path, "pool": item.pool, "message": item.message}


def scan_mapping(tool: str, payload: Mapping[str, Any] | None) -> list[dict[str, str]]:
    return [_finding_face(item) for item in scan_payload(tool, payload)]


def probe(
    *,
    tool: str = "",
    payload: Mapping[str, Any] | None = None,
    scan_store: bool | None = None,
) -> dict[str, Any]:
    """Honesty probe. Default is payload-only so eval stays deterministic."""
    if scan_store is None:
        scan_store = os.environ.get("QAGENT_DOCTOR_STORE") == "1"
    findings: list[dict[str, str]] = []
    if payload is not None:
        findings.extend(scan_mapping(tool, payload))
    if scan_store:
        findings.extend(_scan_store())
    return {
        "ok": not findings,
        "findings": findings,
        "safe_mode": safe_mode_on(),
        "health": science_health(),
        "lamps": health_lamps(),
    }


def _scan_store() -> list[dict[str, str]]:
    hits: list[dict[str, str]] = []
    for row in NativeEln().read():
        tool = str(row.get("type") or "eln")
        if tool == "qagent/twin_signoff":
            continue
        hits.extend(scan_mapping(tool, row))
        if row.get("provenance") == PROVENANCE_QCCD_TWIN and "twin_signoff" not in tool:
            hits.append(
                {
                    "kind": "foreign_qccd_twin",
                    "path": "eln.provenance",
                    "pool": "provenance",
                    "message": "ELN row wears qccd-twin outside twin_signoff",
                }
            )
    for row in AssignmentStore().list():
        aer = row.columns.get("aer_provenance")
        if aer == PROVENANCE_QCCD_TWIN:
            hits.append(
                {
                    "kind": "foreign_qccd_twin",
                    "path": "assignment.aer_provenance",
                    "pool": "provenance",
                    "message": "assignment aer_provenance must not be qccd-twin",
                }
            )
    return hits
