from __future__ import annotations

import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import parse_qs, unquote, urlparse

from qagent.adapters.contracts import ROOT
from qagent.entrypoints.debug_gate import approved_allowed, bind_allowed
from qagent.models.assignment import AssignmentError, normalize_tenant, sanitize_handles
from qagent.models.customer_voice import redact_customer_text
from qagent.models.handles import HANDLE_CIRCUIT
from qagent.models.eln import drop_twin, short_payload
from qagent.services.assignment import (
    approve,
    cancel,
    create,
    fork,
    get_assignment,
    list_assignments,
    preflight,
    receipt,
    reject,
    run,
    verify_assignment_receipt,
)
from qagent.services.chat import (
    classify,
    list_sessions as chat_sessions,
    reset_chat,
    status as chat_status,
    turn,
)
from qagent.services.workplace import save_workplace, workplace_status
from qagent.services.cards import pes_card, signoff_card
from qagent.services.company import company_payload
from qagent.services.eln import collapse_assignment_events, filter_eln_for_assignments, read_eln
from qagent.services.eval_run import run_evals
from qagent.services.health import science_health
from qagent.services.invoke import invoke
from qagent.adapters.pin import circuit_face, circuit_program, pin_from_qasm
from qagent.services.circuit_job import public_job, start_job
from qagent.services.ingest_store import save_ingest
from qagent.services.translate import translate_config
from qagent.services.uploads import KIND_CIRCUIT, KIND_CONFIG, classify_upload, parse_config_text
from qagent.services.vibe_path import run_vibe_path

_SHELL = ROOT / "apps" / "customer-shell"
_HTML = _SHELL / "index.html"
_ALLOWED_STATIC = {".css", ".js", ".svg", ".woff2", ".png"}
_STATIC_TYPES = {
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
    ".woff2": "font/woff2",
    ".png": "image/png",
}
_TENANT_HEADER = "x-qagent-tenant"
_FACE_ELN_CAP = 20


def _safe_static_path(name: str) -> Path | None:
    raw = str(name or "").replace("\\", "/")
    if not raw:
        return None
    parts = raw.split("/")
    if any(not part or part in {".", ".."} or part.startswith(".") for part in parts):
        return None
    path = _SHELL.joinpath(*parts).resolve()
    try:
        path.relative_to(_SHELL.resolve())
    except ValueError:
        return None
    if not path.is_file() or path.suffix not in _ALLOWED_STATIC:
        return None
    return path


def _caller_tenant(
    headers: Mapping[str, str] | None,
    body: Mapping[str, Any] | None = None,
) -> str:
    raw = {str(key).lower(): str(value) for key, value in (headers or {}).items()}
    header = normalize_tenant(raw.get(_TENANT_HEADER))
    from_body = normalize_tenant((body or {}).get("tenant_id"))
    return header or from_body


