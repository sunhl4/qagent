"""H-03g: start_runtime fills empty homes from workplace.json. Not wiring."""

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

_NOTE = ROOT / "docs" / "execution" / "H-03g_runtime_homes.md"
_SCRIPT = ROOT / "scripts" / "start_runtime.sh"
_HANDLES = frozenset({HANDLE_CIRCUIT, HANDLE_ASSET, HANDLE_TWIN})
_ID_RE = re.compile(r"\b[a-z]+_id\b")
_HOMES = (
    ("qdata_home", "QAGENT_QDATA_HOME"),
    ("qchem_home", "QAGENT_QCHEM_HOME"),
    ("ionstack_home", "QAGENT_IONSTACK_HOME"),
    ("knowledge_path", "QAGENT_KNOWLEDGE_PATH"),
)
_CLOUD = "https://cloud.h03g.example"
_HPC = "h03g-hpc-n3v3r-echo"
_QTM = "h03g-qtm-n3v3r-echo"
_LLM = "sk-h03g-llm-n3v3r-echo"
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


def _script_text() -> str:
    return _SCRIPT.read_text(encoding="utf-8")


def _homes_python() -> str:
    text = _script_text()
    marker = "<<'HOMES'"
    start = text.find(marker)
    assert start >= 0, "start_runtime.sh missing HOMES python"
    body_start = text.find("\n", start) + 1
    end = text.find("\nHOMES\n", body_start)
    assert end > body_start, "start_runtime.sh HOMES block unclosed"
    return text[body_start:end]


def _run_homes_py(workplace: Path, extra_env: dict[str, str] | None = None) -> tuple[int, str, str]:
    env = os.environ.copy()
    for field, env_name in _HOMES:
        env.pop(env_name, None)
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
    assert "workplace.json" in text
    assert "QAGENT_QDATA_HOME" in text
    assert "QAGENT_QCHEM_HOME" in text
    assert "QAGENT_IONSTACK_HOME" in text
    assert "QAGENT_KNOWLEDGE_PATH" in text
    assert "不覆盖" in text
    assert "exec" in text
    assert "--profile qagent" in text
    assert "secrets.json" not in _homes_python()
    py = _homes_python()
    assert "qdata_home" in py
    assert "QAGENT_CLOUD_URL" not in py


def test_empty_env_reads_qdata_home() -> None:
    with tempfile.TemporaryDirectory() as raw:
        folder = Path(raw)
        qdata = str(folder / "qdata-old")
        workplace = folder / "workplace.json"
        workplace.write_text(
            json.dumps(
                {
                    "qdata_home": qdata,
                    "qchem_home": str(folder / "qchem-old"),
                    "ionstack_home": str(folder / "ionstack-old"),
                    "knowledge_path": str(folder / "knowledge-old"),
                }
            ),
            encoding="utf-8",
        )
        code, stdout, stderr = _run_homes_py(workplace)
        assert code == 0, stderr
        rows = _rows(stdout)
        assert rows["QAGENT_QDATA_HOME"] == qdata
        assert rows["QAGENT_QCHEM_HOME"] == str(folder / "qchem-old")
        assert rows["QAGENT_IONSTACK_HOME"] == str(folder / "ionstack-old")
        assert rows["QAGENT_KNOWLEDGE_PATH"] == str(folder / "knowledge-old")
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
    assert "start_runtime 读 workplace homes" in text
    assert "QAGENT_CLOUD_URL" in text
    assert "secrets.json" in text
    assert "不覆盖" in text


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
