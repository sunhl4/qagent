"""I-02: planted secrets never enter workplace_status or dsh prompt content."""

from __future__ import annotations

import ast
import json
import os
import stat
import sys
import tempfile
import traceback
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from qagent.adapters.dsh_session import DshSessionClient
from qagent.adapters.workplace_store import SECRET_KEYS, WorkplaceStore, secrets_path, workplace_path
from qagent.services.chat import reset_chat, turn
from qagent.services.workplace import apply_env, job_auth_headers, save_workplace, workplace_status

_ENV_KEYS = (
    "QAGENT_WORKPLACE_FILE",
    "QAGENT_SECRETS_FILE",
    "QAGENT_DSH_ENV_FILE",
    "QAGENT_DSH_SESSION_FILE",
    "QAGENT_DSH_URL",
    "QAGENT_DSH_MUX",
    "QAGENT_DSH_WAIT_S",
    "DEEPSEEK_BASE_URL",
    "DEEPSEEK_API_KEY",
    "DEEPSEEK_MODEL",
)
_LLM = "sk-i02-llm-n3v3r-echo-7k2p"
_HPC = "i02-hpc-n3v3r-echo-4m9q"
_QTM = "i02-qtm-n3v3r-echo-1w8r"
_PLANTED = (_LLM, _HPC, _QTM)
_CHAT_SRC = SRC / "qagent" / "services" / "chat.py"
_WORK_SRC = SRC / "qagent" / "services" / "workplace.py"


@contextmanager
def _temp_workplace():
    previous = {key: os.environ.get(key) for key in _ENV_KEYS}
    tmp = tempfile.TemporaryDirectory()
    try:
        folder = Path(tmp.name)
        os.environ["QAGENT_WORKPLACE_FILE"] = str(folder / "workplace.json")
        os.environ["QAGENT_SECRETS_FILE"] = str(folder / "secrets.json")
        os.environ["QAGENT_DSH_ENV_FILE"] = str(folder / "dsh.env")
        os.environ["QAGENT_DSH_SESSION_FILE"] = str(folder / "dsh-session.json")
        os.environ["QAGENT_DSH_URL"] = "http://127.0.0.1:9"
        os.environ["QAGENT_DSH_MUX"] = "0"
        os.environ["QAGENT_DSH_WAIT_S"] = "0"
        for key in ("DEEPSEEK_BASE_URL", "DEEPSEEK_API_KEY", "DEEPSEEK_MODEL"):
            os.environ.pop(key, None)
        reset_chat()
        yield folder
    finally:
        reset_chat()
        tmp.cleanup()
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _plant() -> None:
    save_workplace(
        {
            "llm_base_url": "http://127.0.0.1:9/v1",
            "llm_model": "unitqc-local",
            "hpc_host": "hpc.example",
            "quantum_host": "qpu.example",
        },
        {"llm_api_key": _LLM, "hpc_secret": _HPC, "quantum_secret": _QTM},
    )


def _assert_absent(blob: str) -> None:
    for secret in _PLANTED:
        assert secret not in blob, secret


def _fstring_names(path: Path) -> set[str]:
    names: set[str] = set()
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.JoinedStr):
            continue
        for part in node.values:
            if not isinstance(part, ast.FormattedValue):
                continue
            for child in ast.walk(part.value):
                if isinstance(child, ast.Name):
                    names.add(child.id)
    return names


class _Fake:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def __call__(self, method: str, payload: dict) -> dict:
        self.calls.append((method, payload))
        if method == "session.create":
            return {"result": {"ok": True, "value": {"sessionId": "sess_i02"}}}
        if method == "session.prompt":
            return {"result": {"ok": True, "value": {"accepted": True}}}
        if method == "session.history":
            return {
                "result": {
                    "ok": True,
                    "value": {
                        "events": [
                            {
                                "event": {
                                    "type": "assistant/message",
                                    "data": {
                                        "message": {
                                            "content": [{"type": "text", "text": "已经看见公司软件包。"}]
                                        }
                                    },
                                }
                            },
                            {"event": {"type": "turn/end", "data": {}}},
                        ],
                        "hasMore": False,
                    },
                }
            }
        raise AssertionError(method)

    def payload(self, method: str) -> dict:
        for name, body in self.calls:
            if name == method:
                return body
        raise AssertionError(f"missing {method}")

    def dumped(self) -> str:
        return json.dumps(self.calls, ensure_ascii=False)


