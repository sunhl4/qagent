"""A-05h: newest card stays in the catalog when store is over budget. Skip-as-green is incomplete."""

from __future__ import annotations

import json
import os
import shutil
import sys
import traceback
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Mapping

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT
sys.path.insert(0, str(ROOT / "src"))

from qagent.adapters.qdata import _CATALOG_CAP
from qagent.adapters.support import load_json, save_json
from qagent.models.handles import HANDLE_ASSET, HANDLE_TWIN
from qagent.services.invoke import invoke

_NOTE = REPO / "docs" / "execution" / "A-05h_newest_card.md"
_STORE = ROOT / ".qagent" / "test-a05h-store"
_RECIPE = "a2_spin_shadow"
_SHOTS = 8
_OLD_COUNT = 25
_COPIED_ASSET = "asset_77f2d9d5757a"
_COPIED_ROW = {
    "kind": "card",
    "name": "a2_spin_shadow",
    "asset_id": "asset_77f2d9d5757a",
    "recipe": "a2_spin_shadow",
}
_ENV_KEYS = (
    "QAGENT_QDATA_URL",
    "QAGENT_QDATA_HOME",
    "QAGENT_QDATA_BIN",
    "QAGENT_QDATA_PYTHON",
    "QAGENT_DATA_DIR",
    "QAGENT_ELN_FILE",
    "QAGENT_KNOWLEDGE_PATH",
)
_ROW_KEYS = frozenset({"kind", "name", HANDLE_ASSET, "recipe"})
_FORBIDDEN = (
    "bitstrings",
    "pauli_terms",
    "counts_full",
    "result_full",
    "qasm",
    "qasm3",
    "body",
    HANDLE_TWIN,
    "Pauli",
    "OPENQASM",
)


@contextmanager
def isolated_store_env() -> Iterator[None]:
    previous = {key: os.environ.get(key) for key in _ENV_KEYS}
    for key in _ENV_KEYS:
        os.environ.pop(key, None)
    _STORE.mkdir(parents=True, exist_ok=True)
    os.environ["QAGENT_DATA_DIR"] = str(_STORE)
    os.environ["QAGENT_ELN_FILE"] = str(_STORE / "eln.jsonl")
    try:
        yield
    finally:
        for key in _ENV_KEYS:
            os.environ.pop(key, None)
        for key, value in previous.items():
            if value is not None:
                os.environ[key] = value


def _keys(obj: object) -> set[str]:
    found: set[str] = set()
    if isinstance(obj, dict):
        for key, value in obj.items():
            found.add(str(key))
            found.update(_keys(value))
    elif isinstance(obj, list):
        for item in obj:
            found.update(_keys(item))
    return found


def _no_forbidden(payload: Mapping[str, Any]) -> None:
    keys = _keys(payload)
    blob = json.dumps(payload, ensure_ascii=False)
    assert HANDLE_TWIN not in keys
    assert HANDLE_TWIN not in blob
    for name in _FORBIDDEN:
        if name in {"Pauli", "OPENQASM"}:
            assert name not in blob
            continue
        assert name not in keys
        if name in {"bitstrings", "OPENQASM"}:
            assert name not in blob


def _seed_old_cards(count: int) -> None:
    path = _STORE / "qdata.json"
    data = load_json(path, {"assets": {}, "jobs": {}, "records": {}})
    assets = data.setdefault("assets", {})
    for index in range(count):
        asset_id = f"asset_old_{index:02d}"
        assets[asset_id] = {
            "asset_id": asset_id,
            "recipe": "a2_chem_pes",
            HANDLE_TWIN: "must-not-list",
            "summary": {
                "recipe": "a2_chem_pes",
                "pauli_terms": ["Z0 X1 Y2"],
                "bitstrings": ["00", "11"],
                "rows": [1, 2],
                "counts_full": {"00": 4},
                "result_full": {"energy": -1.0},
                "qasm3": "OPENQASM 3.0; qubit[2] q;",
                "body": "OPENQASM 3.0; qubit[2] q;",
            },
        }
    save_json(path, data)