def dispatch(
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
    headers: Mapping[str, str] | None = None,
) -> tuple[int, object]:
    body = body or {}
    parsed = urlparse(path)
    path = parsed.path.rstrip("/") or "/"
    query = {key: (values[0] if values else "") for key, values in parse_qs(parsed.query).items()}
    if method == "GET" and path == "/api/health":
        return 200, science_health()
    if method == "GET" and path == "/api/company":
        return 200, company_payload()
    if method == "GET" and path == "/api/workplace":
        return 200, workplace_status()
    if method == "PUT" and path == "/api/workplace":
        if not approved_allowed(headers, True):
            return 403, {"error": "approval requires QAGENT_SHELL_TOKEN"}
        secrets_patch = {
            key: str(body[key])
            for key in ("llm_api_key", "hpc_secret", "quantum_secret")
            if body.get(key)
        }
        row = save_workplace(body, secrets_patch)
        return 200, {"workplace": row.to_public(), "ready": row.ready()}
    if method == "POST" and path == "/api/agent/reset":
        if not approved_allowed(headers, True):
            return 403, {"error": "approval requires QAGENT_SHELL_TOKEN"}
        reset_chat(tenant_id=_caller_tenant(headers))
        return 200, {"ok": True}
    if method == "GET" and path == "/api/cards":
        return 200, {"pes": pes_card(), "signoff": signoff_card()}
    if method == "GET" and path == "/api/eln":
        return _eln_http(query, headers)
    if method == "GET" and path == "/api/assignments":
        assignment_status = query.get("status") or None
        tenant_id = _caller_tenant(headers)
        return 200, {
            "assignments": [
                row.face_payload() for row in list_assignments(assignment_status, tenant_id=tenant_id)
            ]
        }
    if method == "POST" and path == "/api/receipts/verify":
        return 200, verify_assignment_receipt(body)
    if method == "POST" and path == "/api/assignments":
        return 200, create(
            room=str(body.get("room") or "lab"),
            brief=str(body.get("brief") or ""),
            recipe=str(body.get("recipe") or "a2_chem_pes"),
            shots=int(body.get("shots") or 1000),
            tenant_id=_caller_tenant(headers, body),
        ).face_payload()
    assignment = _assignment_action(method, path, body, headers)
    if assignment is not None:
        return assignment
    if method == "GET" and path == "/api/chat/status":
        return 200, _chat_http_face(chat_status(tenant_id=_caller_tenant(headers)))
    if method == "GET" and path == "/api/chat/sessions":
        rows = chat_sessions(tenant_id=_caller_tenant(headers)).get("sessions") or []
        for row in rows:
            if isinstance(row, dict):
                row["title"] = redact_customer_text(str(row.get("title") or ""))
        return 200, {"sessions": rows}
    if method == "POST" and path == "/api/chat":
        return _chat_http(body, headers)
    upload = _upload_http(method, path, body, headers)
    if upload is not None:
        return upload
    circuit = _circuit_http(method, path, body)
    if circuit is not None:
        return circuit
    job = _circuit_job_http(method, path, body, headers)
    if job is not None:
        return job
    if method == "POST" and path == "/api/invoke":
        return _invoke_http(body, headers)
    if method == "POST" and path == "/api/vibe":
        return _vibe_http(body, headers)
    if method == "POST" and path == "/api/eval":
        return _eval_http(body, headers)
    gov = _gov_http(method, path, body, headers, query)
    if gov is not None:
        return gov
    return 404, {"error": "not found"}


def _assignment_action(
    method: str,
    path: str,
    body: dict[str, Any],
    headers: Mapping[str, str] | None,
) -> tuple[int, object] | None:
    parts = [part for part in path.split("/") if part]
    if len(parts) < 3 or parts[0] != "api" or parts[1] != "assignments":
        return None
    assignment_id = parts[2]
    action = parts[3] if len(parts) > 3 else ""
    tenant_id = _caller_tenant(headers, body)
    try:
        if method == "GET" and not action:
            return 200, get_assignment(assignment_id, tenant_id=tenant_id).face_payload()
        if method == "GET" and action == "receipt":
            return 200, receipt(assignment_id, tenant_id=tenant_id)
        if method == "GET" and action == "preflight":
            return 200, preflight(assignment_id, tenant_id=tenant_id)
        if method == "POST" and action == "run":
            approved = bool(body.get("approved"))
            if not approved_allowed(headers, approved):
                return 403, {"error": "approval requires QAGENT_SHELL_TOKEN"}
            return 200, run(
                assignment_id,
                approved=approved,
                attended=bool(body.get("attended")),
                tenant_id=tenant_id,
            ).face_payload()
        if method == "POST" and action == "approve":
            if not approved_allowed(headers, True):
                return 403, {"error": "approval requires QAGENT_SHELL_TOKEN"}
            return 200, approve(assignment_id, tenant_id=tenant_id).face_payload()
        if method == "POST" and action == "reject":
            return 200, reject(assignment_id, tenant_id=tenant_id).face_payload()
        if method == "POST" and action == "cancel":
            return 200, cancel(assignment_id, tenant_id=tenant_id).face_payload()
        if method == "POST" and action == "fork":
            room = str(body["room"]) if body.get("room") else None
            return 200, fork(assignment_id, room=room, tenant_id=tenant_id).face_payload()
    except AssignmentError as exc:
        if str(exc).startswith("unknown assignment_id"):
            return 404, {"error": str(exc)}
        return 400, {"error": str(exc)}
    return 404, {"error": "not found"}


