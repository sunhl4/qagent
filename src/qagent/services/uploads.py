from __future__ import annotations

import json
from typing import Any

KIND_CIRCUIT = "circuit"
KIND_CONFIG = "config"
KIND_UNKNOWN = "unknown"


def classify_upload(filename: str, text: str) -> str:
    name = str(filename or "").lower()
    body = str(text or "").lstrip()
    if name.endswith((".py", ".ipynb", ".qpy")):
        return KIND_UNKNOWN
    if name.endswith((".qasm", ".qasm3")):
        return KIND_CIRCUIT
    if name.endswith((".yaml", ".yml", ".json")):
        return KIND_CONFIG
    if body.startswith("OPENQASM"):
        return KIND_CIRCUIT
    markers = (
        '"algorithm_id"',
        "algorithm_id:",
        "api_version:",
        '"molecule"',
        "molecule:",
        '"basis"',
        '"scenario"',
        "native_format",
        "SparsePauliOp",
        '"paulis"',
        "paulis:",
        '"hamiltonian"',
        "hamiltonian:",
        "maxcut",
        "MaxCut",
        "qiskit",
        "cirq",
        "pennylane",
        "ibm_quantum",
    )
    if any(token in body for token in markers):
        return KIND_CONFIG
    return KIND_UNKNOWN


def parse_config_text(text: str) -> dict[str, Any]:
    stripped = str(text or "").strip()
    if not stripped:
        raise ValueError("empty config")
    if stripped[0] in "{[":
        data = json.loads(stripped)
    else:
        try:
            import yaml  # type: ignore

            data = yaml.safe_load(stripped)
        except ImportError:
            data = _simple_yaml_map(stripped)
    if not isinstance(data, dict):
        raise ValueError("config must be a mapping")
    return data


def _coerce_scalar(raw: str) -> Any:
    text = raw.strip().strip('"').strip("'")
    if text in {"true", "True"}:
        return True
    if text in {"false", "False"}:
        return False
    if text in {"null", "None", "~"}:
        return None
    try:
        if "." in text:
            return float(text)
        return int(text)
    except ValueError:
        return text


def _simple_yaml_map(text: str) -> dict[str, Any]:
    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(0, root)]
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        line = raw.strip()
        if ":" not in line:
            raise ValueError("send JSON, or install PyYAML for nested YAML")
        key, _, rest = line.partition(":")
        key = key.strip()
        rest = rest.strip()
        while len(stack) > 1 and indent < stack[-1][0]:
            stack.pop()
        current = stack[-1][1]
        if not rest:
            child: dict[str, Any] = {}
            current[key] = child
            stack.append((indent + 2, child))
        else:
            current[key] = _coerce_scalar(rest)
    return root
