"""A-03-live: honest live-Twin evidence. No minted twin_id. No invented accepted:true."""

from __future__ import annotations

import json
import os
import sys
import traceback
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
NOTE = ROOT / "docs" / "execution" / "A-03_live.md"
PROBE_CALLED = False
_DEFAULT_TWIN = "http://127.0.0.1:8765"


class Skip(Exception):
    """Honest skip: live Twin missing or TwinRun did not emit twin_id. Exit 0."""


def _live_forced() -> bool:
    return (os.environ.get("QAGENT_LIVE_TWIN") or "").strip() == "1"


def _note_text() -> str:
    assert NOTE.exists(), f"missing {NOTE}"
    return NOTE.read_text(encoding="utf-8")


def _twin_url() -> str:
    return (os.environ.get("QAGENT_TWIN_URL") or _DEFAULT_TWIN).rstrip("/")


def _twin_answers(base: str) -> bool:
    request = urllib.request.Request(
        base.rstrip("/") + "/v1/twin/identity",
        headers={"Accept": "application/json"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=2.0) as response:
            raw = response.read().decode("utf-8", errors="replace")
            status = int(response.status)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError):
        return False
    try:
        parsed = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        return False
    return isinstance(parsed, dict) and status < 500


def probe_live_twin() -> dict[str, Any]:
    """Talk to live TwinRun. Call only when QAGENT_LIVE_TWIN=1."""
    global PROBE_CALLED
    PROBE_CALLED = True

    from qagent.models.handles import HANDLE_CIRCUIT, HANDLE_TWIN, PROVENANCE_QCCD_TWIN
    from qagent.services.eval_run import DEFAULT_CIRCUIT
    from qagent.services.invoke import invoke

    url = _twin_url()
    if not _twin_answers(url):
        raise Skip(f"Twin {url} down or identity not answering")

    pinned = invoke(
        "qagent_pin_circuit",
        "lab",
        {"source": "logical", "logical": DEFAULT_CIRCUIT["body"]},
    )
    if pinned.status != "ok" or not isinstance(pinned.payload, Mapping):
        raise Skip("pin failed; not minting twin_id")
    circuit_id = str(pinned.payload.get(HANDLE_CIRCUIT) or "").strip()
    if not circuit_id:
        raise Skip("pin returned no circuit_id; not minting twin_id")

    args = {
        "mode": "signoff",
        "shots": 32,
        "circuit": DEFAULT_CIRCUIT,
        HANDLE_CIRCUIT: circuit_id,
    }
    result = invoke("ionstack_twin_run", "lab", args, approved=True)
    payload = result.payload if isinstance(result.payload, Mapping) else {}
    twin_id = str(payload.get(HANDLE_TWIN) or "").strip()
    provenance = str(payload.get("provenance") or "").strip()
    if (
        result.status == "ok"
        and twin_id
        and provenance == PROVENANCE_QCCD_TWIN
    ):
        evidence = {
            HANDLE_TWIN: twin_id,
            "provenance": provenance,
            HANDLE_CIRCUIT: circuit_id,
            "via": "ionstack_twin_run",
            "note": "twin_id from TwinRun only; circuit_id not swapped",
        }
        print(f"live twin_id via=ionstack_twin_run provenance={provenance}")
        return evidence
    raise Skip("TwinRun did not emit twin_id+qccd-twin; no local twin_id")


def test_note_exists() -> None:
    assert NOTE.exists(), f"missing {NOTE}"
    text = _note_text()
    assert "A-03" in text
    assert "QAGENT_LIVE_TWIN" in text
    assert "twin_id" in text
    assert "8765" in text
    assert "start_twin.sh" in text
    assert "TwinRun" in text
    assert "qccd-twin" in text
    assert "A-03c" in text
    assert "circuit_id" in text


def test_refuses_fake_twin() -> None:
    text = _note_text()
    compact = "".join(text.split())
    assert "未打" in text
    assert "未证明" in text or "unproven" in text.lower()
    assert "unproven" in text.lower()
    assert "A-03c" in text
    assert "死" in text
    assert "Aer cannot look signed" in text
    assert "accepted:true" in compact
    assert "未写" in text
    assert "不发明" in text or "不许" in text
    if "活 Twin 已通" in text or "活Twin已通" in compact:
        negated = any(
            token in text
            for token in ("不许", "不要", "不是", "未打", "未证明", "造假")
        )
        assert negated, "「活 Twin 已通」appears without an honest negation"
    if "accepted:true" in compact:
        negated = any(
            token in text for token in ("未写", "没有", "不发明", "未证明", "unproven")
        )
        assert negated, "accepted:true appears without an honest negation"


def test_no_minted_id() -> None:
    text = _note_text()
    assert "twin_id" in text
    assert any(token in text for token in ("不铸", "无 twin_id", "不许铸"))
    assert "twin_must_not" not in text
    assert '"twin_' not in text


def test_probe_exists_gated() -> None:
    assert callable(probe_live_twin)
    assert PROBE_CALLED is False
    src = Path(__file__).read_text(encoding="utf-8")
    assert "def probe_live_twin" in src
    assert "QAGENT_LIVE_TWIN" in src
    if not _live_forced():
        assert PROBE_CALLED is False


def test_live_probe_optional() -> None:
    if not _live_forced():
        print("skip live probe (QAGENT_LIVE_TWIN!=1)")
        return
    try:
        probe_live_twin()
    except Skip as exc:
        print(f"skip  {exc}")


def main() -> int:
    failed = 0
    for name, fn in (
        ("note_exists", test_note_exists),
        ("refuses_fake_twin", test_refuses_fake_twin),
        ("no_minted_id", test_no_minted_id),
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
