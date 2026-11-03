#!/usr/bin/env python3
"""Read-only checks for the Company Agent 2000 person-day plan."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "company-agent-2000-person-days-development-plan-v1.0.zh-CN.md"
DATA = ROOT / "docs" / "company-agent-2000-person-days-development-plan-v1.0.json"


def main() -> int:
    errors: list[str] = []
    data = json.loads(DATA.read_text(encoding="utf-8"))
    phase_total = sum(item["person_days"] for item in data["phases"])
    workstream_total = sum(item["person_days"] for item in data["workstreams"])
    role_total = sum(item["person_days"] for item in data["roles"])
    reserve_total = sum(item["person_days"] for item in data["risk_reserve"])
    if phase_total != data["baseline_person_days"]:
        errors.append(f"phase total {phase_total} != baseline {data['baseline_person_days']}")
    if workstream_total != data["baseline_person_days"]:
        errors.append(f"workstream total {workstream_total} != baseline {data['baseline_person_days']}")
    if role_total != data["total_person_days"]:
        errors.append(f"role total {role_total} != total {data['total_person_days']}")
    if reserve_total != data["risk_reserve_person_days"]:
        errors.append(f"risk reserve total {reserve_total} != reserve {data['risk_reserve_person_days']}")
    if phase_total + reserve_total != data["total_person_days"]:
        errors.append("baseline plus reserve does not equal total")
    required = [
        "DSH仍是唯一Agent Runtime",
        "algorithm.catalog",
        "quantum_device_run",
        "在`lab`和`sign`必须ask",
        "在`boot`和`algo`必须deny",
        "2000 人天",
        "2000 人天包含 1740 人天基线建设和 260 人天受控风险储备",
    ]
    document = DOC.read_text(encoding="utf-8")
    for phrase in required:
        if phrase not in document:
            errors.append(f"document missing required boundary: {phrase}")
    for target in [
        "company-agent-2000-person-days-development-plan-v1.0.json",
        "company-agent-harness-framework-v0.8.zh-CN.md",
        "oss-survey/04-工程衔接建议.zh-CN.md",
        "oss-survey/05-复核总报告.zh-CN.md",
    ]:
        if target not in document:
            errors.append(f"document missing source/link: {target}")
    print(json.dumps({
        "scope": "read-only plan arithmetic and boundary check",
        "phase_person_days": phase_total,
        "workstream_person_days": workstream_total,
        "role_person_days": role_total,
        "risk_reserve_person_days": reserve_total,
        "total_person_days": data["total_person_days"],
        "errors": errors,
        "passed": not errors,
    }, ensure_ascii=False, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
