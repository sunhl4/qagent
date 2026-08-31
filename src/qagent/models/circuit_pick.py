from __future__ import annotations

from typing import Any, Mapping


def circuit_rank(row: Mapping[str, Any] | None) -> int:
    """Higher is a richer logical face. No I/O."""
    if not isinstance(row, Mapping):
        return 0
    try:
        n_qubits = int(row.get("n_qubits") or 0)
    except (TypeError, ValueError):
        n_qubits = 0
    try:
        n_instructions = int(row.get("n_instructions") or 0)
    except (TypeError, ValueError):
        n_instructions = 0
    return max(n_qubits, 0) * 1000 + max(n_instructions, 0)


def prefer_circuit(
    current: Mapping[str, Any] | None,
    incoming: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    """Keep the richer circuit_id face. A later empty export does not win."""
    if not isinstance(incoming, Mapping) or not incoming.get("circuit_id"):
        return dict(current) if isinstance(current, Mapping) else None
    incoming_row = dict(incoming)
    if not isinstance(current, Mapping) or not current.get("circuit_id"):
        return incoming_row
    if circuit_rank(incoming_row) > circuit_rank(current):
        return incoming_row
    return dict(current)
