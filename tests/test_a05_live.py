"""A-05-live: honest live catalog evidence. No minted twin_id. No Pauli dump."""

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
NOTE = ROOT / "docs" / "execution" / "A-05_live.md"
CATALOG_CAP = 20
PROBE_CALLED = False
_ROW_KEYS = frozenset({"kind", "name", "asset_id"})
_FORBIDDEN = frozenset(
    {
        "bitstrings",
        "rows",
        "pauli_terms",
        "counts_full",
        "result_full",
        "qasm",
        "qasm3",
        "body",
        "summary",
        "twin_id",
    }
)


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
    except urllib.error.HTTPError:
        return True
    except (urllib.error.URLError, TimeoutError, OSError):
        return False
    return True


def _http_json(url: str) -> tuple[int, Any]:
    request = urllib.request.Request(url, headers={"Accept": "application/json"}, method="GET")
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
        parsed = json.loads(raw) if raw else []
    except json.JSONDecodeError:
        raise Skip("GET /v1/assets did not return JSON") from None
    return status, parsed


def _public_row(raw: Mapping[str, Any]) -> dict[str, str]:
    row: dict[str, str] = {}
    kind = str(raw.get("kind") or "").strip()
    name = str(raw.get("name") or "").strip()
    asset_id = str(raw.get("asset_id") or "").strip()
    if kind:
        row["kind"] = kind[:80]
    if name:
        row["name"] = name[:80]
    if asset_id:
        row["asset_id"] = asset_id
    return row


def _assert_clean(payload: Mapping[str, Any]) -> None:
    blob = json.dumps(payload, ensure_ascii=False)
    leaked = [key for key in _FORBIDDEN if key in blob]
    assert not leaked, leaked
    assets = payload.get("assets") or []
    assert len(assets) <= CATALOG_CAP
    for row in assets:
        assert isinstance(row, dict)
        assert set(row) <= _ROW_KEYS
        assert "twin_id" not in row
        assert "pauli_terms" not in row


def _live_store(home: Path | None) -> Path | None:
    override = (os.environ.get("QAGENT_QDATA_STORE") or "").strip()
    if override:
        path = Path(override)
        return path if path.is_dir() else None
    if home is None:
        return None
    candidate = home / ".qdata-serve"
    return candidate if candidate.is_dir() else None


def _rows_from_cli(exe: str, store: Path) -> list[dict[str, str]]:
    argv = [exe, "assets", "--store", str(store)]
    print("$", " ".join(argv))
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Skip(f"qdata assets failed: {exc}") from exc
    print(f"rc={proc.returncode}")
    if proc.returncode != 0:
        raise Skip(f"qdata assets failed rc={proc.returncode}")
    rows: list[dict[str, str]] = []
    for line in (proc.stdout or "").splitlines():
        text = line.strip()
        if not text:
            continue
        parts = text.split()
        row: dict[str, str] = {}
        if parts:
            row["asset_id"] = parts[0]
        if len(parts) >= 2:
            row["kind"] = parts[1][:80]
        if row:
            rows.append(row)
        if len(rows) >= CATALOG_CAP:
            break
    return rows


