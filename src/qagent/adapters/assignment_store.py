from __future__ import annotations

import json
import os
from pathlib import Path

from qagent.adapters.contracts import ROOT
from qagent.models.assignment import Assignment, AssignmentError, tenant_visible

_DEFAULT = ROOT / ".qagent" / "assignments.jsonl"


def assignment_path() -> Path:
    raw = os.environ.get("QAGENT_ASSIGNMENTS_FILE")
    if raw:
        return Path(raw)
    return _DEFAULT


class AssignmentStore:
    """JSONL store for product assignments. Not a science handle issuer."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or assignment_path()

    def list(self, tenant_id: str = "") -> list[Assignment]:
        if not self.path.is_file():
            return []
        rows: list[Assignment] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = Assignment.from_dict(json.loads(line))
                if tenant_visible(row.tenant_id, tenant_id):
                    rows.append(row)
        return rows

    def get(self, assignment_id: str, tenant_id: str = "") -> Assignment:
        for row in self.list(tenant_id=tenant_id):
            if row.assignment_id == assignment_id:
                return row
        raise AssignmentError(f"unknown assignment_id {assignment_id!r}")

    def put(self, assignment: Assignment) -> Assignment:
        rows = [row for row in self.list() if row.assignment_id != assignment.assignment_id]
        rows.append(assignment)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        text = "".join(json.dumps(row.to_dict(), sort_keys=True) + "\n" for row in rows)
        self.path.write_text(text, encoding="utf-8")
        return assignment