def _eln_http(
    query: Mapping[str, str],
    headers: Mapping[str, str] | None = None,
) -> tuple[int, object]:
    assignment_id = query.get("assignment_id") or None
    rows = read_eln(assignment_id=assignment_id)
    tenant_id = _caller_tenant(headers)
    if tenant_id:
        visible = {row.assignment_id for row in list_assignments(tenant_id=tenant_id)}
        rows = filter_eln_for_assignments(rows, visible)
    if not assignment_id:
        rows = collapse_assignment_events(rows)
    if len(rows) > _FACE_ELN_CAP:
        rows = rows[-_FACE_ELN_CAP:]
    return 200, {"events": [short_payload(drop_twin(row)) for row in rows]}


def _chat_http(body: dict[str, Any], headers: Mapping[str, str] | None) -> tuple[int, object]:
    message = str(body.get("message") or "")
    if classify(message) == "approve" and not approved_allowed(headers, True):
        return 403, {"error": "approval requires QAGENT_SHELL_TOKEN"}
    attached = str(body.get("circuit_id") or "").strip()
    if attached and not attached.startswith("circ_"):
        attached = ""
    algorithm_id = str(body.get("algorithm_id") or "").strip()
    if algorithm_id and not algorithm_id.startswith("org."):
        algorithm_id = ""
    return 200, _chat_http_face(
        turn(
            message=message,
            tenant_id=_caller_tenant(headers),
            circuit_id=attached,
            algorithm_id=algorithm_id,
        )
    )


def _eval_http(body: dict[str, Any], headers: Mapping[str, str] | None) -> tuple[int, object]:
    if not approved_allowed(headers, True):
        return 403, {"error": "approval requires QAGENT_SHELL_TOKEN"}
    from qagent.services.eval_run import DEFAULT_EVAL_IDS

    ids = body.get("ids") or list(DEFAULT_EVAL_IDS)
    rows = [{"id": row.id, "ok": row.ok} for row in run_evals(*ids)]
    return 200, {"passed": all(item["ok"] for item in rows), "results": rows}


def _gov_http(
    method: str,
    path: str,
    body: dict[str, Any],
    headers: Mapping[str, str] | None,
    query: Mapping[str, str] | None = None,
) -> tuple[int, object] | None:
    from qagent.services.doctor import probe
    from qagent.services.gov_face import gov_face
    from qagent.services.handoff import HandoffError, create_handoff, get_handoff, list_handoffs
    from qagent.services.notify import asks_face
    from qagent.services.replay import replay
    from qagent.services.savepoint import enter_safe_mode, restore, snapshot
    from qagent.services.usage import usage_face

    if method == "GET" and path == "/api/doctor":
        return 200, probe(scan_store=False)
    if method == "GET" and path == "/api/errors":
        from qagent.services.errors import lookup_error

        q = query or {}
        return 200, lookup_error(
            slot=str(q.get("slot") or ""),
            code=str(q.get("code") or ""),
            tool=str(q.get("tool") or ""),
            message=str(q.get("message") or ""),
            status=str(q.get("status") or ""),
        )
    if method == "GET" and path == "/api/preset":
        from qagent.services.preset_face import preset_face

        return 200, preset_face()
    if method == "POST" and path == "/api/preset":
        if not approved_allowed(headers, True):
            return 403, {"error": "approval requires QAGENT_SHELL_TOKEN"}
        from qagent.services.preset_face import switch_preset

        try:
            return 200, switch_preset(str(body.get("preset") or ""))
        except ValueError as exc:
            return 400, {"error": str(exc)}
    if method == "GET" and path == "/api/gov/face":
        return 200, gov_face(tenant_id=_caller_tenant(headers))
    if method == "GET" and path == "/api/asks":
        return 200, asks_face()
    if method == "GET" and path == "/api/usage":
        return 200, usage_face()
    if method == "GET" and path == "/api/replay":
        assignment_id = str((query or {}).get("assignment_id") or "")
        try:
            return 200, replay(assignment_id, tenant_id=_caller_tenant(headers))
        except AssignmentError as exc:
            return 404, {"error": str(exc)}
    if method == "GET" and path == "/api/handoff":
        return 200, {"handoffs": list_handoffs()}
    if method == "GET" and path.startswith("/api/handoff/"):
        handoff_id = path.rsplit("/", 1)[-1]
        try:
            return 200, get_handoff(handoff_id)
        except HandoffError as exc:
            return 404, {"error": str(exc)}
    if method == "POST" and path == "/api/handoff":
        if not approved_allowed(headers, True):
            return 403, {"error": "approval requires QAGENT_SHELL_TOKEN"}
        try:
            row = create_handoff(
                source_preset=str(body.get("source_preset") or "lab"),
                target_preset=str(body.get("target_preset") or "lab"),
                handles=body.get("handles") if isinstance(body.get("handles"), dict) else {},
                intent=str(body.get("intent") or ""),
                unresolved=list(body.get("unresolved") or []),
                source_session=str(body.get("source_session") or ""),
            )
        except HandoffError as exc:
            return 400, {"error": str(exc)}
        return 200, row.to_public()
    if method == "POST" and path == "/api/savepoint":
        if not approved_allowed(headers, True):
            return 403, {"error": "approval requires QAGENT_SHELL_TOKEN"}
        if body.get("restore"):
            return 200, restore(str(body.get("savepoint_id") or ""))
        return 200, snapshot(str(body.get("note") or ""))
    if method == "POST" and path == "/api/safe-mode":
        if not approved_allowed(headers, True):
            return 403, {"error": "approval requires QAGENT_SHELL_TOKEN"}
        return 200, enter_safe_mode()
    return None