def test_newest_card_survives_over_budget() -> None:
    if _STORE.exists():
        shutil.rmtree(_STORE)
    _STORE.mkdir(parents=True, exist_ok=True)
    _seed_old_cards(_OLD_COUNT)
    with isolated_store_env():
        assert os.environ.get("QAGENT_DATA_DIR") == str(_STORE)
        assert not os.environ.get("QAGENT_QDATA_URL")
        ran = invoke(
            "qdata_run_recipe",
            "lab",
            {"name": _RECIPE, "shots": _SHOTS},
        )
        listed = invoke("qdata_list_assets", "lab", {})
    assert ran.status == "ok", f"run expected ok, got {ran.status}: {ran.error}"
    run_payload = dict(ran.payload or {})
    assert run_payload, "run_recipe returned empty payload"
    asset_id = str(run_payload.get(HANDLE_ASSET) or "").strip()
    assert asset_id, "no asset_id — A-05h is not done"
    summary = run_payload.get("summary") if isinstance(run_payload.get("summary"), dict) else {}
    source = str(summary.get("source") or "")
    assert source in {"qagent-local-card", "qdata-cli"}, f"source={source!r}"
    assert summary.get("recipe") == _RECIPE
    _no_forbidden(run_payload)
    assert HANDLE_TWIN not in _keys(run_payload)
    assert listed.status == "ok", f"list expected ok, got {listed.status}: {listed.error}"
    list_payload = dict(listed.payload or {})
    assets = list_payload.get("assets")
    assert isinstance(assets, list), f"assets={assets!r}"
    assert len(assets) <= _CATALOG_CAP, f"catalog {len(assets)} > {_CATALOG_CAP}"
    assert any(
        isinstance(row, dict) and row.get(HANDLE_ASSET) == asset_id for row in assets
    ), f"list missing asset_id {asset_id}: {assets}"
    assert not any(
        isinstance(row, dict) and row.get(HANDLE_ASSET) == "asset_old_00" for row in assets
    ), f"oldest card should be squeezed, got {assets}"
    _no_forbidden(list_payload)
    assert HANDLE_TWIN not in _keys(list_payload)
    assert "summary" not in _keys(list_payload)
    hit = next(row for row in assets if isinstance(row, dict) and row.get(HANDLE_ASSET) == asset_id)
    assert set(hit) <= _ROW_KEYS
    assert hit.get("kind") == "card"
    for row in assets:
        assert isinstance(row, dict)
        assert set(row) <= _ROW_KEYS
    print(f"newest asset_id={asset_id} catalog_row={hit} n={len(assets)} source={source}")
    print(f"list={json.dumps(assets, ensure_ascii=False)}")


def test_note_copies_hit() -> None:
    assert _NOTE.is_file(), f"missing {_NOTE}"
    text = _NOTE.read_text(encoding="utf-8")
    assert "_card_rows" in text
    assert "[-limit:]" in text or "items()[-limit:]" in text
    assert "117" in text or "120" in text
    assert _COPIED_ASSET in text
    assert json.dumps(_COPIED_ROW, ensure_ascii=False) in text or all(
        f'"{key}": "{value}"' in text for key, value in _COPIED_ROW.items()
    )
    assert _RECIPE in text
    assert "invoke" in text
    assert "qdata_run_recipe" in text
    assert "qdata_list_assets" in text
    assert "asset_id" in text
    assert "QAGENT_DATA_DIR" in text
    assert "不算 G0" in text
    assert "G0 已通过" not in text
    assert "skip 当绿" in text
    assert "未 commit" in text
    assert "20" in text


def test_this_file_does_not_skip() -> None:
    text = Path(__file__).read_text(encoding="utf-8")
    assert ("pytest" + ".skip") not in text
    assert ("unittest" + ".skip") not in text
    assert ("skip" + "Test") not in text


def test_adapter_keeps_tail() -> None:
    src = (ROOT / "src" / "qagent" / "adapters" / "qdata.py").read_text(encoding="utf-8")
    assert "items())[-limit:]" in src
    assert HANDLE_TWIN not in src
    assert "import qdata\n" not in src
    assert "from qdata " not in src
    assert "from qdata." not in src


def main() -> int:
    if _STORE.exists():
        shutil.rmtree(_STORE)
    failed = 0
    for name, fn in (
        ("newest_card_survives_over_budget", test_newest_card_survives_over_budget),
        ("note_copies_hit", test_note_copies_hit),
        ("this_file_does_not_skip", test_this_file_does_not_skip),
        ("adapter_keeps_tail", test_adapter_keeps_tail),
    ):
        try:
            fn()
            print(f"ok  {name}")
        except Exception:
            failed += 1
            print(f"FAIL {name}")
            traceback.print_exc()
    if _STORE.exists():
        shutil.rmtree(_STORE)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
