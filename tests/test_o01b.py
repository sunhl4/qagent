"""O-01b: freeze loopback bind, approve token, and secret keys off status."""

from __future__ import annotations

import os
import sys
import tempfile
import traceback
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from qagent.entrypoints.debug_gate import approved_allowed, bind_allowed
from qagent.models.workplace import Workplace
from qagent.services.workplace import workplace_status

_NOTE = ROOT / "docs" / "execution" / "O-01b_security.md"
_START_UI = ROOT / "scripts" / "start_ui.sh"
_SECRET_KEYS = ("llm_api_key", "hpc_secret", "quantum_secret")
_TOKEN_ENV = "QAGENT_SHELL_TOKEN"
_WP_ENV = (
    "QAGENT_WORKPLACE_FILE",
    "QAGENT_SECRETS_FILE",
    "QAGENT_DSH_ENV_FILE",
    "QAGENT_CLOUD_URL",
    "DEEPSEEK_BASE_URL",
    "DEEPSEEK_API_KEY",
    "DEEPSEEK_MODEL",
)


@contextmanager
def _isolate_token(value: str | None) -> Iterator[None]:
    previous = os.environ.get(_TOKEN_ENV)
    try:
        if value is None:
            os.environ.pop(_TOKEN_ENV, None)
        else:
            os.environ[_TOKEN_ENV] = value
        yield
    finally:
        if previous is None:
            os.environ.pop(_TOKEN_ENV, None)
        else:
            os.environ[_TOKEN_ENV] = previous


@contextmanager
def _temp_workplace() -> Iterator[Path]:
    previous = {key: os.environ.get(key) for key in _WP_ENV}
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


def test_bind_loopback() -> None:
    with _isolate_token(None):
        assert bind_allowed("127.0.0.1") is True
        assert bind_allowed("0.0.0.0") is False
        assert bind_allowed("") is False


def test_bind_all_interfaces_needs_token() -> None:
    with _isolate_token("o01b-bind-token"):
        assert bind_allowed("127.0.0.1") is True
        assert bind_allowed("0.0.0.0") is True
        assert bind_allowed("") is True


def test_approved_needs_matching_header() -> None:
    with _isolate_token(None):
        assert approved_allowed({}, True) is False
    token = "o01b-approve-token"
    with _isolate_token(token):
        assert approved_allowed({}, True) is False
        assert approved_allowed({"X-QAGENT-DEBUG-TOKEN": token}, True) is True
        assert approved_allowed({"X-QAGENT-APPROVE-TOKEN": token}, True) is True
        assert approved_allowed({"X-QAGENT-DEBUG-TOKEN": "nope"}, True) is False


def test_start_ui_loopback() -> None:
    text = _START_UI.read_text(encoding="utf-8")
    assert "127.0.0.1" in text
    assert "--host 127.0.0.1" in text
    assert "0.0.0.0" not in text


def test_public_keys_hide_secrets() -> None:
    public = Workplace().to_public()
    for key in _SECRET_KEYS:
        assert key not in public
    with _temp_workplace():
        status = workplace_status()
        keys = _all_keys(status)
        for key in _SECRET_KEYS:
            assert key not in keys
            assert key not in status
            assert key not in (status.get("workplace") or {})


def test_note_exists() -> None:
    assert _NOTE.is_file()
    text = _NOTE.read_text(encoding="utf-8")
    assert "QAGENT_SHELL_TOKEN" in text
    assert "127.0.0.1" in text


def main() -> int:
    failed = 0
    for name, fn in (
        ("bind_loopback", test_bind_loopback),
        ("bind_all_interfaces_needs_token", test_bind_all_interfaces_needs_token),
        ("approved_needs_matching_header", test_approved_needs_matching_header),
        ("start_ui_loopback", test_start_ui_loopback),
        ("public_keys_hide_secrets", test_public_keys_hide_secrets),
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