def probe_live_catalog() -> dict[str, Any]:
    """Talk to live qdata assets CLI or GET /v1/assets. Call only when QAGENT_LIVE_QDATA=1."""
    global PROBE_CALLED
    PROBE_CALLED = True

    from qagent.adapters.homes import qdata_bin, qdata_url

    exe = qdata_bin()
    url = qdata_url()
    home_raw = (os.environ.get("QAGENT_QDATA_HOME") or "").strip()
    home = Path(home_raw) if home_raw else None
    exe_ok = bool(exe) and Path(exe).is_file() and os.access(exe, os.X_OK)
    url_ok = bool(url) and _http_reachable(str(url))
    if not exe_ok and not url_ok:
        raise Skip("QAGENT_QDATA_HOME/BIN or QAGENT_QDATA_URL missing or not working")

    evidence: dict[str, Any] = {
        "via": None,
        "length": None,
        "assets": [],
        "note": "no live catalog",
    }

    if exe_ok:
        store = _live_store(home)
        if store is None:
            raise Skip("live home has no store to list")
        rows = _rows_from_cli(str(exe), store)
        evidence["via"] = "qdata-cli"
        evidence["length"] = len(rows)
        evidence["assets"] = rows
        evidence["note"] = f"qdata assets returned length={len(rows)}"
        _assert_clean(evidence)
        print(f"live catalog length={len(rows)} via=qdata-cli (no Pauli, no twin_id)")
        return evidence

    assert url_ok and url
    status, parsed = _http_json(str(url).rstrip("/") + "/v1/assets")
    print(f"GET /v1/assets HTTP {status}")
    if status >= 400:
        raise Skip(f"GET /v1/assets HTTP {status}")
    raw_rows = parsed if isinstance(parsed, list) else parsed.get("assets") if isinstance(parsed, dict) else []
    if not isinstance(raw_rows, list):
        raise Skip("GET /v1/assets JSON was not a list")
    rows = [_public_row(item) for item in raw_rows if isinstance(item, dict)][:CATALOG_CAP]
    evidence["via"] = "qdata-http"
    evidence["length"] = len(rows)
    evidence["assets"] = rows
    evidence["note"] = f"GET /v1/assets returned length={len(rows)}"
    _assert_clean(evidence)
    print(f"live catalog length={len(rows)} via=qdata-http (no Pauli, no twin_id)")
    return evidence


def test_note_exists() -> None:
    assert NOTE.exists(), f"missing {NOTE}"
    text = _note_text()
    assert "A-05" in text
    assert "QAGENT_LIVE_QDATA" in text
    assert "qdata_list_assets" in text
    assert "qdata assets" in text
    assert "/v1/assets" in text
    assert "8787" in text


def test_refuses_live_pass() -> None:
    text = _note_text()
    compact = "".join(text.split())
    assert "未打" in text
    assert "未证明" in text or "unproven" in text.lower()
    assert "unproven" in text.lower()
    assert "活目录已通" in text
    assert "不许" in text or "不要" in text
    assert "离线" in text or "A-05" in text
    if "活目录已通" in text or "活目录已通" in compact:
        negated = any(token in text for token in ("不许", "不要", "不是", "未打", "未证明", "造假"))
        assert negated, "「活目录已通」appears without an honest negation"


def test_no_pauli() -> None:
    text = _note_text()
    assert "Pauli" in text or "pauli" in text
    assert "全文" in text or "不抄" in text
    dump = "Z0" + " X1"
    assert dump not in text
    assert "OPENQASM" not in text
    assert '"pauli_terms"' not in text


def test_no_twin() -> None:
    text = _note_text()
    assert "twin_id" in text
    assert any(token in text for token in ("不铸", "无 twin_id", "不许铸"))
    assert "twin_must_not" not in text
    assert '"twin_' not in text


def test_probe_exists_gated() -> None:
    assert callable(probe_live_catalog)
    assert PROBE_CALLED is False
    src = Path(__file__).read_text(encoding="utf-8")
    assert "def probe_live_catalog" in src
    assert "QAGENT_LIVE_QDATA" in src
    if not _live_forced():
        assert PROBE_CALLED is False


def test_live_probe_optional() -> None:
    if not _live_forced():
        print("skip live probe (QAGENT_LIVE_QDATA!=1)")
        return
    try:
        probe_live_catalog()
    except Skip as exc:
        print(f"skip  {exc}")


def main() -> int:
    failed = 0
    for name, fn in (
        ("note_exists", test_note_exists),
        ("refuses_live_pass", test_refuses_live_pass),
        ("no_pauli", test_no_pauli),
        ("no_twin", test_no_twin),
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
