from __future__ import annotations

import re
from typing import Any, Mapping

_GATE_LINE = re.compile(
    r"^\s*([A-Za-z][A-Za-z0-9_]*)\s*(?:\(([^)]*)\))?\s+(.+?)\s*;?\s*$"
)
_QUBIT = re.compile(r"(?:q|qubit)\s*\[\s*(\d+)\s*\]", re.IGNORECASE)
_QUBIT_DECL = re.compile(r"\bqubit\s*\[\s*(\d+)\s*\]", re.IGNORECASE)
_QREG_DECL = re.compile(r"\bqreg\s+\w+\s*\[\s*(\d+)\s*\]", re.IGNORECASE)
_SKIP = frozenset(
    {
        "openqasm",
        "include",
        "qubit",
        "qreg",
        "creg",
        "bit",
        "measure",
        "barrier",
        "reset",
        "gate",
        "def",
        "const",
        "let",
        "input",
        "output",
    }
)
_TWO = frozenset({"cx", "cnot", "cz", "cy", "swap", "cp", "crz", "crx", "cry"})
_MAX_CHARS = 200_000


def program_filename(ansatz: str = "", molecule: str = "") -> str:
    """Human download name. Not a handle."""
    ansatz_key = str(ansatz or "").strip().lower()
    molecule_key = str(molecule or "").strip().lower()
    if ansatz_key == "uccsd" and molecule_key in {"h2", "hydrogen"}:
        return "氢分子-UCCSD.qasm"
    if ansatz_key == "uccsd":
        return "UCCSD线路.qasm"
    if ansatz_key:
        return f"{ansatz_key}线路.qasm"
    return "线路.qasm"


def emit_qasm3(n_qubits: int, gates: list[Mapping[str, Any]]) -> str:
    """OpenQASM 3 from a short gate list. No science imports."""
    width = max(1, int(n_qubits))
    lines = ["OPENQASM 3.0;", 'include "stdgates.inc";', f"qubit[{width}] q;"]
    for item in gates:
        if not isinstance(item, Mapping):
            continue
        name = _qasm_gate_name(str(item.get("name") or ""))
        qubits = [int(q) for q in (item.get("qubits") or []) if str(q).strip() != ""]
        if not name or not qubits:
            continue
        args = _qasm_params(item.get("params"))
        targets = ", ".join(f"q[{q}]" for q in qubits)
        if args:
            lines.append(f"{name}({args}) {targets};")
        else:
            lines.append(f"{name} {targets};")
    return "\n".join(lines) + "\n"


def parse_qasm(text: str) -> dict[str, Any]:
    """Best-effort logical body from OpenQASM 2/3. Honest empty gates if unread."""
    raw = str(text or "")
    if len(raw) > _MAX_CHARS:
        raise ValueError("线路文件太大。请先截成一份逻辑线路再附上。")
    source = raw.strip()
    if not source:
        raise ValueError("没有读到线路。请附上 OpenQASM。")
    n_qubits = _n_qubits(source)
    if n_qubits < 1:
        raise ValueError("读不懂这份线路里的比特数。请用 OpenQASM。")
    gates: list[dict[str, Any]] = []
    for line in source.splitlines():
        trimmed = line.split("//", 1)[0].strip()
        if not trimmed or trimmed.startswith("#"):
            continue
        gate = _parse_gate_line(trimmed)
        if gate:
            gates.append(gate)
    return {
        "n_qubits": n_qubits,
        "body": {
            "schema_version": "3",
            "ir_kind": "logical",
            "n_qubits": n_qubits,
            "instructions": gates,
        },
    }


def _n_qubits(source: str) -> int:
    found = _QUBIT_DECL.search(source) or _QREG_DECL.search(source)
    if found:
        return max(1, int(found.group(1)))
    indexes = [int(match.group(1)) for match in _QUBIT.finditer(source)]
    if indexes:
        return max(indexes) + 1
    return 0


def _parse_gate_line(line: str) -> dict[str, Any] | None:
    match = _GATE_LINE.match(line.rstrip(";"))
    if not match:
        return None
    name = match.group(1).lower()
    if name in _SKIP:
        return None
    if name == "cnot":
        name = "cx"
    params = _read_params(match.group(2))
    qubits = [int(item) for item in _QUBIT.findall(match.group(3) or "")]
    if not qubits:
        return None
    if name in _TWO and len(qubits) < 2:
        return None
    return {"kind": "gate", "name": name, "qubits": qubits, "params": params}


def _read_params(raw: str | None) -> list[float | str]:
    if not raw or not raw.strip():
        return []
    out: list[float | str] = []
    for part in raw.split(","):
        token = part.strip()
        if not token:
            continue
        try:
            out.append(float(token))
        except ValueError:
            out.append(token)
    return out


def _qasm_gate_name(name: str) -> str:
    key = name.strip().lower()
    if key == "cnot":
        return "cx"
    return key


def _qasm_params(raw: Any) -> str:
    if not isinstance(raw, list) or not raw:
        return ""
    bits: list[str] = []
    for item in raw:
        if isinstance(item, (int, float)) and not isinstance(item, bool):
            bits.append(f"{item:g}")
        elif item is not None and str(item).strip():
            bits.append(str(item).strip())
    return ", ".join(bits)
