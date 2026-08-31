from __future__ import annotations

from typing import Any, Mapping

# Assignment stages store tool names. The face only ships Chinese labels.
_STAGE_LABELS = {
    "qagent_list_engines": "已接软件",
    "qdata_run_recipe": "资产",
    "qagent_pin_circuit": "线路",
    "qiskit_aer_run": "对照",
    "cirq_simulator_run": "对照",
    "ionstack_compile_estimate": "预估",
    "ionstack_twin_run": "签收",
    "qdata_dequant_gate": "对照",
}


def life_labels(
    stages: object,
    *,
    has_asset: bool = False,
    has_circuit: bool = False,
    has_twin: bool = False,
    has_estimate: bool = False,
    has_b3: bool = False,
) -> list[str]:
    """Ordered short labels. Never returns tool names."""
    seen: list[str] = []
    if isinstance(stages, list):
        for item in stages:
            label = _STAGE_LABELS.get(str(item))
            if label and label not in seen:
                seen.append(label)
    if seen:
        return seen
    fallback = (
        ("资产", has_asset),
        ("线路", has_circuit),
        ("预估", has_estimate),
        ("签收", has_twin),
        ("对照", has_b3),
    )
    return [label for label, on in fallback if on]


def life_from_assignment(columns: Mapping[str, Any] | None, handles: Mapping[str, Any] | None) -> list[str]:
    columns = columns or {}
    handles = handles or {}
    return life_labels(
        columns.get("stages"),
        has_asset=bool(handles.get("asset_id")),
        has_circuit=bool(handles.get("circuit_id")),
        has_twin=bool(handles.get("twin_id")),
        has_estimate=columns.get("makespan_ns") is not None,
        has_b3=bool(isinstance(columns.get("b3"), dict) and columns.get("b3", {}).get("verdict")),
    )
