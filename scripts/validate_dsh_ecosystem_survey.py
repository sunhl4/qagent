# -*- coding: utf-8 -*-
"""Check the DSH ecosystem survey counts, catalog level, and deep-read shape.

Read-only. Does not clone repositories or execute plugins.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "dsh-ecosystem-survey"
CATALOG = DOC / "catalog.json"
DEEP = DOC / "deep"

REQUIRED = (
    "id", "name", "repository", "url", "snapshot_date", "evidence_level",
    "group", "problem", "mechanism", "ui", "verdict", "verdict_reason", "landing",
)
GROUPS = {"界面", "任务与注意力", "审批", "知识记忆", "办公内容", "连接器"}
VERDICTS = {"思想可取", "只借机制", "暂缓", "拒绝"}
APPENDIX_REQUIRED = {
    "dsh-ads", "dsh-gomoku", "dsh-minigames", "whale-girl", "dsh-mpkg-wallpaper",
    "dsh-skin", "dsh-png-pet", "dsh-cpr-guide", "dsh-spirit-guide",
    "AI-Novel-Writer", "gamify-edu",
}
SHA = re.compile(r"\b([0-9a-f]{40})\b")
ANCHOR = re.compile(r"`[^`\n:]+:\d+(?:-\d+)?`")


def main() -> None:
    errors: list[str] = []
    doc = json.loads(CATALOG.read_text(encoding="utf-8"))
    entries = doc["entries"]
    appendix = doc["appendix"]
    if len(entries) < 200:
        errors.append(f"catalog has {len(entries)} entries, need at least 200")
    ids = [e["id"] for e in entries]
    if len(ids) != len(set(ids)):
        errors.append("duplicate catalog ids")
    repos = [e["repository"] for e in entries]
    if len(repos) != len(set(repos)):
        errors.append("duplicate repositories")
    names = {e["name"] for e in entries}
    appendix_names = {a["name"] for a in appendix}
    if names & appendix_names:
        errors.append(f"appendix names in catalog: {sorted(names & appendix_names)}")
    if missing := APPENDIX_REQUIRED - appendix_names:
        errors.append(f"required appendix names missing: {sorted(missing)}")
    if APPENDIX_REQUIRED & names:
        errors.append("excluded names counted in the main table")
    deep_names = set()
    for entry in entries:
        for key in REQUIRED:
            if key not in entry or entry[key] in ("", None):
                errors.append(f"{entry.get('id')} missing {key}")
                break
        if entry.get("evidence_level") != "catalog":
            errors.append(f"{entry.get('id')} is not catalog-level")
        if entry.get("group") not in GROUPS:
            errors.append(f"{entry.get('id')} bad group")
        if entry.get("verdict") not in VERDICTS:
            errors.append(f"{entry.get('id')} bad verdict")
        if entry.get("verdict") in {"拒绝", "暂缓"} and not entry.get("verdict_reason"):
            errors.append(f"{entry.get('id')} missing verdict reason")
        if entry.get("deep_read"):
            deep_names.add(entry["name"])
    essays = sorted(p for p in DEEP.glob("D*.zh-CN.md") if p.name != "README.zh-CN.md")
    if len(essays) != 30:
        errors.append(f"expected 30 deep essays, found {len(essays)}")
    essay_names = set()
    for path in essays:
        text = path.read_text(encoding="utf-8")
        name = path.name.split("-", 1)[1].removesuffix(".zh-CN.md")
        essay_names.add(name)
        if not SHA.search(text):
            errors.append(f"{path.name} missing full sha")
        if "静态阅读" not in text:
            errors.append(f"{path.name} missing static-reading level")
        anchors = ANCHOR.findall(text)
        if len(anchors) < 6:
            errors.append(f"{path.name} has {len(anchors)} anchors")
        if "公司边界" not in text:
            errors.append(f"{path.name} missing company boundary")
    if essay_names != deep_names:
        errors.append(
            "deep files and catalog deep_read diverge: "
            f"only files {sorted(essay_names - deep_names)} "
            f"only catalog {sorted(deep_names - essay_names)}"
        )
    report = {
        "entries": len(entries),
        "appendix": len(appendix),
        "deep": len(essays),
        "errors": errors,
        "passed": not errors,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
