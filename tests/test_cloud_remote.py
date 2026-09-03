"""Company cloud URLs: env > workplace > file. Empty is not localhost."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from qagent.adapters.cloud import qdata_url, qchem_url, twin_url, hub_url, resolve_cloud_url
from qagent.adapters.docs import WiredDocs
from qagent.adapters.hub import NativeHub
from qagent.models.handles import HANDLE_ASSET, HANDLE_TWIN
from qagent.services.health import science_health
from qagent.services.invoke import invoke

_ENV_KEYS = (
    "QAGENT_QDATA_URL",
    "QAGENT_QCHEM_URL",
    "QAGENT_TWIN_URL",
    "QAGENT_ALGO_HUB_URL",
    "QAGENT_QDATA_HOME",
    "QAGENT_QCHEM_HOME",
    "QAGENT_IONSTACK_HOME",
    "QAGENT_CLOUD_FILE",
    "QAGENT_WORKPLACE_FILE",
    "QAGENT_SECRETS_FILE",
    "QAGENT_DATA_DIR",
)


class _HubHandler(BaseHTTPRequestHandler):
    def log_message(self, *_args) -> None:
        return

    def do_GET(self) -> None:  # noqa: N802
        payload = {
            "api_version": "hub/v1",
            "assets": [
                {
                    "id": "org.remote.demo",
                    "kind": "algorithm",
                    "title": "Remote fixture",
                    "summary": "HTTP hub index",
                }
            ],
        }
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


class _QchemHandler(BaseHTTPRequestHandler):
    def log_message(self, *_args) -> None:
        return

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(length)
        if self.path == "/v1/run":
            payload = {
                HANDLE_ASSET: "asset_remote1",
                "summary": {"scenario": "minimal_vqe", "energy": -1.1},
                "pauli_terms": "MUST_NOT_LEAK",
                "qasm3": "OPENQASM 3.0;",
            }
        elif self.path == "/v1/parity":
            payload = {"table_id": "parity_remote1"}
        else:
            self.send_response(404)
            self.end_headers()
            return
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def _isolate(folder: Path) -> dict[str, str | None]:
    previous = {key: os.environ.get(key) for key in _ENV_KEYS}
    for key in _ENV_KEYS:
        os.environ.pop(key, None)
    os.environ["QAGENT_CLOUD_FILE"] = str(folder / "company.json")
    os.environ["QAGENT_WORKPLACE_FILE"] = str(folder / "workplace.json")
    os.environ["QAGENT_SECRETS_FILE"] = str(folder / "secrets.json")
    store = ROOT / ".qagent" / "test-cloud-remote-store"
    store.mkdir(parents=True, exist_ok=True)
    os.environ["QAGENT_DATA_DIR"] = str(store)
    (folder / "company.json").write_text(
        json.dumps({"qdata_url": "", "qchem_url": "", "twin_url": "", "hub_url": ""}),
        encoding="utf-8",
    )
    (folder / "workplace.json").write_text("{}", encoding="utf-8")
    return previous


def _restore(previous: dict[str, str | None]) -> None:
    for key, value in previous.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def _serve(handler) -> tuple[ThreadingHTTPServer, str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    return server, f"http://{host}:{port}"


def test_empty_url_is_not_localhost() -> None:
    with tempfile.TemporaryDirectory() as raw:
        previous = _isolate(Path(raw))
        try:
            assert qdata_url() is None
            assert qchem_url() is None
            assert twin_url() is None
            assert hub_url() is None
            health = science_health()
            assert health["qdata_live"] is False
            assert health["twin_live"] is False
            assert health["qdata_cloud"] == "not_configured"
            assert health["twin_cloud"] == "not_configured"
            assert health["qchem_cloud"] == "not_configured"
            assert "8787" not in json.dumps(health["cloud"])
            assert "8765" not in json.dumps(health["cloud"])
        finally:
            _restore(previous)


def test_company_file_then_env_wins() -> None:
    with tempfile.TemporaryDirectory() as raw:
        folder = Path(raw)
        previous = _isolate(folder)
        try:
            folder.joinpath("company.json").write_text(
                json.dumps({"qdata_url": "https://file.example", "qchem_url": "", "twin_url": "", "hub_url": ""}),
                encoding="utf-8",
            )
            assert qdata_url() == "https://file.example"
            os.environ["QAGENT_QDATA_URL"] = "https://env.example"
            assert qdata_url() == "https://env.example"
            os.environ.pop("QAGENT_QDATA_URL")
            folder.joinpath("workplace.json").write_text(
                json.dumps({"qdata_url": "https://wp.example"}),
                encoding="utf-8",
            )
            assert resolve_cloud_url("qdata_url") == "https://wp.example"
        finally:
            _restore(previous)


def test_docs_default_company_knowledge() -> None:
    hits = WiredDocs().search({"query": "TwinRun circuit.body mode shots"})
    assert hits.get("empty") is False
    knowledge = [item for item in hits.get("hits") or [] if item.get("source") == "knowledge"]
    assert knowledge
    paths = {item["path"].replace("\\", "/") for item in knowledge}
    assert "manuals/twinrun_fields.md" in paths


def test_qchem_http_fixture() -> None:
    server, url = _serve(_QchemHandler)
    with tempfile.TemporaryDirectory() as raw:
        previous = _isolate(Path(raw))
        os.environ["QAGENT_QCHEM_URL"] = url
        try:
            result = invoke("qchem_run", "lab", {"scenario": "minimal_vqe"})
            assert result.status == "ok", result.error
            assert result.payload
            assert result.payload.get(HANDLE_ASSET)
            blob = json.dumps(result.payload)
            assert "MUST_NOT_LEAK" not in blob
            assert "OPENQASM" not in blob
            assert HANDLE_TWIN not in (result.payload or {})
            parity = invoke("qchem_export_parity", "lab", {HANDLE_ASSET: result.payload[HANDLE_ASSET]})
            assert parity.status == "ok", parity.error
            assert parity.payload and parity.payload.get("table_id") == "parity_remote1"
        finally:
            server.shutdown()
            _restore(previous)


def test_hub_remote_index() -> None:
    server, url = _serve(_HubHandler)
    with tempfile.TemporaryDirectory() as raw:
        previous = _isolate(Path(raw))
        os.environ["QAGENT_ALGO_HUB_URL"] = url
        try:
            listed = NativeHub().list_assets({})
            assert listed["source"] == "remote"
            ids = [row["id"] for row in listed["assets"]]
            assert "org.remote.demo" in ids
            assert HANDLE_TWIN not in json.dumps(listed)
        finally:
            server.shutdown()
            _restore(previous)


def main() -> int:
    failed = 0
    for name, fn in (
        ("empty_url_is_not_localhost", test_empty_url_is_not_localhost),
        ("company_file_then_env_wins", test_company_file_then_env_wins),
        ("docs_default_company_knowledge", test_docs_default_company_knowledge),
        ("qchem_http_fixture", test_qchem_http_fixture),
        ("hub_remote_index", test_hub_remote_index),
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
