"""A-05i: list_assets reads live GET /v1/assets. Skip-as-green is incomplete."""

from __future__ import annotations

import json
import os
import shutil
import sys
import threading
import time
import traceback
import urllib.error
import urllib.request
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Iterator, Mapping

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT
sys.path.insert(0, str(ROOT / "src"))

from qagent.adapters.qdata import _ALLOWED, _CATALOG_CAP, _ROW_KEYS
from qagent.models.handles import HANDLE_ASSET, HANDLE_TWIN
from qagent.services.invoke import invoke

_NOTE = REPO / "docs" / "execution" / "A-05i_live_http_assets.md"
_LIVE_URL = "http://127.0.0.1:8787"
_STORE = ROOT / ".qagent" / "test-a05i-store"
_COPIED_ASSET = "209528abb69468e9041518ee7f8fc4dc4ddc97eb62dfedbf771a664fd4ef7170"
_FIXTURE_ASSET = "asset_a05i_http"
_DEAD_URL = "http://127.0.0.1:1"
_ENV_KEYS = (
    "QAGENT_QDATA_URL",
    "QAGENT_QDATA_HOME",
    "QAGENT_QDATA_BIN",
    "QAGENT_QDATA_PYTHON",
    "QAGENT_DATA_DIR",
    "QAGENT_ELN_FILE",
    "QAGENT_KNOWLEDGE_PATH",
)
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
    "created_utc",
)


@contextmanager
def isolated_list_env(**overrides: str) -> Iterator[None]:
    previous = {key: os.environ.get(key) for key in _ENV_KEYS}
    for key in _ENV_KEYS:
        os.environ.pop(key, None)
    _STORE.mkdir(parents=True, exist_ok=True)
    os.environ["QAGENT_DATA_DIR"] = str(_STORE)
    os.environ["QAGENT_ELN_FILE"] = str(_STORE / "eln.jsonl")
    os.environ.update(overrides)
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


def _http_json(url: str, method: str = "GET", body: dict[str, Any] | None = None) -> Any:
    request = urllib.request.Request(
        url,
        data=None if body is None else json.dumps(body).encode("utf-8"),
        method=method,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=8) as response:
        raw = response.read().decode("utf-8")
    return json.loads(raw) if raw else {}


def _healthz() -> dict[str, Any]:
    try:
        parsed = _http_json(f"{_LIVE_URL}/v1/healthz")
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise AssertionError(f":8787 healthz not reachable: {exc}") from exc
    if not isinstance(parsed, dict):
        raise AssertionError(f":8787 healthz must be an object, got {type(parsed).__name__}")
    return parsed


def _ensure_live_asset() -> str:
    try:
        rows = _http_json(f"{_LIVE_URL}/v1/assets")
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise AssertionError(f":8787 /v1/assets not reachable: {exc}") from exc
    if isinstance(rows, list):
        for item in rows:
            if isinstance(item, dict) and item.get(HANDLE_ASSET):
                return str(item[HANDLE_ASSET])
    try:
        queued = _http_json(
            f"{_LIVE_URL}/v1/jobs/sample-to-solver",
            "POST",
            {"provider": "chem.h2_sto3g", "shots_grid": [128], "m_grid": [4], "seed": 0},
        )
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise AssertionError(f"sample-to-solver submit failed: {exc}") from exc
    job_id = str((queued or {}).get("job_id") or "").strip()
    assert job_id, f"no job_id from sample-to-solver: {queued!r}"
    for _ in range(80):
        time.sleep(0.25)
        try:
            got = _http_json(f"{_LIVE_URL}/v1/jobs/{job_id}")
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
            continue
        if not isinstance(got, dict):
            continue
        if got.get("status") == "failed":
            raise AssertionError(f"sample-to-solver failed: {got!r}")
        result = got.get("result") if isinstance(got.get("result"), dict) else {}
        asset_id = str(result.get(HANDLE_ASSET) or "").strip()
        if got.get("status") == "done" and asset_id:
            return asset_id
    raise AssertionError(f"sample-to-solver did not finish with asset_id: {job_id}")


class _FatAssetHandler(BaseHTTPRequestHandler):
    def log_message(self, *_args: object) -> None:
        return

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path != "/v1/assets":
            self.send_error(404)
            return
        payload = [
            {
                HANDLE_ASSET: _FIXTURE_ASSET,
                "kind": "sample-to-solver",
                "created_utc": "2026-08-27T00:00:00Z",
                "pauli_terms": ["Z0 X1 Y2"],
                "bitstrings": ["00", "11"],
                "body": "OPENQASM 3.0; qubit[2] q;",
            }
        ]
        blob = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(blob)))
        self.end_headers()
        self.wfile.write(blob)


