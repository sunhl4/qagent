"""L1-04c-align: CI note follows list_engines. Cirq wired. Helper source has no cirq word."""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ROOT = Path(__file__).resolve().parents[1]
NOTE = REPO / "docs" / "execution" / "L1-04c_ci.md"
HELPER = ROOT / "scripts" / "check_missing_pack_tests.py"

sys.path.insert(0, str(ROOT / "src"))

from qagent.services.benchmark import missing_pack_tests
from qagent.services.engines import list_engines

_RUN_TESTS = "PYTHONPATH=src python3 tests/run_tests.py"
_RUN_HARD = "PYTHONPATH=src python3 tests/run_qagent_vs_codex.py"
_FIVE = ("qdata", "qchem", "ionstack", "route", "qiskit")

_G3_PASSED = (
    "G3 通过",
    "G3通过",
    "G3 passed",
    "G3 已通过",
    "G3 验收通过",
)

_STALE = (
    "Cirq reserved",
    "Cirq 是 reserved",
    "不进 engines[]",
    "不进 `engines[]`",
    "**不进** `engines[]`",
    "本步不要求 Cirq",
    "Cirq 留在 `reserved_engines`",
    "Cirq 留在 reserved_engines",
)


def _note() -> str:
    return NOTE.read_text(encoding="utf-8")


def test_note_keeps_l104c_anchors() -> None:
    assert NOTE.is_file(), NOTE
    text = _note()
    assert "missing_pack_tests" in text
    assert "benchmark_v1" in text
    assert _RUN_TESTS in text
    assert _RUN_HARD in text


def test_note_follows_list_engines() -> None:
    text = _note()
    assert "list_engines()" in text
    assert "Cirq 已接线" in text
    assert "已在 `list_engines()`" in text
    assert "五包仍打头" in text
    for pack_id in _FIVE:
        assert pack_id in text, pack_id
    assert "Cirq 夹具" in text
    assert "单测提到" in text
    assert "CI 跟目录走" in text or "跟 `list_engines()`" in text


def test_stale_reserved_gone() -> None:
    text = _note()
    hits = [phrase for phrase in _STALE if phrase in text]
    assert not hits, hits


def test_no_g3_passed() -> None:
    text = _note()
    hits = [phrase for phrase in _G3_PASSED if phrase in text]
    assert not hits, f"note claims G3 passed: {hits}"
    assert "不算 G3" in text or "不是 G3 过门" in text


def test_helper_source_has_no_cirq() -> None:
    assert HELPER.is_file(), HELPER
    helper = HELPER.read_text(encoding="utf-8")
    assert "cirq" not in helper
    assert "missing_pack_tests(Path(" in helper


def test_missing_follows_wired_catalog() -> None:
    ids = [pack.id for pack in list_engines()]
    assert ids[:5] == list(_FIVE)
    assert "cirq" in ids
    assert missing_pack_tests(ROOT / "tests") == []


def main() -> int:
    failed = 0
    for name, fn in (
        ("note_anchors", test_note_keeps_l104c_anchors),
        ("note_follows_list", test_note_follows_list_engines),
        ("stale_reserved_gone", test_stale_reserved_gone),
        ("no_g3_passed", test_no_g3_passed),
        ("helper_no_cirq", test_helper_source_has_no_cirq),
        ("missing_follows_catalog", test_missing_follows_wired_catalog),
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
