"""A-01g: live invoke(qdata_run_recipe) must hit qdata-cli + asset_id. Skip-as-green is incomplete."""

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
from qagent.models.handles import HANDLE_ASSET, HANDLE_TWIN
from qagent.services.invoke import invoke

_LIVE_HOME = "/Users/shl/nvidia/qdata"
_RECIPE = "a2_spin_shadow"
_SHOTS = 8
_NOTE = ROOT / "docs" / "execution" / "A-01g_live_hit.md"
_OLD_LIVE = ROOT / "docs" / "execution" / "A-01_live.md"
_STORE = ROOT / ".qagent" / "test-a01g-store"
_COPIED_ASSET = "asset_182483a482ba"
_ENV_KEYS = (
    "QAGENT_QDATA_URL",
    "QAGENT_QDATA_HOME",
    "QAGENT_QDATA_BIN",
    "QAGENT_QDATA_PYTHON",
    "QAGENT_DATA_DIR",
    "QAGENT_ELN_FILE",
)
_CIRCUIT_BODY = ("qasm", "qasm3", "circuit", "circuit_body", "OPENQASM")


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
    assert "circuit_id" not in payload
    for name in _CIRCUIT_BODY:
        assert name not in keys
        if name == "OPENQASM":
            assert name not in blob


def test_live_invoke_qdata_cli() -> None:
    home = Path(_LIVE_HOME)
    exe = home / ".venv" / "bin" / "qdata"
    assert home.is_dir(), f"live QAGENT_QDATA_HOME missing: {home}"
    assert exe.is_file(), f"live qdata CLI missing: {exe}"
    with live_qdata_env():
        assert os.environ.get("QAGENT_QDATA_HOME") == _LIVE_HOME
        assert not os.environ.get("QAGENT_QDATA_URL")
        assert qdata_bin() == str(exe)
        invoked = invoke(
            "qdata_run_recipe",
            "lab",
            {"name": _RECIPE, "shots": _SHOTS, "data_dir": str(_STORE)},
        )
    assert invoked.status == "ok", f"expected ok, got {invoked.status}: {invoked.error}"
    payload = dict(invoked.payload or {})
    assert payload, "invoke returned empty payload"
    asset_id = str(payload.get(HANDLE_ASSET) or "").strip()
    assert asset_id, "no live asset_id — A-01g is not done"
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    assert summary.get("source") == "qdata-cli", f"source={summary.get('source')!r}"
    assert summary.get("source") != "qagent-local-card"
    assert summary.get("recipe") == _RECIPE
    _no_forbidden(payload)
    print(f"live asset_id={asset_id} source=qdata-cli recipe={_RECIPE}")


def test_note_copies_hit() -> None:
    assert _NOTE.is_file(), f"missing {_NOTE}"
    text = _NOTE.read_text(encoding="utf-8")
    assert _COPIED_ASSET in text
    assert "qdata-cli" in text
    assert _RECIPE in text
    assert "invoke" in text
    assert "asset_id" in text
    assert "不算 G0" in text
    assert "不算 G2" in text
    assert "不算接线 Pennylane" in text
    assert "G0 已通过" not in text
    assert "没有** `asset_id` 字段" in text
    assert "A-01_live" in text
    assert "未打" in text
    assert "未证明" in text


def test_a01_live_contract_untouched() -> None:
    assert _OLD_LIVE.is_file(), f"missing {_OLD_LIVE}"
    text = _OLD_LIVE.read_text(encoding="utf-8")
    assert "未打" in text
    assert "未证明" in text
    assert "unproven" in text.lower()
    assert "活 qdata **未证明**" in text


def main() -> int:
    if _STORE.exists():
        shutil.rmtree(_STORE)
    failed = 0
    for name, fn in (
        ("live_invoke_qdata_cli", test_live_invoke_qdata_cli),
        ("note_copies_hit", test_note_copies_hit),
        ("a01_live_contract_untouched", test_a01_live_contract_untouched),
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
