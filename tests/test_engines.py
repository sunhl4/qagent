from __future__ import annotations

import traceback

from qagent.services.engines import list_engines

_FIVE = ["qdata", "qchem", "ionstack", "route", "qiskit"]


def test_five_packs() -> None:
    ids = [e.id for e in list_engines()]
    assert ids[:5] == _FIVE
    assert set(_FIVE) <= set(ids)


def test_qiskit_is_interop_not_machine() -> None:
    pack = next(e for e in list_engines() if e.id == "qiskit")
    assert pack.kind == "interop"
    assert "twin_id" not in pack.identity_fields


def main() -> int:
    failed = 0
    for name, fn in (
        ("five_packs", test_five_packs),
        ("qiskit_interop", test_qiskit_is_interop_not_machine),
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

