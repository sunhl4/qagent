"""A-01h: live qdata HTTP. invoke(qdata_submit_job) must return job_id. Skip-as-green is incomplete."""

from __future__ import annotations

import json
import os
import shutil
import sys
import traceback
import urllib.error
import urllib.request
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Mapping

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from qagent.models.handles import HANDLE_TWIN
from qagent.services.invoke import invoke

_LIVE_URL = "http://127.0.0.1:8787"
_KIND = "surrogate"
_NOTE = ROOT / "docs" / "execution" / "A-01h_http.md"
_OLD_LIVE = ROOT / "docs" / "execution" / "A-01_live.md"
_STORE = ROOT / ".qagent" / "test-a01h-store"
_COPIED_INVOKE_JOB = "4ba3afa7fc97441ca8139e6a849da378"
_COPIED_HTTP_JOB = "02ff89a045c3485b98170576689daf24"
_ENV_KEYS = (
    "QAGENT_QDATA_URL",
    "QAGENT_QDATA_HOME",
    "QAGENT_QDATA_BIN",
    "QAGENT_QDATA_PYTHON",
    "QAGENT_DATA_DIR",
    "QAGENT_ELN_FILE",
)


@contextmanager
def live_qdata_http_env() -> Iterator[None]:
    previous = {key: os.environ.get(key) for key in _ENV_KEYS}
    for key in _ENV_KEYS:
        os.environ.pop(key, None)
    _STORE.mkdir(parents=True, exist_ok=True)
    os.environ["QAGENT_QDATA_URL"] = _LIVE_URL
    os.environ["QAGENT_DATA_DIR"] = str(_STORE)
    os.environ["QAGENT_ELN_FILE"] = str(_STORE / "eln.jsonl")
    try:
        yield
    finally:
        for key in _ENV_KEYS:
            os.environ.pop(key, None)
        for key, value in previous.items():
            if value is not None:
                os.environ[key] = value


def _keys(obj: object) -> set[str]:
    found: set[str] = set()
    if isinstance(obj, dict):
        for key, value in obj.items():
            found.add(str(key))
            found.update(_keys(value))
    elif isinstance(obj, list):
        for item in obj:
            found.update(_keys(item))
    return found


def _no_twin(payload: Mapping[str, Any]) -> None:
    keys = _keys(payload)
    blob = json.dumps(payload, ensure_ascii=False)
    assert HANDLE_TWIN not in keys
    assert HANDLE_TWIN not in blob


def _healthz() -> dict[str, Any]:
    url = f"{_LIVE_URL}/v1/healthz"
    try:
        with urllib.request.urlopen(url, timeout=8) as resp:
            raw = resp.read().decode("utf-8")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise AssertionError(f":8787 healthz not reachable ({url}): {exc}") from exc
    try:
        parsed = json.loads(raw) if raw else {}
    except json.JSONDecodeError as exc:
        raise AssertionError(f":8787 healthz is not JSON: {raw!r}") from exc
    if not isinstance(parsed, dict):
        raise AssertionError(f":8787 healthz must be an object, got {type(parsed).__name__}")
    return parsed


def test_healthz_live() -> None:
    health = _healthz()
    assert health.get("status") == "ok", f"healthz={health!r}"
    print(f"healthz={json.dumps(health, ensure_ascii=False)}")


def test_live_invoke_submit_job() -> None:
    health = _healthz()
    assert health.get("status") == "ok", f":8787 healthz failed: {health!r}"
    with live_qdata_http_env():
        assert os.environ.get("QAGENT_QDATA_URL") == _LIVE_URL
        assert not os.environ.get("QAGENT_QDATA_HOME")
        invoked = invoke("qdata_submit_job", "lab", {"kind": _KIND, "payload": {}})
    assert invoked.status == "ok", f"expected ok, got {invoked.status}: {invoked.error}"
    payload = dict(invoked.payload or {})
    assert payload, "invoke returned empty payload"
    job_id = str(payload.get("job_id") or "").strip()
    assert job_id, "no live job_id — A-01h is not done"
    assert payload.get("status") != "done"
    assert payload.get("accepted") is not True
    _no_twin(payload)
    print(f"live job_id={job_id} kind={_KIND} invoke_status={invoked.status}")


def test_note_copies_hit() -> None:
    assert _NOTE.is_file(), f"missing {_NOTE}"
    text = _NOTE.read_text(encoding="utf-8")
    assert _COPIED_INVOKE_JOB in text
    assert _COPIED_HTTP_JOB in text
    assert "qdata_submit_job" in text
    assert "invoke" in text
    assert "/v1/healthz" in text
    assert "/v1/jobs/surrogate" in text
    assert _LIVE_URL in text
    assert "QAGENT_QDATA_URL" in text
    assert "job_id" in text
    assert "queued" in text
    assert "不算 G0" in text
    assert "不算 G2" in text
    assert "不算接线 Pennylane" in text
    assert "G0 已通过" not in text
    assert "accepted:true" not in text
    assert "skip 当绿" in text
    assert "未 commit" in text
    assert "apply_env" in text
    assert "workplace.json" in text
    assert "A-01_live" in text
    assert "未打" in text
    assert "未证明" in text


def test_a01_live_contract_untouched() -> None:
    assert _OLD_LIVE.is_file(), f"missing {_OLD_LIVE}"
    text = _OLD_LIVE.read_text(encoding="utf-8")
    assert "未打" in text
    assert "未证明" in text
    assert "unproven" in text.lower()
    assert "活 qdata **未证明**" in text


def test_this_file_does_not_skip() -> None:
    text = Path(__file__).read_text(encoding="utf-8")
    assert ("pytest" + ".skip") not in text
    assert ("unittest" + ".skip") not in text
    assert ("skip" + "Test") not in text
    assert ("from qagent.services." + "workplace") not in text


def main() -> int:
    if _STORE.exists():
        shutil.rmtree(_STORE)
    failed = 0
    for name, fn in (
        ("healthz_live", test_healthz_live),
        ("live_invoke_submit_job", test_live_invoke_submit_job),
        ("note_copies_hit", test_note_copies_hit),
        ("a01_live_contract_untouched", test_a01_live_contract_untouched),
        ("this_file_does_not_skip", test_this_file_does_not_skip),
    ):
        try:
            fn()
            print(f"ok  {name}")
        except Exception:
            failed += 1
            print(f"FAIL {name}")
            traceback.print_exc()
    if _STORE.exists():
        shutil.rmtree(_STORE)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
