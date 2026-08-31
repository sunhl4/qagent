"""H-01d-live: probe already-running dsh mux for rpcId. No third loop. No minted twin_id."""

from __future__ import annotations

import json
import os
import traceback
import urllib.error
import urllib.request
from pathlib import Path

os.environ.setdefault("QAGENT_DSH_URL", "http://127.0.0.1:3081")

from qagent.adapters.dsh_session import DshSessionClient, DshSessionError, dsh_base_url


ROOT = Path(__file__).resolve().parents[1]
NOTE = ROOT / "docs" / "execution" / "H-01d_live_mux.md"
HARMLESS = "只回复一个汉字：好。不要调用任何工具，不要改文件。"
TWIN_TOOL = "ionstack_twin_run"


class Skip(Exception):
    """Honest skip: live dsh missing or create refused. Exit 0."""


def _live_mux_forced() -> bool:
    return (os.environ.get("QAGENT_LIVE_MUX") or "").strip() == "1"


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


def _mux_sse(base: str) -> tuple[int, str, str]:
    status, body, headers = _get(
        base.rstrip("/") + "/api/events.mux",
        headers={"Accept": "text/event-stream"},
        timeout=1.2,
    )
    return status, body, headers.get("upgrade") or ""


def probe_live() -> dict[str, object]:
    base = dsh_base_url()
    if not _reachable(base):
        if not _live_mux_forced():
            raise Skip("3081 down and QAGENT_LIVE_MUX is not 1")
        raise AssertionError("QAGENT_LIVE_MUX=1 but 3081 is down")

    client = DshSessionClient(base_url=base, timeout=12.0)
    try:
        session_id = client.create(agent_preset="qagent")
        create_error = ""
    except DshSessionError as exc:
        raise Skip(f"session.create failed: {exc.code}: {exc}") from exc

    assert session_id, "create returned empty sessionId"
    print(f"create=ok sessionId={session_id}")

    mux_status, mux_body, mux_upgrade = _mux_sse(base)
    print(f"mux_sse_http={mux_status} upgrade={mux_upgrade!r} body={mux_body[:80]!r}")
    assert mux_status != 500, f"mux GET with SSE accept was HTTP {mux_status}"

    peeked = client.peek_mux_approval(session_id)
    mux_rpc = str((peeked or {}).get("rpc_id") or "").strip() if isinstance(peeked, dict) else ""
    rpc_seen = bool(mux_rpc)
    print(f"peek_mux={peeked} rpcId_seen={rpc_seen}")

    prompt_ok = False
    try:
        prompted = client.prompt(session_id, HARMLESS)
        prompt_ok = True
        print(f"session.prompt={json.dumps(prompted, ensure_ascii=False)[:200]}")
    except DshSessionError as exc:
        print(f"session.prompt failed: {exc.code}: {exc}")

    snap: dict[str, object] = {}
    if prompt_ok:
        snap = client.wait_for_turn(session_id, timeout=20.0)
        print(
            "snap",
            "running=", snap.get("running"),
            "awaiting=", snap.get("awaiting"),
            "tools=", snap.get("used_tools"),
            "pending=", snap.get("pending_approval"),
            "reply=", repr(str(snap.get("reply") or "")[:80]),
        )

    pending = snap.get("pending_approval") if isinstance(snap.get("pending_approval"), dict) else None
    respond_attempted = False
    accepted: bool | None = None
    if pending:
        tool = str(pending.get("tool") or "")
        rpc_id = str(pending.get("rpc_id") or "").strip()
        approval_id = str(pending.get("approval_id") or "").strip()
        if not rpc_id:
            print("pending without mux rpcId — not posting /api/respond")
        elif tool == TWIN_TOOL or "twin_id" in json.dumps(pending):
            print("pending looks like TwinRun — not approving, not minting twin_id")
        else:
            receipt = client.approve_once(session_id, approval_id, rpc_id)
            respond_attempted = True
            accepted = receipt.get("accepted") is True
            print(f"respond_attempted=true accepted={accepted}")
    else:
        print("respond_attempted=false (no pending approval; will not invent rpcId)")

    assert "twin_id" not in session_id
    if pending:
        assert "twin_id" not in json.dumps(pending)

    evidence = {
        "create_ok": True,
        "create_error": create_error,
        "session_id": session_id,
        "mux_sse_http": mux_status,
        "rpcId_seen": rpc_seen,
        "respond_attempted": respond_attempted,
        "accepted": accepted,
    }
    print(
        "live",
        f"create=ok",
        f"mux_sse={mux_status}",
        f"rpcId_seen={rpc_seen}",
        f"respond_attempted={respond_attempted}",
        f"accepted={accepted}",
    )
    return evidence


def test_note_records_evidence() -> None:
    assert NOTE.exists(), f"missing {NOTE}"
    text = NOTE.read_text(encoding="utf-8")
    assert "200" in text
    assert "426" in text
    assert "rpcId" in text
    assert "respond" in text
    assert "accepted:true" not in text.replace(" ", "") or "session.prompt" in text
    assert "假 accepted" not in text or "没有" in text or "未" in text


def main() -> int:
    failed = 0
    try:
        probe_live()
        print("ok  live_mux_probe")
    except Skip as exc:
        print(f"skip  {exc}")
    except Exception:
        failed += 1
        print("FAIL live_mux_probe")
        traceback.print_exc()
    try:
        test_note_records_evidence()
        print("ok  note")
    except Exception:
        failed += 1
        print("FAIL note")
        traceback.print_exc()
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
