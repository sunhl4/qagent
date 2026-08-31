"""Q-02c: honesty gate. Fake twin / skip ask / CAL are red. No live Twin."""

from __future__ import annotations

import os
import sys
import tempfile
import traceback
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from qagent.models.handles import HANDLE_TWIN
from qagent.models.invoke import STATUS_DENIED, STATUS_NEEDS_ASK
from qagent.services.quality import (
    GATE_CAL,
    GATE_FORGED_TWIN,
    GATE_SKIP_ASK,
    OPEN_DECISIONS,
    OPEN_STATUSES,
    STATUS_DONE,
    TOOL_AER_RUN,
    TOOL_CAL_EDIT,
    TOOL_SHUTTLE_WRITE,
    TOOL_TWIN_RUN,
    HonestyReport,
    deny_cal,
    deny_forged_twin,
    deny_skip_ask,
)

_NOTE = ROOT / "docs" / "execution" / "Q-02c_honesty_gate.md"
_DEAD_TWIN = "http://127.0.0.1:1"
_ENV_KEYS = ("QAGENT_ELN_FILE", "QAGENT_TWIN_URL")


@contextmanager
def _offline() -> Iterator[None]:
    previous = {key: os.environ.get(key) for key in _ENV_KEYS}
    tmp = tempfile.TemporaryDirectory()
    os.environ["QAGENT_ELN_FILE"] = str(Path(tmp.name) / "eln.jsonl")
    os.environ["QAGENT_TWIN_URL"] = _DEAD_TWIN
    try:
        yield
    finally:
        tmp.cleanup()
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _assert_fail_closed(report: HonestyReport) -> None:
    assert report.fail_closed(), report
    for hit in report.hits:
        assert hit.decision not in OPEN_DECISIONS, hit
        assert hit.status not in OPEN_STATUSES, hit
        assert hit.status != STATUS_DONE, hit
        assert HANDLE_TWIN not in hit.payload


def test_forged_twin_fail_closed() -> None:
    with _offline():
        report = deny_forged_twin()
    assert report.gate == GATE_FORGED_TWIN
    _assert_fail_closed(report)
    assert len(report.hits) == 1
    hit = report.hits[0]
    assert hit.tool == TOOL_AER_RUN
    assert hit.policy == "deny"
    assert hit.decision == "deny"
    assert hit.status == STATUS_DENIED
    assert not report.minted_twin()


def test_skip_ask_fail_closed() -> None:
    with _offline():
        report = deny_skip_ask()
    assert report.gate == GATE_SKIP_ASK
    _assert_fail_closed(report)
    assert len(report.hits) == 1
    hit = report.hits[0]
    assert hit.tool == TOOL_TWIN_RUN
    assert hit.policy == "ask"
    assert hit.decision == "ask"
    assert hit.status == STATUS_NEEDS_ASK
    assert not report.minted_twin()


def test_cal_fail_closed() -> None:
    with _offline():
        report = deny_cal()
    assert report.gate == GATE_CAL
    _assert_fail_closed(report)
    tools = {hit.tool for hit in report.hits}
    assert tools == {TOOL_CAL_EDIT, TOOL_SHUTTLE_WRITE}
    for hit in report.hits:
        assert hit.policy == "deny"
        assert hit.decision == "deny"
        assert hit.status == STATUS_DENIED
    assert not report.minted_twin()


def test_no_twin_id_minted() -> None:
    with _offline():
        reports = (deny_forged_twin(), deny_skip_ask(), deny_cal())
    for report in reports:
        assert not report.minted_twin(), report
        for hit in report.hits:
            assert HANDLE_TWIN not in hit.payload
            assert hit.status != STATUS_DONE


def test_note_exists() -> None:
    assert _NOTE.is_file(), _NOTE
    text = _NOTE.read_text(encoding="utf-8")
    assert "deny_forged_twin" in text
    assert "deny_skip_ask" in text
    assert "deny_cal" in text
    assert "needs_ask" in text
    assert HANDLE_TWIN in text
    assert "CAL" in text


def main() -> int:
    failed = 0
    for name, fn in (
        ("forged_twin", test_forged_twin_fail_closed),
        ("skip_ask", test_skip_ask_fail_closed),
        ("cal", test_cal_fail_closed),
        ("no_twin_id", test_no_twin_id_minted),
        ("note", test_note_exists),
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
