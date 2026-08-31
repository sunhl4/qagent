"""A-02-live: honest live-qchem evidence. No minted twin_id. No invented qchem-cli."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import traceback
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
NOTE = ROOT / "docs" / "execution" / "A-02_live.md"
PROBE_CALLED = False
LIVE_SCENARIO = "minimal_vqe"
_CIRCUIT_BODY = ("qasm", "qasm3", "circuit", "circuit_body", "OPENQASM")


class Skip(Exception):
    """Honest skip: live qchem-run missing or not working. Exit 0."""


def _live_forced() -> bool:
    return (os.environ.get("QAGENT_LIVE_QCHEM") or "").strip() == "1"


def _note_text() -> str:
    assert NOTE.exists(), f"missing {NOTE}"
    return NOTE.read_text(encoding="utf-8")


def _no_forbidden_handles(payload: Mapping[str, Any]) -> None:
    blob = json.dumps(payload, ensure_ascii=False)
    assert "twin_id" not in blob
    assert "circuit_id" not in payload
    for key in _CIRCUIT_BODY:
        assert key not in payload


def probe_live_qchem() -> dict[str, Any]:
    """Talk to live qchem-run. Call only when QAGENT_LIVE_QCHEM=1."""
    global PROBE_CALLED
    PROBE_CALLED = True

    from qagent.adapters.homes import qchem_bin, qchem_bin_requested

    exe = qchem_bin()
    requested = qchem_bin_requested()
    exe_ok = bool(exe) and Path(exe).is_file() and os.access(exe, os.X_OK)
    if not exe_ok:
        raise Skip(f"QAGENT_QCHEM_HOME/BIN missing or not working ({requested or 'unset'})")

    evidence: dict[str, Any] = {
        "asset_id": None,
        "via": None,
        "note": "no live asset_id",
    }
    argv = [str(exe), "--scenario", LIVE_SCENARIO, "--json-summary"]
    print("$", " ".join(argv))
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=180, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Skip(f"qchem-run failed: {exc}") from exc
    print(f"rc={proc.returncode}")
    print((proc.stdout or "")[:400])
    if proc.stderr:
        print((proc.stderr or "")[:200])
    if proc.returncode != 0:
        raise Skip(f"qchem-run failed rc={proc.returncode}")
    try:
        summary = json.loads((proc.stdout or "").strip() or "{}")
    except json.JSONDecodeError as exc:
        raise Skip("qchem-run did not print JSON") from exc
    if not isinstance(summary, dict):
        raise Skip("qchem-run JSON was not an object")
    asset_id = str(summary.get("asset_id") or summary.get("experiment_id") or "").strip()
    if not asset_id:
        raise Skip("qchem-run printed no asset_id")
    evidence["asset_id"] = asset_id
    evidence["via"] = "qchem-cli"
    evidence["note"] = f"qchem-run returned asset_id={asset_id}"
    _no_forbidden_handles(evidence)
    print(f"live asset_id={asset_id} via=qchem-cli")
    return evidence


def test_note_exists() -> None:
    assert NOTE.exists(), f"missing {NOTE}"
    text = _note_text()
    assert "A-02" in text
    assert "QAGENT_LIVE_QCHEM" in text
    assert "asset_id" in text
    assert "qchem-run" in text
    assert "minimal_vqe" in text


def test_refuses_fake_cli() -> None:
    text = _note_text()
    compact = "".join(text.split())
    assert "未打" in text
    assert "未证明" in text or "unproven" in text.lower()
    assert "unproven" in text.lower()
    assert "qchem-cli" in compact
    assert "未写" in text
    assert "不发明" in text or "不许" in text
    assert "假" in text or "fake" in text.lower()
    assert "qagent-local-card" in text or "本地卡" in text
    assert "A-02" in text
    if "活 qchem 已通" in text or "活qchem已通" in compact:
        negated = any(token in text for token in ("不许", "不要", "不是", "未打", "未证明", "造假"))
        assert negated, "「活 qchem 已通」appears without an honest negation"


def test_no_twin_id() -> None:
    text = _note_text()
    assert "twin_id" in text
    assert any(token in text for token in ("不铸", "无 twin_id", "不许铸"))
    assert "twin_must_not" not in text
    assert '"twin_' not in text


def test_probe_exists_gated() -> None:
    assert callable(probe_live_qchem)
    assert PROBE_CALLED is False
    src = Path(__file__).read_text(encoding="utf-8")
    assert "def probe_live_qchem" in src
    assert "QAGENT_LIVE_QCHEM" in src
    if not _live_forced():
        assert PROBE_CALLED is False


def test_live_probe_optional() -> None:
    if not _live_forced():
        print("skip live probe (QAGENT_LIVE_QCHEM!=1)")
        return
    try:
        probe_live_qchem()
    except Skip as exc:
        print(f"skip  {exc}")


def main() -> int:
    failed = 0
    for name, fn in (
        ("note_exists", test_note_exists),
        ("refuses_fake_cli", test_refuses_fake_cli),
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
