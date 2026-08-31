"""H-03h: start_ui fills empty homes from dsh.env / workplace. Not wiring."""

from __future__ import annotations

import json
import os
import re
import socket
import stat
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from qagent.models.handles import HANDLE_ASSET, HANDLE_CIRCUIT, HANDLE_TWIN

_NOTE = ROOT / "docs" / "execution" / "H-03h_ui_homes.md"
_SCRIPT = ROOT / "scripts" / "start_ui.sh"
_HANDLES = frozenset({HANDLE_CIRCUIT, HANDLE_ASSET, HANDLE_TWIN})
_ID_RE = re.compile(r"\b[a-z]+_id\b")
_HOMES = (
    ("qdata_home", "QAGENT_QDATA_HOME"),
    ("qchem_home", "QAGENT_QCHEM_HOME"),
    ("ionstack_home", "QAGENT_IONSTACK_HOME"),
    ("knowledge_path", "QAGENT_KNOWLEDGE_PATH"),
)
_CLOUD = "https://cloud.h03h.example"
_HPC = "h03h-hpc-n3v3r-echo"
_QTM = "h03h-qtm-n3v3r-echo"
_LLM = "sk-h03h-llm-n3v3r-echo"
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
_CLAIM_PASS = ("G0 已通过", "G0 passed")
_DUMP = (
    'printf "%s\\n" '
    '"QAGENT_QDATA_HOME=${QAGENT_QDATA_HOME-}" '
    '"QAGENT_QCHEM_HOME=${QAGENT_QCHEM_HOME-}" '
    '"QAGENT_IONSTACK_HOME=${QAGENT_IONSTACK_HOME-}" '
    '"QAGENT_KNOWLEDGE_PATH=${QAGENT_KNOWLEDGE_PATH-}"'
)


def _script_text() -> str:
    return _SCRIPT.read_text(encoding="utf-8")


def _homes_python() -> str:
    text = _script_text()
    marker = "<<'HOMES'"
    start = text.find(marker)
    assert start >= 0, "start_ui.sh missing HOMES python"
    body_start = text.find("\n", start) + 1
    end = text.find("\nHOMES\n", body_start)
    assert end > body_start, "start_ui.sh HOMES block unclosed"
    return text[body_start:end]


def _run_homes_py(workplace: Path, extra_env: dict[str, str] | None = None) -> tuple[int, str, str]:
    env = os.environ.copy()
    for _field, env_name in _HOMES:
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


def _free_port() -> str:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = str(sock.getsockname()[1])
    sock.close()
    return port


