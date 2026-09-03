from __future__ import annotations

from typing import Any

from qagent.adapters.dsh_session import DshSessionClient, DshSessionError
from qagent.adapters.dsh_session_store import (
    archive_session_id,
    clear_session_id,
    journal_session,
    list_journal,
    load_session_id,
    save_session_id,
)
from qagent.models.customer_voice import CUSTOMER_VOICE_HINT  # C-01x lock; I-02 keeps prompt raw
from qagent.services.gate import classify
from qagent.services.ingest_store import clear_ingest, load_ingest
from qagent.services.workplace import apply_env, load_workplace

__all__ = ["classify", "list_sessions", "reset_chat", "status", "turn"]

_NO_PENDING = "现在没有待批准的上机。不会新开 session，也不会把这句话当成新任务发给运行时，更不会伪造上机句柄。"
_PENDING_FACE_KEYS = ("approval_id", "rpc_id", "tool", "reason")


def turn(
    *,
    message: str,
    client: DshSessionClient | None = None,
    tenant_id: str = "",
    circuit_id: str = "",
    algorithm_id: str = "",
) -> dict[str, Any]:
    """Product chat. Talks to dsh session.* . Never calls services.agent._loop."""
    apply_env()
    action = classify(message)
    if action == "empty":
        return _out("说你要做什么。模型会自己选公司工具，没有写死的配方流程。", None, tenant_id=tenant_id)
    if not load_workplace().ready():
        return _out(
            "先在设置里接上你们的本地大模型（地址和模型名）。接好之前我不会假装已经在 vibe。",
            None,
            tenant_id=tenant_id,
        )
    text = (message or "").strip()
    ingested = load_ingest(tenant_id)
    attached = str(circuit_id or "").strip()
    if not attached.startswith("circ_"):
        attached = str(ingested.get("circuit_id") or "").strip()
    if attached.startswith("circ_") and action not in {"approve", "reject"}:
        text = (
            f"{text}\n\n（客户已附上线路 {attached}。"
            "后续工具用这个 circuit_id，不要把句柄念给客户听。）"
        )
    chosen = str(algorithm_id or "").strip()
    if not chosen.startswith("org."):
        chosen = str(ingested.get("algorithm_id") or "").strip()
    if chosen.startswith("org.") and action not in {"approve", "reject"}:
        extra = _ingest_hint(ingested)
        text = (
            f"{text}\n\n（客户已附上配置，algorithm_id={chosen}。"
            f"{extra}"
            "用 qagent_hub_validate 核对后走对应工具，不要把内部 id 念给客户听。）"
        )
    try:
        worker = client or DshSessionClient()
        if action in {"approve", "reject"}:
            return _decide_existing(worker, action, tenant_id=tenant_id)
        existing = load_session_id(tenant_id=tenant_id)
        session_id = _ensure_session(worker, tenant_id=tenant_id)
        try:
            journal_session(session_id, tenant_id=tenant_id, title=_session_title(message))
        except OSError:
            pass
        before = (
            worker.snapshot(session_id)
            if existing
            else {"reply": "", "event_count": 0, "assistant_index": 0, "turn_index": 0}
        )
        worker.prompt(session_id, text)
        snap = worker.wait_for_turn(session_id, since=before)
        return _from_snap(snap, action=action, tenant_id=tenant_id)
    except DshSessionError as exc:
        return _out(str(exc), None, tenant_id=tenant_id)
    except Exception:
        return _out("这一轮没办完。再发一句即可。不会改用自研循环。", None, tenant_id=tenant_id)


