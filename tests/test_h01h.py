"""H-01h: product 3081 defaults to lab. Skip-as-green is incomplete."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from qagent.models.handles import HANDLE_ASSET, HANDLE_CIRCUIT, HANDLE_TWIN
from qagent.services.policy import decide

NOTE = ROOT / "docs" / "execution" / "H-01h_product_lab_preset.md"
START = ROOT / "scripts" / "start_runtime.sh"
UI = ROOT / "scripts" / "start_ui.sh"
ASSIGNMENT = ROOT / "src" / "qagent" / "services" / "assignment.py"
_HANDLES = frozenset({HANDLE_CIRCUIT, HANDLE_ASSET, HANDLE_TWIN})
_ID_RE = __import__("re").compile(r"\b[a-z]+_id\b")
_G0_LAB = (
    ("qagent_list_engines", {}, "allow"),
    ("qccd_docs_search", {}, "allow"),
    ("ionstack_twin_identity", {}, "allow"),
    ("qchem_run", {}, "allow"),
    ("qdata_list_assets", {}, "allow"),
    ("qdata_sandbox_exec", {}, "allow"),
    ("qdata_run_recipe", {"name": "a2_chem_pes"}, "allow"),
)


def _text(path: Path) -> str:
    assert path.is_file(), f"missing {path}"
    return path.read_text(encoding="utf-8")


def test_note() -> None:
    text = _text(NOTE)
    assert "H-01h" in text
    assert "lab" in text
    assert "algo" in text
    assert "qagent-policy" in text
    assert "twin_id" in text
    assert "accepted:true" in text
    print("note names the leftover sign/algo block")


def test_start_runtime_defaults_lab() -> None:
    text = _text(START)
    assert "H-01h" in text
    assert 'QAGENT_PRESET:-lab' in text
    assert 'QAGENT_PRESET:-algo' not in text
    assert "active_preset" in text
    assert "QAGENT_H01H_HEAL_ONLY" in text
    ui = _text(UI)
    assert 'QAGENT_PRESET:-lab' in ui
    print("start_runtime and start_ui default lab")


def test_heal_stale_sign_to_lab() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        preset = Path(tmp) / "active_preset"
        preset.write_text("sign\n", encoding="utf-8")
        env = os.environ.copy()
        env.pop("QAGENT_PRESET", None)
        env["QAGENT_PRESET_FILE"] = str(preset)
        env["QAGENT_H01H_HEAL_ONLY"] = "1"
        proc = subprocess.run(
            ["bash", str(START)],
            cwd=str(ROOT),
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0, proc.stderr
        assert preset.read_text(encoding="utf-8").strip() == "lab"
    print("stale sign heals to lab")


def test_explicit_algo_still_writes() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        preset = Path(tmp) / "active_preset"
        preset.write_text("lab\n", encoding="utf-8")
        env = os.environ.copy()
        env["QAGENT_PRESET"] = "algo"
        env["QAGENT_PRESET_FILE"] = str(preset)
        env["QAGENT_H01H_HEAL_ONLY"] = "1"
        proc = subprocess.run(
            ["bash", str(START)],
            cwd=str(ROOT),
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0, proc.stderr
        assert preset.read_text(encoding="utf-8").strip() == "algo"
    print("explicit algo still writes")


def test_lab_allows_g0_tools_sign_algo_block() -> None:
    for tool, args, want in _G0_LAB:
        assert decide(tool, "lab", args) == want, (tool, "lab", args)
        if tool == "qagent_list_engines":
            continue
        if tool == "ionstack_twin_identity":
            assert decide(tool, "algo", args) == "deny"
            assert decide(tool, "sign", args) == "allow"
            continue
        if tool == "qccd_docs_search":
            assert decide(tool, "algo", args) == "allow"
            assert decide(tool, "sign", args) == "deny"
            continue
        assert decide(tool, "algo", args) == "deny", (tool, "algo")
        assert decide(tool, "sign", args) == "deny", (tool, "sign")
    assert decide("qdata_run_recipe", "lab", {}) == "deny"
    assert decide("ionstack_twin_run", "lab", {"shots": 1000}) == "ask"
    print("lab allows G0 tools; sign/algo still block the rest")


def test_no_fourth_handle_or_extra_pipeline() -> None:
    for path in (START, NOTE):
        for match in _ID_RE.findall(_text(path)):
            assert match in _HANDLES, (path.name, match)
    assert _text(ASSIGNMENT).count('"mode": "pipeline"') == 3
    print("still three handles; pipeline count frozen")


def main() -> int:
    failed = 0
    for name, fn in (
        ("note", test_note),
        ("start_runtime_defaults_lab", test_start_runtime_defaults_lab),
        ("heal_stale_sign_to_lab", test_heal_stale_sign_to_lab),
        ("explicit_algo_still_writes", test_explicit_algo_still_writes),
        ("lab_allows_g0_tools_sign_algo_block", test_lab_allows_g0_tools_sign_algo_block),
        ("no_fourth_handle_or_extra_pipeline", test_no_fourth_handle_or_extra_pipeline),
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
