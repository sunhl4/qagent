from __future__ import annotations

from typing import Any, Mapping


class NativeWorkflow:
    """Circuit job FSM. Calls invoke() for estimate / aer / twin. No science import."""

    def circuit_job(self, args: Mapping[str, Any]) -> dict[str, Any]:
        from qagent.services.circuit_job import run_tool

        return run_tool(args)
