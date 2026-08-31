"""A-05 short asset catalog. Isolates store. No pytest required."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import traceback
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from qagent.adapters.qdata import (
    WiredQData,
    _ALLOWED,
    _CATALOG_CAP,
    _FORBIDDEN_OUT,
    _NAME_CAP,
)
from qagent.adapters.support import load_json, save_json
from qagent.models.engine import STATUS_RESERVED, STATUS_WIRED
from qagent.models.handles import HANDLE_ASSET, HANDLE_TWIN, HANDLES
from qagent.services.engines import list_engines
from qagent.services.invoke import invoke

_ENV_KEYS = (
    "QAGENT_QDATA_URL",
    "QAGENT_QDATA_HOME",
    "QAGENT_QDATA_BIN",
    "QAGENT_QDATA_PYTHON",
    "QAGENT_DATA_DIR",
    "QAGENT_KNOWLEDGE_PATH",
)
_STORE = ROOT / ".qagent" / "test-a05-store"
_CANONICAL_PACKS = ("qdata", "qchem", "ionstack", "route", "qiskit")
_FORBIDDEN_KEYS = frozenset(_FORBIDDEN_OUT | {"qasm", "qasm3", "body", HANDLE_TWIN})
_ROW_KEYS = frozenset({"kind", "name", HANDLE_ASSET, "recipe"})


@contextmanager
def isolated_catalog_env(**overrides: str) -> Iterator[None]:
    previous = {key: os.environ.get(key) for key in _ENV_KEYS}
    for key in _ENV_KEYS:
        os.environ.pop(key, None)
    os.environ.update(overrides)
    try:
        yield
    finally:
        for key in _ENV_KEYS:
            os.environ.pop(key, None)
        for key, value in previous.items():
            if value is not None:
                os.environ[key] = value


def _reset_store() -> None:
    if _STORE.exists():
        shutil.rmtree(_STORE)
    _STORE.mkdir(parents=True, exist_ok=True)


def _store_args(**extra: object) -> dict:
    _STORE.mkdir(parents=True, exist_ok=True)
    return {"data_dir": str(_STORE), "store_dir": str(_STORE), **extra}


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


def _seed_fat_cards(count: int) -> None:
    path = _STORE / "qdata.json"
    data = load_json(path, {"assets": {}, "jobs": {}, "records": {}})
    assets = data.setdefault("assets", {})
    for index in range(count):
        asset_id = f"asset_fat_{index:02d}"
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


def test_invoke_list_assets_and_engines() -> None:
    _reset_store()
    with tempfile.TemporaryDirectory() as tmp:
        Path(tmp, "hit.md").write_text("short knowledge title only\n", encoding="utf-8")
        with isolated_catalog_env(QAGENT_KNOWLEDGE_PATH=tmp):
            port = WiredQData()
            card = port.run_recipe(_store_args(name="a2_chem_pes"))
            listed = invoke("qdata_list_assets", "lab", _store_args())
            engines = invoke("qagent_list_engines", "lab", {})
            providers = invoke("qdata_list_providers", "lab", {})
    assert card.get(HANDLE_ASSET)
    assert listed.status == "ok"
    assert listed.payload is not None
    assets = listed.payload.get("assets") or []
    assert assets
    kinds = {row.get("kind") for row in assets if isinstance(row, dict)}
    assert {"recipe", "card", "knowledge"} <= kinds
    recipes = [row for row in assets if row.get("kind") == "recipe"]
    assert [row.get("recipe") for row in recipes] == list(_ALLOWED)
    cards = [row for row in assets if row.get("kind") == "card"]
    assert any(row.get(HANDLE_ASSET) == card[HANDLE_ASSET] for row in cards)
    knowledge = [row for row in assets if row.get("kind") == "knowledge"]
    assert any("hit.md" in str(row.get("name") or "") for row in knowledge)
    assert engines.status == "ok"
    assert engines.payload is not None
    pack_ids = [row["id"] for row in engines.payload.get("engines") or []]
    assert pack_ids[:5] == list(_CANONICAL_PACKS)
    assert set(_CANONICAL_PACKS) <= set(pack_ids)
    assert providers.status == "ok"
    assert providers.payload is not None
    names = [row.get("name") for row in providers.payload.get("providers") or []]
    assert names == list(_ALLOWED)


def test_no_forbidden_keys() -> None:
    _reset_store()
    _seed_fat_cards(3)
    with isolated_catalog_env():
        payload = WiredQData().list_assets(_store_args())
        invoked = invoke("qdata_list_assets", "lab", _store_args())
        providers = WiredQData().list_providers({})
    assert invoked.status == "ok"
    for blob in (payload, invoked.payload or {}, providers):
        leaked = _FORBIDDEN_KEYS & _keys(blob)
        assert not leaked, leaked
        assert HANDLE_TWIN not in _keys(blob)
        assert "summary" not in _keys(blob)
    for row in payload.get("assets") or []:
        assert set(row) <= _ROW_KEYS
        assert row.get("kind") in {"recipe", "card", "knowledge"}
        assert row.get("name")
        if row.get("kind") == "card":
            assert row.get(HANDLE_ASSET)
        if row.get("kind") == "recipe":
            assert row.get("recipe")


def test_list_length_bounded() -> None:
    _reset_store()
    _seed_fat_cards(30)
    long_recipe = "Z" * 200
    path = _STORE / "qdata.json"
    data = load_json(path, {"assets": {}, "jobs": {}, "records": {}})
    data["assets"]["asset_long"] = {
        "asset_id": "asset_long",
        "recipe": long_recipe,
        "summary": {"kind": long_recipe, "pauli_terms": ["X0" * 40]},
    }
    save_json(path, data)
    with tempfile.TemporaryDirectory() as tmp:
        for index in range(12):
            Path(tmp, f"k{index}.md").write_text(f"note {index}\n", encoding="utf-8")
        with isolated_catalog_env(QAGENT_KNOWLEDGE_PATH=tmp):
            payload = WiredQData().list_assets(_store_args())
            invoked = invoke("qdata_list_assets", "lab", _store_args())
    assets = payload["assets"]
    assert len(assets) <= _CATALOG_CAP
    assert len((invoked.payload or {}).get("assets") or []) <= _CATALOG_CAP
    assert len(assets) == _CATALOG_CAP
    for row in assets:
        assert len(str(row.get("name") or "")) <= _NAME_CAP
        if row.get("recipe"):
            assert len(str(row["recipe"])) <= _NAME_CAP


def test_no_twin_id() -> None:
    _reset_store()
    _seed_fat_cards(2)
    with isolated_catalog_env():
        payload = WiredQData().list_assets(_store_args())
        invoked = invoke("qdata_list_assets", "lab", _store_args())
        providers = invoke("qdata_list_providers", "lab", {})
    text = (ROOT / "src/qagent/adapters/qdata.py").read_text(encoding="utf-8")
    assert HANDLE_TWIN not in text
    assert HANDLE_TWIN not in _keys(payload)
    assert HANDLE_TWIN not in _keys(invoked.payload or {})
    assert HANDLE_TWIN not in _keys(providers.payload or {})
    for row in payload["assets"]:
        assert not (set(row) - _ROW_KEYS) & set(HANDLES)


def test_engines_reserved_stay_reserved() -> None:
    packs = list_engines()
    invoked = invoke("qagent_list_engines", "lab", {})
    assert invoked.status == "ok"
    assert invoked.payload is not None
    rows = invoked.payload.get("engines") or []
    ids = [row["id"] for row in rows]
    assert [pack.id for pack in packs][:5] == list(_CANONICAL_PACKS)
    assert ids[:5] == list(_CANONICAL_PACKS)
    assert set(_CANONICAL_PACKS) <= set(ids)
    assert set(_CANONICAL_PACKS) <= {pack.id for pack in packs}
    assert "pennylane" not in ids
    assert "uqc-hardware" not in ids
    for pack, row in zip(packs, rows):
        assert pack.status == row["status"]
        if pack.status == STATUS_RESERVED:
            assert row["status"] == STATUS_RESERVED
        else:
            assert pack.status == STATUS_WIRED
            assert row["status"] == STATUS_WIRED
    assert all(
        pack.status == STATUS_WIRED
        for pack in packs
        if pack.id in _CANONICAL_PACKS
    )


def main() -> int:
    if _STORE.exists():
        shutil.rmtree(_STORE)
    failed = 0
    for name, fn in (
        ("invoke_list_assets_and_engines", test_invoke_list_assets_and_engines),
        ("no_forbidden_keys", test_no_forbidden_keys),
        ("list_length_bounded", test_list_length_bounded),
        ("no_twin_id", test_no_twin_id),
        ("engines_reserved_stay_reserved", test_engines_reserved_stay_reserved),
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
