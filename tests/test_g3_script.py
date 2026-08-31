"""G3 eval checklist exists. Refuses to claim G3 pass. Codex stays stub. No fourth handle."""

from __future__ import annotations

import re
import traceback
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "docs" / "execution" / "G3_eval.md"

_REQUIRED = ("30", "Q-h06", "stub", "run_qagent_vs_codex.py")
_HANDLES = frozenset({"circuit_id", "asset_id", "twin_id"})
_ID_RE = re.compile(r"\b[a-z]+_id\b")

_CLAIM_PASS = (
    "G3 已通过",
    "G3 passed",
    "G3 验收通过",
    "G3 通过",
    "G3通过",
)

_OFFICIAL_INVOKED = (
    "official Codex was invoked",
    "invoked official Codex",
    "spawned official Codex",
    "已调官方 Codex",
    "已调用官方 Codex",
    "官方 Codex 已跑",
)


def _read() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_script_exists() -> None:
    assert SCRIPT.is_file(), SCRIPT
    text = _read()
    assert text.strip(), SCRIPT
    assert "G3" in text


def test_mentions_required() -> None:
    text = _read()
    missing = [needle for needle in _REQUIRED if needle not in text]
    assert not missing, f"checklist missing {missing}"
    assert "PYTHONPATH=src python3 tests/run_qagent_vs_codex.py" in text
    assert "bare Codex" in text
    assert "may_fail" in text
    assert "30/30" in text
    assert "skip" in text
    assert "不算 G3 过门" in text


def test_refuses_g3_pass_phrases() -> None:
    text = _read()
    hits = [phrase for phrase in _CLAIM_PASS if phrase in text]
    assert not hits, f"checklist claims G3 passed: {hits}"


def test_no_official_codex_invoked() -> None:
    text = _read()
    hits = [phrase for phrase in _OFFICIAL_INVOKED if phrase in text]
    assert not hits, f"checklist claims official Codex was invoked: {hits}"
    assert "不 spawn 官方 Codex" in text or "不调官方 Codex" in text


def test_no_fourth_handle() -> None:
    text = _read()
    found = set(_ID_RE.findall(text))
    extra = found - _HANDLES
    assert not extra, f"invented handles: {sorted(extra)}"
    assert _HANDLES <= found


def main() -> int:
    failed = 0
    for name, fn in (
        ("exists", test_script_exists),
        ("mentions", test_mentions_required),
        ("no_g3_pass", test_refuses_g3_pass_phrases),
        ("no_official_codex", test_no_official_codex_invoked),
        ("no_fourth_handle", test_no_fourth_handle),
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
