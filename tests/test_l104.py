"""L1-04: freeze pack I/O field names. No unit test = fail. No science kernels."""

from __future__ import annotations

import sys
import tempfile
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from qagent.models.handles import HANDLE_ASSET, HANDLE_TWIN, PROVENANCE_AER, PROVENANCE_CIRQ
from qagent.services.benchmark import (
    FIELD_CASES,
    FIELD_FORBIDDEN_OUTPUT,
    FIELD_INVOKE_TOOL,
    FIELD_OUTPUT_CONST,
    FIELD_PACK_ID,
    FIELD_REQUIRED_OUTPUT,
    FIELD_VERSION,
    load_fixture,
    missing_pack_tests,
)
from qagent.services.engines import list_engines

_NOTE = ROOT / "docs" / "execution" / "L1-04_fixture.md"
_TESTS = ROOT / "tests"
_SRC_GATE = ROOT / "src" / "qagent" / "services" / "benchmark.py"
_HANDLE = "twin" + "_id"
_FAKE_PACK = "ghostpack"
_FIVE = ("qdata", "qchem", "ionstack", "route", "qiskit")


def _cases_by_pack() -> dict[str, dict]:
    raw = load_fixture()
    cases = raw[FIELD_CASES]
    return {row[FIELD_PACK_ID]: row for row in cases}


def test_fixture_parses_and_covers_wired() -> None:
    raw = load_fixture()
    assert raw.get(FIELD_VERSION) == "v1"
    cases = raw[FIELD_CASES]
    assert isinstance(cases, list)
    by_pack = _cases_by_pack()
    wired = [pack.id for pack in list_engines()]
    assert wired[:5] == list(_FIVE)
    assert set(_FIVE) <= set(wired)
    for pack_id in _FIVE:
        assert pack_id in by_pack, pack_id
        case = by_pack[pack_id]
        assert case[FIELD_INVOKE_TOOL]
        assert isinstance(case[FIELD_REQUIRED_OUTPUT], list)
    if "cirq" in wired:
        assert "cirq" in by_pack
        case = by_pack["cirq"]
        assert case[FIELD_INVOKE_TOOL]
        assert isinstance(case[FIELD_REQUIRED_OUTPUT], list)
    else:
        assert "cirq" not in by_pack


def test_cirq_not_required() -> None:
    ids = {pack.id for pack in list_engines()}
    by_pack = _cases_by_pack()
    for pack_id in _FIVE:
        assert pack_id in by_pack, pack_id
    if "cirq" in ids:
        assert "cirq" in by_pack
    else:
        assert "cirq" not in by_pack
        missing = missing_pack_tests(_TESTS)
        assert "cirq" not in missing


def test_no_required_twin_id() -> None:
    for case in load_fixture()[FIELD_CASES]:
        required = case.get(FIELD_REQUIRED_OUTPUT) or []
        assert HANDLE_TWIN not in required
        assert _HANDLE not in required


def test_frozen_honest_keys() -> None:
    by_pack = _cases_by_pack()
    qdata = by_pack["qdata"]
    assert qdata[FIELD_INVOKE_TOOL] == "qdata_run_recipe"
    assert HANDLE_ASSET in qdata[FIELD_REQUIRED_OUTPUT]
    assert HANDLE_TWIN in qdata[FIELD_FORBIDDEN_OUTPUT]

    qchem = by_pack["qchem"]
    assert qchem[FIELD_INVOKE_TOOL] == "qchem_run"
    assert HANDLE_ASSET in qchem[FIELD_REQUIRED_OUTPUT]
    assert HANDLE_TWIN in qchem[FIELD_FORBIDDEN_OUTPUT]

    ionstack = by_pack["ionstack"]
    assert ionstack[FIELD_INVOKE_TOOL] == "ionstack_twin_identity"
    assert HANDLE_TWIN in ionstack[FIELD_FORBIDDEN_OUTPUT]
    assert HANDLE_TWIN not in ionstack[FIELD_REQUIRED_OUTPUT]

    route = by_pack["route"]
    assert route[FIELD_INVOKE_TOOL] == "ionstack_compile_estimate"
    assert "makespan_ns" in route[FIELD_REQUIRED_OUTPUT]
    assert "ok" in route[FIELD_FORBIDDEN_OUTPUT]

    qiskit = by_pack["qiskit"]
    assert qiskit[FIELD_INVOKE_TOOL] == "qiskit_aer_run"
    assert "provenance" in qiskit[FIELD_REQUIRED_OUTPUT]
    assert qiskit[FIELD_OUTPUT_CONST]["provenance"] == PROVENANCE_AER
    assert HANDLE_TWIN in qiskit[FIELD_FORBIDDEN_OUTPUT]

    if "cirq" in by_pack:
        cirq = by_pack["cirq"]
        assert cirq[FIELD_INVOKE_TOOL] == "cirq_simulator_run"
        assert "provenance" in cirq[FIELD_REQUIRED_OUTPUT]
        assert cirq[FIELD_OUTPUT_CONST]["provenance"] == PROVENANCE_CIRQ
        assert HANDLE_TWIN in cirq[FIELD_FORBIDDEN_OUTPUT]


def test_current_tree_has_fixture_and_tests() -> None:
    assert missing_pack_tests(_TESTS) == []


def test_temp_dir_extra_pack_missing() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        (root / "test_blank.py").write_text("# blank acceptance dir\n", encoding="utf-8")
        extra = missing_pack_tests(root, engine_ids=[_FAKE_PACK])
        assert extra == [_FAKE_PACK]
        known_without_test = missing_pack_tests(root, engine_ids=["qdata"])
        assert known_without_test == ["qdata"]


def test_no_science_imports_in_gate() -> None:
    text = _SRC_GATE.read_text(encoding="utf-8")
    assert "import qdata" not in text
    assert "from qdata" not in text
    assert "import ionstack" not in text
    assert "from ionstack" not in text
    assert "import qchem" not in text
    assert "from qchem" not in text
    assert "import qiskit" not in text
    assert "from qiskit" not in text
    assert "import cirq" not in text
    assert "from cirq" not in text


def test_note_exists() -> None:
    assert _NOTE.exists()
    text = _NOTE.read_text(encoding="utf-8")
    assert "benchmark_v1" in text
    assert "missing_pack_tests" in text
    assert "run_tests.py" in text


def main() -> int:
    failed = 0
    for name, fn in (
        ("fixture_covers_wired", test_fixture_parses_and_covers_wired),
        ("cirq_not_required", test_cirq_not_required),
        ("no_required_twin_id", test_no_required_twin_id),
        ("frozen_honest_keys", test_frozen_honest_keys),
        ("current_tree_complete", test_current_tree_has_fixture_and_tests),
        ("temp_extra_pack_missing", test_temp_dir_extra_pack_missing),
        ("no_science_imports", test_no_science_imports_in_gate),
        ("note", test_note_exists),
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