def _run_script_copy(
    *,
    dsh_env: dict[str, str] | None = None,
    workplace: dict[str, object] | None = None,
    extra_env: dict[str, str] | None = None,
    dsh_text: str | None = None,
    bad_workplace: str | None = None,
) -> tuple[int, str, str]:
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        scripts = root / "scripts"
        hidden = root / ".qagent"
        scripts.mkdir()
        hidden.mkdir()
        body = _script_text().replace(
            'exec python3 -m qagent.entrypoints.shell_cli --serve --host 127.0.0.1 --port "${PORT}"',
            _DUMP,
        )
        dest = scripts / "start_ui.sh"
        dest.write_text(body, encoding="utf-8")
        dest.chmod(dest.stat().st_mode | stat.S_IEXEC)
        if dsh_text is not None:
            (hidden / "dsh.env").write_text(dsh_text, encoding="utf-8")
        elif dsh_env is not None:
            lines = [f"{key}={value}" for key, value in dsh_env.items()]
            (hidden / "dsh.env").write_text("\n".join(lines) + "\n", encoding="utf-8")
        if bad_workplace is not None:
            (hidden / "workplace.json").write_text(bad_workplace, encoding="utf-8")
        elif workplace is not None:
            (hidden / "workplace.json").write_text(json.dumps(workplace), encoding="utf-8")
        env = os.environ.copy()
        for _field, env_name in _HOMES:
            env.pop(env_name, None)
        env.pop("QAGENT_CLOUD_URL", None)
        env.pop("QAGENT_WORKPLACE_FILE", None)
        env["QAGENT_UI_PORT"] = _free_port()
        env["QAGENT_SHELL_TOKEN"] = "h03h-token"
        if extra_env:
            env.update(extra_env)
        result = subprocess.run(
            ["bash", str(dest)],
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
        if key.startswith("QAGENT_"):
            rows[key] = value
    return rows


def test_script_source_mentions_homes() -> None:
    text = _script_text()
    py = _homes_python()
    assert "workplace.json" in text
    assert "dsh.env" in text
    assert "QAGENT_QDATA_HOME" in text
    assert "QAGENT_QCHEM_HOME" in text
    assert "QAGENT_IONSTACK_HOME" in text
    assert "QAGENT_KNOWLEDGE_PATH" in text
    assert "qdata_home" in py
    assert "qchem_home" in py
    assert "ionstack_home" in py
    assert "knowledge_path" in py
    assert "不覆盖" in text
    assert "exec" in text
    assert "shell_cli" in text
    assert "--serve" in text
    assert "role=customer" in text
    assert "?token=${QAGENT_SHELL_TOKEN}" in text
    assert "客户租户示例" in text
    assert "--profile qagent" not in text
    assert "ionstack_twin_run" not in text
    assert "QAGENT_CLOUD_URL=" not in text
    assert "hpc_secret" not in text
    assert "quantum_secret" not in text
    assert "secrets.json" not in py
    assert "QAGENT_CLOUD_URL" not in py
    for phrase in _CLAIM_PASS:
        assert phrase not in text


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


def test_dsh_env_then_workplace() -> None:
    with tempfile.TemporaryDirectory() as raw:
        folder = Path(raw)
        from_dsh = str(folder / "qdata-from-dsh")
        from_json = str(folder / "qdata-from-json")
        qchem = str(folder / "qchem-from-json")
        code, stdout, stderr = _run_script_copy(
            dsh_env={"QAGENT_QDATA_HOME": from_dsh, "DEEPSEEK_API_KEY": _LLM},
            workplace={
                "qdata_home": from_json,
                "qchem_home": qchem,
                "ionstack_home": str(folder / "ionstack-from-json"),
                "knowledge_path": str(folder / "knowledge-from-json"),
            },
        )
        assert code == 0, stderr
        rows = _rows(stdout)
        assert rows["QAGENT_QDATA_HOME"] == from_dsh
        assert rows["QAGENT_QCHEM_HOME"] == qchem
        assert rows["QAGENT_IONSTACK_HOME"] == str(folder / "ionstack-from-json")
        assert rows["QAGENT_KNOWLEDGE_PATH"] == str(folder / "knowledge-from-json")
        assert "QAGENT_CLOUD_URL" not in stdout
        assert _LLM not in stdout
        assert from_json not in stdout


def test_script_copy_keeps_existing_env() -> None:
    with tempfile.TemporaryDirectory() as raw:
        folder = Path(raw)
        kept = str(folder / "qdata-kept")
        code, stdout, stderr = _run_script_copy(
            dsh_env={"QAGENT_QDATA_HOME": str(folder / "qdata-from-dsh")},
            workplace={"qdata_home": str(folder / "qdata-from-json")},
            extra_env={"QAGENT_QDATA_HOME": kept},
        )
        assert code == 0, stderr
        rows = _rows(stdout)
        assert rows["QAGENT_QDATA_HOME"] == kept
        assert str(folder / "qdata-from-dsh") not in stdout
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

        dsh_text = "\n".join(
            [
                f"QAGENT_QDATA_HOME={qdata}",
                f"QAGENT_CLOUD_URL={_CLOUD}",
                f"hpc_secret={_HPC}",
                f"quantum_secret={_QTM}",
                f"llm_api_key={_LLM}",
            ]
        ) + "\n"
        code, stdout, stderr = _run_script_copy(
            dsh_text=dsh_text,
            workplace={"cloud_url": _CLOUD, "hpc_secret": _HPC, "quantum_secret": _QTM},
        )
        assert code == 0, stderr
        rows = _rows(stdout)
        assert rows["QAGENT_QDATA_HOME"] == qdata
        assert "QAGENT_CLOUD_URL" not in rows
        for needle in _FORBIDDEN:
            assert needle not in stdout
            assert needle not in stderr


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

        code, stdout, stderr = _run_script_copy(bad_workplace="{not-json")
        assert code == 0, stderr
        rows = _rows(stdout)
        assert rows.get("QAGENT_QDATA_HOME", "") == ""
        assert "QAGENT_CLOUD_URL" not in stdout


def test_note_homes_not_wiring() -> None:
    assert _NOTE.is_file()
    text = _NOTE.read_text(encoding="utf-8")
    assert "不算接线" in text
    assert "start_ui 读 homes" in text
    assert "QAGENT_CLOUD_URL" in text
    assert "secrets.json" in text
    assert "不覆盖" in text
    assert "不算 G0" in text
    assert "shell_cli" in text
    assert "--serve" in text
    for phrase in _CLAIM_PASS:
        assert phrase not in text


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
        ("dsh_env_then_workplace", test_dsh_env_then_workplace),
        ("script_copy_keeps_existing_env", test_script_copy_keeps_existing_env),
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
