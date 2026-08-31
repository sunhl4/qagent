"""H-03d-live: honest live model-switch evidence. No minted twin_id. No fake switch."""

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
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

NOTE = ROOT / "docs" / "execution" / "H-03d_live.md"
PROBE_CALLED = False
_SECRET = "sk-h03d-never-echo-xyz"
_HPC = "hpc-pass-h03d-live"
_QTM = "q-pass-h03d-live"
_SECRET_KEYS = ("llm_api_key", "hpc_secret", "quantum_secret")
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


class Skip(Exception):
    """Honest skip: live dsh missing or host.describe unavailable. Exit 0."""


def _live_forced() -> bool:
    mux = (os.environ.get("QAGENT_LIVE_MUX") or "").strip() == "1"
    h03 = (os.environ.get("QAGENT_LIVE_H03") or "").strip() == "1"
    return mux or h03


def _note_text() -> str:
    assert NOTE.exists(), f"missing {NOTE}"
    return NOTE.read_text(encoding="utf-8")


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


def _get(url: str, *, timeout: float = 2.0) -> tuple[int, str]:
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read(4096).decode("utf-8", errors="replace")
            return int(response.status), body
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return int(exc.code), body


def _reachable(base: str) -> bool:
    try:
        _get(base.rstrip("/") + "/", timeout=2.0)
        return True
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def probe_live_model_switch() -> dict[str, Any]:
    """Talk to already-running dsh. Call only when QAGENT_LIVE_MUX=1 or QAGENT_LIVE_H03=1."""
    global PROBE_CALLED
    PROBE_CALLED = True

    from qagent.adapters.dsh_session import DshSessionClient, DshSessionError, dsh_base_url

    base = dsh_base_url()
    if not _reachable(base):
        raise Skip("3081 down")

    client = DshSessionClient(base_url=base, timeout=12.0)
    try:
        described = client.rpc("host.describe", {})
    except DshSessionError as exc:
        raise Skip(f"host.describe unavailable: {exc.code}: {exc}") from exc

    if not isinstance(described, dict):
        raise Skip("host.describe unavailable: not an object")
    model = str(described.get("model") or "").strip()
    provider = str(described.get("provider") or "").strip()
    if not model:
        raise Skip("host.describe unavailable: empty model")
    print(f"host.describe model={model} provider={provider}")

    session_id = ""
    try:
        session_id = client.create(agent_preset="qagent")
        print(f"create=ok sessionId={session_id}")
    except DshSessionError as exc:
        print(f"session.create skipped: {exc.code}: {exc}")
    assert "twin_id" not in session_id

    # Observational only. This package must not write workplace store, so it
    # cannot apply_env a new default and re-describe. Current model ≠ switched.
    evidence: dict[str, Any] = {
        "describe_ok": True,
        "model": model,
        "provider": provider,
        "session_id": session_id,
        "respond_attempted": False,
        "switched": False,
        "note": "host.describe 见到当前模型，未见 apply_env 之后的新模型",
    }
    print(
        "live",
        f"describe=ok model={model}",
        "switched=false",
        "respond_attempted=false",
        "未打 换默认模型下一句人话生效",
    )
    return evidence


def test_note_exists() -> None:
    assert NOTE.exists(), f"missing {NOTE}"
    text = _note_text()
    assert "H-03d" in text
    assert "host.describe" in text
    assert "apply_env" in text
    assert "GET /api/workplace" in text
    assert "QAGENT_LIVE_H03" in text
    assert "QAGENT_LIVE_MUX" in text
    assert "3081" in text
    assert "DEEPSEEK_MODEL" in text


def test_refuses_fake_switch() -> None:
    text = _note_text()
    compact = "".join(text.split())
    assert "未打" in text
    assert "未证明" in text or "unproven" in text.lower()
    assert "unproven" in text.lower()
    assert "host.describe" in text
    assert "apply_env" in text
    assert "下一句" in text
    assert "新模型" in text
    assert "未尝试" in text or "不 POST" in text
    assert "/api/respond" in text
    assert any(token in text for token in ("不铸", "不编造", "禁止铸造"))
    assert "twin_id" in text
    if "活模型切换已通" in text or "活模型切换已通" in compact:
        negated = any(token in text for token in ("不许", "不要", "不是", "未打", "未证明", "造假", "拒绝"))
        assert negated, "「活模型切换已通」appears without an honest negation"
    src = Path(__file__).read_text(encoding="utf-8")
    start = src.index("def probe_live_model_switch")
    end = src.index("def test_note_exists")
    probe_src = src[start:end]
    assert "/api/respond" not in probe_src
    assert "client.respond" not in probe_src
    assert "minted-rpc" not in _note_text()


def test_get_never_secrets() -> None:
    text = _note_text()
    assert "GET /api/workplace" in text
    assert any(token in text for token in ("永不", "没有密钥", "不含密钥", "不回密钥", "无密钥", "没有密钥值"))
    assert "llm_api_key" in text
    assert "has_*" in text or "has_llm_key" in text

    from qagent.entrypoints.shell_http import dispatch
    from qagent.services.workplace import save_workplace

    with _temp_workplace():
        save_workplace(
            {"llm_model": "unitqc-local", "llm_pool": _POOL},
            {
                "llm_api_key": _SECRET,
                "hpc_secret": _HPC,
                "quantum_secret": _QTM,
            },
        )
        code, payload = dispatch("GET", "/api/workplace")
        assert code == 200
        assert isinstance(payload, dict)
        dumped = json.dumps(payload, ensure_ascii=False)
        assert _SECRET not in dumped
        assert _HPC not in dumped
        assert _QTM not in dumped
        keys = _all_keys(payload)
        for key in _SECRET_KEYS:
            assert key not in keys
            assert key not in payload
            assert key not in (payload.get("workplace") or {})
        public = payload["workplace"]
        assert public["has_llm_key"] is True
        assert public["has_hpc_secret"] is True
        assert public["has_quantum_secret"] is True


def test_probe_exists_gated() -> None:
    assert callable(probe_live_model_switch)
    assert PROBE_CALLED is False
    src = Path(__file__).read_text(encoding="utf-8")
    assert "def probe_live_model_switch" in src
    assert "QAGENT_LIVE_MUX" in src
    assert "QAGENT_LIVE_H03" in src
    assert "host.describe" in src
    if not _live_forced():
        assert PROBE_CALLED is False


def test_live_probe_optional() -> None:
    if not _live_forced():
        print("skip live probe (QAGENT_LIVE_MUX/QAGENT_LIVE_H03!=1)")
        return
    try:
        evidence = probe_live_model_switch()
        assert evidence.get("switched") is not True
        assert evidence.get("respond_attempted") is False
    except Skip as exc:
        print(f"skip  {exc}")


def main() -> int:
    failed = 0
    for name, fn in (
        ("note_exists", test_note_exists),
        ("refuses_fake_switch", test_refuses_fake_switch),
        ("get_never_secrets", test_get_never_secrets),
        ("probe_exists_gated", test_probe_exists_gated),
        ("live_probe_optional", test_live_probe_optional),
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
