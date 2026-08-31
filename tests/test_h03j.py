"""H-03j: empty-llm save keeps existing DEEPSEEK_* in dsh.env. Skip-as-green is incomplete."""

from __future__ import annotations

import os
import sys
import tempfile
import traceback
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT
sys.path.insert(0, str(ROOT / "src"))

from qagent.adapters.workplace_store import WorkplaceStore, dsh_env_path
from qagent.services.workplace import save_workplace

_NOTE = REPO / "docs" / "execution" / "H-03j_keep_llm_env.md"
_STORE = ROOT / "src" / "qagent" / "adapters" / "workplace_store.py"
_LLM = "sk-h03j-keep-existing"
_HPC = "h03j-hpc-n3v3r-echo"
_CLOUD = "https://cloud.h03j.example"
_ENV_KEYS = (
    "QAGENT_WORKPLACE_FILE",
    "QAGENT_SECRETS_FILE",
    "QAGENT_DSH_ENV_FILE",
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
        for key in ("QAGENT_CLOUD_URL", "DEEPSEEK_BASE_URL", "DEEPSEEK_API_KEY", "DEEPSEEK_MODEL"):
            os.environ.pop(key, None)
        yield folder
    finally:
        tmp.cleanup()
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _dsh_map() -> dict[str, str]:
    rows: dict[str, str] = {}
    for line in dsh_env_path().read_text(encoding="utf-8").splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        rows[key] = value
    return rows


def test_empty_llm_save_keeps_existing_deepseek() -> None:
    with _temp_workplace() as folder:
        dsh_env_path().write_text(
            "DEEPSEEK_BASE_URL=http://127.0.0.1:9/v1\n"
            "DEEPSEEK_MODEL=unitqc-local\n",
            encoding="utf-8",
        )
        qdata = str(folder / "qdata-keep")
        qchem = str(folder / "qchem-keep")
        ion = str(folder / "ionstack-keep")
        save_workplace(
            {
                "qdata_home": qdata,
                "qchem_home": qchem,
                "ionstack_home": ion,
            }
        )
        rows = _dsh_map()
        assert rows["DEEPSEEK_BASE_URL"] == "http://127.0.0.1:9/v1"
        assert rows["DEEPSEEK_MODEL"] == "unitqc-local"
        assert "DEEPSEEK_API_KEY" not in rows
        assert rows["QAGENT_QDATA_HOME"] == qdata
        assert rows["QAGENT_QCHEM_HOME"] == qchem
        assert rows["QAGENT_IONSTACK_HOME"] == ion
        print(f"kept DEEPSEEK_* and wrote homes keys={sorted(rows)}")


def test_nonempty_llm_still_overwrites() -> None:
    with _temp_workplace() as folder:
        dsh_env_path().write_text(
            "DEEPSEEK_BASE_URL=http://127.0.0.1:9/v1\n"
            "DEEPSEEK_MODEL=unitqc-local\n",
            encoding="utf-8",
        )
        save_workplace(
            {
                "llm_base_url": "http://127.0.0.1:8002/v1",
                "llm_model": "chem-7b",
                "qdata_home": str(folder / "qdata-b"),
            },
            {"llm_api_key": _LLM},
        )
        rows = _dsh_map()
        assert rows["DEEPSEEK_BASE_URL"] == "http://127.0.0.1:8002/v1"
        assert rows["DEEPSEEK_MODEL"] == "chem-7b"
        assert rows["DEEPSEEK_API_KEY"] == _LLM
        print("non-empty llm overwrite ok")


def test_cloud_and_hpc_still_out() -> None:
    with _temp_workplace() as folder:
        dsh_env_path().write_text(
            "DEEPSEEK_BASE_URL=http://127.0.0.1:9/v1\nQAGENT_CLOUD_URL=https://old.example\n",
            encoding="utf-8",
        )
        save_workplace(
            {"qdata_home": str(folder / "qdata-c"), "cloud_url": _CLOUD},
            {"hpc_secret": _HPC},
        )
        text = dsh_env_path().read_text(encoding="utf-8")
        rows = _dsh_map()
        assert "QAGENT_CLOUD_URL" not in rows
        assert _CLOUD not in text
        assert _HPC not in text
        assert rows["DEEPSEEK_BASE_URL"] == "http://127.0.0.1:9/v1"
        print("cloud/hpc stayed out; DEEPSEEK_BASE_URL kept")


def test_note_copies_hit() -> None:
    assert _NOTE.is_file(), f"missing {_NOTE}"
    text = _NOTE.read_text(encoding="utf-8")
    assert "DEEPSEEK_BASE_URL" in text
    assert "DEEPSEEK_MODEL" in text
    assert "write_dsh_env" in text
    assert "空 llm" in text or "empty llm" in text
    assert "不算 G0" in text
    assert "G0 已通过" not in text
    assert "不写密钥" in text or "不读 secrets" in text
    assert "未 commit" in text
    src = _STORE.read_text(encoding="utf-8")
    assert "_existing_dsh_env" in src
    assert "DEEPSEEK_BASE_URL" in src


def test_this_file_does_not_skip() -> None:
    text = Path(__file__).read_text(encoding="utf-8")
    assert ("pytest" + ".skip") not in text
    assert ("unittest" + ".skip") not in text
    assert ("skip" + "Test") not in text


def main() -> int:
    failed = 0
    for name, fn in (
        ("empty_llm_save_keeps_existing_deepseek", test_empty_llm_save_keeps_existing_deepseek),
        ("nonempty_llm_still_overwrites", test_nonempty_llm_still_overwrites),
        ("cloud_and_hpc_still_out", test_cloud_and_hpc_still_out),
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
