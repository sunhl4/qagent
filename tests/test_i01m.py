"""I-01m: PUT /api/workplace requires token. GET stays open. save_workplace() stays open."""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import traceback
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))
os.environ.setdefault("QAGENT_DSH_MUX", "0")

from qagent.entrypoints.shell_http import dispatch
from qagent.models.handles import HANDLE_ASSET, HANDLE_CIRCUIT, HANDLE_TWIN
from qagent.services.workplace import save_workplace

_NOTE = ROOT / "docs" / "execution" / "I-01m_workplace_http.md"
_HANDLES = frozenset({HANDLE_CIRCUIT, HANDLE_ASSET, HANDLE_TWIN})
_NOTE_IDS = _HANDLES
_ID_RE = re.compile(r"\b[a-z]+_id\b")
_CLAIM_PASS = ("G0 已通过", "G2 已通过", "G0 passed", "G2 passed")
_FORBIDDEN = {"error": "approval requires QAGENT_SHELL_TOKEN"}
_TOKEN = "i01m-secret"
_SECRET = "sk-i01m-never-write-without-token"
_ENV_KEYS = (
    "QAGENT_WORKPLACE_FILE",
    "QAGENT_SECRETS_FILE",
    "QAGENT_DSH_ENV_FILE",
    "QAGENT_DSH_SESSION_FILE",
    "QAGENT_DSH_URL",
    "QAGENT_DSH_MUX",
    "QAGENT_DSH_WAIT_S",
    "QAGENT_AGENT_THREAD",
    "QAGENT_SHELL_TOKEN",
    "DEEPSEEK_BASE_URL",
    "DEEPSEEK_API_KEY",
    "DEEPSEEK_MODEL",
)
_PUT_BODY = {
    "llm_base_url": "http://127.0.0.1:9/v1",
    "llm_model": "unitqc-local",
    "llm_api_key": _SECRET,
}


@contextmanager
def isolated(*, token: str | None = None) -> Iterator[Path]:
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
        os.environ["QAGENT_AGENT_THREAD"] = str(folder / "thread.json")
        for key in ("DEEPSEEK_BASE_URL", "DEEPSEEK_API_KEY", "DEEPSEEK_MODEL"):
            os.environ.pop(key, None)
        if token is None:
            os.environ.pop("QAGENT_SHELL_TOKEN", None)
        else:
            os.environ["QAGENT_SHELL_TOKEN"] = token
        yield folder
    finally:
        tmp.cleanup()
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _blob_on_disk(folder: Path) -> str:
    parts: list[str] = []
    for name in ("secrets.json", "dsh.env", "workplace.json"):
        path = folder / name
        if path.is_file():
            parts.append(path.read_text(encoding="utf-8"))
    return "".join(parts)


def test_put_without_token_is_403() -> None:
    with isolated() as folder:
        code, forbidden = dispatch("PUT", "/api/workplace", dict(_PUT_BODY), {})
        assert code == 403
        assert forbidden == _FORBIDDEN
        assert _SECRET not in _blob_on_disk(folder)
        secrets = folder / "secrets.json"
        if secrets.is_file():
            assert _SECRET not in secrets.read_text(encoding="utf-8")


def test_put_token_mismatch_is_403() -> None:
    with isolated(token=_TOKEN) as folder:
        code, forbidden = dispatch(
            "PUT",
            "/api/workplace",
            dict(_PUT_BODY),
            {"X-QAGENT-DEBUG-TOKEN": "nope"},
        )
        assert code == 403
        assert forbidden == _FORBIDDEN
        assert _SECRET not in _blob_on_disk(folder)


def test_put_with_matching_token_then_get_hides_secret() -> None:
    with isolated(token=_TOKEN) as folder:
        code, saved = dispatch(
            "PUT",
            "/api/workplace",
            dict(_PUT_BODY),
            {"X-QAGENT-DEBUG-TOKEN": _TOKEN},
        )
        assert code == 200
        assert set(saved) == {"workplace", "ready"}
        assert saved["ready"] is True
        dumped_put = json.dumps(saved)
        assert _SECRET not in dumped_put
        extra = set(_ID_RE.findall(dumped_put))
        assert not extra, extra

        code, status = dispatch("GET", "/api/workplace")
        assert code == 200
        dumped = json.dumps(status)
        assert _SECRET not in dumped
        assert "llm_api_key" not in dumped
        assert status["workplace"]["has_llm_key"] is True
        extra = set(_ID_RE.findall(dumped)) - _HANDLES
        assert not extra, extra
        secrets = folder / "secrets.json"
        assert secrets.is_file()
        assert _SECRET in secrets.read_text(encoding="utf-8")


def test_get_workplace_stays_open() -> None:
    with isolated():
        code, status = dispatch("GET", "/api/workplace")
        assert code == 200
        assert "workplace" in status
        assert "ready" in status


def test_save_workplace_service_needs_no_token() -> None:
    with isolated() as folder:
        row = save_workplace(
            {"llm_base_url": "http://127.0.0.1:9/v1", "llm_model": "unitqc-local"},
            {"llm_api_key": _SECRET},
        )
        assert row.ready() is True
        assert row.has_llm_key is True
        assert _SECRET in (folder / "secrets.json").read_text(encoding="utf-8")


def test_note_exists() -> None:
    assert _NOTE.is_file(), _NOTE
    text = _NOTE.read_text(encoding="utf-8")
    assert "不算接线" in text
    assert "workplace PUT 无 token 403" in text
    hits = [phrase for phrase in _CLAIM_PASS if phrase in text]
    assert not hits, hits
    extra = set(_ID_RE.findall(text)) - _NOTE_IDS
    assert not extra, extra


def main() -> int:
    failed = 0
    for name, fn in (
        ("put_without_token_is_403", test_put_without_token_is_403),
        ("put_token_mismatch_is_403", test_put_token_mismatch_is_403),
        ("put_with_matching_token_then_get_hides_secret", test_put_with_matching_token_then_get_hides_secret),
        ("get_workplace_stays_open", test_get_workplace_stays_open),
        ("save_workplace_service_needs_no_token", test_save_workplace_service_needs_no_token),
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