def _decide_existing(worker: DshSessionClient, action: str, *, tenant_id: str = "") -> dict[str, Any]:
    """Approve/reject the live dsh ask on the stored session. Never session.create."""
    session_id = load_session_id(tenant_id=tenant_id)
    if not session_id:
        return _out(_NO_PENDING, None, tenant_id=tenant_id)
    snap = worker.snapshot(session_id)
    pending = snap.get("pending_approval")
    if not isinstance(pending, dict):
        return _out(_NO_PENDING, None, session_id=session_id, tenant_id=tenant_id)
    approval_id = str(pending.get("approval_id") or "").strip()
    rpc_id = str(pending.get("rpc_id") or "").strip()
    if not approval_id:
        return _out(_NO_PENDING, None, session_id=session_id, tenant_id=tenant_id)
    if not rpc_id:
        return _out(
            "看见待批准的上机，但没有 mux rpcId，没法对同一条 session 做 allowed-once。不会伪造上机句柄。",
            "approve",
            session_id=session_id,
            pending_approval=pending,
            tenant_id=tenant_id,
        )
    before = worker.snapshot(session_id)
    if action == "approve":
        worker.approve_once(session_id, approval_id, rpc_id)
        outcome = "allowed-once"
    else:
        worker.reject_once(session_id, approval_id, rpc_id)
        outcome = "rejected"
    after = worker.wait_for_turn(session_id, since=before)
    reply = str(after.get("reply") or "").strip()
    stamp = f"同一条 session，outcome 是 {outcome}。"
    if stamp not in reply:
        reply = f"{stamp} {reply}".strip() if reply else stamp
    used = list(after.get("used_tools") or [])
    if "dsh.respond" not in used:
        used.append("dsh.respond")
    awaiting = after.get("awaiting")
    return _out(
        reply,
        awaiting if awaiting == "approve" else None,
        used,
        session_id=session_id,
        cards=list(after.get("cards") or []),
        running=bool(after.get("running")),
        pending_approval=after.get("pending_approval"),
        circuit=after.get("circuit") if isinstance(after.get("circuit"), dict) else None,
        tenant_id=tenant_id,
    )


def status(*, client: DshSessionClient | None = None, tenant_id: str = "") -> dict[str, Any]:
    """Short-poll the same dsh session. Used by 3080 bubbles."""
    apply_env()
    session_id = load_session_id(tenant_id=tenant_id)
    if not session_id:
        return _out("还没有运行时会话。", None, tenant_id=tenant_id)
    if not load_workplace().ready():
        return _out(
            "先在设置里接上你们的本地大模型（地址和模型名）。接好之前我不会假装已经在 vibe。",
            None,
            tenant_id=tenant_id,
        )
    try:
        worker = client or DshSessionClient()
        return _from_snap(worker.snapshot(session_id), action="run", tenant_id=tenant_id)
    except DshSessionError as exc:
        return _out(str(exc), None, tenant_id=tenant_id)
    except Exception:
        return _out("这一轮没办完。再发一句即可。不会改用自研循环。", None, tenant_id=tenant_id)


def reset_chat(tenant_id: str = "") -> None:
    try:
        archive_session_id(load_session_id(tenant_id=tenant_id) or "", tenant_id=tenant_id)
    except OSError:
        pass
    clear_session_id(tenant_id=tenant_id)
    try:
        clear_ingest(tenant_id)
    except OSError:
        pass


def list_sessions(tenant_id: str = "") -> dict[str, Any]:
    """Face list of this tenant's sessions. Record only; no switch, no replay."""
    current = str(load_session_id(tenant_id=tenant_id) or "")
    rows = []
    for entry in list_journal(tenant_id=tenant_id):
        rows.append(
            {
                "title": str(entry.get("title") or "").strip() or "还没留话的对话",
                "updated_at": str(entry.get("updated_at") or entry.get("created_at") or ""),
                "current": bool(entry.get("session_id") == current),
                "archived": bool(entry.get("archived")),
            }
        )
    rows.sort(key=lambda row: str(row.get("updated_at") or ""), reverse=True)
    return {"sessions": rows[:8]}


