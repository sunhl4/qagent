"""One-shot UQC transport worker; no model, session, or tool loop."""
from __future__ import annotations

import contextlib
import datetime
import io
import json
import logging
import os
import re
import sys
import traceback
from pathlib import Path

PROVIDER = "uqc-cloud"
NAME = re.compile(r"[A-Za-z0-9_.-]{1,128}")
RECEIPT = re.compile(r"[A-Za-z0-9_.:-]{1,128}")

# The UQC SDK validator accepts only rx, ry and rzz *calls*.  OpenQASM 3
# standard-gate calls are still useful workspace input, so the worker performs
# a deliberately small source-to-source lowering before invoking the SDK.  It
# does not import a quantum/science package or attempt to infer arbitrary gate
# definitions; unsupported operations fail closed before network dispatch.
_SINGLE_QUBIT_GATES = {
    "h", "x", "y", "z", "s", "sdg", "t", "tdg", "sx", "sxdg",
    "rx", "ry", "rz", "p", "u1", "r", "u", "u2", "u3",
}
_TWO_QUBIT_GATES = {"rzz", "cx", "cz", "swap"}
_IGNORED_GLOBAL_GATES = {"gphase", "id"}
_PASSTHROUGH_WORDS = {
    "openqasm", "include", "pragma", "qubit", "bit", "const", "input", "output",
    "let", "array", "int", "uint", "float", "angle", "bool", "duration", "stretch",
    "readonly", "mutable", "alias", "measure", "barrier",
}
_REJECTED_CONSTRUCTS = {
    "if", "else", "for", "while", "switch", "def", "defcal", "extern", "return",
    "break", "continue", "reset", "delay", "box",
}
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_OPERAND = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)(?:\[\s*(\d+)\s*\])?$")
_QUBIT_DECLARATION = re.compile(
    r"^qubit(?:\[\s*(\d+)\s*\])?\s+([A-Za-z_][A-Za-z0-9_]*)\s*;?$",
    re.IGNORECASE,
)
_QASM_REFERENCE = r"[A-Za-z_][A-Za-z0-9_]*(?:\[\s*\d+\s*\])?"
_MEASUREMENT_STATEMENT = re.compile(
    rf"^(?:measure\s+{_QASM_REFERENCE}(?:\s*->\s*{_QASM_REFERENCE})?"
    rf"|{_QASM_REFERENCE}\s*=\s*measure\s+{_QASM_REFERENCE})\s*;?$",
    re.IGNORECASE,
)
_CANONICAL_RZZ_DEFINITION = re.compile(
    r"gate\s+rzz\s*\(\s*p0\s*\)\s+([A-Za-z_][A-Za-z0-9_]*)\s*,\s*"
    r"([A-Za-z_][A-Za-z0-9_]*)\s*\{\s*"
    r"cx\s+\1\s*,\s*\2\s*;\s*"
    r"rz\s*\(\s*p0\s*\)\s+\2\s*;\s*"
    r"cx\s+\1\s*,\s*\2\s*;\s*\}\s*$",
    re.IGNORECASE | re.DOTALL,
)


def _strip_line_comments(source: str) -> str:
    result: list[str] = []
    in_string = False
    escaped = False
    index = 0
    while index < len(source):
        char = source[index]
        if in_string:
            result.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            index += 1
            continue
        if char == '"':
            in_string = True
            result.append(char)
            index += 1
            continue
        if source.startswith("//", index):
            newline = source.find("\n", index)
            if newline < 0:
                break
            result.append("\n")
            index = newline + 1
            continue
        result.append(char)
        index += 1
    return "".join(result)


def _split_statements(source: str) -> list[str]:
    """Split top-level OpenQASM statements without interpreting gate bodies."""
    statements: list[str] = []
    current: list[str] = []
    braces = 0
    in_string = False
    escaped = False
    for char in _strip_line_comments(source):
        current.append(char)
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            braces += 1
        elif char == "}" and braces:
            braces -= 1
            if braces == 0:
                value = "".join(current).strip()
                if value:
                    statements.append(value)
                current = []
        elif char == ";" and braces == 0:
            value = "".join(current).strip()
            if value:
                statements.append(value)
            current = []
    value = "".join(current).strip()
    if value:
        statements.append(value)
    return statements


