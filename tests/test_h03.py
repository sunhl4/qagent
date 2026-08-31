"""H-03c/d: next dsh turn sees the new default model; GET never echoes secrets."""

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

from qagent.adapters.workplace_store import dsh_env_path
from qagent.models.workplace import Workplace, parse_llm_pool
from qagent.services.workplace import apply_env, save_workplace, workplace_status

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
_SECRET = "sk-h03-never-echo-xyz"


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


def test_parse_llm_pool() -> None:
    rows = parse_llm_pool(_POOL + "\n# skip\nbad line\n | | \n")
    assert rows == [
        {"name": "unitqc-local", "base_url": "http://127.0.0.1:9/v1", "model": "unitqc-local"},
        {"name": "unitqc-chem", "base_url": "http://127.0.0.1:8002/v1", "model": "chem-7b"},
    ]
    assert parse_llm_pool("") == []
    assert Workplace().ready() is False


def test_save_writes_dsh_model() -> None:
    with _temp_workplace():
        row = save_workplace(
            {"llm_model": "unitqc-local", "llm_pool": _POOL},
            {"llm_api_key": _SECRET},
        )
        assert row.llm_model == "unitqc-local"
        assert row.llm_base_url == "http://127.0.0.1:9/v1"
        assert row.ready() is True
        text = dsh_env_path().read_text(encoding="utf-8")
        assert "DEEPSEEK_MODEL=unitqc-local" in text
        assert "DEEPSEEK_BASE_URL=http://127.0.0.1:9/v1" in text


def test_apply_env_sets_model() -> None:
    with _temp_workplace():
        save_workplace({"llm_model": "unitqc-local", "llm_pool": _POOL})
        os.environ.pop("DEEPSEEK_MODEL", None)
        os.environ.pop("DEEPSEEK_BASE_URL", None)
        apply_env()
        assert os.environ["DEEPSEEK_MODEL"] == "unitqc-local"
        assert os.environ["DEEPSEEK_BASE_URL"] == "http://127.0.0.1:9/v1"


def test_switch_model_updates_dsh_env() -> None:
    with _temp_workplace():
        save_workplace({"llm_model": "unitqc-local", "llm_pool": _POOL})
        assert "DEEPSEEK_MODEL=unitqc-local" in dsh_env_path().read_text(encoding="utf-8")
        row = save_workplace({"llm_model": "unitqc-chem", "llm_pool": _POOL})
        text = dsh_env_path().read_text(encoding="utf-8")
        assert "DEEPSEEK_MODEL=chem-7b" in text
        assert "DEEPSEEK_BASE_URL=http://127.0.0.1:8002/v1" in text
        assert "DEEPSEEK_MODEL=unitqc-local" not in text
        assert row.llm_model == "chem-7b"
        assert row.ready() is True
        os.environ.pop("DEEPSEEK_MODEL", None)
        apply_env()
        assert os.environ["DEEPSEEK_MODEL"] == "chem-7b"


def test_status_json_hides_secrets() -> None:
    with _temp_workplace():
        save_workplace(
            {"llm_model": "unitqc-local", "llm_pool": _POOL, "hpc_host": "hpc.example"},
            {
                "llm_api_key": _SECRET,
                "hpc_secret": "hpc-pass-h03",
                "quantum_secret": "q-pass-h03",
            },
        )
        status = workplace_status()
        dumped = json.dumps(status, ensure_ascii=False)
        assert _SECRET not in dumped
        assert "hpc-pass-h03" not in dumped
        assert "q-pass-h03" not in dumped
        public = status["workplace"]
        assert "llm_api_key" not in public
        assert "hpc_secret" not in public
        assert "quantum_secret" not in public
        assert public["has_llm_key"] is True
        assert public["has_hpc_secret"] is True
        assert public["has_quantum_secret"] is True


def test_empty_address_not_ready() -> None:
    with _temp_workplace():
        row = save_workplace({"llm_model": "", "llm_base_url": "", "llm_pool": _POOL})
        assert row.ready() is False
        assert row.llm_model == ""
        assert workplace_status()["ready"] is False
        row2 = save_workplace({"llm_base_url": "", "llm_model": "no-such-pool", "llm_pool": _POOL})
        assert row2.ready() is False
        assert row2.llm_model == "no-such-pool"
        assert row2.llm_base_url == ""


def main() -> int:
    failed = 0
    for name, fn in (
        ("parse_llm_pool", test_parse_llm_pool),
        ("save_writes_dsh_model", test_save_writes_dsh_model),
        ("apply_env_sets_model", test_apply_env_sets_model),
        ("switch_model_updates_dsh_env", test_switch_model_updates_dsh_env),
        ("status_json_hides_secrets", test_status_json_hides_secrets),
        ("empty_address_not_ready", test_empty_address_not_ready),
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
