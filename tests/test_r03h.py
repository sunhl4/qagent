"""R-03h: live 3080 HTTP approve signs receipt. Skip-as-green is incomplete."""

from __future__ import annotations

import json
import sys
import traceback
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT
sys.path.insert(0, str(ROOT / "src"))

from qagent.models.handles import HANDLE_TWIN
from qagent.models.assignment import SOURCE_TWIN

_NOTE = REPO / "docs" / "execution" / "R-03h_http_receipt.md"
_FACE = "http://127.0.0.1:3080"
_TOKEN = "workbench-review"
_COPIED_TWIN = "5c9ce47cda91d673598ba1283fed4e5ab4c1c17d2c770245ecab2534e3e071a5"
_FORBIDDEN = {"error": "approval requires QAGENT_SHELL_TOKEN"}
_SOUTHBOUND = ("calibration", "cal", "shuttle", "ms_matrix")


def _headers(*, token: bool) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-QAGENT-DEBUG-TOKEN"] = _TOKEN
        headers["X-QAGENT-APPROVE-TOKEN"] = _TOKEN
    return headers


def _call(method: str, path: str, body: dict[str, Any] | None = None, *, token: bool = True) -> tuple[int, dict[str, Any]]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        _FACE + path,
        data=data,
        headers=_headers(token=token),
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
            code = int(response.status)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            parsed = {"raw": raw}
        if not isinstance(parsed, dict):
            parsed = {"raw": raw}
        return exc.code, parsed
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise AssertionError(f"3080 not reachable ({path}): {exc}") from exc
    try:
        parsed = json.loads(raw) if raw else {}
    except json.JSONDecodeError as exc:
        raise AssertionError(f"3080 body is not JSON ({path}): {raw!r}") from exc
    if not isinstance(parsed, dict):
        raise AssertionError(f"3080 JSON must be an object, got {type(parsed).__name__}")
    return code, parsed


def test_approve_without_token_is_403() -> None:
    code, created = _call("POST", "/api/assignments", {"room": "lab", "brief": "r03h-403", "shots": 8}, token=False)
    assert code == 200, created
    aid = created["assignment_id"]
    code, ran = _call("POST", f"/api/assignments/{aid}/run", {}, token=False)
    assert code == 200, ran
    assert ran.get("status") == "needs_ask"
    code, forbidden = _call("POST", f"/api/assignments/{aid}/approve", {}, token=False)
    assert code == 403
    assert forbidden == _FORBIDDEN
    print("approve without token is 403")


def test_live_http_approve_signs_receipt() -> None:
    code, created = _call("POST", "/api/assignments", {"room": "lab", "brief": "r03h-live", "shots": 8})
    assert code == 200, created
    aid = str(created.get("assignment_id") or "")
    assert aid, created
    code, ran = _call("POST", f"/api/assignments/{aid}/run", {})
    assert code == 200, ran
    assert ran.get("status") == "needs_ask", ran
    assert HANDLE_TWIN not in (ran.get("handles") or {})
    code, done = _call("POST", f"/api/assignments/{aid}/approve", {})
    assert code == 200, done
    assert done.get("status") == "signed", f"expected signed, got {done}"
    code, sealed = _call("GET", f"/api/assignments/{aid}/receipt")
    assert code == 200, sealed
    twin_id = str((sealed.get("handles") or {}).get(HANDLE_TWIN) or "").strip()
    assert twin_id, "no live HTTP receipt twin_id — R-03h is not done"
    assert sealed.get("signed") is True
    assert SOURCE_TWIN in (sealed.get("sources") or [])
    assert sealed.get("status") == "signed"
    for leaked in _SOUTHBOUND:
        assert leaked not in json.dumps(sealed, ensure_ascii=False)
    code, verified = _call("POST", "/api/receipts/verify", sealed)
    assert code == 200, verified
    assert verified.get("ok") is True, verified
    print(
        f"live HTTP receipt signed=true twin_id={twin_id} "
        f"assignment_id={aid} verify_ok={verified.get('ok')}"
    )


def test_note_copies_hit() -> None:
    assert _NOTE.is_file(), f"missing {_NOTE}"
    text = _NOTE.read_text(encoding="utf-8")
    assert _COPIED_TWIN in text
    assert "signed" in text
    assert "qccd-twin" in text
    assert "/api/assignments" in text
    assert "approve" in text
    assert "receipt" in text
    assert "不算 G0" in text
    assert "不算 G2" in text
    assert "G0 已通过" not in text
    assert "G2 已通过" not in text
    assert "CAL" in text
    assert "不进工具" in text
    assert "skip 当绿" in text
    assert "未 commit" in text
    assert "诚实" in text


def test_this_file_does_not_skip() -> None:
    text = Path(__file__).read_text(encoding="utf-8")
    assert ("pytest" + ".skip") not in text
    assert ("unittest" + ".skip") not in text
    assert ("skip" + "Test") not in text


def main() -> int:
    failed = 0
    for name, fn in (
        ("approve_without_token_is_403", test_approve_without_token_is_403),
        ("live_http_approve_signs_receipt", test_live_http_approve_signs_receipt),
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
