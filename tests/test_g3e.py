"""G3e: G3 checklist aligns Cirq wired. Codex stays stub. Refuses G3 pass. No fourth handle."""

from __future__ import annotations

import re
import traceback
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "docs" / "execution" / "G3_eval.md"
NOTE = REPO / "docs" / "execution" / "G3e_cirq.md"
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
_STALE = (
    "Cirq reserved",
    "Cirq 是 reserved",
    "不在 `engines[]`",
    "不在 engines[]",
    "把 Cirq reserved 算进",
)
_REQUIRED = ("30", "Q-h06", "stub", "run_qagent_vs_codex.py")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_script_aligned() -> None:
    text = _read(SCRIPT)
    assert "Cirq" in text
    assert "provenance=cirq" in text
    assert "qccd-twin" in text
    assert "Aer / IBM / 本地卡 / Cirq" in text
    assert "不许发" in text and "twin_id" in text
    assert "我们的机器" in text
    missing = [needle for needle in _REQUIRED if needle not in text]
    assert not missing, f"checklist missing {missing}"
    assert "PYTHONPATH=src python3 tests/run_qagent_vs_codex.py" in text
    assert "bare Codex" in text
    assert "may_fail" in text
    assert "30/30" in text
    assert "skip" in text
    assert "不算 G3 过门" in text
    for phrase in _STALE:
        assert phrase not in text, phrase


def test_note_exists() -> None:
    assert NOTE.is_file(), NOTE
    text = _read(NOTE)
    assert "G3e" in text
    assert "provenance=cirq" in text
    assert "qccd-twin" in text
    assert "我们的机器" in text
    assert "stub" in text
    assert "不算 G3" in text or "不是 G3 过门" in text
    for phrase in _STALE:
        assert phrase not in text, phrase


def test_refuses_to_claim_pass() -> None:
    blob = _read(SCRIPT) + _read(NOTE)
    for phrase in _CLAIM_PASS:
        assert phrase not in blob, phrase


def test_no_official_codex_invoked() -> None:
    blob = _read(SCRIPT) + _read(NOTE)
    hits = [phrase for phrase in _OFFICIAL_INVOKED if phrase in blob]
    assert not hits, f"claims official Codex was invoked: {hits}"
    script = _read(SCRIPT)
    assert "不 spawn 官方 Codex" in script or "不调官方 Codex" in script
    assert "不 spawn 官方 Codex" in blob or "不调官方 Codex" in blob


def test_no_fourth_handle() -> None:
    for path in (SCRIPT, NOTE):
        found = set(_ID_RE.findall(_read(path)))
        extra = found - _HANDLES
        assert not extra, f"{path.name} invented handles: {sorted(extra)}"
        assert "tenant_id" not in _read(path)
        assert _HANDLES <= found


def main() -> int:
    failed = 0
    for name, fn in (
        ("script_aligned", test_script_aligned),
        ("note_exists", test_note_exists),
        ("refuses_to_claim_pass", test_refuses_to_claim_pass),
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
