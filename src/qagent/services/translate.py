from __future__ import annotations

from typing import Any, Mapping

ORIGIN_NATIVE = "native"
ORIGIN_COMPANY = "company"
ORIGIN_TRANSLATED = "translated"

FROM_HUB = "hub"
FROM_COMPANY = "company"
FROM_QISKIT = "qiskit"
FROM_CIRQ = "cirq"
FROM_PENNYLANE = "pennylane"
FROM_IBM = "ibm"
FROM_PAULI = "pauli"
FROM_MOLECULE = "molecule"
FROM_MAXCUT = "maxcut"

_COMPANY_FORMATS = frozenset({"qchem-stack.scenario", "uqc-algorithm.json"})
_QCHEM_SCENARIOS = frozenset(
    {
        "minimal_vqe",
        "uccsd_pauli",
        "uccsd",
        "h2_uccsd",
        "adapt_vqe",
        "iqeb",
        "gqe",
    }
)
_UQC_ACTIONS = frozenset({"build", "run", "estimate", "compile", "optimize"})
_COPY_KEYS = (
    "scenario",
    "molecule",
    "basis",
    "geometry",
    "charge",
    "spin",
    "multiplicity",
    "active_space",
    "mapping",
    "ansatz",
    "action",
    "edges",
    "graph",
    "n_qubits",
    "layers",
    "reps",
    "shots",
)
_SKIP_COPY = frozenset(
    {
        "qasm",
        "qasm2",
        "qasm3",
        "openqasm",
        "body",
        "twin_id",
        "token",
        "secret",
        "password",
        "pauli_terms",
        "bitstrings",
        "counts_full",
    }
)
_BRIEFS = {
    FROM_HUB: "公司流程配置",
    FROM_COMPANY: "公司算法包",
    FROM_QISKIT: "外部线路包，已转到公司作业",
    FROM_CIRQ: "外部线路包，已转到公司作业",
    FROM_PENNYLANE: "外部线路包，已转到公司作业",
    FROM_IBM: "外部线路包，已转到公司作业",
    FROM_PAULI: "Pauli 哈密顿量，已转到公司作业",
    FROM_MOLECULE: "分子输入，已转到化学计算作业",
    FROM_MAXCUT: "组合优化输入，已转到公司作业",
}


def detect_from_kind(raw: Mapping[str, Any]) -> str:
    """Classify a parsed mapping. Empty means unread. No science imports."""
    if not isinstance(raw, dict) or not raw:
        return ""
    if str(raw.get("api_version") or "") == "hub/v1" and str(raw.get("algorithm_id") or "").startswith(
        "org."
    ):
        return FROM_HUB
    if _is_company(raw):
        return FROM_COMPANY
    blob = _blob(raw)
    if _is_ibm(raw, blob):
        return FROM_IBM
    if "pennylane" in blob or "qml.device" in blob:
        return FROM_PENNYLANE
    if _is_cirq(raw, blob):
        return FROM_CIRQ
    if _is_qiskit(raw, blob):
        if _has_pauli(raw) and not extract_qasm(raw) and not _has_molecule(raw):
            return FROM_PAULI
        return FROM_QISKIT
    if _is_maxcut(raw, blob):
        return FROM_MAXCUT
    if _has_pauli(raw):
        return FROM_PAULI
    if _has_molecule(raw):
        return FROM_MOLECULE
    if extract_qasm(raw):
        return FROM_QISKIT
    return ""


def extract_qasm(raw: Any) -> str:
    """First OpenQASM string in a nested mapping. Not a face field."""
    found: list[str] = []
    _collect_qasm(raw, found)
    return found[0] if found else ""


