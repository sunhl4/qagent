"""A-01i: live qdata get_job. submit then invoke(qdata_get_job). Skip-as-green is incomplete."""

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
_NOTE = ROOT / "docs" / "execution" / "A-01i_get_job.md"
_OLD_LIVE = ROOT / "docs" / "execution" / "A-01_live.md"
_STORE = ROOT / ".qagent" / "test-a01i-store"
_COPIED_INVOKE_JOB = "8179cf73884f457ab50ac4e27c81536d"
_COPIED_HTTP_JOB = "712337a00c4741a8a245c52e7a7cc8cf"
_COPIED_JOB_STATUS = "failed"
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


def test_live_invoke_get_job() -> None:
    health = _healthz()
    assert health.get("status") == "ok", f":8787 healthz failed: {health!r}"
    with live_qdata_http_env():
        assert os.environ.get("QAGENT_QDATA_URL") == _LIVE_URL
        assert not os.environ.get("QAGENT_QDATA_HOME")
        submitted = invoke("qdata_submit_job", "lab", {"kind": _KIND, "payload": {}})
        assert submitted.status == "ok", f"submit expected ok, got {submitted.status}: {submitted.error}"
        submit_payload = dict(submitted.payload or {})
        job_id = str(submit_payload.get("job_id") or "").strip()
        assert job_id, "no live job_id — cannot get_job"
        _no_twin(submit_payload)
        got = invoke("qdata_get_job", "lab", {"job_id": job_id})
    assert got.status == "ok", f"get_job expected ok, got {got.status}: {got.error}"
    payload = dict(got.payload or {})
    assert payload, "get_job returned empty payload"
    assert "status" in payload, f"get_job payload missing status: {payload!r}"
    assert payload.get("status") != "done", f"must not write status=done, got {payload!r}"
    assert payload.get("accepted") is not True
    _no_twin(payload)
    print(
        f"live job_id={job_id} kind={_KIND} invoke_status={got.status} "
        f"payload_status={payload.get('status')!r} payload={json.dumps(payload, ensure_ascii=False)}"
    )


def test_note_copies_hit() -> None:
    assert _NOTE.is_file(), f"missing {_NOTE}"
    text = _NOTE.read_text(encoding="utf-8")
    assert _COPIED_INVOKE_JOB in text
    assert _COPIED_HTTP_JOB in text
    assert _COPIED_JOB_STATUS in text
    assert "qdata_get_job" in text
    assert "qdata_submit_job" in text
    assert "invoke" in text
    assert "/v1/jobs/" in text
    assert _LIVE_URL in text
    assert "QAGENT_QDATA_URL" in text
    assert "job_id" in text
    assert '"status"' in text
    assert "train_features" in text
    assert "不算 G0" in text
    assert "不算 G2" in text
    assert "G0 已通过" not in text
    assert "accepted:true" not in text
    assert "skip 当绿" in text
    assert "未 commit" in text
    assert "apply_env" in text
    assert "workplace.json" in text
    assert "A-01_live" in text


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
    assert ("apply_env" + "()") not in text


def main() -> int:
    if _STORE.exists():
        shutil.rmtree(_STORE)
    failed = 0
    for name, fn in (
        ("healthz_live", test_healthz_live),
        ("live_invoke_get_job", test_live_invoke_get_job),
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
