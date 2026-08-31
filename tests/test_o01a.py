"""O-01a: freeze dsh 0.1.0-rc.8 and Codex 0.147.0. Disagree = fail, no silent bump."""

from __future__ import annotations

import json
import re
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_NOTE = ROOT / "docs" / "execution" / "O-01a_pins.md"

FROZEN_DSH = "0.1.0-rc.8"
FROZEN_CODEX = "0.147.0"
FROZEN_SUBAGENT = "0.1.0-rc.8"

_PKG_CODEX = "@openai/codex"
_PKG_SUBAGENT = "@deepseek-ai/dsh-subagent-codex"


def _pins() -> dict:
    return json.loads((ROOT / "pins.json").read_text(encoding="utf-8"))


def _profile_pkg() -> dict:
    return json.loads((ROOT / "profiles" / "qagent" / "package.json").read_text(encoding="utf-8"))


def _bootstrap_dsh_ver() -> str:
    text = (ROOT / "scripts" / "bootstrap_wp0.sh").read_text(encoding="utf-8")
    match = re.search(r'^DSH_VER="([^"]+)"', text, re.M)
    assert match, "DSH_VER missing in bootstrap_wp0.sh"
    return match.group(1)


def _readme() -> str:
    return (ROOT / "profiles" / "qagent" / "README.md").read_text(encoding="utf-8")


def _observed() -> dict[str, str]:
    pins = _pins()
    deps = _profile_pkg()["dependencies"]
    return {
        "pins.deepseek_harness": pins["deepseek_harness"]["version"],
        "bootstrap.DSH_VER": _bootstrap_dsh_ver(),
        "pins.openai_codex": pins["openai_codex"]["version"],
        "package.@openai/codex": deps[_PKG_CODEX],
        "pins.dsh_subagent_codex": pins["dsh_subagent_codex"]["version"],
        "package.@deepseek-ai/dsh-subagent-codex": deps[_PKG_SUBAGENT],
    }


def test_pins_json_frozen() -> None:
    pins = _pins()
    assert pins["deepseek_harness"]["version"] == FROZEN_DSH
    assert pins["openai_codex"]["version"] == FROZEN_CODEX
    assert pins["dsh_subagent_codex"]["version"] == FROZEN_SUBAGENT


def test_package_json_frozen() -> None:
    deps = _profile_pkg()["dependencies"]
    assert deps[_PKG_SUBAGENT] == FROZEN_SUBAGENT
    assert deps[_PKG_CODEX] == FROZEN_CODEX


def test_bootstrap_dsh_ver_frozen() -> None:
    assert _bootstrap_dsh_ver() == FROZEN_DSH


def test_readme_mentions_both_pins() -> None:
    text = _readme()
    assert f"@deepseek-ai/dsh@{FROZEN_DSH}" in text
    assert f"{_PKG_CODEX}@{FROZEN_CODEX}" in text
    assert f"{_PKG_SUBAGENT}@{FROZEN_SUBAGENT}" in text


def test_sources_agree() -> None:
    observed = _observed()
    dsh_keys = ("pins.deepseek_harness", "bootstrap.DSH_VER")
    codex_keys = ("pins.openai_codex", "package.@openai/codex")
    sub_keys = ("pins.dsh_subagent_codex", "package.@deepseek-ai/dsh-subagent-codex")
    drift = []
    for key in dsh_keys:
        if observed[key] != FROZEN_DSH:
            drift.append(f"{key}={observed[key]!r} want {FROZEN_DSH}")
    for key in codex_keys:
        if observed[key] != FROZEN_CODEX:
            drift.append(f"{key}={observed[key]!r} want {FROZEN_CODEX}")
    for key in sub_keys:
        if observed[key] != FROZEN_SUBAGENT:
            drift.append(f"{key}={observed[key]!r} want {FROZEN_SUBAGENT}")
    dsh_vals = {observed[key] for key in dsh_keys}
    codex_vals = {observed[key] for key in codex_keys}
    sub_vals = {observed[key] for key in sub_keys}
    if len(dsh_vals) != 1:
        drift.append(f"dsh sources disagree: {dsh_vals}")
    if len(codex_vals) != 1:
        drift.append(f"codex sources disagree: {codex_vals}")
    if len(sub_vals) != 1:
        drift.append(f"subagent sources disagree: {sub_vals}")
    assert not drift, "pin drift — fail, do not silently upgrade; see O-01a_pins.md: " + "; ".join(drift)


def test_note_freeze_not_bump() -> None:
    assert _NOTE.is_file()
    text = _NOTE.read_text(encoding="utf-8")
    assert FROZEN_DSH in text
    assert FROZEN_CODEX in text
    assert "冻住" in text
    assert "书面升 pin" in text
    assert "无书面升 pin" in text or "不升 pin" in text


def main() -> int:
    failed = 0
    for name, fn in (
        ("pins_json_frozen", test_pins_json_frozen),
        ("package_json_frozen", test_package_json_frozen),
        ("bootstrap_dsh_ver_frozen", test_bootstrap_dsh_ver_frozen),
        ("readme_mentions_both_pins", test_readme_mentions_both_pins),
        ("sources_agree", test_sources_agree),
        ("note_freeze_not_bump", test_note_freeze_not_bump),
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