def _chat_http_face(payload: Mapping[str, Any]) -> dict[str, Any]:
    """HTTP chat face. No session_id / used_tools. 3080 reads reply / awaiting / cards / ready / open_settings / running / circuit."""
    face = dict(payload)
    face.pop("session_id", None)
    face.pop("used_tools", None)
    face.pop("algorithm_id", None)
    if isinstance(face.get("reply"), str):
        face["reply"] = redact_customer_text(face["reply"])
    circuit = face.get("circuit")
    if isinstance(circuit, dict) and circuit.get(HANDLE_CIRCUIT):
        face["circuit"] = _circuit_http_meta(circuit)
    return face


def _circuit_http_meta(circuit: Mapping[str, Any]) -> dict[str, Any]:
    """Size the drawn pin for the face. No qasm3 / body / third handle."""
    circuit_id = str(circuit.get(HANDLE_CIRCUIT) or "")
    drawn = circuit_face(circuit_id) or {}
    out: dict[str, Any] = {HANDLE_CIRCUIT: circuit_id}
    n_qubits = circuit.get("n_qubits") or drawn.get("n_qubits")
    n_instructions = circuit.get("n_instructions") or drawn.get("n_instructions")
    if not n_instructions and drawn.get("gates"):
        n_instructions = len(drawn["gates"])
    if n_qubits:
        out["n_qubits"] = int(n_qubits)
    if n_instructions:
        out["n_instructions"] = int(n_instructions)
    ansatz = circuit.get("ansatz") or drawn.get("ansatz")
    if ansatz:
        out["ansatz"] = str(ansatz)
    molecule = circuit.get("molecule") or drawn.get("molecule")
    if molecule:
        out["molecule"] = str(molecule)
    return out


def _circuit_http(method: str, path: str, body: dict[str, Any] | None = None) -> tuple[int, object] | None:
    parts = [part for part in path.split("/") if part]
    if not parts or parts[0] != "api" or parts[1] != "circuits":
        return None
    if method == "POST" and len(parts) == 2:
        return _circuit_upload(body or {})
    if method != "GET" or len(parts) < 3:
        return None
    circuit_id = parts[2]
    if len(parts) == 3:
        row = circuit_face(circuit_id)
        if not row:
            return 404, {"error": "circuit not pinned"}
        return 200, row
    if len(parts) == 4 and parts[3] == "program":
        row = circuit_program(circuit_id)
        if not row:
            return 404, {"error": "circuit not pinned"}
        return 200, row
    return None