def _ingest_hint(ingested: dict[str, Any]) -> str:
    origin = str(ingested.get("origin") or "")
    if origin == "translated":
        lead = "这份是外部文件，已转到公司流程配置。"
    elif origin == "company":
        lead = "这份是公司算法包输入，已套上公司流程信封。"
    else:
        lead = ""
    bits: list[str] = []
    brief = str(ingested.get("brief") or "").strip()
    if brief:
        bits.append(brief)
    config = ingested.get("config") if isinstance(ingested.get("config"), dict) else {}
    algo = config.get("algorithm") if isinstance(config.get("algorithm"), dict) else {}
    molecule = str(algo.get("molecule") or config.get("molecule") or "").strip()
    basis = str(algo.get("basis") or config.get("basis") or "").strip()
    if molecule:
        bits.append(f"分子 {molecule}")
    if basis:
        bits.append(f"基组 {basis}")
    detail = "，".join(bits)
    if lead and detail:
        return f"{lead}{detail}。"
    if lead:
        return lead
    if detail:
        return f"{detail}。"
    return ""


def _session_title(text: str) -> str:
    raw = str(text or "").strip()
    if not raw:
        return ""
    return raw.splitlines()[0].strip()[:24]


def _ensure_session(client: DshSessionClient, tenant_id: str = "") -> str:
    existing = load_session_id(tenant_id=tenant_id)
    if existing:
        return existing
    session_id = client.create()
    save_session_id(session_id, tenant_id=tenant_id)
    return session_id


def _from_snap(snap: dict[str, Any], *, action: str, tenant_id: str = "") -> dict[str, Any]:
    reply = str(snap.get("reply") or "").strip()
    awaiting = snap.get("awaiting")
    running = bool(snap.get("running"))
    if not reply:
        if awaiting == "approve":
            reply = "上机需要你批准。回「批准」才继续同一条 session，不会重开黄金路径。"
        elif running:
            reply = "还在办。结果出来后会出现在这边。"
        else:
            reply = "已经交给运行时。结果出来后会出现在这边。"
    if action == "approve" and not awaiting:
        awaiting = None
    return _out(
        reply,
        awaiting if awaiting == "approve" else None,
        list(snap.get("used_tools") or ["dsh.session.prompt"]),
        session_id=str(snap.get("session_id") or load_session_id(tenant_id=tenant_id) or ""),
        cards=list(snap.get("cards") or []),
        running=running,
        pending_approval=snap.get("pending_approval"),
        circuit=snap.get("circuit") if isinstance(snap.get("circuit"), dict) else None,
        tenant_id=tenant_id,
    )


def _pending_face(pending: object) -> dict[str, str] | None:
    """Copy snapshot fields the face may show. Never invent ids. Never a fourth handle."""
    if not isinstance(pending, dict):
        return None
    slim: dict[str, str] = {}
    for key in _PENDING_FACE_KEYS:
        raw = pending.get(key)
        if raw is None:
            continue
        value = str(raw).strip()
        if value:
            slim[key] = value
    return slim or None


def _out(
    reply: str,
    awaiting: str | None,
    used: list[str] | None = None,
    *,
    session_id: str = "",
    cards: list[dict[str, str]] | None = None,
    running: bool = False,
    pending_approval: object = None,
    circuit: object = None,
    tenant_id: str = "",
) -> dict[str, Any]:
    ready = load_workplace().ready()
    payload: dict[str, Any] = {
        "reply": reply,
        "awaiting": awaiting,
        "used_tools": list(used or []),
        "ready": ready,
        "open_settings": not ready,
        "via": "dsh-session",
        "session_id": session_id or load_session_id(tenant_id=tenant_id) or "",
        "cards": list(cards or []),
        "running": running,
    }
    slim = _pending_face(pending_approval)
    if slim:
        payload["pending_approval"] = slim
    if isinstance(circuit, dict) and circuit.get("circuit_id"):
        face = {"circuit_id": str(circuit["circuit_id"])}
        if circuit.get("n_qubits"):
            face["n_qubits"] = int(circuit["n_qubits"])
        if circuit.get("n_instructions"):
            face["n_instructions"] = int(circuit["n_instructions"])
        if circuit.get("ansatz"):
            face["ansatz"] = str(circuit["ansatz"])
        payload["circuit"] = face
    return payload
