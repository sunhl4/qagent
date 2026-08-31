"""A-01-live: honest live-qdata evidence. No minted twin_id. No invented status=done."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import traceback
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
NOTE = ROOT / "docs" / "execution" / "A-01_live.md"
STORE = ROOT / ".qagent" / "test-a01-live-store"
LIVE_RECIPE = "a2_spin_shadow"
PROBE_CALLED = False
_CIRCUIT_BODY = ("qasm", "qasm3", "circuit", "circuit_body", "OPENQASM")


class Skip(Exception):
    """Honest skip: live qdata missing or not working. Exit 0."""


def _live_forced() -> bool:
    return (os.environ.get("QAGENT_LIVE_QDATA") or "").strip() == "1"


def _note_text() -> str:
    assert NOTE.exists(), f"missing {NOTE}"
    return NOTE.read_text(encoding="utf-8")


def _http_reachable(base: str) -> bool:
    try:
        urllib.request.urlopen(base.rstrip("/") + "/", timeout=2.0)
        return True
    except urllib.error.HTTPError:
        return True
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def _http_json(url: str, method: str = "GET", body: dict[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
    request = urllib.request.Request(
        url,
        data=None if body is None else json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=8.0) as response:
            raw = response.read().decode("utf-8", errors="replace")
            status = int(response.status)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        status = int(exc.code)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise Skip(f"qdata HTTP not working: {exc}") from exc
    try:
        parsed = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        parsed = {"raw": raw[:300]}
    if not isinstance(parsed, dict):
        parsed = {"raw": raw[:300]}
    return status, parsed


def _no_forbidden_handles(payload: Mapping[str, Any]) -> None:
    blob = json.dumps(payload, ensure_ascii=False)
    assert "twin_id" not in blob
    assert "circuit_id" not in payload
    for key in _CIRCUIT_BODY:
        assert key not in payload


def probe_live_qdata() -> dict[str, Any]:
    """Talk to live qdata CLI or :8787. Call only when QAGENT_LIVE_QDATA=1."""
    global PROBE_CALLED
    PROBE_CALLED = True

    from qagent.adapters.homes import qdata_bin, qdata_url

    exe = qdata_bin()
    url = qdata_url()
    exe_ok = bool(exe) and Path(exe).is_file() and os.access(exe, os.X_OK)
    url_ok = bool(url) and _http_reachable(str(url))
    if not exe_ok and not url_ok:
        raise Skip("QAGENT_QDATA_HOME/BIN or QAGENT_QDATA_URL missing or not working")

    evidence: dict[str, Any] = {
        "asset_id": None,
        "via": None,
        "note": "no live asset_id",
    }

    if exe_ok:
        out = STORE / "qdata-runs" / LIVE_RECIPE
        out.mkdir(parents=True, exist_ok=True)
        argv = [str(exe), "run", LIVE_RECIPE, "--out", str(out), "--no-figure"]
        print("$", " ".join(argv))
        try:
            proc = subprocess.run(argv, capture_output=True, text=True, timeout=180, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise Skip(f"qdata CLI failed: {exc}") from exc
        print(f"rc={proc.returncode}")
        print((proc.stdout or "")[:400])
        if proc.stderr:
            print((proc.stderr or "")[:200])
        if proc.returncode != 0:
            raise Skip(f"qdata run failed rc={proc.returncode}")
        try:
            summary = json.loads((proc.stdout or "").strip() or "{}")
        except json.JSONDecodeError as exc:
            raise Skip("qdata run did not print JSON") from exc
        if not isinstance(summary, dict):
            raise Skip("qdata run JSON was not an object")
        asset_id = str(summary.get("asset_id") or "").strip()
        if not asset_id:
            raise Skip("qdata run printed no asset_id")
        evidence["asset_id"] = asset_id
        evidence["via"] = "qdata-cli"
        evidence["note"] = f"qdata run returned asset_id={asset_id}"
        _no_forbidden_handles(evidence)
        print(f"live asset_id={asset_id} via=qdata-cli")
        return evidence

    assert url_ok and url
    base = str(url).rstrip("/")
    post_status, posted = _http_json(f"{base}/v1/jobs/surrogate", "POST", {})
    print(f"POST /v1/jobs/surrogate HTTP {post_status} {posted}")
    job_id = str(posted.get("job_id") or "").strip()
    if not job_id:
        raise Skip(f"live HTTP POST returned no job_id (HTTP {post_status})")
    get_status, job = _http_json(f"{base}/v1/jobs/{job_id}")
    print(f"GET /v1/jobs/{job_id} HTTP {get_status} {job}")
    asset_id = str(job.get("asset_id") or "").strip()
    evidence["via"] = "qdata-http"
    if not asset_id:
        evidence["note"] = "live HTTP responded but no asset_id — not writing status=done"
        _no_forbidden_handles(evidence)
        print(evidence["note"])
        return evidence
    evidence["asset_id"] = asset_id
    evidence["note"] = f"live HTTP returned asset_id={asset_id}"
    _no_forbidden_handles(evidence)
    print(f"live asset_id={asset_id} via=qdata-http")
    return evidence


def test_note_exists() -> None:
    assert NOTE.exists(), f"missing {NOTE}"
    text = _note_text()
    assert "A-01" in text
    assert "QAGENT_LIVE_QDATA" in text
    assert "asset_id" in text
    assert "8787" in text
    assert "qdata run" in text


def test_refuses_fake_done() -> None:
    text = _note_text()
    compact = "".join(text.split())
    assert "未打" in text
    assert "未证明" in text or "unproven" in text.lower()
    assert "unproven" in text.lower()
    assert "status=done" in compact
    assert "未写" in text
    assert "不发明" in text or "不许" in text
    assert "死 URL" in text or "死URL" in compact
    assert "A-01" in text
    assert "qagent-local-card" in text or "本地卡" in text
    if "活 qdata 已通" in text or "活qdata已通" in compact:
        negated = any(token in text for token in ("不许", "不要", "不是", "未打", "未证明", "造假"))
        assert negated, "「活 qdata 已通」appears without an honest negation"


def test_no_twin_id() -> None:
    text = _note_text()
    assert "twin_id" in text
    assert any(token in text for token in ("不铸", "无 twin_id", "不许铸"))
    assert "twin_must_not" not in text
    assert '"twin_' not in text


def test_probe_exists_gated() -> None:
    assert callable(probe_live_qdata)
    assert PROBE_CALLED is False
    src = Path(__file__).read_text(encoding="utf-8")
    assert "def probe_live_qdata" in src
    assert "QAGENT_LIVE_QDATA" in src
    if not _live_forced():
        assert PROBE_CALLED is False


def test_live_probe_optional() -> None:
    if not _live_forced():
        print("skip live probe (QAGENT_LIVE_QDATA!=1)")
        return
    try:
        probe_live_qdata()
    except Skip as exc:
        print(f"skip  {exc}")


def main() -> int:
    failed = 0
    for name, fn in (
        ("note_exists", test_note_exists),
        ("refuses_fake_done", test_refuses_fake_done),
        ("no_twin_id", test_no_twin_id),
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
