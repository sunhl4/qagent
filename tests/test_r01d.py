"""R-01d: Skill trigger does not bypass ask. No third loop. No minted twin_id."""

from __future__ import annotations

import re
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from qagent.models.handles import HANDLE_TWIN
from qagent.models.invoke import STATUS_NEEDS_ASK
from qagent.services.invoke import invoke
from qagent.services.policy import decide

SKILLS = ROOT / "skills"
PROFILE_SKILLS = ROOT / "profiles" / "qagent" / "skills"
_NOTE = ROOT / "docs" / "execution" / "R-01d_skill_ask.md"
_DEFAULT_HINT = re.compile(
    r"默认建议.{0,12}不是唯一入口|not the only (entry|path|way)|default suggestion",
    re.I,
)
_ASK_LOCK = re.compile(
    r"不能绕过\s*ask|cannot bypass ask|must not bypass ask|can't bypass ask",
    re.I,
)
_AUTO_APPROVE = re.compile(
    r"auto[-_]?approve|自动批准\s*TwinRun|自动批准\s*ionstack_twin_run",
    re.I,
)


def _skill_mds() -> list[Path]:
    paths = sorted(SKILLS.glob("*/SKILL.md"))
    assert paths, "qagent/skills must have SKILL.md files"
    return paths


def test_every_skill_is_default_suggestion() -> None:
    for path in _skill_mds():
        text = path.read_text(encoding="utf-8")
        assert _DEFAULT_HINT.search(text), f"{path.parent.name} must say 默认建议，不是唯一入口"


def test_twin_run_skill_cannot_bypass_ask() -> None:
    text = (SKILLS / "twin-run" / "SKILL.md").read_text(encoding="utf-8")
    assert _ASK_LOCK.search(text)
    assert "Skill 触发" in text and "ask" in text


def test_decide_twin_run_lab_ask_algo_deny() -> None:
    assert decide("ionstack_twin_run", "lab", {"shots": 1000}) == "ask"
    assert decide("ionstack_twin_run", "algo", {"shots": 1000}) == "deny"


def test_invoke_twin_run_lab_unapproved_needs_ask() -> None:
    result = invoke("ionstack_twin_run", "lab", {"shots": 1000})
    assert result.decision == "ask"
    assert result.status == STATUS_NEEDS_ASK
    payload = result.payload or {}
    assert HANDLE_TWIN not in payload
    assert "twin_id" not in payload


def test_no_skill_auto_approves_twin_run() -> None:
    for path in _skill_mds():
        text = path.read_text(encoding="utf-8")
        assert _AUTO_APPROVE.search(text) is None, f"{path.parent.name} must not auto-approve TwinRun"


def test_profile_skills_stay_in_sync() -> None:
    for path in _skill_mds():
        pointed = PROFILE_SKILLS / path.parent.name / "SKILL.md"
        assert pointed.is_file(), f"profile missing {path.parent.name}"
        assert pointed.read_text(encoding="utf-8") == path.read_text(encoding="utf-8")


def test_note_exists() -> None:
    assert _NOTE.is_file()
    text = _NOTE.read_text(encoding="utf-8")
    assert "ask" in text
    assert "ionstack_twin_run" in text
    assert "不能绕过" in text or "不绕过" in text
    assert "默认建议" in text or "不是唯一入口" in text
    assert "第三套" in text or "third loop" in text.lower()


def main() -> int:
    failed = 0
    for name, fn in (
        ("every_skill_is_default_suggestion", test_every_skill_is_default_suggestion),
        ("twin_run_skill_cannot_bypass_ask", test_twin_run_skill_cannot_bypass_ask),
        ("decide_twin_run_lab_ask_algo_deny", test_decide_twin_run_lab_ask_algo_deny),
        ("invoke_twin_run_lab_unapproved_needs_ask", test_invoke_twin_run_lab_unapproved_needs_ask),
        ("no_skill_auto_approves_twin_run", test_no_skill_auto_approves_twin_run),
        ("profile_skills_stay_in_sync", test_profile_skills_stay_in_sync),
        ("note_exists", test_note_exists),
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
