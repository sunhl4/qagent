"""A-01e: start_qdata fills empty QAGENT_QDATA_HOME from workplace. Not wiring."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from qagent.models.handles import HANDLE_ASSET, HANDLE_CIRCUIT, HANDLE_TWIN

_NOTE = ROOT / "docs" / "execution" / "A-01e_start_qdata_home.md"
_SCRIPT = ROOT / "scripts" / "start_qdata.sh"
_HANDLES = frozenset({HANDLE_CIRCUIT, HANDLE_ASSET, HANDLE_TWIN})
_ID_RE = re.compile(r"\b[a-z]+_id\b")
_CLOUD = "https://cloud.a01e.example"
_HPC = "a01e-hpc-n3v3r-echo"
_QTM = "a01e-qtm-n3v3r-echo"
_LLM = "sk-a01e-llm-n3v3r-echo"
_FORBIDDEN = (
    "QAGENT_CLOUD_URL",
    "hpc_secret",
    "quantum_secret",
    "llm_api_key",
    _CLOUD,
    _HPC,
    _QTM,
    _LLM,
)
_HONEST_FAIL = "set QAGENT_QDATA_HOME to the qdata checkout"


def _script_text() -> str:
    return _SCRIPT.read_text(encoding="utf-8")


def _homes_python() -> str:
    text = _script_text()
    marker = "<<'HOMES'"
    start = text.find(marker)
    assert start >= 0, "start_qdata.sh missing HOMES python"
    body_start = text.find("\n", start) + 1
    end = text.find("\nHOMES\n", body_start)
    assert end > body_start, "start_qdata.sh HOMES block unclosed"
    return text[body_start:end]


def _run_homes_py(workplace: Path, extra_env: dict[str, str] | None = None) -> tuple[int, str, str]:
    env = os.environ.copy()
    env.pop("QAGENT_QDATA_HOME", None)
    env.pop("QAGENT_QCHEM_HOME", None)
    env.pop("QAGENT_IONSTACK_HOME", None)
    env.pop("QAGENT_KNOWLEDGE_PATH", None)
    env.pop("QAGENT_CLOUD_URL", None)
    if extra_env:
        env.update(extra_env)
    result = subprocess.run(
        ["python3", "-", str(workplace)],
        input=_homes_python(),
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    return result.returncode, result.stdout, result.stderr


def _rows(stdout: str) -> dict[str, str]:
    rows: dict[str, str] = {}
    for line in stdout.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        rows[key] = value
    return rows


def test_script_source_mentions_homes() -> None:
    text = _script_text()
    py = _homes_python()
    assert "workplace.json" in text
    assert "dsh.env" in text
    assert "QAGENT_QDATA_HOME" in text
    assert "qdata_home" in py
    assert "不覆盖" in text
    assert _HONEST_FAIL in text
    assert "qdata CLI missing at" in text
    assert "exec" in text
    assert "127.0.0.1" in text
    assert "serve" in text
    assert "secrets.json" not in py
    assert "QAGENT_CLOUD_URL" not in py
    assert "qchem_home" not in py
    assert "ionstack_home" not in py
    assert "knowledge_path" not in py


def test_empty_env_reads_qdata_home() -> None:
    with tempfile.TemporaryDirectory() as raw:
        folder = Path(raw)
        qdata = str(folder / "qdata-from-settings")
        workplace = folder / "workplace.json"
        workplace.write_text(
            json.dumps(
                {
                    "qdata_home": qdata,
                    "qchem_home": str(folder / "qchem-ignore"),
                    "ionstack_home": str(folder / "ionstack-ignore"),
                    "knowledge_path": str(folder / "knowledge-ignore"),
                }
            ),
            encoding="utf-8",
        )
        code, stdout, stderr = _run_homes_py(workplace)
        assert code == 0, stderr
        rows = _rows(stdout)
        assert rows["QAGENT_QDATA_HOME"] == qdata
        assert "QAGENT_QCHEM_HOME" not in rows
        assert "QAGENT_IONSTACK_HOME" not in rows
        assert "QAGENT_KNOWLEDGE_PATH" not in rows
        assert "QAGENT_CLOUD_URL" not in rows
        assert "QAGENT_CLOUD_URL" not in stdout


def test_existing_env_not_overwritten() -> None:
    with tempfile.TemporaryDirectory() as raw:
        folder = Path(raw)
        kept = str(folder / "qdata-kept")
        workplace = folder / "workplace.json"
        workplace.write_text(
            json.dumps({"qdata_home": str(folder / "qdata-from-json")}),
            encoding="utf-8",
        )
        code, stdout, stderr = _run_homes_py(
            workplace, extra_env={"QAGENT_QDATA_HOME": kept}
        )
        assert code == 0, stderr
        rows = _rows(stdout)
        assert "QAGENT_QDATA_HOME" not in rows
        assert kept not in stdout
        assert str(folder / "qdata-from-json") not in stdout


def test_no_home_keeps_honest_fail() -> None:
    text = _script_text()
    assert _HONEST_FAIL in text
    with tempfile.TemporaryDirectory() as raw:
        folder = Path(raw)
        missing = folder / "no-such-workplace.json"
        code, stdout, stderr = _run_homes_py(missing)
        assert code == 0, stderr
        assert stdout == ""
        empty = folder / "workplace.json"
        empty.write_text(json.dumps({"qchem_home": str(folder / "qchem-only")}), encoding="utf-8")
        code, stdout, stderr = _run_homes_py(empty)
        assert code == 0, stderr
        assert stdout == ""
        assert "QAGENT_QDATA_HOME" not in stdout


def test_cloud_and_secrets_stay_out() -> None:
    with tempfile.TemporaryDirectory() as raw:
        folder = Path(raw)
        qdata = str(folder / "qdata-ok")
        workplace = folder / "workplace.json"
        workplace.write_text(
            json.dumps(
                {
                    "qdata_home": qdata,
                    "cloud_url": _CLOUD,
                    "hpc_secret": _HPC,
                    "quantum_secret": _QTM,
                    "llm_api_key": _LLM,
                }
            ),
            encoding="utf-8",
        )
        secrets = folder / "secrets.json"
        secrets.write_text(
            json.dumps({"hpc_secret": "from-secrets-file", "llm_api_key": "from-secrets"}),
            encoding="utf-8",
        )
        code, stdout, stderr = _run_homes_py(workplace)
        assert code == 0, stderr
        rows = _rows(stdout)
        assert rows["QAGENT_QDATA_HOME"] == qdata
        for needle in _FORBIDDEN:
            assert needle not in stdout
            assert needle not in stderr
        assert "from-secrets" not in stdout
        assert "QAGENT_CLOUD_URL" not in rows
        assert "hpc_secret" not in rows
        assert "quantum_secret" not in rows
        assert "llm_api_key" not in rows
        assert "secrets.json" not in _homes_python()


def test_missing_or_bad_json_is_quiet() -> None:
    with tempfile.TemporaryDirectory() as raw:
        folder = Path(raw)
        missing = folder / "no-such-workplace.json"
        code, stdout, stderr = _run_homes_py(missing)
        assert code == 0, stderr
        assert stdout == ""
        broken = folder / "workplace.json"
        broken.write_text("{not-json", encoding="utf-8")
        code, stdout, stderr = _run_homes_py(broken)
        assert code == 0, stderr
        assert stdout == ""
        empty = folder / "empty.json"
        empty.write_text(json.dumps({"qdata_home": "  ", "cloud_url": _CLOUD}), encoding="utf-8")
        code, stdout, stderr = _run_homes_py(empty)
        assert code == 0, stderr
        assert stdout == ""
        assert _CLOUD not in stdout


def test_note_homes_not_wiring() -> None:
    assert _NOTE.is_file()
    text = _NOTE.read_text(encoding="utf-8")
    assert "不算接线" in text
    assert "start_qdata 读 homes" in text
    assert "不算活 qdata 已通" in text
    assert "不覆盖" in text
    assert "QAGENT_CLOUD_URL" in text
    assert "secrets.json" in text


def test_no_fourth_handle() -> None:
    for path in (_SCRIPT, _NOTE, Path(__file__)):
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
        ("script_source_mentions_homes", test_script_source_mentions_homes),
        ("empty_env_reads_qdata_home", test_empty_env_reads_qdata_home),
        ("existing_env_not_overwritten", test_existing_env_not_overwritten),
        ("no_home_keeps_honest_fail", test_no_home_keeps_honest_fail),
        ("cloud_and_secrets_stay_out", test_cloud_and_secrets_stay_out),
        ("missing_or_bad_json_is_quiet", test_missing_or_bad_json_is_quiet),
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
