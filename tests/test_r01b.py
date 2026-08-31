"""R-01b: register existing skills on the qagent dsh profile."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "profiles" / "qagent"
SKILLS = ROOT / "skills"
VISIBILITY = PROFILE / "skill-visibility.json"
PRESET_CORDIS = PROFILE / "agent-presets" / "qagent" / "agent.cordis.yml"
START_RUNTIME = ROOT / "scripts" / "start_runtime.sh"
PATCH = PROFILE / "cordis.patch.yml"
_SKILL_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_FRONTMATTER = re.compile(r"\A---\r?\n(.*?)\r?\n---", re.S)
_AUTO_APPROVE = re.compile(
    r"(?im)^(allowed-tools|auto-approve|auto_approve|autoApprove)\s*:"
)


def _strip_yaml_comments(text: str) -> str:
    lines = []
    for line in text.splitlines():
        stripped = line.split("#", 1)[0].rstrip()
        if stripped:
            lines.append(stripped)
    return "\n".join(lines).strip()


def _frontmatter(text: str) -> str:
    match = _FRONTMATTER.match(text)
    return match.group(1) if match else ""


def _load_visibility() -> dict:
    data = json.loads(VISIBILITY.read_text(encoding="utf-8"))
    assert isinstance(data.get("skills"), list)
    return data


def _visible(data: dict, preset: str) -> set[str]:
    return {row["id"] for row in data["skills"] if preset in row["visible"]}


def test_profile_preset_stays_empty() -> None:
    assert (PROFILE / "agent-presets" / "qagent" / "preset.yml").is_file()
    assert PRESET_CORDIS.is_file()
    text = PRESET_CORDIS.read_text(encoding="utf-8")
    body = _strip_yaml_comments(text)
    assert body == "[]"
    assert re.search(r"(?m)^[^#]*\bid:\s*persona\b", text) is None
    assert re.search(r"(?m)^[^#]*name:\s*['\"]?@deepseek-ai/dsh-persona", text) is None


def test_visibility_hides_twin_from_algo() -> None:
    data = _load_visibility()
    ids = {row["id"] for row in data["skills"]}
    assert "twin-run" in ids
    assert "write-provider" in ids
    assert "vibe-across-engines" in ids
    assert "read-b3" in ids
    assert "run-frozen-recipe" in ids
    assert not any("cal" in skill_id or "shuttle" in skill_id for skill_id in ids)
    for row in data["skills"]:
        assert _SKILL_NAME.match(row["id"])
        assert (SKILLS / row["id"] / "SKILL.md").is_file()
        assert set(row["visible"]) <= {"lab", "algo", "sign"}
    algo = _visible(data, "algo")
    lab = _visible(data, "lab")
    sign = _visible(data, "sign")
    assert "twin-run" not in algo
    assert "twin-run" in lab
    assert "twin-run" in sign
    assert "write-provider" in algo
    assert "write-provider" not in lab
    assert "write-provider" not in sign
    pointed = PROFILE / "skills"
    assert pointed.is_dir()
    assert (pointed / "twin-run" / "SKILL.md").is_file()
    assert (pointed / "write-provider" / "SKILL.md").is_file()


def test_start_runtime_mentions_skills_sync() -> None:
    text = START_RUNTIME.read_text(encoding="utf-8")
    assert "skills sync" in text
    assert "skill-visibility.json" in text
    assert "DSH_HOME}/skills" in text or "${DSH_HOME}/skills" in text
    assert ".credentials.yaml" in text
    assert "cp -f" in text and "agent.cordis.yml" in text


def test_no_twin_run_auto_approve_in_frontmatter() -> None:
    for skill_md in SKILLS.glob("*/SKILL.md"):
        text = skill_md.read_text(encoding="utf-8")
        matter = _frontmatter(text)
        assert matter, f"{skill_md.name} needs dsh name/description frontmatter"
        assert "name:" in matter
        assert "description:" in matter
        if "ionstack_twin_run" in matter:
            assert _AUTO_APPROVE.search(matter) is None
        for line in matter.splitlines():
            if _AUTO_APPROVE.match(line):
                assert "ionstack_twin_run" not in line
    twin = _frontmatter((SKILLS / "twin-run" / "SKILL.md").read_text(encoding="utf-8"))
    assert "ionstack_twin_run" not in twin
    assert "ask" in twin.lower() or "ask" in (SKILLS / "twin-run" / "SKILL.md").read_text(encoding="utf-8")
    body = (SKILLS / "twin-run" / "SKILL.md").read_text(encoding="utf-8")
    assert "Skill 触发也不能绕过 ask" in body
    patch = PATCH.read_text(encoding="utf-8")
    assert "/Users/" not in patch
    assert "ionstack_twin_run" not in patch
    assert "mcpServers" not in patch
    assert re.search(r"(?m)^[^#]*\bmcp\s*:", patch) is None
    assert "permissionMode: never" in patch


def _sync_script() -> str:
    text = START_RUNTIME.read_text(encoding="utf-8")
    match = re.search(r"python3 - .*? <<'PY'\n(.*)\nPY\n", text, re.S)
    assert match, "start_runtime.sh must embed skills sync python"
    return match.group(1)


def test_skills_sync_hides_twin_from_algo() -> None:
    script = _sync_script()
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp)
        subprocess.run(
            [sys.executable, "-", str(VISIBILITY), str(SKILLS), str(dest), "algo"],
            input=script,
            text=True,
            check=True,
        )
        names = {p.name for p in dest.iterdir()}
        assert "twin-run" not in names
        assert "write-provider" in names
        subprocess.run(
            [sys.executable, "-", str(VISIBILITY), str(SKILLS), str(dest), "lab"],
            input=script,
            text=True,
            check=True,
        )
        names = {p.name for p in dest.iterdir()}
        assert "twin-run" in names
        assert "write-provider" not in names
        assert (dest / "twin-run" / "SKILL.md").is_file()


def main() -> int:
    failed = 0
    for name, fn in [
        ("profile_preset_stays_empty", test_profile_preset_stays_empty),
        ("visibility_hides_twin_from_algo", test_visibility_hides_twin_from_algo),
        ("start_runtime_mentions_skills_sync", test_start_runtime_mentions_skills_sync),
        ("no_twin_run_auto_approve_in_frontmatter", test_no_twin_run_auto_approve_in_frontmatter),
        ("skills_sync_hides_twin_from_algo", test_skills_sync_hides_twin_from_algo),
    ]:
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
