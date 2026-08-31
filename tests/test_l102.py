"""L1-02: Codex oneshot/attended seams. No SPI scratch. No parent context."""

from __future__ import annotations

import json
import traceback
from pathlib import Path

from qagent.adapters.codex import WiredCodex
from qagent.adapters.contracts import ROOT
from qagent.services.eval_run import run_evals

_HANDLE = "twin" + "_id"
_TOOL = "ionstack_" + "twin" + "_run"
_SCRATCH = ROOT / ".qagent" / "spi_scratch"
_PROVIDER = _SCRATCH / "problem_provider.py"
_ADAPTER = ROOT / "src" / "qagent" / "adapters" / "codex.py"
_THIS = Path(__file__).resolve()
_NOTE = ROOT / "docs" / "execution" / "L1-02_codex_attended.md"


def _files_under(*roots: Path) -> frozenset[str]:
    found: set[str] = set()
    for root in roots:
        if not root.exists():
            continue
        if root.is_file():
            found.add(str(root.resolve()))
            continue
        for path in root.rglob("*"):
            if path.is_file():
                found.add(str(path.resolve()))
    return frozenset(found)


def _watch_roots() -> tuple[Path, ...]:
    return (_SCRATCH, ROOT / "src" / "qagent" / "adapters")


def _payload_blob(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True)


def test_oneshot_does_not_write_spi_scratch() -> None:
    if _PROVIDER.exists():
        _PROVIDER.unlink()
    before = _files_under(*_watch_roots())
    out = WiredCodex().oneshot({"task": "add a test ProblemProvider"})
    after = _files_under(*_watch_roots())
    assert not _PROVIDER.exists()
    assert after <= before
    assert out.get("needs_app_server") is True
    assert out.get("not_wired") is True
    assert out.get("inherits_parent_context") is False
    assert out.get("tools_called") == []
    assert _HANDLE not in _payload_blob(out)
    assert _TOOL not in _payload_blob(out)
    assert "TwinRun" not in _payload_blob(out)


def test_attended_not_approved_no_diff_no_files() -> None:
    if _PROVIDER.exists():
        _PROVIDER.unlink()
    before = _files_under(*_watch_roots())
    out = WiredCodex().attended({"task": "edit a file"})
    after = _files_under(*_watch_roots())
    assert out.get("applied") is False
    assert out.get("diff") is None
    assert out.get("approval_item") == "fileChange"
    assert out.get("no_diff_until_approved") is True
    assert out.get("inherits_parent_context") is False
    assert after <= before
    assert not _PROVIDER.exists()


def test_attended_approved_no_parent_context() -> None:
    if _PROVIDER.exists():
        _PROVIDER.unlink()
    before = _files_under(*_watch_roots())
    out = WiredCodex().attended({"task": "edit a file", "approved": True})
    after = _files_under(*_watch_roots())
    blob = _payload_blob(out)
    assert out.get("inherits_parent_context") is False
    assert out.get("applied") is False
    assert out.get("diff") is None
    assert out.get("approval_item") == "fileChange"
    assert isinstance(out.get("file_change"), dict)
    assert out["file_change"].get("status") == "pending"
    assert "TwinRun" not in blob
    assert _HANDLE not in blob
    assert _TOOL not in blob
    assert after <= before
    assert not _PROVIDER.exists()


def test_diff_has_no_forbidden_symbols() -> None:
    for path in (_ADAPTER, _THIS, _NOTE):
        text = path.read_text(encoding="utf-8")
        assert _HANDLE not in text, path
        assert _TOOL not in text, path


def test_e13_e17_eval_shape() -> None:
    rows = {row.id: row for row in run_evals("E13", "E17")}
    assert rows["E13"].ok, rows["E13"].detail
    assert rows["E17"].ok, rows["E17"].detail


def main() -> int:
    failed = 0
    for name, fn in (
        ("oneshot_no_spi_scratch", test_oneshot_does_not_write_spi_scratch),
        ("attended_unapproved", test_attended_not_approved_no_diff_no_files),
        ("attended_approved", test_attended_approved_no_parent_context),
        ("diff_symbols", test_diff_has_no_forbidden_symbols),
        ("e13_e17_eval", test_e13_e17_eval_shape),
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
