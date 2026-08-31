"""O-01k: handbooks document Cirq in the catalog as interop; not our machine."""

from __future__ import annotations

import re
import traceback
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
INTERNAL = REPO / "docs" / "handbooks" / "internal.md"
CUSTOMER = REPO / "docs" / "handbooks" / "customer.md"
NOTE = REPO / "docs" / "execution" / "O-01k_cirq_handbook.md"
_HANDLES = frozenset({"circuit_id", "asset_id", "twin_id"})
_FAKE_TWIN = ("twin_fixture", "twin_demo", "twin_leak", "twin_abc")
_ID_RE = re.compile(r"\b[a-z]+_id\b")
_CLAIM_PASS = ("G0 已通过", "G2 已通过", "G0 passed", "G2 passed")
_BANNED_IDS = ("tenant_id", "session_id", "assignment_id")
_CUSTOMER_LINE = "别人的模拟器不是我们的机器签收"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_internal_cirq_in_catalog_not_machine() -> None:
    text = _read(INTERNAL)
    assert "Cirq" in text
    assert "软件包目录" in text
    assert "kind" in text
    assert "互通" in text
    assert "provenance" in text
    assert "不是我们的机器" in text
    assert "Pennylane" in text
    assert "真机" in text
    assert "加包" in text
    assert "加包不是加句柄" in text
    assert "加 Cirq、Pennylane、真机" not in text
    assert "import cirq" not in text
    assert "dsh" in text
    assert "--profile qagent" in text
    assert "3080" in text
    assert "TwinRun" in text
    assert "CAL" in text
    assert "shuttle" in text
    assert "设置" in text
    assert "组内" in text
    assert "密钥" in text


def test_customer_simulator_not_our_receipt() -> None:
    text = _read(CUSTOMER)
    assert _CUSTOMER_LINE in text
    assert text.count(_CUSTOMER_LINE) == 1
    assert "Cirq" not in text
    assert "Pennylane" not in text
    assert "import cirq" not in text
    assert "session_id" not in text


def test_no_g_pass_claim() -> None:
    blob = _read(INTERNAL) + _read(CUSTOMER) + _read(NOTE)
    for phrase in _CLAIM_PASS:
        assert phrase not in blob, phrase


def test_no_fourth_handle() -> None:
    for path in (INTERNAL, CUSTOMER, NOTE):
        text = _read(path)
        found = set(_ID_RE.findall(text))
        extra = found - _HANDLES
        assert not extra, f"{path.name} invented handles: {sorted(extra)}"
        for banned in _BANNED_IDS:
            assert banned not in text, f"{path.name} wrote {banned}"
        for fake in _FAKE_TWIN:
            assert fake not in text
        assert "第四个句柄是" not in text
        assert "第四个句柄：" not in text
        assert "import cirq" not in text


def test_note_exists() -> None:
    assert NOTE.is_file(), NOTE
    text = _read(NOTE)
    assert "O-01k" in text
    assert "internal.md" in text
    assert "customer.md" in text
    assert "Cirq" in text
    assert "软件包目录" in text
    assert "kind" in text
    assert "互通" in text
    assert "provenance" in text
    assert "不是我们的机器" in text
    assert "Pennylane" in text
    assert _CUSTOMER_LINE in text
    assert "第三套" in text
    assert "O-01c_handbooks.md" in text
    for phrase in _CLAIM_PASS:
        assert phrase not in text, phrase
    for banned in _BANNED_IDS:
        assert banned not in text, banned
    assert "import cirq" not in text


def main() -> int:
    failed = 0
    for name, fn in (
        ("internal_cirq_in_catalog_not_machine", test_internal_cirq_in_catalog_not_machine),
        ("customer_simulator_not_our_receipt", test_customer_simulator_not_our_receipt),
        ("no_g_pass_claim", test_no_g_pass_claim),
        ("no_fourth_handle", test_no_fourth_handle),
        ("note_exists", test_note_exists),
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
