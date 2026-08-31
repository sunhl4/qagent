"""H-01j: live product 批准 allowed-once. Skip-as-green is incomplete."""

from __future__ import annotations

import re
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from qagent.models.handles import HANDLE_ASSET, HANDLE_CIRCUIT, HANDLE_TWIN

NOTE = ROOT / "docs" / "execution" / "H-01j_live_allowed_once.md"
JS = ROOT / "apps" / "customer-shell" / "app.js"
ASSIGNMENT = ROOT / "src" / "qagent" / "services" / "assignment.py"
_HANDLES = frozenset({HANDLE_CIRCUIT, HANDLE_ASSET, HANDLE_TWIN})
_KNOWN = _HANDLES | {"rpc_id", "approval_id", "sessionId"}
_ID_RE = re.compile(r"\b[a-z]+_id\b")


def _text(path: Path) -> str:
    assert path.is_file(), f"missing {path}"
    return path.read_text(encoding="utf-8")


def test_note() -> None:
    text = _text(NOTE)
    assert "H-01j" in text
    assert "allowed-once" in text
    assert "S-TWIN-02" in text
    assert "e5dcc262" in text
    assert "bc41e0fd" in text
    assert "批准" in text
    assert "twin_id" in text
    assert "不算 G0" in text
    assert "假 twin_id" in text or "没有假" in text
    print("note records allowed-once and honest TwinRun miss")


def test_bubble_still_send_approve() -> None:
    js = _text(JS)
    assert 'send("批准")' in js
    assert "/approve" not in js
    print("bubble still send 批准")


def test_no_fourth_handle_or_extra_pipeline() -> None:
    for path in (NOTE,):
        for match in _ID_RE.findall(_text(path)):
            assert match in _KNOWN, (path.name, match)
    assert _text(ASSIGNMENT).count('"mode": "pipeline"') == 3
    print("still three handles; pipeline count frozen")


def main() -> int:
    failed = 0
    for name, fn in (
        ("note", test_note),
        ("bubble_still_send_approve", test_bubble_still_send_approve),
        ("no_fourth_handle_or_extra_pipeline", test_no_fourth_handle_or_extra_pipeline),
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