def translate_config(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Wrap a customer mapping onto hub/v1. Face stays slim; qasm stays off the face."""
    from qagent.adapters.hub import NativeHub

    if not isinstance(raw, dict):
        return _fail("config must be a mapping")
    from_kind = detect_from_kind(raw)
    if not from_kind:
        return _fail("读不懂这份文件。请改成 OpenQASM，或带分子 / 哈密顿量 / 图的 JSON。")
    origin = _origin(from_kind)
    qasm = extract_qasm(raw)
    hub = NativeHub()
    if from_kind == FROM_HUB:
        checked = hub.validate({"config": dict(raw)})
        return _pack(
            origin=origin,
            from_kind=from_kind,
            checked=checked,
            config=dict(raw),
            qasm=qasm,
        )
    if qasm and from_kind not in {FROM_COMPANY, FROM_MOLECULE, FROM_PAULI, FROM_MAXCUT}:
        if not _has_molecule(raw) and not _has_pauli(raw):
            return {
                "ok": True,
                "origin": ORIGIN_TRANSLATED,
                "from_kind": from_kind,
                "algorithm_id": "",
                "errors": [],
                "config": None,
                "qasm": qasm,
                "brief": _BRIEFS.get(from_kind, "外部线路包，已转到公司作业"),
            }
    algorithm_id = _choose_id(hub, raw, from_kind)
    native_format = _native_format(hub, algorithm_id, raw)
    wrapped = {
        "api_version": "hub/v1",
        "algorithm_id": algorithm_id,
        "algorithm": _algorithm_body(raw, native_format),
    }
    checked = hub.validate({"config": wrapped})
    return _pack(
        origin=origin,
        from_kind=from_kind,
        checked=checked,
        config=wrapped,
        qasm=qasm,
    )


def _origin(from_kind: str) -> str:
    if from_kind == FROM_HUB:
        return ORIGIN_NATIVE
    if from_kind == FROM_COMPANY:
        return ORIGIN_COMPANY
    return ORIGIN_TRANSLATED


def _pack(
    *,
    origin: str,
    from_kind: str,
    checked: Mapping[str, Any],
    config: dict[str, Any] | None,
    qasm: str,
) -> dict[str, Any]:
    return {
        "ok": bool(checked.get("ok")),
        "origin": origin,
        "from_kind": from_kind,
        "algorithm_id": str(checked.get("algorithm_id") or ""),
        "errors": list(checked.get("errors") or []),
        "config": config,
        "qasm": qasm,
        "brief": _BRIEFS.get(from_kind, "配置"),
    }


def _fail(message: str) -> dict[str, Any]:
    return {
        "ok": False,
        "origin": "",
        "from_kind": "",
        "algorithm_id": "",
        "errors": [message],
        "config": None,
        "qasm": "",
        "brief": "",
    }


def _choose_id(hub: Any, raw: Mapping[str, Any], from_kind: str) -> str:
    existing = str(raw.get("algorithm_id") or "").strip()
    if existing.startswith("org."):
        return existing
    algo = raw.get("algorithm") if isinstance(raw.get("algorithm"), dict) else {}
    nested = str(algo.get("algorithm_id") or "").strip()
    if nested.startswith("org."):
        return nested
    if from_kind == FROM_MAXCUT:
        return str(hub.choose({"hint": "maxcut"}).get("algorithm_id") or "org.algo.qaoa.maxcut")
    if from_kind == FROM_PAULI or (_has_pauli(raw) and not _has_molecule(raw)):
        return str(hub.choose({"has_molecule": False}).get("algorithm_id") or "org.algo.vqe.hea")
    if from_kind in {FROM_MOLECULE, FROM_COMPANY} or _has_molecule(raw):
        return str(hub.choose({"has_molecule": True}).get("algorithm_id") or "org.chem.vqe")
    return str(hub.choose({"hint": from_kind}).get("algorithm_id") or "org.chem.vqe")


def _native_format(hub: Any, algorithm_id: str, raw: Mapping[str, Any]) -> str:
    algo = raw.get("algorithm") if isinstance(raw.get("algorithm"), dict) else {}
    existing = str(algo.get("native_format") or raw.get("native_format") or "")
    if existing:
        return existing
    try:
        card = hub.describe({"id": algorithm_id})
    except (KeyError, ValueError):
        return ""
    return str(card.get("native_format") or "")


def _algorithm_body(raw: Mapping[str, Any], native_format: str) -> dict[str, Any]:
    existing = raw.get("algorithm") if isinstance(raw.get("algorithm"), dict) else {}
    out = {key: value for key, value in existing.items() if key not in _SKIP_COPY}
    if native_format:
        out["native_format"] = native_format
    for key in _COPY_KEYS:
        if key in raw and key not in out and key not in _SKIP_COPY:
            out[key] = raw[key]
    pack_id = str(raw.get("id") or "").strip()
    if pack_id and not pack_id.startswith("org.") and "pack_id" not in out:
        out["pack_id"] = pack_id
    ham = _hamiltonian_view(raw)
    if ham and "hamiltonian" not in out:
        out["hamiltonian"] = ham
    return out


def _hamiltonian_view(raw: Mapping[str, Any]) -> dict[str, Any] | None:
    ham = raw.get("hamiltonian")
    if isinstance(ham, dict):
        return {key: value for key, value in ham.items() if key not in _SKIP_COPY}
    paulis = raw.get("paulis")
    if isinstance(paulis, list):
        return {"terms": paulis}
    terms = raw.get("terms")
    if isinstance(terms, list) and (_has_pauli(raw) or raw.get("ops")):
        return {"terms": terms}
    return None


def _is_company(raw: Mapping[str, Any]) -> bool:
    algo = raw.get("algorithm") if isinstance(raw.get("algorithm"), dict) else {}
    native = str(algo.get("native_format") or raw.get("native_format") or "")
    if native in _COMPANY_FORMATS:
        return True
    if str(raw.get("algorithm_id") or "").startswith("org.") and str(raw.get("api_version") or "") != "hub/v1":
        return True
    scenario = str(raw.get("scenario") or algo.get("scenario") or "")
    if scenario in _QCHEM_SCENARIOS:
        return True
    action = str(raw.get("action") or "").lower()
    if action in _UQC_ACTIONS and (raw.get("molecule") or raw.get("id") or raw.get("basis")):
        return True
    return False


def _is_ibm(raw: Mapping[str, Any], blob: str) -> bool:
    if any(token in blob for token in ("ibm_quantum", "ibm_brisbane", "ibmq_", "runtime_job", "ibm quantum")):
        return True
    backend = str(raw.get("backend") or raw.get("backend_name") or "").lower()
    return backend.startswith("ibm") or backend.startswith("ibmq")


def _is_cirq(raw: Mapping[str, Any], blob: str) -> bool:
    if raw.get("cirq_type") or raw.get("cirq"):
        return True
    return "cirq" in blob


def _is_qiskit(raw: Mapping[str, Any], blob: str) -> bool:
    if raw.get("qiskit") or raw.get("QuantumCircuit"):
        return True
    return any(token in blob for token in ("qiskit", "quantumcircuit", "sparsepauliop"))


def _is_maxcut(raw: Mapping[str, Any], blob: str) -> bool:
    problem = str(raw.get("problem") or raw.get("task") or "").lower().replace("-", "")
    if problem in {"maxcut", "qaoa"}:
        return True
    if raw.get("edges") and ("maxcut" in blob or "qaoa" in blob or raw.get("graph")):
        return True
    return "maxcut" in blob or "max-cut" in blob


def _has_molecule(raw: Mapping[str, Any]) -> bool:
    algo = raw.get("algorithm") if isinstance(raw.get("algorithm"), dict) else {}
    for row in (raw, algo):
        if row.get("molecule") or row.get("geometry") or row.get("atoms") or row.get("xyz"):
            return True
    return False


def _has_pauli(raw: Mapping[str, Any]) -> bool:
    if raw.get("paulis") or raw.get("sparse_pauli") or raw.get("SparsePauliOp"):
        return True
    if raw.get("pauli_terms") or raw.get("hamiltonian"):
        return True
    ham = raw.get("hamiltonian")
    if isinstance(ham, dict) and (ham.get("terms") or ham.get("paulis") or ham.get("ops")):
        return True
    return False


def _blob(raw: Mapping[str, Any]) -> str:
    try:
        import json

        return json.dumps(raw, default=str).lower()
    except (TypeError, ValueError):
        return str(raw).lower()


def _collect_qasm(raw: Any, found: list[str]) -> None:
    if found:
        return
    if isinstance(raw, str):
        text = raw.strip()
        if text.startswith("OPENQASM"):
            found.append(text)
        return
    if isinstance(raw, Mapping):
        for key in ("qasm3", "qasm", "qasm2", "openqasm", "program"):
            value = raw.get(key)
            if isinstance(value, str) and value.strip().startswith("OPENQASM"):
                found.append(value.strip())
                return
        for value in raw.values():
            _collect_qasm(value, found)
            if found:
                return
        return
    if isinstance(raw, list):
        for item in raw[:16]:
            _collect_qasm(item, found)
            if found:
                return
