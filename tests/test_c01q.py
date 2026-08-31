"""C-01q: inbox/receipt paint circuit_id and asset_id from handles. Chat mux still send(批准)."""

from __future__ import annotations

import json
import traceback
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SHELL = ROOT / "apps" / "customer-shell"
NOTE = ROOT / "docs" / "execution" / "C-01q_face_handles.md"
_CLAIM_PASS = ("G0 已通过", "G1 已通过", "G2 已通过", "G0 passed", "G1 passed", "G2 passed")
_FACE = "http://127.0.0.1:3080"
_TOKEN = "workbench-review"


def _js() -> str:
    return (SHELL / "app.js").read_text(encoding="utf-8")


def _paint_inbox() -> str:
    return _js().split("function paintInbox")[1].split("function receiptKey")[0]


def _paint_face() -> str:
    return _js().split("function paintFaceRow")[1].split("function paintReceipts")[0]


def _add_message() -> str:
    return _js().split('if (extras && extras.awaiting === "approve")')[1].split("function paintWelcome")[0]


def _headers() -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "X-QAGENT-DEBUG-TOKEN": _TOKEN,
        "X-QAGENT-APPROVE-TOKEN": _TOKEN,
    }


def _call(path: str) -> tuple[int, dict[str, Any]]:
    request = urllib.request.Request(_FACE + path, headers=_headers(), method="GET")
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            raw = response.read().decode("utf-8")
            code = int(response.status)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        code = exc.code
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise AssertionError(f"3080 not reachable ({path}): {exc}") from exc
    parsed = json.loads(raw) if raw else {}
    if not isinstance(parsed, dict):
        raise AssertionError(f"3080 JSON must be an object: {raw!r}")
    return code, parsed


def test_face_paints_circuit_and_asset_from_handles() -> None:
    js = _js()
    inbox = _paint_inbox()
    face = _paint_face()
    assert "function faceCircuitId" in js
    assert "function faceAssetId" in js
    assert "handles.circuit_id" in js
    assert "handles.asset_id" in js
    assert "这份线路" in inbox
    assert "已备好的数据" in inbox
    assert "inbox-circuit" in inbox
    assert "inbox-asset" in inbox
    assert "这份线路" in face
    assert "已备好的数据" in face
    assert "receipt-circuit" in face
    assert "receipt-asset" in face
    assert "row.columns" not in inbox
    assert "row.columns" not in face
    assert "ask.args" not in inbox
    assert "ask.args" not in face
    assert "/approve" not in js
    assert "twin_id=" not in js
    assert "job_id" not in inbox
    assert "job_id" not in face


def test_live_http_face_already_has_handles() -> None:
    code, payload = _call("/api/assignments")
    assert code == 200
    rows = payload.get("assignments") or []
    hit = next((row for row in rows if (row.get("handles") or {}).get("circuit_id")), None)
    assert hit, "3080 face must already carry handles.circuit_id"
    handles = hit["handles"]
    assert handles.get("circuit_id", "").startswith("circ_")
    assert "columns" not in hit
    print(
        f"live face assignment_id={hit.get('assignment_id')} "
        f"status={hit.get('status')} circuit_id={handles.get('circuit_id')} "
        f"asset_id={handles.get('asset_id')}"
    )


def test_chat_bubble_still_sends_approve() -> None:
    bubble = _add_message()
    assert 'send("批准")' in bubble
    assert 'send("先不批")' in bubble
    assert "assignmentAction" not in bubble


def test_note_copies_hit() -> None:
    assert NOTE.is_file(), NOTE
    text = NOTE.read_text(encoding="utf-8")
    assert "这份线路" in text
    assert "已备好的数据" in text
    assert "circuit_id" in text
    assert "asset_id" in text
    assert "inbox-circuit" in text
    assert "receipt-circuit" in text
    assert "不算 G0" in text
    assert "不算 G1" in text
    assert 'send("批准")' in text
    assert "未 commit" in text
    for phrase in _CLAIM_PASS:
        assert phrase not in text


def test_this_file_does_not_skip() -> None:
    text = Path(__file__).read_text(encoding="utf-8")
    assert ("pytest" + ".skip") not in text
    assert ("unittest" + ".skip") not in text
    assert ("skip" + "Test") not in text


def main() -> int:
    failed = 0
    for name, fn in (
        ("face_paints_circuit_and_asset_from_handles", test_face_paints_circuit_and_asset_from_handles),
        ("live_http_face_already_has_handles", test_live_http_face_already_has_handles),
        ("chat_bubble_still_sends_approve", test_chat_bubble_still_sends_approve),
        ("note_copies_hit", test_note_copies_hit),
        ("this_file_does_not_skip", test_this_file_does_not_skip),
    ):
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