def test_status_json_hides_planted_secrets() -> None:
    with _temp_workplace():
        _plant()
        status = workplace_status()
        dumped = json.dumps(status, ensure_ascii=False)
        _assert_absent(dumped)
        public = status["workplace"]
        for key in SECRET_KEYS:
            assert key not in public
        assert public["has_llm_key"] is True
        assert public["has_hpc_secret"] is True
        assert public["has_quantum_secret"] is True
        assert secrets_path().is_file()
        assert stat.S_IMODE(secrets_path().stat().st_mode) == 0o600
        on_disk = json.loads(workplace_path().read_text(encoding="utf-8"))
        for key in SECRET_KEYS:
            assert key not in on_disk
        _assert_absent(json.dumps(on_disk, ensure_ascii=False))


def test_chat_prompt_hides_planted_secrets() -> None:
    with _temp_workplace():
        _plant()
        fake = _Fake()
        out = turn(message="看看我们接了哪些软件", client=DshSessionClient(transport=fake))
        prompt = fake.payload("session.prompt")
        assert prompt["content"][0]["text"] == "看看我们接了哪些软件"
        _assert_absent(json.dumps(prompt, ensure_ascii=False))
        _assert_absent(fake.dumped())
        _assert_absent(json.dumps(out, ensure_ascii=False))
        headers = job_auth_headers()
        assert _HPC in json.dumps(headers, ensure_ascii=False)
        _assert_absent(json.dumps(workplace_status(), ensure_ascii=False))


def test_apply_env_keeps_job_secrets_out_of_env() -> None:
    with _temp_workplace():
        _plant()
        apply_env()
        assert os.environ.get("DEEPSEEK_API_KEY") == _LLM
        env_blob = json.dumps(dict(os.environ), ensure_ascii=False)
        assert _HPC not in env_blob
        assert _QTM not in env_blob


def test_source_does_not_format_secrets_for_dsh() -> None:
    chat = _CHAT_SRC.read_text(encoding="utf-8")
    work = _WORK_SRC.read_text(encoding="utf-8")
    for key in SECRET_KEYS:
        assert key not in chat
    assert "secrets()" not in chat
    assert "session.prompt" not in work
    assert "json.dumps(secrets" not in work
    assert "json.dumps(hidden" not in work
    assert "{hidden" not in work
    assert "{secrets" not in work
    banned = {"hidden", "secrets", "llm_key"}
    assert _fstring_names(_CHAT_SRC).isdisjoint(banned)
    assert _fstring_names(_WORK_SRC).isdisjoint(banned)


def test_public_file_secret_keys_are_dropped() -> None:
    with _temp_workplace():
        workplace_path().parent.mkdir(parents=True, exist_ok=True)
        workplace_path().write_text(
            json.dumps(
                {
                    "llm_base_url": "http://127.0.0.1:9/v1",
                    "llm_model": "unitqc-local",
                    "llm_api_key": _LLM,
                    "hpc_secret": _HPC,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        dumped = json.dumps(workplace_status(), ensure_ascii=False)
        _assert_absent(dumped)
        save_workplace({"llm_model": "unitqc-local"})
        saved = json.loads(workplace_path().read_text(encoding="utf-8"))
        for key in SECRET_KEYS:
            assert key not in saved
        _assert_absent(json.dumps(saved, ensure_ascii=False))
        assert WorkplaceStore().local_auth_headers() == {}


def main() -> int:
    failed = 0
    for name, fn in (
        ("status_json_hides_planted_secrets", test_status_json_hides_planted_secrets),
        ("chat_prompt_hides_planted_secrets", test_chat_prompt_hides_planted_secrets),
        ("apply_env_keeps_job_secrets_out_of_env", test_apply_env_keeps_job_secrets_out_of_env),
        ("source_does_not_format_secrets_for_dsh", test_source_does_not_format_secrets_for_dsh),
        ("public_file_secret_keys_are_dropped", test_public_file_secret_keys_are_dropped),
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