@contextmanager
def fixture_assets_url() -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _FatAssetHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    try:
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_live_http_assets_appear() -> None:
    health = _healthz()
    assert health.get("status") == "ok", f"healthz={health!r}"
    asset_id = _ensure_live_asset()
    assert asset_id, "no live asset_id — A-05i is not done"
    if _STORE.exists():
        shutil.rmtree(_STORE)
    _STORE.mkdir(parents=True, exist_ok=True)
    with isolated_list_env(QAGENT_QDATA_URL=_LIVE_URL):
        assert os.environ.get("QAGENT_QDATA_URL") == _LIVE_URL
        listed = invoke("qdata_list_assets", "lab", {})
    assert listed.status == "ok", f"list expected ok, got {listed.status}: {listed.error}"
    payload = dict(listed.payload or {})
    assets = payload.get("assets")
    assert isinstance(assets, list), f"assets={assets!r}"
    assert len(assets) <= _CATALOG_CAP
    hit = next(
        (row for row in assets if isinstance(row, dict) and row.get(HANDLE_ASSET) == asset_id),
        None,
    )
    assert hit is not None, f"list missing live asset {asset_id}: {assets}"
    assert hit.get("kind") == "card"
    assert set(hit) <= set(_ROW_KEYS)
    recipes = [row.get("recipe") for row in assets if isinstance(row, dict) and row.get("kind") == "recipe"]
    assert recipes == list(_ALLOWED)
    _no_forbidden(payload)
    print(f"live asset_id={asset_id} catalog_row={hit} n={len(assets)}")


def test_fixture_strips_fat_http_row() -> None:
    if _STORE.exists():
        shutil.rmtree(_STORE)
    _STORE.mkdir(parents=True, exist_ok=True)
    with fixture_assets_url() as url:
        with isolated_list_env(QAGENT_QDATA_URL=url):
            listed = invoke("qdata_list_assets", "lab", {})
    assert listed.status == "ok", f"list expected ok, got {listed.status}: {listed.error}"
    payload = dict(listed.payload or {})
    assets = payload.get("assets")
    assert isinstance(assets, list)
    hit = next(
        (row for row in assets if isinstance(row, dict) and row.get(HANDLE_ASSET) == _FIXTURE_ASSET),
        None,
    )
    assert hit is not None, f"fixture asset missing: {assets}"
    assert hit.get("kind") == "card"
    assert hit.get("name") == "sample-to-solver"
    assert set(hit) <= set(_ROW_KEYS)
    _no_forbidden(payload)
    print(f"fixture row={hit}")


def test_dead_url_is_honest() -> None:
    if _STORE.exists():
        shutil.rmtree(_STORE)
    _STORE.mkdir(parents=True, exist_ok=True)
    with isolated_list_env(QAGENT_QDATA_URL=_DEAD_URL):
        listed = invoke("qdata_list_assets", "lab", {})
    assert listed.status != "ok", f"dead URL must not list ok: {listed.payload}"
    blob = json.dumps({"error": listed.error, "payload": listed.payload}, ensure_ascii=False)
    assert HANDLE_TWIN not in blob
    print(f"dead url status={listed.status} error={listed.error}")


def test_note_copies_hit() -> None:
    assert _NOTE.is_file(), f"missing {_NOTE}"
    text = _NOTE.read_text(encoding="utf-8")
    assert _COPIED_ASSET in text
    assert "/v1/assets" in text
    assert "qdata_list_assets" in text
    assert "invoke" in text
    assert _LIVE_URL in text
    assert "QAGENT_QDATA_URL" in text
    assert HANDLE_ASSET in text
    assert "sample-to-solver" in text
    assert "不算 G0" in text
    assert "不算 G2" in text
    assert "不算接线 Pennylane" in text
    assert "G0 已通过" not in text
    assert "skip 当绿" in text
    assert "未 commit" in text
    assert "apply_env" in text
    assert "20" in text


def test_adapter_hits_http_list() -> None:
    src = (ROOT / "src" / "qagent" / "adapters" / "qdata.py").read_text(encoding="utf-8")
    assert "/v1/assets" in src
    assert "_qdata_http_list" in src
    assert "_remote_card_rows" in src
    assert HANDLE_TWIN not in src
    assert "import qdata\n" not in src
    assert "from qdata " not in src
    assert "from qdata." not in src


def test_this_file_does_not_skip() -> None:
    text = Path(__file__).read_text(encoding="utf-8")
    assert ("pytest" + ".skip") not in text
    assert ("unittest" + ".skip") not in text
    assert ("skip" + "Test") not in text
    assert ("from qagent.services." + "workplace") not in text


def main() -> int:
    if _STORE.exists():
        shutil.rmtree(_STORE)
    failed = 0
    for name, fn in (
        ("live_http_assets_appear", test_live_http_assets_appear),
        ("fixture_strips_fat_http_row", test_fixture_strips_fat_http_row),
        ("dead_url_is_honest", test_dead_url_is_honest),
        ("note_copies_hit", test_note_copies_hit),
        ("adapter_hits_http_list", test_adapter_hits_http_list),
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
