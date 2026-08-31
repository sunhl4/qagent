"""I-03p: ELN face paints shots_actual. No twin_id."""

from __future__ import annotations

import json
import traceback
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SHELL = ROOT / "apps" / "customer-shell"
NOTE = ROOT / "docs" / "execution" / "I-03p_eln_shots.md"
_CLAIM_PASS = ("G0 已通过", "G1 已通过", "G2 已通过", "G0 passed", "G1 passed", "G2 passed")
_FACE = "http://127.0.0.1:3080"
_TOKEN = "workbench-review"


def _js() -> str:
    return (SHELL / "app.js").read_text(encoding="utf-8")


def _paint() -> str:
    return _js().split("function paintEln")[1].split("async function refreshInbox")[0]


def _headers() -> dict[str, str]:
    return {"X-QAGENT-DEBUG-TOKEN": _TOKEN}


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


def test_eln_paints_shots_not_twin() -> None:
    js = _js()
    paint = _paint()
    assert "function elnShots" in js
    assert "row.shots_actual" in js
    assert "实打 · " in paint
    assert "eln-shots" in paint
    assert "twin_id" not in paint
    assert "row.columns" not in paint
    assert "qasm3" not in paint
    assert "recipe" not in paint or "recipe_pin" in paint


def _eln_signoff(rows: list[Any]) -> dict[str, Any] | None:
    return next(
        (row for row in rows if row.get("type") == "qagent/twin_signoff" and row.get("shots_actual")),
        None,
    )


def test_live_http_eln_has_shots() -> None:
    code, payload = _call("/api/eln")
    assert code == 200
    signoff = _eln_signoff(payload.get("events") or [])
    if not signoff:
        _, listed = _call("/api/assignments?status=signed")
        for row in reversed(listed.get("assignments") or []):
            aid = row.get("assignment_id")
            if not aid:
                continue
            code, payload = _call(f"/api/eln?assignment_id={aid}")
            assert code == 200
            signoff = _eln_signoff(payload.get("events") or [])
            if signoff:
                break
    assert signoff, "GET /api/eln must expose shots_actual on a tagged signed assignment"
    assert "twin_id" not in signoff
    print(f"live eln signoff assignment_id={signoff.get('assignment_id')} shots_actual={signoff.get('shots_actual')}")


def test_note_copies_hit() -> None:
    assert NOTE.is_file(), NOTE
    text = NOTE.read_text(encoding="utf-8")
    assert "实打 · " in text
    assert "shots_actual" in text
    assert "eln-shots" in text
    assert "不算 G0" in text
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
        ("eln_paints_shots_not_twin", test_eln_paints_shots_not_twin),
        ("live_http_eln_has_shots", test_live_http_eln_has_shots),
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
