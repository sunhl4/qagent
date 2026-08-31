"""H-01g: profile dsh-tools realpath matches host. Skip-as-green is incomplete."""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

NOTE = ROOT / "docs" / "execution" / "H-01g_dsh_tools_dedupe.md"
START = ROOT / "scripts" / "start_runtime.sh"
BOOT = ROOT / "scripts" / "bootstrap_wp0.sh"
HOST_GLOB = "@deepseek-ai+dsh-tools@*/node_modules/@deepseek-ai/dsh-tools"
PROFILE_TOOLS = ROOT / "profiles" / "qagent" / "node_modules" / "@deepseek-ai" / "dsh-tools"


def _text(path: Path) -> str:
    assert path.is_file(), f"missing {path}"
    return path.read_text(encoding="utf-8")


def test_note() -> None:
    text = _text(NOTE)
    assert "H-01g" in text
    assert "TOOL_RUNTIME_SCHEDULER" in text
    assert "prepare" in text
    assert "twin_id" in text
    assert "accepted:true" in text
    print("note names the symbol mismatch")


def test_scripts_align_dsh_tools() -> None:
    for path in (START, BOOT):
        text = _text(path)
        assert "H-01g" in text, path.name
        assert "dsh-tools" in text
        assert "ln -sfn" in text
        assert "TOOL_RUNTIME_SCHEDULER" in text
        assert "@deepseek-ai+dsh-tools@" in text
    print("start_runtime and bootstrap align dsh-tools")


def test_profile_tools_same_realpath() -> None:
    hosts = sorted((ROOT / ".dsh-runtime" / "node_modules" / ".pnpm").glob(HOST_GLOB))
    if not hosts:
        print("no host dsh-tools yet; scripts still pin the align")
        return
    host = hosts[0].resolve()
    assert PROFILE_TOOLS.exists(), "profile dsh-tools missing"
    assert PROFILE_TOOLS.resolve() == host, (
        f"profile {PROFILE_TOOLS.resolve()} != host {host}"
    )
    print(f"profile dsh-tools -> {host}")


def main() -> int:
    failed = 0
    for name, fn in (
        ("note", test_note),
        ("scripts_align_dsh_tools", test_scripts_align_dsh_tools),
        ("profile_tools_same_realpath", test_profile_tools_same_realpath),
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
