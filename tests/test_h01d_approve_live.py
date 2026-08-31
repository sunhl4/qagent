"""H-01d-approve-live: honest mux approve evidence. No minted rpcId. No invented accepted:true."""

from __future__ import annotations

import json
import os
import traceback
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NOTE = ROOT / "docs" / "execution" / "H-01d_approve_live.md"
HARMLESS = "只回复一个汉字：好。不要调用任何工具，不要改文件。"
TWIN_TOOL = "ionstack_twin_run"
PROBE_CALLED = False


class Skip(Exception):
    """Honest skip: live dsh missing or create refused. Exit 0."""


def _live_mux_forced() -> bool:
    return (os.environ.get("QAGENT_LIVE_MUX") or "").strip() == "1"


def _note_text() -> str:
    assert NOTE.exists(), f"missing {NOTE}"
    return NOTE.read_text(encoding="utf-8")


def _get(url: str, *, headers: dict[str, str] | None = None, timeout: float = 2.0) -> tuple[int, str, dict[str, str]]:
    request = urllib.request.Request(url, headers=headers or {}, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read(4096).decode("utf-8", errors="replace")
            return int(response.status), body, {k.lower(): v for k, v in response.headers.items()}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return int(exc.code), body, {k.lower(): v for k, v in exc.headers.items()}


def _reachable(base: str) -> bool:
    try:
        _get(base.rstrip("/") + "/", timeout=2.0)
        return True
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def _post_respond(
    base: str,
    *,
    rpc_id: str,
    session_id: str,
    approval_id: str,
    outcome: str,
) -> tuple[int, dict]:
    """POST /api/respond echoing mux rpcId. Never mints rpcId."""
    echoed = str(rpc_id or "").strip()
    if not echoed:
        raise Skip("refuse minted rpcId: empty rpc_id")
    body = {
        "type": "client-response",
        "rpcId": echoed,
        "result": {
            "ok": True,
            "value": {
                "sessionId": session_id,
                "approvalId": approval_id,
                "outcome": outcome,
            },
        },
    }
    request = urllib.request.Request(
        base.rstrip("/") + "/api/respond",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=12.0) as response:
            raw = response.read().decode("utf-8", errors="replace")
            status = int(response.status)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        status = int(exc.code)
    try:
        parsed = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        parsed = {"raw": raw[:300]}
    if not isinstance(parsed, dict):
        parsed = {"raw": raw[:300]}
    return status, parsed


def probe_live_approve() -> dict[str, object]:
    """Talk to already-running dsh. Call only when QAGENT_LIVE_MUX=1."""
    global PROBE_CALLED
    PROBE_CALLED = True

    from qagent.adapters.dsh_session import DshSessionClient, DshSessionError, dsh_base_url

    base = dsh_base_url()
    if not _reachable(base):
        raise Skip("3081 down")

    client = DshSessionClient(base_url=base, timeout=12.0)
    try:
        session_id = client.create(agent_preset="qagent")
    except DshSessionError as exc:
        raise Skip(f"session.create failed: {exc.code}: {exc}") from exc

    if not session_id:
        raise Skip("session.create returned empty sessionId")
    print(f"create=ok sessionId={session_id}")
    assert "twin_id" not in session_id

    mux_status, mux_body, mux_headers = _get(
        base.rstrip("/") + "/api/events.mux",
        headers={"Accept": "text/event-stream"},
        timeout=1.2,
    )
    mux_upgrade = mux_headers.get("upgrade") or ""
    print(f"mux_get={mux_status} upgrade={mux_upgrade!r} body={mux_body[:80]!r}")

    try:
        prompted = client.prompt(session_id, HARMLESS)
        print(f"session.prompt={json.dumps(prompted, ensure_ascii=False)[:200]}")
        snap = client.wait_for_turn(session_id, timeout=20.0)
        print(
            "snap",
            "running=", snap.get("running"),
            "awaiting=", snap.get("awaiting"),
            "pending=", snap.get("pending_approval"),
            "reply=", repr(str(snap.get("reply") or "")[:80]),
        )
    except DshSessionError as exc:
        print(f"session.prompt failed: {exc.code}: {exc}")

    peeked = client.peek_mux_approval(session_id)
    print(f"peek_mux={peeked}")

    evidence: dict[str, object] = {
        "create_ok": True,
        "session_id": session_id,
        "mux_get": mux_status,
        "mux_upgrade": mux_upgrade,
        "rpcId_seen": False,
        "respond_attempted": False,
        "respond_http": None,
        "accepted": None,
        "dsh_reject": "",
        "note": "未见 rpcId",
    }

    if peeked is None:
        print("未见 rpcId — not posting /api/respond — not writing accepted:true")
        return evidence

    rpc_id = str(peeked.get("rpc_id") or "").strip()
    approval_id = str(peeked.get("approval_id") or "").strip()
    tool = str(peeked.get("tool") or "")
    peeked_session = str(peeked.get("session_id") or session_id).strip()
    blob = json.dumps(peeked, ensure_ascii=False)
    assert "twin_id" not in blob

    if not rpc_id or not approval_id:
        print("未见 rpcId — peek incomplete; not posting /api/respond — not writing accepted:true")
        evidence["note"] = "未见 rpcId"
        return evidence

    if peeked_session and peeked_session != session_id:
        print(f"peek session mismatch {peeked_session} != {session_id} — not posting")
        evidence["note"] = "未见 rpcId"
        return evidence

    evidence["rpcId_seen"] = True
    evidence["peeked_rpc_id"] = rpc_id
    evidence["peeked_approval_id"] = approval_id
    evidence["peeked_tool"] = tool

    if tool == TWIN_TOOL:
        outcome = "rejected"
        print("peek is TwinRun — POST rejected (do not call TwinRun), echo mux rpcId")
    else:
        outcome = "allowed-once"

    status, parsed = _post_respond(
        base,
        rpc_id=rpc_id,
        session_id=session_id,
        approval_id=approval_id,
        outcome=outcome,
    )
    evidence["respond_attempted"] = True
    evidence["respond_http"] = status
    evidence["respond_body"] = parsed
    accepted = parsed.get("accepted") is True
    evidence["accepted"] = accepted
    if accepted:
        evidence["note"] = f"dsh accepted respond HTTP {status} echoing mux rpcId"
        print(f"respond HTTP {status} accepted=true (echoed mux rpcId, not minted)")
    else:
        reason = str(parsed.get("reason") or parsed)
        evidence["dsh_reject"] = reason
        evidence["note"] = f"dsh rejected respond HTTP {status}: {reason}"
        print(f"respond HTTP {status} dsh did not accept: {reason}")
    return evidence


def test_note_exists() -> None:
    assert NOTE.exists(), f"missing {NOTE}"
    text = _note_text()
    assert "H-01d" in text
    assert "POST /api/respond" in text or "/api/respond" in text


def test_refuses_fake_accepted() -> None:
    text = _note_text()
    compact = "".join(text.split())
    assert "未证明" in text or "unproven" in text.lower()
    assert "/api/respond" in text
    assert "POST" in text
    assert "426" in text
    assert "websocket" in text.lower()
    assert "未见 rpcId" in text or "未见rpcId" in compact
    assert "未尝试" in text or "不 POST" in text or "没有" in text
    if "accepted:true" in compact:
        negated = any(token in text for token in ("未证明", "unproven", "未见", "未写", "没有", "不把"))
        assert negated, "accepted:true appears without an honest negation"


def test_no_minted_rpc() -> None:
    text = _note_text()
    assert "rpcId" in text
    assert any(token in text for token in ("不铸", "不编造", "禁止铸造"))
    assert "minted-rpc" not in text
    src = Path(__file__).read_text(encoding="utf-8")
    assert "echoed" in src or "回显" in src


def test_probe_exists_gated() -> None:
    assert callable(probe_live_approve)
    assert PROBE_CALLED is False
    src = Path(__file__).read_text(encoding="utf-8")
    assert "def probe_live_approve" in src
    assert "QAGENT_LIVE_MUX" in src
    if not _live_mux_forced():
        assert PROBE_CALLED is False


def test_live_probe_optional() -> None:
    if not _live_mux_forced():
        print("skip live probe (QAGENT_LIVE_MUX!=1)")
        return
    try:
        probe_live_approve()
    except Skip as exc:
        print(f"skip  {exc}")


def main() -> int:
    failed = 0
    for name, fn in [
        ("note_exists", test_note_exists),
        ("refuses_fake_accepted", test_refuses_fake_accepted),
        ("no_minted_rpc", test_no_minted_rpc),
        ("probe_exists_gated", test_probe_exists_gated),
        ("live_probe_optional", test_live_probe_optional),
    ]:
        try:
            fn()
            print(f"ok  {name}")
        except Exception:
            failed += 1
            print(f"FAIL {name}")
            traceback.print_exc()
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
