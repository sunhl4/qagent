"""I-03j: GET /api/cards washes nested ELN. No twin_id / body / secrets. Not G2."""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import traceback
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Mapping

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from qagent.entrypoints.shell_http import dispatch
from qagent.models.eln import (
    EVENT_B3,
    EVENT_RECIPE_PIN,
    EVENT_TWIN_SIGNOFF,
    FIELD_ASSIGNMENT_ID,
    FORBIDDEN_ELN_KEYS,
    SECRET_ELN_KEYS,
)
from qagent.models.handles import HANDLE_ASSET, HANDLE_CIRCUIT, HANDLE_TWIN, HANDLES
from qagent.services.cards import pes_card, signoff_card
from qagent.services.eln import append_twin_signoff

_ENV_KEYS = ("QAGENT_ELN_FILE",)
_AID = "asg_i03j_src"
_SECRET = "sk-i03j-n3v3r-eln-7k2p"
_HPC = "i03j-hpc-n3v3r-eln-4m9q"
_QTM = "i03j-qtm-n3v3r-eln-1w8r"
_PLANTED = (_SECRET, _HPC, _QTM)
_TWIN = "twin_from_qccd_rest"
_NOTE = ROOT / "docs" / "execution" / "I-03j_cards.md"
_CARDS = SRC / "qagent" / "services" / "cards.py"
_ALLOWED_IDS = frozenset({FIELD_ASSIGNMENT_ID})
_ID_RE = re.compile(r"\b[a-z]+_id\b")
_CLAIM_PASS = ("G0 已通过", "G2 已通过", "G0 passed", "G2 passed")
_SCIENCE = ("qdata", "ionstack", "qchem", "qiskit", "pennylane")


@contextmanager
def isolated_eln() -> Iterator[Path]:
    previous = {key: os.environ.get(key) for key in _ENV_KEYS}
    tmp = tempfile.TemporaryDirectory()
    try:
        path = Path(tmp.name) / "eln.jsonl"
        os.environ["QAGENT_ELN_FILE"] = str(path)
        yield path
    finally:
        tmp.cleanup()
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _nested_keys(value: object) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, Mapping):
        for key, inner in value.items():
            keys.add(str(key))
            keys.update(_nested_keys(inner))
    elif isinstance(value, list):
        for inner in value:
            keys.update(_nested_keys(inner))
    return keys


def _assert_clean_card(payload: Mapping[str, Any]) -> None:
    keys = _nested_keys(payload)
    assert HANDLE_TWIN not in keys
    assert not SECRET_ELN_KEYS & keys
    assert not FORBIDDEN_ELN_KEYS & keys
    assert "body" not in keys
    assert "qasm" not in keys
    assert "qasm3" not in keys
    assert "counts" not in keys
    extra = {key for key in keys if key.endswith("_id")} - _ALLOWED_IDS
    assert not extra, extra
    blob = json.dumps(payload, ensure_ascii=False)
    assert HANDLE_TWIN not in blob
    assert _TWIN not in blob
    for planted in _PLANTED:
        assert planted not in blob
    assert "secret-circuit" not in blob
    assert "OPENQASM" not in blob
    assert "raw-circuit" not in blob
    found = set(_ID_RE.findall(blob)) - _ALLOWED_IDS - set(HANDLES)
    assert HANDLE_TWIN not in found
    assert not (found - set(HANDLES)), found


