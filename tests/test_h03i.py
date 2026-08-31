"""H-03i: live 3080 face HOME health. Skip-as-green is incomplete."""

from __future__ import annotations

import json
import re
import sys
import traceback
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from qagent.models.handles import HANDLE_ASSET, HANDLE_CIRCUIT, HANDLE_TWIN

_NOTE = ROOT / "docs" / "execution" / "H-03i_face_homes.md"
_FACE = "http://127.0.0.1:3080"
_TOKEN = "workbench-review"
_HEALTH_URL = f"{_FACE}/api/health?token={_TOKEN}"
_WORKPLACE_URL = f"{_FACE}/api/workplace?token={_TOKEN}"
_COPIED_HEALTH = (
    '{"twin_live": true, "qdata_live": true, "qchem_live": true, '
    '"qdata_cli": true, "runtime_url": "http://127.0.0.1:3081"}'
)
_HANDLES = frozenset({HANDLE_CIRCUIT, HANDLE_ASSET, HANDLE_TWIN})
_ID_RE = re.compile(r"\b[a-z]+_id\b")
_SECRET_KEYS = ("llm_api_key", "hpc_secret", "quantum_secret")
_CLAIM_PASS = ("G0 已通过", "G0 passed")


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


def _get_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            raw = response.read().decode("utf-8")
            code = int(response.status)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise AssertionError(f"3080 HTTP {exc.code} ({url}): {body}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise AssertionError(f"3080 not reachable ({url}): {exc}") from exc
    assert code == 200, f"3080 expected 200, got {code} ({url}): {raw!r}"
    try:
        parsed = json.loads(raw) if raw else {}
    except json.JSONDecodeError as exc:
        raise AssertionError(f"3080 body is not JSON ({url}): {raw!r}") from exc
    if not isinstance(parsed, dict):
        raise AssertionError(f"3080 JSON must be an object, got {type(parsed).__name__}")
    return parsed


def test_live_health_homes() -> None:
    health = _get_json(_HEALTH_URL)
    assert health.get("qchem_live") is True, f"qchem_live={health!r}"
    assert health.get("qdata_cli") is True, f"qdata_cli={health!r}"
    assert health.get("twin_live") is True, f"twin_live={health!r}"
    assert health.get("qdata_live") is True, f"qdata_live={health!r}"
    assert health.get("runtime_url") == "http://127.0.0.1:3081"
    blob = json.dumps(health, ensure_ascii=False)
    assert HANDLE_TWIN not in _all_keys(health)
    assert HANDLE_TWIN not in blob
    for key in _SECRET_KEYS:
        assert key not in blob
    print(f"health={json.dumps(health, ensure_ascii=False)}")


def test_live_workplace_not_ready() -> None:
    payload = _get_json(_WORKPLACE_URL)
    public = payload.get("workplace") if isinstance(payload.get("workplace"), dict) else {}
    ready = payload.get("ready")
    has_llm = public.get("has_llm_key")
    assert public.get("llm_base_url") == "https://api.deepseek.com/v1"
    assert public.get("llm_model") == "deepseek-v4-flash"
    assert ready is True, f"form is filled; ready={ready!r}"
    assert has_llm is False, f"has_llm_key={has_llm!r}"
    keys = _all_keys(payload)
    for key in _SECRET_KEYS:
        assert key not in keys
        assert f'"{key}"' not in json.dumps(payload)
    print(
        "workplace",
        f"ready={ready!r}",
        f"has_llm_key={has_llm!r}",
        f"qdata_home={public.get('qdata_home')!r}",
        f"qchem_home={public.get('qchem_home')!r}",
    )


def test_note_copies_health() -> None:
    assert _NOTE.is_file(), f"missing {_NOTE}"
    text = _NOTE.read_text(encoding="utf-8")
    assert _COPIED_HEALTH in text
    assert '"qchem_live": true' in text
    assert '"qdata_cli": true' in text
    assert '"twin_live": true' in text
    assert '"qdata_live": true' in text
    assert '"runtime_url": "http://127.0.0.1:3081"' in text
    assert _HEALTH_URL in text
    assert "GET /api/health" in text
    assert "GET /api/workplace" in text
    assert "表单已 ready" in text
    assert "has_llm_key" in text
    assert "不算接线" in text
    assert "不算 G0" in text
    assert "skip 当绿" in text
    assert "未 commit" in text
    assert "secrets.json" in text
    assert "不读" in text
    assert "3080 不通必须失败" in text
    assert HANDLE_CIRCUIT in text
    assert HANDLE_ASSET in text
    assert HANDLE_TWIN in text
    assert "twin_id=" not in text
    assert "twin_id:" not in text
    for phrase in _CLAIM_PASS:
        assert phrase not in text
    for key in _SECRET_KEYS:
        assert f'"{key}"' not in text or "没有" in text
    assert "sk-" not in text


def test_this_file_does_not_skip() -> None:
    text = Path(__file__).read_text(encoding="utf-8")
    assert ("pytest" + ".skip") not in text
    assert ("unittest" + ".skip") not in text
    assert ("skip" + "Test") not in text
    assert ("class " + "Skip") not in text
    assert ("raise " + "Skip") not in text
    assert ("apply_env" + "()") not in text
    assert ("from qagent.services." + "workplace") not in text
    assert ("from qagent.services." + "health") not in text
    assert ("dispatch" + "(") not in text


def test_no_fourth_handle() -> None:
    for path in (_NOTE, Path(__file__)):
        extra = set(_ID_RE.findall(path.read_text(encoding="utf-8"))) - _HANDLES
        assert not extra, f"{path.name} invented handles: {sorted(extra)}"


def main() -> int:
    failed = 0
    for name, fn in (
        ("live_health_homes", test_live_health_homes),
        ("live_workplace_not_ready", test_live_workplace_not_ready),
        ("note_copies_health", test_note_copies_health),
        ("this_file_does_not_skip", test_this_file_does_not_skip),
        ("no_fourth_handle", test_no_fourth_handle),
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