def _upload_http(
    method: str,
    path: str,
    body: dict[str, Any],
    headers: Mapping[str, str] | None,
) -> tuple[int, object] | None:
    if method != "POST" or path != "/api/uploads":
        return None
    filename = str(body.get("filename") or "")
    text = str(body.get("text") or body.get("qasm3") or body.get("qasm") or "")
    kind = classify_upload(filename, text)
    if kind == KIND_CIRCUIT:
        try:
            pinned = pin_from_qasm(text)
        except ValueError as exc:
            return 400, {"error": str(exc), "kind": KIND_CIRCUIT}
        circuit_id = str(pinned.get(HANDLE_CIRCUIT) or "")
        face = circuit_face(circuit_id) or {HANDLE_CIRCUIT: circuit_id, "n_qubits": pinned.get("n_qubits")}
        try:
            row = start_job(circuit_id=circuit_id, tenant_id=_caller_tenant(headers, body))
            job = public_job(row)
        except (ValueError, AssignmentError) as exc:
            return 200, {"kind": KIND_CIRCUIT, "circuit": face, "error": str(exc)}
        return 200, {"kind": KIND_CIRCUIT, "circuit": face, "job": job}
    if kind == KIND_CONFIG:
        try:
            config = parse_config_text(text)
        except (ValueError, json.JSONDecodeError) as exc:
            return 400, {"error": str(exc), "kind": KIND_CONFIG}
        tenant_id = _caller_tenant(headers, body)
        face = translate_config(config)
        circuit_meta: dict[str, Any] | None = None
        job: dict[str, Any] | None = None
        qasm = str(face.get("qasm") or "").strip()
        if qasm:
            try:
                pinned = pin_from_qasm(qasm)
            except ValueError as exc:
                return 400, {"error": str(exc), "kind": KIND_CONFIG}
            circuit_id = str(pinned.get(HANDLE_CIRCUIT) or "")
            circuit_meta = circuit_face(circuit_id) or {
                HANDLE_CIRCUIT: circuit_id,
                "n_qubits": pinned.get("n_qubits"),
            }
            try:
                job = public_job(start_job(circuit_id=circuit_id, tenant_id=tenant_id))
            except (ValueError, AssignmentError) as exc:
                job = {"error": str(exc)}
        if face.get("ok") and (face.get("algorithm_id") or circuit_meta):
            save_ingest(
                tenant_id,
                {
                    "algorithm_id": face.get("algorithm_id") or "",
                    "origin": face.get("origin") or "",
                    "from_kind": face.get("from_kind") or "",
                    "brief": face.get("brief") or "",
                    "circuit_id": (circuit_meta or {}).get(HANDLE_CIRCUIT) or "",
                    "config": face.get("config") if isinstance(face.get("config"), dict) else {},
                },
            )
        out: dict[str, Any] = {
            "kind": KIND_CONFIG,
            "ok": bool(face.get("ok")),
            "origin": str(face.get("origin") or ""),
            "from_kind": str(face.get("from_kind") or ""),
            "errors": list(face.get("errors") or []),
        }
        if face.get("algorithm_id"):
            out["algorithm_id"] = face["algorithm_id"]
        if circuit_meta:
            out["circuit"] = circuit_meta
        if job:
            out["job"] = job
        return 200, out
    name = filename.lower()
    if name.endswith((".py", ".ipynb")):
        return 400, {"error": "请导出 OpenQASM 或 JSON，不要上传可执行脚本。"}
    if name.endswith(".qpy"):
        return 400, {"error": "请导出 OpenQASM 或 JSON，不要上传二进制线路包。"}
    return 400, {"error": "发 OpenQASM，或一份能读懂的 YAML/JSON（公司流程或外部算法包均可）。"}


def _circuit_job_http(
    method: str,
    path: str,
    body: dict[str, Any],
    headers: Mapping[str, str] | None,
) -> tuple[int, object] | None:
    parts = [part for part in path.split("/") if part]
    if len(parts) < 2 or parts[0] != "api" or parts[1] != "circuit-jobs":
        return None
    tenant_id = _caller_tenant(headers, body)
    if method == "POST" and len(parts) == 2:
        circuit_id = str(body.get("circuit_id") or "").strip()
        if not circuit_id:
            return 400, {"error": "circuit_id is required"}
        try:
            row = start_job(
                circuit_id=circuit_id,
                shots=int(body.get("shots") or 1000),
                backend=str(body.get("backend") or "twin"),
                tenant_id=tenant_id,
            )
        except (ValueError, AssignmentError) as exc:
            return 400, {"error": str(exc)}
        return 200, public_job(row)
    if method == "GET" and len(parts) == 3:
        try:
            return 200, public_job(get_assignment(parts[2], tenant_id=tenant_id))
        except AssignmentError as exc:
            return 404, {"error": str(exc)}
    return None


def _circuit_upload(body: Mapping[str, Any]) -> tuple[int, object]:
    text = str(body.get("qasm3") or body.get("qasm2") or body.get("qasm") or "")
    try:
        pinned = pin_from_qasm(text)
    except ValueError as exc:
        return 400, {"error": str(exc)}
    circuit_id = str(pinned.get(HANDLE_CIRCUIT) or "")
    face = circuit_face(circuit_id) or {
        HANDLE_CIRCUIT: circuit_id,
        "n_qubits": pinned.get("n_qubits"),
    }
    return 200, face