def _plant_fat_lines(path: Path) -> None:
    fat_pin = {
        "type": EVENT_RECIPE_PIN,
        FIELD_ASSIGNMENT_ID: _AID,
        "recipe": "a2_chem_pes",
        HANDLE_TWIN: _TWIN,
        "llm_api_key": _SECRET,
        "hpc_secret": _HPC,
        "quantum_secret": _QTM,
        "body": "OPENQASM 3; secret-circuit",
        "qasm": "OPENQASM 2;",
        "qasm3": "OPENQASM 3;",
        "counts": {"00": 8},
        "params": {"shots": 8, "body": "raw-circuit", "hpc_secret": _HPC, HANDLE_TWIN: _TWIN},
    }
    fat_signoff = {
        "type": EVENT_TWIN_SIGNOFF,
        FIELD_ASSIGNMENT_ID: _AID,
        HANDLE_TWIN: _TWIN,
        "shots_actual": 64,
        "llm_api_key": _SECRET,
        "hpc_secret": _HPC,
        "quantum_secret": _QTM,
        "body": "OPENQASM 3; secret-circuit",
        "qasm3": "OPENQASM 3;",
        "counts": {"11": 4},
        HANDLE_CIRCUIT: "circ_i03j_leak",
        HANDLE_ASSET: "asset_i03j_leak",
    }
    fat_b3 = {
        "type": EVENT_B3,
        FIELD_ASSIGNMENT_ID: _AID,
        "verdict": "inconclusive",
        HANDLE_TWIN: _TWIN,
        "body": "OPENQASM 3; secret-circuit",
        "hpc_secret": _HPC,
    }
    with path.open("a", encoding="utf-8") as handle:
        for row in (fat_pin, fat_signoff, fat_b3):
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def test_cards_wash_append_and_http() -> None:
    with isolated_eln() as path:
        append_twin_signoff(twin_id=_TWIN, shots_actual=32, assignment_id=_AID)
        on_disk = path.read_text(encoding="utf-8")
        assert HANDLE_TWIN in on_disk
        assert _TWIN in on_disk
        _plant_fat_lines(path)

        pes = pes_card()
        signoff = signoff_card()
        assert pes["kind"] == "pes"
        assert signoff["kind"] == "signoff"
        recipe = pes["recipe"]
        assert isinstance(recipe, dict)
        assert recipe.get("type") == EVENT_RECIPE_PIN
        assert recipe.get(FIELD_ASSIGNMENT_ID) == _AID
        assert recipe.get("recipe") == "a2_chem_pes"
        twin_row = signoff["twin"]
        assert isinstance(twin_row, dict)
        assert twin_row.get("type") == EVENT_TWIN_SIGNOFF
        assert twin_row.get(FIELD_ASSIGNMENT_ID) == _AID
        assert twin_row.get("shots_actual") == 64
        b3 = signoff["b3"]
        assert isinstance(b3, dict)
        assert b3.get("type") == EVENT_B3
        assert b3.get("verdict") == "inconclusive"

        _assert_clean_card(pes)
        _assert_clean_card(signoff)

        code, payload = dispatch("GET", "/api/cards")
        assert code == 200
        assert isinstance(payload, dict)
        assert payload["pes"]["kind"] == "pes"
        assert payload["signoff"]["kind"] == "signoff"
        _assert_clean_card(payload)
        assert payload["pes"]["recipe"]["recipe"] == "a2_chem_pes"
        assert payload["signoff"]["twin"]["shots_actual"] == 64


def test_cards_source_has_no_fourth_handle() -> None:
    text = _CARDS.read_text(encoding="utf-8")
    assert "drop_twin" in text
    assert "short_payload" in text
    extra = set(_ID_RE.findall(text)) - _ALLOWED_IDS - set(HANDLES)
    assert not extra, extra
    for name in _SCIENCE:
        assert name not in text, name
        assert f"import {name}" not in text


def test_note_exists() -> None:
    assert _NOTE.is_file(), _NOTE
    text = _NOTE.read_text(encoding="utf-8")
    assert "不算 G2" in text
    assert "不泄 twin_id" in text
    assert "GET /api/cards" in text
    assert "kind" in text
    assert "第四" in text
    assert "不算接线" in text
    for phrase in _CLAIM_PASS:
        assert phrase not in text, phrase


def main() -> int:
    failed = 0
    for name, fn in (
        ("cards_wash_append_and_http", test_cards_wash_append_and_http),
        ("cards_source_has_no_fourth_handle", test_cards_source_has_no_fourth_handle),
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