def _split_csv(value: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    parentheses = 0
    brackets = 0
    for char in value:
        if char == "(":
            parentheses += 1
        elif char == ")":
            parentheses -= 1
        elif char == "[":
            brackets += 1
        elif char == "]":
            brackets -= 1
        if char == "," and parentheses == 0 and brackets == 0:
            part = "".join(current).strip()
            if not part:
                raise ValueError("empty gate argument")
            parts.append(part)
            current = []
        else:
            current.append(char)
    part = "".join(current).strip()
    if not part:
        raise ValueError("empty gate argument")
    parts.append(part)
    return parts


def _matching_parenthesis(value: str, start: int) -> int:
    depth = 0
    for index in range(start, len(value)):
        if value[index] == "(":
            depth += 1
        elif value[index] == ")":
            depth -= 1
            if depth == 0:
                return index
    return -1


def _parse_gate_invocation(statement: str) -> tuple[str, list[str], list[str]]:
    value = statement.strip().rstrip(";").strip()
    match = re.match(r"([A-Za-z_][A-Za-z0-9_]*)\s*(.*)$", value, re.DOTALL)
    if not match:
        raise ValueError("unsupported QASM statement")
    name = match.group(1).lower()
    rest = match.group(2).strip()
    if not rest:
        return name, [], []
    if rest.startswith("("):
        close = _matching_parenthesis(rest, 0)
        if close < 0:
            raise ValueError("unbalanced gate arguments")
        inside = rest[1:close].strip()
        tail = rest[close + 1 :].strip()
        if tail:
            return name, _split_csv(inside), _split_csv(tail)
        return name, [], _split_csv(inside)
    return name, [], _split_csv(rest)


def _operand_parts(operand: str) -> tuple[str, int | None]:
    match = _OPERAND.fullmatch(operand.strip())
    if not match:
        raise ValueError("gate operands must be named qubits")
    return match.group(1), int(match.group(2)) if match.group(2) is not None else None


def _qubit_registers(statements: list[str]) -> dict[str, int]:
    registers: dict[str, int] = {}
    for statement in statements:
        match = _QUBIT_DECLARATION.fullmatch(statement.strip())
        if match:
            registers[match.group(2)] = int(match.group(1) or 1)
    return registers


def _validate_source_shape(program: str) -> None:
    if not program.lstrip().startswith(("OPENQASM 3.0;", "OPENQASM 3;")):
        raise ValueError("unsupported program")
    statements = _split_statements(program)
    if not statements:
        raise ValueError("empty program")
    for statement in statements:
        value = statement.strip()
        word_match = re.match(r"([A-Za-z_][A-Za-z0-9_]*)", value)
        word = word_match.group(1).lower() if word_match else ""
        if word in _REJECTED_CONSTRUCTS or value.startswith(("gate ", "gate\t")):
            if value.startswith(("gate rzz", "gate\trzz")):
                body = value.removesuffix(";").strip()
                if not _CANONICAL_RZZ_DEFINITION.fullmatch(body):
                    raise ValueError("unsupported custom gate definition")
            else:
                raise ValueError(f"unsupported program construct {word or 'gate'}")
        elif (word == "measure" or "= measure " in value.lower()) \
                and not _MEASUREMENT_STATEMENT.fullmatch(value):
            raise ValueError("unsupported measurement statement")


def _expanded_operands(operands: list[str], count: int, registers: dict[str, int]) -> list[list[str]]:
    if len(operands) != count:
        raise ValueError("gate has an invalid number of qubit operands")
    parsed = [_operand_parts(value) for value in operands]
    if any(index is not None for _, index in parsed):
        if any(index is None for _, index in parsed):
            raise ValueError("mixed register and indexed gate operands")
        return [[value.strip() for value in operands]]
    if count != 1:
        raise ValueError("multi-qubit register broadcast is unsupported")
    name = parsed[0][0]
    size = registers.get(name)
    if size is None:
        raise ValueError("gate register is undeclared")
    return [[f"{name}[{index}]" for index in range(size)]]


def _negative(expression: str) -> str:
    return f"-({expression})"


def _emit_rotation(name: str, angle: str, operand: str) -> list[str]:
    if name in {"rx", "ry"}:
        return [f"{name}({angle}) {operand};"]
    # RZ(theta) = RX(-pi/2) RY(theta) RX(pi/2), up to no phase.
    return [f"rx(-pi/2) {operand};", f"ry({angle}) {operand};", f"rx(pi/2) {operand};"]


def _emit_hadamard(operand: str) -> list[str]:
    # H = RY(-pi/2) RX(-pi), up to a global phase.
    return [f"rx(-pi) {operand};", f"ry(-pi/2) {operand};"]


def _emit_cx(control: str, target: str) -> list[str]:
    # A native-basis CNOT decomposition. Global phase is irrelevant to a
    # measurement-only submission and the rzz definition is normalized later.
    rows = _emit_hadamard(target)
    rows += _emit_rotation("rz", "pi/2", control)
    rows += _emit_rotation("rz", "pi/2", target)
    rows.append(f"rzz(-pi/2) {control}, {target};")
    rows += _emit_hadamard(target)
    return rows


def _emit_single_gate(name: str, params: list[str], operand: str) -> list[str]:
    if name in {"rx", "ry"}:
        if len(params) != 1:
            raise ValueError(f"gate {name} requires one parameter")
        return _emit_rotation(name, params[0], operand)
    if name in {"rz", "p", "u1"}:
        if len(params) != 1:
            raise ValueError(f"gate {name} requires one parameter")
        return _emit_rotation("rz", params[0], operand)
    if name == "r":
        if len(params) != 2:
            raise ValueError("gate r requires two parameters")
        return (_emit_rotation("rz", _negative(params[1]), operand)
                + [f"ry({params[0]}) {operand};"]
                + _emit_rotation("rz", params[1], operand))
    if name in {"u", "u3"}:
        if len(params) != 3:
            raise ValueError(f"gate {name} requires three parameters")
        return (_emit_rotation("rz", params[2], operand)
                + [f"ry({params[0]}) {operand};"]
                + _emit_rotation("rz", params[1], operand))
    if name == "u2":
        if len(params) != 2:
            raise ValueError("gate u2 requires two parameters")
        return (_emit_rotation("rz", params[1], operand)
                + [f"ry(pi/2) {operand};"]
                + _emit_rotation("rz", params[0], operand))
    if params:
        raise ValueError(f"gate {name} does not take parameters")
    if name == "h":
        return _emit_hadamard(operand)
    if name == "x":
        return [f"rx(pi) {operand};"]
    if name == "y":
        return [f"ry(pi) {operand};"]
    if name == "z":
        return _emit_rotation("rz", "pi", operand)
    if name in {"s", "t", "sdg", "tdg", "sx", "sxdg"}:
        angle = {"s": "pi/2", "t": "pi/4", "sdg": "-pi/2", "tdg": "-pi/4"}.get(name)
        if angle is not None:
            return _emit_rotation("rz", angle, operand)
        return [f"rx({'pi/2' if name == 'sx' else '-pi/2'}) {operand};"]
    raise ValueError(f"unsupported gate {name}")


def compile_program(program: str) -> str:
    """Lower common static OpenQASM 3 gates to the UQC submission basis."""
    statements = _split_statements(program)
    if not statements:
        raise ValueError("empty program")
    registers = _qubit_registers(statements)
    output: list[str] = []
    used_gate = False
    for statement in statements:
        value = statement.strip()
        if not value:
            continue
        first = re.match(r"([A-Za-z_][A-Za-z0-9_]*)", value)
        word = first.group(1).lower() if first else ""
        if value.startswith("gate ") or value.startswith("gate\t"):
            raise ValueError("custom gate definitions are unsupported input")
        if word in _REJECTED_CONSTRUCTS:
            raise ValueError(f"unsupported program construct {word}")
        # OpenQASM 3 writes a register measure as `c = measure q;` or
        # `c[0] = measure q[0];`. The bit name is not a gate. A whole-register
        # assignment is rewritten to `measure q;` so the later dialect pass can
        # expand it into per-qubit assignments the platform record expects.
        assigned = re.fullmatch(
            r"([A-Za-z_][A-Za-z0-9_]*(?:\[[^\]]+\])?)\s*=\s*measure\s+"
            r"([A-Za-z_][A-Za-z0-9_]*(?:\[[^\]]+\])?)\s*;?",
            value,
        )
        if assigned:
            left, right = assigned.group(1), assigned.group(2)
            if "[" in right:
                output.append(f"{left} = measure {right};")
            else:
                output.append(f"measure {right};")
            continue
        if word in _PASSTHROUGH_WORDS:
            output.append(value if value.endswith((";", "}")) else value + ";")
            continue
        name, params, operands = _parse_gate_invocation(value)
        # OpenQASM 3 permits argument-style calls for parameterless standard
        # gates (for example ``h(q[0])``).  The generic parser initially sees
        # those operands as the parenthesized parameter list; reclassify them
        # only for the known parameterless gate names.
        parameterless = {"h", "x", "y", "z", "s", "sdg", "t", "tdg", "sx", "sxdg", "cx", "cz", "swap"}
        if (not operands and name in parameterless
                and all(_OPERAND.fullmatch(item.strip()) for item in params)):
            operands, params = params, []
        if name in _IGNORED_GLOBAL_GATES:
            if name == "gphase":
                if len(params) not in {0, 1}:
                    raise ValueError("gate gphase has invalid parameters")
                if not operands:
                    continue
            elif params or operands:
                raise ValueError("gate id has invalid arguments")
            continue
        if name in _SINGLE_QUBIT_GATES:
            for expanded in _expanded_operands(operands, 1, registers):
                output.extend(_emit_single_gate(name, params, expanded[0]))
            used_gate = True
            continue
        if name in _TWO_QUBIT_GATES:
            if name == "rzz" and len(params) != 1:
                raise ValueError("gate rzz requires one parameter")
            if name != "rzz" and params:
                raise ValueError(f"gate {name} does not take parameters")
            expanded = _expanded_operands(operands, 2, registers)
            for pair in expanded:
                if name == "rzz":
                    output.append(f"rzz({params[0]}) {pair[0]}, {pair[1]};")
                elif name == "cx":
                    output.extend(_emit_cx(pair[0], pair[1]))
                elif name == "cz":
                    output.extend(_emit_hadamard(pair[1]))
                    output.extend(_emit_cx(pair[0], pair[1]))
                    output.extend(_emit_hadamard(pair[1]))
                else:
                    output.extend(_emit_cx(pair[0], pair[1]))
                    output.extend(_emit_cx(pair[1], pair[0]))
                    output.extend(_emit_cx(pair[0], pair[1]))
            used_gate = True
            continue
        raise ValueError(f"unsupported gate {name or 'unknown'}")
    if not used_gate:
        raise ValueError("program contains no supported gate operations")
    compiled = "\n".join(output).strip() + "\n"
    if len(compiled.encode("utf-8")) > 64_000:
        raise ValueError("compiled program size")
    return compiled


def devices(chips):
    if not isinstance(chips, dict) or len(chips) > 32:
        raise ValueError("invalid device list")
    rows = []
    for name, item in chips.items():
        if not isinstance(name, str) or not NAME.fullmatch(name) or not isinstance(item, dict):
            raise ValueError("invalid device")
        info = item.get("device_info") or {}
        kind = str(item.get("chip_type", "")).lower()
        category = "simulator" if kind in {"sim", "emu"} else (
            "hardware" if kind in {"qpu", "hardware", "real"} else "unknown"
        )
        qubits = item.get("qubits", info.get("qubit_count", 0))
        maximum = info.get("max_shots", 0)
        if (type(qubits) is not int or not 0 <= qubits <= 1_000_000
            or type(maximum) is not int or not 0 <= maximum <= 1_000_000):
            raise ValueError("invalid device limits")
        rows.append({"name": name, "description": str(item.get("description") or name)[:256],
                     "state": str(item.get("status") or info.get("chip_status") or "unknown")[:32],
                     "kind": category, "qubits": qubits, "max_shots": maximum})
    return rows


def result_metrics(raw):
    """Normalize the ARTIQ histogram into bounded analysis metrics (top-8 probabilities)."""
    if not isinstance(raw, list) or not raw or not isinstance(raw[0], dict):
        raise ValueError("unsupported result format")
    datasets = raw[0].get("datasets") or {}
    histogram = datasets.get("computational_basis_histogram")
    if not isinstance(histogram, list) or not 1 <= len(histogram) <= 256:
        raise ValueError("unsupported result format")
    counts: dict[int, int] = {}
    total = 0
    for entry in histogram:
        if not (isinstance(entry, (list, tuple)) and len(entry) == 2):
            raise ValueError("unsupported result format")
        index, count = entry[0], entry[1]
        if (type(index) is not int or not 0 <= index <= 0xFFFFFFFFFFFFFFFF
            or type(count) is not int or count < 0):
            raise ValueError("unsupported result format")
        if count:
            counts[index] = counts.get(index, 0) + count
        total += count
    if total <= 0 or not counts:
        raise ValueError("unsupported result format")
    width = max(max(counts).bit_length(), 1)
    if width > 62:
        raise ValueError("unsupported result format")
    items = [
        {"name": f"p_{format(index, f'0{width}b')}", "kind": "probability", "unit": "dimensionless",
         "value": round(counts[index] / total, 6)}
        for index in sorted(counts, key=lambda idx: (-counts[idx], idx))[:8]
    ]
    return total, items


def normalize_program(program: str) -> str:
    """Rewrite the compiled program into the platform's accepted dialect.

    The remote parser fails closed on two shapes that are valid static OpenQASM
    but that the platform's qiskit-based loader needs translated:

    - invocations of ``rzz`` without an inline ``gate rzz`` definition (the
      platform gate is not in ``stdgates.inc``; its canonical definition body
      is skipped by the platform validator, but must be present for parsing);
    - a register-wide ``measure <reg>;`` without result bits (the platform
      record needs assigned per-qubit measures to expose the histogram).

    Standard gates are lowered separately by ``compile_program`` before this
    shape normalization.
    """
    import re

    if not isinstance(program, str):
        raise ValueError("unsupported program")
    _validate_source_shape(program)
    measure = re.search(r"\bmeasure\s+([A-Za-z_][A-Za-z0-9_]*)\s*;", program)
    if measure:
        register = measure.group(1)
        size = re.search(r"\bqubit\[(\d+)\]\s*" + re.escape(register) + r"\s*;", program)
        if size and not re.search(r"\b" + re.escape(register) + r"\[\d+\]\s*=", program):
            count = int(size.group(1))
            bits = "meas_bits" if re.search(r"\bmeas\b", program) else "meas"
            decl = f"bit[{count}] {bits};\n"
            assignments = "\n".join(
                f"{bits}[{index}] = measure {register}[{index}];"
                for index in range(count)
            )
            program = program.replace(measure.group(0), decl + assignments + "\n", 1)
    if re.search(r"\brzz\s*\(", program) and not re.search(r"\bgate\s+rzz\s*\(", program):
        anchor = re.search(r'\binclude\s+"stdgates\.inc"\s*;', program) \
            or re.search(r"OPENQASM\s+3(?:\.0)?\s*;", program)
        block = ("gate rzz(p0) _gate_q_0, _gate_q_1 {\n"
                 "  cx _gate_q_0, _gate_q_1;\n"
                 "  rz(p0) _gate_q_1;\n"
                 "  cx _gate_q_0, _gate_q_1;\n"
                 "}\n")
        if anchor:
            program = program.replace(anchor.group(0), anchor.group(0) + "\n" + block, 1)
    if not program.lstrip().startswith(("OPENQASM 3.0;", "OPENQASM 3;")):
        raise ValueError("unsupported program")
    return program


def execute(client, operation, payload):
    if operation == "cloud.devices":
        return {"provider": PROVIDER, "devices": devices(client.get_chips())}
    if operation == "cloud.status":
        receipt = payload["cloud_task"]
        state = client.get_task_status(task_id=receipt)
        if not isinstance(state, str) or not state.strip() or len(state) > 64:
            raise ValueError("invalid state")
        return {"provider": PROVIDER, "cloud_task": receipt, "state": state}
    if operation == "cloud.result":
        receipt = payload["cloud_task"]
        shots, items = result_metrics(client.get_task_result(task_id=receipt))
        return {"provider": PROVIDER, "cloud_task": receipt, "state": "completed",
                "summary": {"status": "completed", "shots": shots,
                            "metrics": {"schema_version": "scientific-metrics/1.0", "items": items}}}
    if operation != "cloud.submit":
        raise ValueError("unknown operation")
    target = payload["target"]
    shots = payload["shots"]
    # Run the platform's own static-circuit gate before any network step: the
    # SDK only accepts the simulator's basis gates, and a rejected program must
    # surface as its own operator-log class instead of a generic task failure.
    # Soft import: exercise() against a fixture client must stay SDK-free; the
    # SDK repeats this check inside submit_task regardless.
    try:
        from uqc_client.validator import ensure_static_qasm
    except ImportError:
        ensure_static_qasm = None
    program = normalize_program(compile_program(payload["program"]))
    if ensure_static_qasm is not None:
        ensure_static_qasm(program)
    live = next((row for row in devices(client.get_chips()) if row["name"] == target), None)
    # Names and descriptions are never sufficient authorization to run hardware.
    if (not live or live["kind"] != "simulator" or live["state"].lower() != "online"
        or shots > live["max_shots"]):
        raise ValueError("simulator unavailable")
    receipt = client.submit_task(convert_qprog=program, target=target, shots=shots)
    if not isinstance(receipt, str) or not RECEIPT.fullmatch(receipt):
        raise ValueError("invalid receipt")
    return {"provider": PROVIDER, "cloud_task": receipt, "target": target,
            "state": "submitted", "shots": shots}


def _log_failure(operation: str, exc: BaseException) -> None:
    """Operator-facing diagnosis: exception class + bounded frames, never values.

    Mirrors the provider gateway operator log's security posture: SDK error text
    may embed program bodies or account material, so only the exception class
    and frame names/lines reach the file. A broken log channel must never
    prevent the worker's bounded JSON answer.
    """
    try:
        log_dir = Path(os.environ.get(
            "XDG_CACHE_HOME", str(Path(os.environ.get("HOME", "/tmp")) / ".cache")
        )) / "unitqc-company-agent"
        log_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        target = log_dir / "gateway-errors.log"
        if target.exists() and target.is_symlink():
            return
        entries = [f"{type(exc).__name__}\n"]
        for _frame in traceback.extract_tb(exc.__traceback__):
            entries.append(f"  {_frame.name}:{_frame.lineno}\n")
        stamp = datetime.datetime.now(datetime.UTC).isoformat()
        with open(target, "a", encoding="utf-8") as stream:
            if hasattr(os, "fchmod"):
                os.fchmod(stream.fileno(), 0o600)
            stream.write(f"{stamp} uqc-cloud worker {operation}\n" + "".join(entries) + "\n")
    except OSError:
        return


def main():
    logging.disable(logging.CRITICAL)
    operation = ""
    payload_data: dict = {}
    try:
        request = json.loads(sys.stdin.buffer.read(100_001))
        if isinstance(request, dict) and isinstance(request.get("payload"), dict):
            operation = str(request.get("operation") or "")
            payload_data = request["payload"]
    except Exception:
        pass
    client = None
    result = None
    failure = None
    try:
        # SDK logs and diagnostics are untrusted; stdout is reserved for bounded JSON.
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            os.environ["SERVER_HOST"] = os.environ["UQC_CLOUD_HOST"]
            os.environ["SERVER_PORT"] = os.environ["UQC_CLOUD_PORT"]
            from uqc_client import UQC

            client = UQC(token=os.environ["UQC_CLOUD_API_KEY"])
            result = execute(client, operation, payload_data)
    except Exception as exc:
        result = None
        failure = exc
    finally:
        if failure is not None:
            _log_failure(operation, failure)
        if client is not None:
            with contextlib.suppress(Exception), contextlib.redirect_stdout(io.StringIO()):
                client._async_mgr.run(client._disconnect())
    encoded = json.dumps({"ok": result is not None, "result": result}, ensure_ascii=False,
                         allow_nan=False, separators=(",", ":"))
    if len(encoded.encode()) > 64_000:
        encoded = '{"ok":false,"result":null}'
    print(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
