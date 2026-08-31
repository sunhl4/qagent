"""I-03l: GET /api/eln face keeps the newest 20 rows. Disk stays full."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import traceback
import urllib.error
import urllib.request
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT
sys.path.insert(0, str(ROOT / "src"))

from qagent.entrypoints.shell_http import dispatch
from qagent.models.eln import EVENT_ESTIMATE, EVENT_RECIPE_PIN
from qagent.services.eln import append_estimate, append_recipe_pin, read_eln

_NOTE = REPO / "docs" / "execution" / "I-03l_eln_cap.md"
_FACE = "http://127.0.0.1:3080"
_TOKEN = "workbench-review"
_CAP = 20
_PLANTED = 25


@contextmanager
def isolated_eln() -> Iterator[Path]:
    previous = os.environ.get("QAGENT_ELN_FILE")
    handle, name = tempfile.mkstemp(prefix="i03l-eln-", suffix=".jsonl")
    os.close(handle)
    path = Path(name)
    os.environ["QAGENT_ELN_FILE"] = str(path)
    try:
        yield path
    finally:
        if previous is None:
            os.environ.pop("QAGENT_ELN_FILE", None)
        else:
            os.environ["QAGENT_ELN_FILE"] = previous
        path.unlink(missing_ok=True)


def test_http_keeps_newest_cap() -> None:
    with isolated_eln():
        append_recipe_pin(recipe="a2_chem_pes", assignment_id="asg_i03l_old")
        for index in range(_PLANTED):
            append_estimate(makespan_ns=float(index), assignment_id=f"asg_i03l_{index:02d}")
        disk = read_eln()
        assert len(disk) == _PLANTED + 1
        code, payload = dispatch("GET", "/api/eln")
        assert code == 200
        events = payload["events"]
        assert len(events) == _CAP, len(events)
        types = [row.get("type") for row in events]
        assert EVENT_RECIPE_PIN not in types
        assert types[-1] == EVENT_ESTIMATE
        assert events[-1].get("assignment_id") == "asg_i03l_24"
        assert events[0].get("assignment_id") == "asg_i03l_05"
        assert "twin_id" not in json.dumps(payload)


def test_live_http_is_capped() -> None:
    request = urllib.request.Request(
        _FACE + "/api/eln",
        headers={"X-QAGENT-DEBUG-TOKEN": _TOKEN},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
            code = int(response.status)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise AssertionError(f"3080 not reachable (/api/eln): {exc}") from exc
    assert code == 200
    events = payload.get("events") or []
    assert isinstance(events, list)
    assert len(events) <= _CAP, len(events)
    assert len(events) > 0
    print(f"live eln n={len(events)} last_type={events[-1].get('type')}")


def test_note_copies_hit() -> None:
    assert _NOTE.is_file(), _NOTE
    text = _NOTE.read_text(encoding="utf-8")
    assert "20" in text
    assert "/api/eln" in text
    assert "short_payload" in text
    assert "不算 G0" in text
    assert "不算 G2" in text
    assert "G0 已通过" not in text
    assert "G2 已通过" not in text
    assert "skip 当绿" in text
    assert "未 commit" in text
    assert "不改 short_payload()" in text


def test_this_file_does_not_skip() -> None:
    text = Path(__file__).read_text(encoding="utf-8")
    assert ("pytest" + ".skip") not in text
    assert ("unittest" + ".skip") not in text
    assert ("skip" + "Test") not in text


def main() -> int:
    failed = 0
    for name, fn in (
        ("http_keeps_newest_cap", test_http_keeps_newest_cap),
        ("live_http_is_capped", test_live_http_is_capped),
        ("note_copies_hit", test_note_copies_hit),
        ("this_file_does_not_skip", test_this_file_does_not_skip),
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
