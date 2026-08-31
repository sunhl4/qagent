"""H-03e: workplace_status next_model is the public model name, never secrets."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import traceback
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from qagent.entrypoints.shell_http import dispatch
from qagent.services.workplace import save_workplace, workplace_status

_NOTE = ROOT / "docs" / "execution" / "H-03e_next_model.md"
_ENV_KEYS = (
    "QAGENT_WORKPLACE_FILE",
    "QAGENT_SECRETS_FILE",
    "QAGENT_DSH_ENV_FILE",
    "DEEPSEEK_BASE_URL",
    "DEEPSEEK_API_KEY",
    "DEEPSEEK_MODEL",
)
_POOL = (
    "unitqc-local | http://127.0.0.1:9/v1 | unitqc-local\n"
    "unitqc-chem | http://127.0.0.1:8002/v1 | chem-7b\n"
)
_SECRET = "sk-h03e-never-echo-xyz"
_HPC = "hpc-pass-h03e"
_QTM = "q-pass-h03e"
_SECRET_KEYS = ("llm_api_key", "hpc_secret", "quantum_secret")


@contextmanager
def _temp_workplace():
    previous = {key: os.environ.get(key) for key in _ENV_KEYS}
    tmp = tempfile.TemporaryDirectory()
    try:
        folder = Path(tmp.name)
        os.environ["QAGENT_WORKPLACE_FILE"] = str(folder / "workplace.json")
        os.environ["QAGENT_SECRETS_FILE"] = str(folder / "secrets.json")
        os.environ["QAGENT_DSH_ENV_FILE"] = str(folder / "dsh.env")
        for key in ("DEEPSEEK_BASE_URL", "DEEPSEEK_API_KEY", "DEEPSEEK_MODEL"):
            os.environ.pop(key, None)
        yield folder
    finally:
        tmp.cleanup()
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _all_keys(payload: object) -> set[str]:
    found: set[str] = set()
    if isinstance(payload, dict):
        for key, value in payload.items():
            found.add(str(key))
            found.update(_all_keys(value))
    elif isinstance(payload, list):
        for item in payload:
            found.update(_all_keys(item))
    return found


def test_next_model_matches_llm_model_when_set() -> None:
    with _temp_workplace():
        save_workplace({"llm_model": "unitqc-local", "llm_pool": _POOL})
        status = workplace_status()
        public = status["workplace"]
        assert status["ready"] is True
        assert public["llm_model"] == "unitqc-local"
        assert status["next_model"] == public["llm_model"]
        save_workplace({"llm_model": "unitqc-chem", "llm_pool": _POOL})
        status = workplace_status()
        public = status["workplace"]
        assert status["ready"] is True
        assert public["llm_model"] == "chem-7b"
        assert status["next_model"] == public["llm_model"]


def test_next_model_empty_when_not_ready() -> None:
    with _temp_workplace():
        status = workplace_status()
        assert status["ready"] is False
        assert status["next_model"] == ""
        save_workplace({"llm_model": "no-such-pool", "llm_base_url": "", "llm_pool": _POOL})
        status = workplace_status()
        assert status["ready"] is False
        assert status["workplace"]["llm_model"] == "no-such-pool"
        assert status["next_model"] == ""


def test_secret_keys_absent() -> None:
    with _temp_workplace():
        save_workplace(
            {"llm_model": "unitqc-local", "llm_pool": _POOL, "hpc_host": "hpc.example"},
            {
                "llm_api_key": _SECRET,
                "hpc_secret": _HPC,
                "quantum_secret": _QTM,
            },
        )
        status = workplace_status()
        dumped = json.dumps(status, ensure_ascii=False)
        keys = _all_keys(status)
        for key in _SECRET_KEYS:
            assert key not in keys
            assert key not in status
            assert key not in status["workplace"]
        assert _SECRET not in dumped
        assert _HPC not in dumped
        assert _QTM not in dumped
        assert "twin_id" not in keys
        public = status["workplace"]
        assert public["has_llm_key"] is True
        assert public["has_hpc_secret"] is True
        assert public["has_quantum_secret"] is True
        assert status["next_model"] == public["llm_model"]
        code, got = dispatch("GET", "/api/workplace")
        assert code == 200
        assert isinstance(got, dict)
        assert got["next_model"] == public["llm_model"]
        get_keys = _all_keys(got)
        for key in _SECRET_KEYS:
            assert key not in get_keys
        assert got["workplace"]["has_llm_key"] is True
        assert got["workplace"]["has_hpc_secret"] is True
        assert got["workplace"]["has_quantum_secret"] is True


def test_note_exists() -> None:
    assert _NOTE.is_file()
    text = _NOTE.read_text(encoding="utf-8")
    assert "next_model" in text
    assert "llm_api_key" in text
    assert "活模型切换" in text


def main() -> int:
    failed = 0
    for name, fn in (
        ("next_model_matches_llm_model_when_set", test_next_model_matches_llm_model_when_set),
        ("next_model_empty_when_not_ready", test_next_model_empty_when_not_ready),
        ("secret_keys_absent", test_secret_keys_absent),
        ("note_exists", test_note_exists),
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
