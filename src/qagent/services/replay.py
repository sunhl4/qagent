from __future__ import annotations

from typing import Any

from qagent.models.assignment import sanitize_handles
from qagent.models.eln import drop_twin, short_payload
from qagent.services.assignment import get_assignment, list_assignments
from qagent.services.eln import filter_eln_for_assignments, read_eln
from qagent.services.usage import list_usage


def replay(assignment_id: str = "", tenant_id: str = "") -> dict[str, Any]:
    """Project ELN + assignment + usage. Does not start an agent loop."""
    if assignment_id:
        row = get_assignment(assignment_id, tenant_id=tenant_id)
        events = [short_payload(drop_twin(item)) for item in read_eln(assignment_id=assignment_id)]
        usage = [item for item in list_usage() if item.get("tool")]
        return {
            "assignment_id": row.assignment_id,
            "status": row.status,
            "handles": sanitize_handles(row.handles),
            "events": events,
            "usage_count": len(usage),
        }
    rows = list_assignments(tenant_id=tenant_id)
    visible = {item.assignment_id for item in rows}
    events = filter_eln_for_assignments(read_eln(), visible)
    return {
        "assignments": [item.assignment_id for item in rows[-20:]],
        "events": [short_payload(drop_twin(item)) for item in events[-40:]],
        "usage_count": len(list_usage()),
    }
