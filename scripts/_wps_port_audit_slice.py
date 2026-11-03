"""One-shot contract patch for the WPS-suite porting audit slice (L4 companion).

Appends ``company_office_audit`` to ``company.office`` so the agent can run the
read-only format audit of §4.12 (three scopes, GB/T 9704-2012 draft baseline,
honest ``unchecked`` list) without touching the P0-P4.5 slices the parallel
session owns. Insertion anchors: end of the contiguous office block in
``tools.json``, end of the capability tool list, and after
``company_office_matter`` in the fixed-presets visibility order (boot/lab/algo;
sign stays office-free). Every insertion asserts absence first, so a parallel
contract batch cannot be doubled by re-running this script.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "contracts" / "tools.json"
CAPS = ROOT / "contracts" / "capabilities.json"
PRESETS = ROOT / "contracts" / "presets.json"

NEW_NAME = "company_office_audit"


def tool_row() -> dict[str, object]:
    _PROJECT = {
        "type": "string",
        "pattern": "^[A-Za-z0-9_](?:[A-Za-z0-9_.-]*[A-Za-z0-9_-])?$",
        "maxLength": 128,
        "description": (
            "Project directory inside the mounted workspace root; must be a direct child directory of it."
        ),
    }
    return {
        "name": NEW_NAME,
        "capability": "company.office",
        "operation": "office.audit",
        "input_handles": [],
        "output_handles": [],
        "description": (
            "Read-only docx format audit inside one project directory of the mounted workspace, the L4 "
            "companion to surgical edits: mode=baseline checks one existing .docx against the GB/T 9704-2012 "
            "draft rule table (A4 page and 37/35/28/26mm margins, body 仿宋 16pt, first-line indent 2 chars, "
            "26.5-30pt line band, title 小标宋 22pt centered, heading1 黑体 / heading2 楷体 / heading3 仿宋) "
            "and reports bounded issues with L{n} paragraph locators plus counts; mode=imported never "
            "applies the rule table - it describes the file's own dominant format as bounded facts and "
            "flags only structural anomalies such as several sections. What the bounded parser does not "
            "verify is listed in ``unchecked`` and never claimed as passing; the rule table is a replaceable "
            "draft pending the firm's confirmation. Bounded to 5000 checked paragraphs (more is truncated "
            "and honestly marked), 20MB file cap, 128 reported issues; page headers/tables/embedded fonts "
            "stay unchecked. Standard library only; no conversion, no fixing, no external calls, no quantum "
            "handles, nothing is written."
        ),
        "parameters": {
            "type": "object",
            "required": ["project", "path", "mode"],
            "properties": {
                "project": _PROJECT,
                "path": {
                    "type": "string",
                    "pattern": "^[^\\\\:*?\"<>|\\u0000-\\u001f]{1,256}$",
                    "description": (
                        "Workspace path relative to the project directory pointing at an existing .docx; "
                        "any other suffix refuses."
                    ),
                },
                "mode": {
                    "type": "string",
                    "enum": ["baseline", "imported"],
                    "description": (
                        "baseline = audit against the GB/T 9704-2012 draft rule table (also the scope for an "
                        "explicit full re-template request); imported = describe the file's own dominant "
                        "format, no template applied."
                    ),
                },
            },
            "additionalProperties": False,
        },
        "output": {
            "type": "object",
            "required": [
                "mode", "path", "sha256", "bytes", "sections",
                "paragraphs_total", "paragraphs_checked", "truncated",
                "rule_set", "facts", "issues", "unchecked", "trust",
            ],
            "properties": {
                "mode": {"type": "string", "enum": ["baseline", "imported"]},
                "path": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 256,
                    "description": "Workspace file path as project/relative compound.",
                },
                "sha256": {
                    "type": "string",
                    "pattern": "^[0-9a-f]{64}$",
                    "maxLength": 64,
                },
                "bytes": {"type": "integer", "minimum": 1},
                "sections": {"type": "integer", "minimum": 0},
                "paragraphs_total": {
                    "type": "integer",
                    "minimum": 0,
                    "description": (
                        "Every w:p of the body in document order, the company_office_analyze L{n} numbering."
                    ),
                },
                "paragraphs_checked": {"type": "integer", "minimum": 0},
                "truncated": {
                    "type": "boolean",
                    "description": (
                        "True when more paragraphs existed than the checked cap; the tail is named in "
                        "unchecked, never silently dropped."
                    ),
                },
                "rule_set": {
                    "type": "object",
                    "required": ["id", "title", "status"],
                    "properties": {
                        "id": {"type": "string", "minLength": 1, "maxLength": 32},
                        "title": {"type": "string", "minLength": 1, "maxLength": 80},
                        "status": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 32,
                            "description": (
                                "Replaces the draft baseline once the firm confirms its own rule table."
                            ),
                        },
                    },
                    "additionalProperties": False,
                },
                "facts": {
                    "type": "array",
                    "maxItems": 16,
                    "description": (
                        "Observed format facts (margins, page size, dominant font/size/line spacing); "
                        "the imported-mode deliverable."
                    ),
                    "items": {
                        "type": "object",
                        "required": ["key", "value", "source"],
                        "properties": {
                            "key": {"type": "string", "minLength": 1, "maxLength": 32},
                            "value": {"type": "string", "minLength": 1, "maxLength": 80},
                            "source": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": 32,
                                "description": "Where the fact was read, e.g. sect or doc_defaults or L12.",
                            },
                        },
                        "additionalProperties": False,
                    },
                },
                "issues": {
                    "type": "array",
                    "maxItems": 128,
                    "items": {
                        "type": "object",
                        "required": ["code", "locator", "detail"],
                        "properties": {
                            "code": {"type": "string", "minLength": 1, "maxLength": 64},
                            "locator": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": 24,
                                "description": (
                                    "L12, L14 etc. for paragraph findings; sect / styles / document "
                                    "for structural ones."
                                ),
                            },
                            "detail": {"type": "string", "minLength": 1, "maxLength": 200},
                        },
                        "additionalProperties": False,
                    },
                },
                "unchecked": {
                    "type": "array",
                    "maxItems": 16,
                    "description": "Items the bounded parser does not verify; honesty clause, not a pass.",
                    "items": {
                        "type": "object",
                        "required": ["code", "detail"],
                        "properties": {
                            "code": {"type": "string", "minLength": 1, "maxLength": 64},
                            "detail": {"type": "string", "minLength": 1, "maxLength": 200},
                        },
                        "additionalProperties": False,
                    },
                },
                "trust": {"type": "string", "const": "untrusted_reference_data"},
            },
            "additionalProperties": False,
        },
    }


def main() -> None:
    tools = json.loads(TOOLS.read_text(encoding="utf-8"))
    rows = tools["tools"]
    names = [row["name"] for row in rows]
    if NEW_NAME in names:
        raise RuntimeError(f"{NEW_NAME} already present; refusing a double audit slice")
    matter_at = names.index("company_office_matter")
    rows[matter_at + 1 : matter_at + 1] = [tool_row()]

    caps = json.loads(CAPS.read_text(encoding="utf-8"))
    office = next(c for c in caps["capabilities"] if c["id"] == "company.office")
    if NEW_NAME in office["tools"]:
        raise RuntimeError(f"{NEW_NAME} already in capability; refusing a double audit slice")
    office["tools"].append(NEW_NAME)

    presets = json.loads(PRESETS.read_text(encoding="utf-8"))
    for preset in ("boot", "lab", "algo"):
        visible = presets["presets"][preset]["visible_tools"]
        if NEW_NAME in visible:
            raise RuntimeError(f"{NEW_NAME} already visible in {preset}; refusing a double audit slice")
        anchor_at = visible.index("company_office_matter")
        visible.insert(anchor_at + 1, NEW_NAME)

    for path, payload in ((TOOLS, tools), (CAPS, caps), (PRESETS, presets)):
        text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        path.write_text(text, encoding="utf-8", newline="\n")
    print("audit slice patched:", NEW_NAME)


if __name__ == "__main__":
    main()
