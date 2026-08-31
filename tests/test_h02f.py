"""H-02f: agent.turn is dead as a product entry. _loop stays in source."""

from __future__ import annotations

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

from qagent.models.handles import HANDLE_ASSET, HANDLE_CIRCUIT, HANDLE_TWIN
from qagent.services.agent import reset_agent, turn

_AGENT = SRC / "qagent" / "services" / "agent.py"
_HTTP = SRC / "qagent" / "entrypoints" / "shell_http.py"
_NOTE = ROOT / "docs" / "execution" / "H-02f_turn_dead.md"
_HANDLES = frozenset({HANDLE_CIRCUIT, HANDLE_ASSET, HANDLE_TWIN})
_ID_RE = re.compile(r"\b[a-z]+_id\b")
_CLAIM_PASS = ("G0 已通过", "G2 已通过", "G0 passed", "G2 passed")
_ENV_KEYS = ("QAGENT_AGENT_THREAD",)


@contextmanager
def isolated() -> Iterator[Path]:
    previous = {key: os.environ.get(key) for key in _ENV_KEYS}
    tmp = tempfile.TemporaryDirectory()
    try:
        folder = Path(tmp.name)
        os.environ["QAGENT_AGENT_THREAD"] = str(folder / "thread.json")
        yield folder
    finally:
        tmp.cleanup()
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def test_turn_raises() -> None:
    with isolated():
        try:
            turn(message="扫氢分子")
        except RuntimeError as exc:
            text = str(exc)
            assert "chat.turn" in text or "services.chat" in text
            assert "不是产品循环" in text
        else:
            raise AssertionError("turn() must raise")


def test_reset_agent_ok() -> None:
    with isolated():
        reset_agent()


def test_loop_still_in_source() -> None:
    text = _AGENT.read_text(encoding="utf-8")
    assert "def _loop" in text


def test_http_source_has_no_agent() -> None:
    text = _HTTP.read_text(encoding="utf-8")
    assert "services.agent" not in text
    assert "reset_agent" not in text


def test_note_exists() -> None:
    assert _NOTE.is_file(), _NOTE
    text = _NOTE.read_text(encoding="utf-8")
    assert "不算接线" in text
    assert "turn 不是产品循环" in text
    hits = [phrase for phrase in _CLAIM_PASS if phrase in text]
    assert not hits, hits
    extra = set(_ID_RE.findall(text)) - _HANDLES
    assert not extra, extra


def main() -> int:
    failed = 0
    for name, fn in (
        ("turn_raises", test_turn_raises),
        ("reset_agent_ok", test_reset_agent_ok),
        ("loop_still_in_source", test_loop_still_in_source),
        ("http_source_has_no_agent", test_http_source_has_no_agent),
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
