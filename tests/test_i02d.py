"""I-02d: remote job HTTP carries Bearer. Loopback Twin/qdata do not."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import traceback
import urllib.request
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT
sys.path.insert(0, str(ROOT / "src"))

from qagent.adapters.support import is_loopback_url, json_headers, try_http_json
from qagent.adapters.workplace_store import WorkplaceStore
from qagent.services.workplace import job_auth_headers, save_workplace, workplace_status

_NOTE = REPO / "docs" / "execution" / "I-02d_job_headers.md"
_HPC = "i02d-hpc-n3v3r-echo-4m9q"
_QTM = "i02d-qtm-n3v3r-echo-1w8r"
_ENV = (
    "QAGENT_WORKPLACE_FILE",
    "QAGENT_SECRETS_FILE",
    "QAGENT_DSH_ENV_FILE",
)


@contextmanager
def isolated_workplace():
    previous = {key: os.environ.get(key) for key in _ENV}
    tmp = tempfile.TemporaryDirectory()
    try:
        folder = Path(tmp.name)
        os.environ["QAGENT_WORKPLACE_FILE"] = str(folder / "workplace.json")
        os.environ["QAGENT_SECRETS_FILE"] = str(folder / "secrets.json")
        os.environ["QAGENT_DSH_ENV_FILE"] = str(folder / "dsh.env")
        yield folder
    finally:
        tmp.cleanup()
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def test_loopback_skips_bearer() -> None:
    with isolated_workplace():
        save_workplace(
            {"hpc_host": "hpc.example", "quantum_host": "qpu.example"},
            {"hpc_secret": _HPC, "quantum_secret": _QTM},
        )
        assert is_loopback_url("http://127.0.0.1:8765/v1/twin/identity")
        assert is_loopback_url("http://localhost:8787/v1/assets")
        assert not is_loopback_url("https://hpc.example/v1/jobs")
        loop = json_headers("http://127.0.0.1:8765/v1/twin/identity")
        assert "Authorization" not in loop
        assert _HPC not in json.dumps(loop)
        remote = json_headers("https://hpc.example/v1/jobs")
        assert remote.get("Authorization") == f"Bearer {_HPC}"
        status = json.dumps(workplace_status(), ensure_ascii=False)
        assert _HPC not in status
        assert _QTM not in status
        assert job_auth_headers()["Authorization"] == f"Bearer {_HPC}"
        assert WorkplaceStore().local_auth_headers()["Authorization"] == f"Bearer {_HPC}"


def test_live_loopback_twin_still_works() -> None:
    live = try_http_json("GET", "/v1/twin/identity")
    assert live is not None, "Twin :8765 must stay reachable without job Bearer"
    assert live.get("preset")
    assert "twin_id" not in json.dumps({"preset": live.get("preset"), "n_qubits": live.get("n_qubits")})
    print(f"loopback twin preset={live.get('preset')} n_qubits={live.get('n_qubits')}")


def test_live_qdata_loopback_still_works() -> None:
    req = urllib.request.Request("http://127.0.0.1:8787/v1/healthz")
    with urllib.request.urlopen(req, timeout=3) as response:
        payload = json.loads(response.read().decode("utf-8"))
    assert payload.get("status") == "ok"
    local = json_headers("http://127.0.0.1:8787/v1/healthz")
    assert "Authorization" not in local


def test_note_copies_hit() -> None:
    assert _NOTE.is_file(), _NOTE
    text = _NOTE.read_text(encoding="utf-8")
    assert "json_headers" in text
    assert "loopback" in text or "127.0.0.1" in text
    assert "Bearer" in text
    assert "不算 G0" in text
    assert "G0 已通过" not in text
    assert "skip 当绿" in text
    assert "未 commit" in text
    assert "Authorization" in text


def test_this_file_does_not_skip() -> None:
    text = Path(__file__).read_text(encoding="utf-8")
    assert ("pytest" + ".skip") not in text
    assert ("unittest" + ".skip") not in text
    assert ("skip" + "Test") not in text


def main() -> int:
    failed = 0
    for name, fn in (
        ("loopback_skips_bearer", test_loopback_skips_bearer),
        ("live_loopback_twin_still_works", test_live_loopback_twin_still_works),
        ("live_qdata_loopback_still_works", test_live_qdata_loopback_still_works),
        ("note_copies_hit", test_note_copies_hit),
        ("this_file_does_not_skip", test_this_file_does_not_skip),
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
