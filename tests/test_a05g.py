"""A-05g: live invoke(run_recipe) then list_assets must show that card. Skip-as-green is incomplete."""

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
sys.path.insert(0, str(ROOT / "src"))

from qagent.adapters.homes import qdata_bin
from qagent.adapters.qdata import _CATALOG_CAP
from qagent.models.handles import HANDLE_ASSET, HANDLE_TWIN
from qagent.services.invoke import invoke

_LIVE_HOME = "/Users/shl/nvidia/qdata"
_RECIPE = "a2_spin_shadow"
_SHOTS = 8
_NOTE = ROOT / "docs" / "execution" / "A-05g_live_catalog.md"
_OLD_LIVE = ROOT / "docs" / "execution" / "A-05_live.md"
_STORE = ROOT / ".qagent" / "test-a05g-store"
_COPIED_ASSET = "asset_ffe79d915e4c"
_COPIED_ROW = {
    "kind": "card",
    "name": "a2_spin_shadow",
    "asset_id": "asset_ffe79d915e4c",
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
def live_qdata_env() -> Iterator[None]:
    previous = {key: os.environ.get(key) for key in _ENV_KEYS}
    for key in _ENV_KEYS:
        os.environ.pop(key, None)
    _STORE.mkdir(parents=True, exist_ok=True)
    os.environ["QAGENT_QDATA_HOME"] = _LIVE_HOME
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


def test_live_run_then_list_has_card() -> None:
    home = Path(_LIVE_HOME)
    exe = home / ".venv" / "bin" / "qdata"
    assert home.is_dir(), f"live QAGENT_QDATA_HOME missing: {home}"
    assert exe.is_file(), f"live qdata CLI missing: {exe}"
    with live_qdata_env():
        assert os.environ.get("QAGENT_QDATA_HOME") == _LIVE_HOME
        assert os.environ.get("QAGENT_DATA_DIR") == str(_STORE)
        assert not os.environ.get("QAGENT_QDATA_URL")
        assert qdata_bin() == str(exe)
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
    assert asset_id, "no live asset_id — A-05g is not done"
    summary = run_payload.get("summary") if isinstance(run_payload.get("summary"), dict) else {}
    assert summary.get("source") == "qdata-cli", f"source={summary.get('source')!r}"
    assert summary.get("source") != "qagent-local-card"
    assert summary.get("recipe") == _RECIPE
    _no_forbidden(run_payload)
    assert listed.status == "ok", f"list expected ok, got {listed.status}: {listed.error}"
    list_payload = dict(listed.payload or {})
    assets = list_payload.get("assets")
    assert isinstance(assets, list), f"assets={assets!r}"
    assert len(assets) <= _CATALOG_CAP, f"catalog {len(assets)} > {_CATALOG_CAP}"
    assert any(
        isinstance(row, dict) and row.get(HANDLE_ASSET) == asset_id for row in assets
    ), f"list missing asset_id {asset_id}: {assets}"
    _no_forbidden(list_payload)
    assert HANDLE_TWIN not in _keys(list_payload)
    assert "summary" not in _keys(list_payload)
    hit = next(row for row in assets if isinstance(row, dict) and row.get(HANDLE_ASSET) == asset_id)
    assert set(hit) <= _ROW_KEYS
    assert hit.get("kind") == "card"
    for row in assets:
        assert isinstance(row, dict)
        assert set(row) <= _ROW_KEYS
    print(f"live asset_id={asset_id} catalog_row={hit} n={len(assets)}")


def test_note_copies_hit() -> None:
    assert _NOTE.is_file(), f"missing {_NOTE}"
    text = _NOTE.read_text(encoding="utf-8")
    assert _COPIED_ASSET in text
    assert json.dumps(_COPIED_ROW, ensure_ascii=False) in text or all(
        f'"{key}": "{value}"' in text for key, value in _COPIED_ROW.items()
    )
    assert "qdata-cli" in text
    assert _RECIPE in text
    assert "invoke" in text
    assert "qdata_run_recipe" in text
    assert "qdata_list_assets" in text
    assert "asset_id" in text
    assert "QAGENT_DATA_DIR" in text
    assert "QAGENT_QDATA_HOME" in text
    assert "不算 G0" in text
    assert "不算 G2" in text
    assert "不算接线 Pennylane" in text
    assert "G0 已通过" not in text
    assert "skip 当绿" in text
    assert "未 commit" in text
    assert "apply_env" in text
    assert "workplace.json" in text
    assert "QAGENT_QDATA_URL" in text
    assert "A-05_live" in text
    assert "未打" in text
    assert "未证明" in text


def test_a05_live_contract_untouched() -> None:
    assert _OLD_LIVE.is_file(), f"missing {_OLD_LIVE}"
    text = _OLD_LIVE.read_text(encoding="utf-8")
    assert "未打" in text
    assert "未证明" in text
    assert "unproven" in text.lower()
    assert "不许**说「活目录已通」" in text or "不许说「活目录已通」" in text.replace("**", "")


def test_this_file_does_not_skip() -> None:
    text = Path(__file__).read_text(encoding="utf-8")
    assert ("pytest" + ".skip") not in text
    assert ("unittest" + ".skip") not in text
    assert ("skip" + "Test") not in text
    assert ("from qagent.services." + "workplace") not in text
    assert ("apply" + "_env(") not in text


def main() -> int:
    if _STORE.exists():
        shutil.rmtree(_STORE)
    failed = 0
    for name, fn in (
        ("live_run_then_list_has_card", test_live_run_then_list_has_card),
        ("note_copies_hit", test_note_copies_hit),
        ("a05_live_contract_untouched", test_a05_live_contract_untouched),
        ("this_file_does_not_skip", test_this_file_does_not_skip),
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
