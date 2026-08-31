"""H-03f: settings homes land in dsh.env. Not wiring. No fourth handle."""

from __future__ import annotations

import os
import re
import sys
import tempfile
import traceback
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from qagent.adapters.workplace_store import dsh_env_path
from qagent.models.handles import HANDLE_ASSET, HANDLE_CIRCUIT, HANDLE_TWIN
from qagent.services.workplace import save_workplace

_NOTE = ROOT / "docs" / "execution" / "H-03f_homes_dsh_env.md"
_STORE = ROOT / "src" / "qagent" / "adapters" / "workplace_store.py"
_HANDLES = frozenset({HANDLE_CIRCUIT, HANDLE_ASSET, HANDLE_TWIN})
_ID_RE = re.compile(r"\b[a-z]+_id\b")
_HOMES = (
    ("qdata_home", "QAGENT_QDATA_HOME"),
    ("qchem_home", "QAGENT_QCHEM_HOME"),
    ("ionstack_home", "QAGENT_IONSTACK_HOME"),
    ("knowledge_path", "QAGENT_KNOWLEDGE_PATH"),
)
_LLM = "sk-h03f-llm-ok-to-mirror"
_HPC = "h03f-hpc-n3v3r-echo"
_QTM = "h03f-qtm-n3v3r-echo"
_CLOUD = "https://cloud.h03f.example"
_ENV_KEYS = (
    "QAGENT_WORKPLACE_FILE",
    "QAGENT_SECRETS_FILE",
    "QAGENT_DSH_ENV_FILE",
    "QAGENT_QDATA_HOME",
    "QAGENT_QCHEM_HOME",
    "QAGENT_IONSTACK_HOME",
    "QAGENT_KNOWLEDGE_PATH",
    "QAGENT_CLOUD_URL",
    "DEEPSEEK_BASE_URL",
    "DEEPSEEK_API_KEY",
    "DEEPSEEK_MODEL",
)


@contextmanager
def _temp_workplace():
    previous = {key: os.environ.get(key) for key in _ENV_KEYS}
    tmp = tempfile.TemporaryDirectory()
    try:
        folder = Path(tmp.name)
        os.environ["QAGENT_WORKPLACE_FILE"] = str(folder / "workplace.json")
        os.environ["QAGENT_SECRETS_FILE"] = str(folder / "secrets.json")
        os.environ["QAGENT_DSH_ENV_FILE"] = str(folder / "dsh.env")
        for key in _ENV_KEYS:
            if key.startswith("QAGENT_WORKPLACE") or key.endswith("_FILE"):
                continue
            os.environ.pop(key, None)
        yield folder
    finally:
        tmp.cleanup()
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _homes(folder: Path) -> dict[str, str]:
    return {
        "qdata_home": str(folder / "qdata-a"),
        "qchem_home": str(folder / "qchem-a"),
        "ionstack_home": str(folder / "ionstack-a"),
        "knowledge_path": str(folder / "knowledge-a"),
    }


def _dsh_text() -> str:
    return dsh_env_path().read_text(encoding="utf-8")


def _dsh_map() -> dict[str, str]:
    rows: dict[str, str] = {}
    for line in _dsh_text().splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        rows[key] = value
    return rows


def test_save_writes_four_homes() -> None:
    with _temp_workplace() as folder:
        homes = _homes(folder)
        save_workplace(
            {
                "llm_base_url": "http://127.0.0.1:9/v1",
                "llm_model": "unitqc-local",
                **homes,
            },
            {"llm_api_key": _LLM},
        )
        text = _dsh_text()
        rows = _dsh_map()
        for field, env_name in _HOMES:
            assert f"{env_name}={homes[field]}" in text
            assert rows[env_name] == homes[field]
            assert f"{env_name}=" in text
        assert "DEEPSEEK_BASE_URL=http://127.0.0.1:9/v1" in text
        assert "DEEPSEEK_MODEL=unitqc-local" in text
        assert f"DEEPSEEK_API_KEY={_LLM}" in text
        switched = str(folder / "qdata-b")
        save_workplace({"qdata_home": switched})
        rows = _dsh_map()
        assert rows["QAGENT_QDATA_HOME"] == switched
        assert rows["QAGENT_QDATA_HOME"] != homes["qdata_home"]
        assert rows["QAGENT_QCHEM_HOME"] == homes["qchem_home"]


def test_clear_home_drops_line() -> None:
    with _temp_workplace() as folder:
        homes = _homes(folder)
        save_workplace(homes)
        save_workplace({"qchem_home": ""})
        text = _dsh_text()
        rows = _dsh_map()
        assert "QAGENT_QCHEM_HOME" not in rows
        assert "QAGENT_QCHEM_HOME=" not in text
        assert f"QAGENT_QDATA_HOME={homes['qdata_home']}" in text
        assert f"QAGENT_IONSTACK_HOME={homes['ionstack_home']}" in text
        assert f"QAGENT_KNOWLEDGE_PATH={homes['knowledge_path']}" in text


def test_cloud_and_hpc_secret_stay_out() -> None:
    with _temp_workplace() as folder:
        homes = _homes(folder)
        save_workplace(
            {**homes, "cloud_url": _CLOUD},
            {"llm_api_key": _LLM, "hpc_secret": _HPC, "quantum_secret": _QTM},
        )
        text = _dsh_text()
        assert "QAGENT_CLOUD_URL" not in text
        assert _CLOUD not in text
        assert _HPC not in text
        assert _QTM not in text
        assert "hpc_secret" not in text
        assert "quantum_secret" not in text
        for field, env_name in _HOMES:
            assert f"{env_name}={homes[field]}" in text
        assert f"DEEPSEEK_API_KEY={_LLM}" in text


def test_note_homes_not_wiring() -> None:
    assert _NOTE.is_file()
    text = _NOTE.read_text(encoding="utf-8")
    assert "不算接线" in text
    assert "homes 进 dsh.env" in text
    assert "QAGENT_CLOUD_URL" in text
    assert "hpc_secret" in text


def test_no_fourth_handle() -> None:
    for path in (_STORE, _NOTE, Path(__file__)):
        extra = set(_ID_RE.findall(path.read_text(encoding="utf-8"))) - _HANDLES
        assert not extra, f"{path.name} invented handles: {sorted(extra)}"
    note = _NOTE.read_text(encoding="utf-8")
    assert HANDLE_CIRCUIT in note
    assert HANDLE_ASSET in note
    assert HANDLE_TWIN in note
    assert "twin_id=" not in note
    assert "twin_id:" not in note


def main() -> int:
    failed = 0
    for name, fn in (
        ("save_writes_four_homes", test_save_writes_four_homes),
        ("clear_home_drops_line", test_clear_home_drops_line),
        ("cloud_and_hpc_secret_stay_out", test_cloud_and_hpc_secret_stay_out),
        ("note_homes_not_wiring", test_note_homes_not_wiring),
        ("no_fourth_handle", test_no_fourth_handle),
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