def _invoke_http(body: dict[str, Any], headers: Mapping[str, str] | None) -> tuple[int, object]:
    approved = bool(body.get("approved"))
    if not approved_allowed(headers, approved):
        return 403, {"error": "approval requires QAGENT_SHELL_TOKEN"}
    result = invoke(
        str(body.get("tool") or ""),
        str(body.get("preset") or "lab"),
        body.get("args") if isinstance(body.get("args"), dict) else {},
        approved=approved,
    )
    return 200, _invoke_http_face(result)


def _vibe_http(body: dict[str, Any], headers: Mapping[str, str] | None) -> tuple[int, object]:
    approved = bool(body.get("approved"))
    if not approved_allowed(headers, approved):
        return 403, {"error": "approval requires QAGENT_SHELL_TOKEN"}
    return 200, _vibe_http_face(
        run_vibe_path(
            str(body.get("preset") or "lab"),
            recipe=str(body.get("recipe") or "a2_chem_pes"),
            shots=int(body.get("shots") or 1000),
            approved=approved,
        )
    )


def _invoke_http_face(result: Any) -> dict[str, Any]:
    """HTTP invoke face. No payload / args / third-handle field."""
    face: dict[str, Any] = {
        "tool": result.tool,
        "decision": result.decision,
        "status": result.status,
    }
    if result.slot_id:
        face["slot_id"] = result.slot_id
    return face


def _vibe_http_face(path: Mapping[str, Any]) -> dict[str, Any]:
    """HTTP vibe face. No steps / circuit body / extra handle keys."""
    face: dict[str, Any] = {
        "status": path.get("status"),
        "tool": path.get("tool"),
        "summary": path.get("summary"),
    }
    handles = sanitize_handles(path.get("handles") if isinstance(path.get("handles"), Mapping) else None)
    if handles:
        face["handles"] = handles
    return face


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return

    def _json(self, code: int, payload: object) -> None:
        raw = json.dumps(payload, default=str).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _bytes(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _html(self) -> None:
        body = _HTML.read_bytes() if _HTML.is_file() else b"<p>missing shell</p>"
        self._bytes(200, body, "text/html; charset=utf-8")

    def _static(self, name: str) -> None:
        path = _safe_static_path(name)
        if path is None:
            self._json(404, {"error": "not found"})
            return
        ctype = _STATIC_TYPES.get(path.suffix) or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self._bytes(200, path.read_bytes(), ctype)

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path in {"/", "/index.html"}:
            self._html()
            return
        if path.startswith("/static/"):
            self._static(unquote(path.removeprefix("/static/")))
            return
        try:
            code, payload = dispatch("GET", self.path, {}, self.headers)
        except Exception:
            self._json(500, {"error": "这一轮没办完。再发一句即可。"})
            return
        self._json(code, payload)

    def _read_json_body(self) -> dict[str, Any] | None:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            self._json(400, {"error": "invalid json"})
            return None
        if not isinstance(body, dict):
            self._json(400, {"error": "invalid json"})
            return None
        return body

    def do_POST(self) -> None:  # noqa: N802
        body = self._read_json_body()
        if body is None:
            return
        try:
            code, payload = dispatch("POST", urlparse(self.path).path, body, self.headers)
        except Exception:
            self._json(500, {"error": "这一轮没办完。再发一句即可。"})
            return
        self._json(code, payload)

    def do_PUT(self) -> None:  # noqa: N802
        body = self._read_json_body()
        if body is None:
            return
        try:
            code, payload = dispatch("PUT", urlparse(self.path).path, body, self.headers)
        except Exception:
            self._json(500, {"error": "这一轮没办完。再发一句即可。"})
            return
        self._json(code, payload)


def serve(host: str = "127.0.0.1", port: int = 3080) -> None:
    if not bind_allowed(host):
        raise RuntimeError("qagent-shell refuses non-loopback bind without QAGENT_SHELL_TOKEN")
    from qagent.services.workplace import apply_env

    apply_env()
    httpd = ThreadingHTTPServer((host, port), _Handler)
    print(f"qagent-shell http://{host}:{port}")
    httpd.serve_forever()
