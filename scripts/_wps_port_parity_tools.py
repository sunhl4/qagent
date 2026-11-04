"""Insert the parity tools that close the remaining WPS-suite gaps."""
# ruff: noqa: E501
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "contracts" / "tools.json"
CAPS = ROOT / "contracts" / "capabilities.json"
PRESETS = ROOT / "contracts" / "presets.json"
NAMES = [
    "company_office_review_table",
    "company_office_files",
    "company_office_fix",
    "company_office_surface",
]
PROJECT = {
    "type": "string",
    "pattern": "^[A-Za-z0-9_](?:[A-Za-z0-9_.-]*[A-Za-z0-9_-])?$",
    "maxLength": 128,
    "description": "Project directory inside the mounted workspace root.",
}
PATH = {
    "type": "string",
    "pattern": "^[^\\\\:*?\"<>|\\u0000-\\u001f]{1,256}$",
    "description": "Workspace path relative to the project directory.",
}
PURPOSE = {"type": "string", "minLength": 1, "maxLength": 80, "description": "One-line reason recorded on the audit line."}


def _tool(name: str, operation: str, description: str, parameters: dict, output: dict) -> dict:
    return {
        "name": name,
        "capability": "company.office",
        "operation": operation,
        "input_handles": [],
        "output_handles": [],
        "description": description,
        "parameters": parameters,
        "output": output,
    }


def tools() -> list[dict]:
    trust = {"type": "string", "const": "untrusted_reference_data"}
    sha = {"type": "string", "pattern": "^[0-9a-f]{64}$", "maxLength": 64}
    return [
        _tool(
            NAMES[0],
            "office.review_table",
            "Write an xlsx analysis table: each column is followed by a {{name}}_依据 column (lineRef：summary) and a provenance sheet. purpose is required. 20MB cap. No quantum handles.",
            {
                "type": "object",
                "required": ["project", "path", "purpose", "columns"],
                "additionalProperties": False,
                "properties": {
                    "project": PROJECT,
                    "path": PATH,
                    "purpose": PURPOSE,
                    "overwrite": {"type": "boolean", "default": False},
                    "columns": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": 32,
                        "items": {"type": "object", "additionalProperties": True},
                    },
                },
            },
            {
                "type": "object",
                "required": ["path", "rows", "bytes", "sha256", "trust"],
                "additionalProperties": False,
                "properties": {
                    "path": {"type": "string", "minLength": 1, "maxLength": 256},
                    "rows": {"type": "integer", "minimum": 1},
                    "bytes": {"type": "integer", "minimum": 1},
                    "sha256": sha,
                    "trust": trust,
                },
            },
        ),
        _tool(
            NAMES[1],
            "office.files",
            "Move, rename or copy files inside one project without changing bytes, or revert the last journalled batch. Deletes are refused. purpose is required.",
            {
                "type": "object",
                "required": ["project", "purpose", "action"],
                "additionalProperties": False,
                "properties": {
                    "project": PROJECT,
                    "purpose": PURPOSE,
                    "action": {"type": "string", "enum": ["copy", "move", "rename", "revert"]},
                    "ops": {
                        "type": "array",
                        "maxItems": 32,
                        "items": {
                            "type": "object",
                            "required": ["source", "target"],
                            "additionalProperties": False,
                            "properties": {
                                "source": {"type": "string", "minLength": 1, "maxLength": 200},
                                "target": {"type": "string", "minLength": 1, "maxLength": 200},
                            },
                        },
                    },
                },
            },
            {
                "type": "object",
                "required": ["action", "applied", "ops", "trust"],
                "additionalProperties": False,
                "properties": {
                    "action": {"type": "string"},
                    "applied": {"type": "integer", "minimum": 0},
                    "ops": {"type": "array", "maxItems": 32, "items": {"type": "object", "additionalProperties": True}},
                    "trust": trust,
                },
            },
        ),
        _tool(
            NAMES[2],
            "office.fix",
            "Apply page geometry and default font from the format audit without changing paragraph text, then re-audit. purpose is required.",
            {
                "type": "object",
                "required": ["project", "path", "purpose"],
                "additionalProperties": False,
                "properties": {"project": PROJECT, "path": PATH, "purpose": PURPOSE},
            },
            {
                "type": "object",
                "required": ["path", "before_issues", "after_issues", "bytes", "sha256", "trust"],
                "additionalProperties": False,
                "properties": {
                    "path": {"type": "string", "minLength": 1, "maxLength": 256},
                    "before_issues": {"type": "integer", "minimum": 0},
                    "after_issues": {"type": "integer", "minimum": 0},
                    "bytes": {"type": "integer", "minimum": 1},
                    "sha256": sha,
                    "trust": trust,
                },
            },
        ),
        _tool(
            NAMES[3],
            "office.surface",
            "Read w:ins/w:del with author colors that are not stored in the file. accept writes word/lawmind-disposition.xml and leaves the track; reject removes the caller's own revision. Other authors are read-only. purpose is required.",
            {
                "type": "object",
                "required": ["project", "path", "purpose", "action"],
                "additionalProperties": False,
                "properties": {
                    "project": PROJECT,
                    "path": PATH,
                    "purpose": PURPOSE,
                    "action": {"type": "string", "enum": ["accept", "read", "reject"]},
                    "author": {"type": "string", "minLength": 1, "maxLength": 64},
                    "revision_id": {"type": "string", "minLength": 1, "maxLength": 32},
                },
            },
            {
                "type": "object",
                "required": ["path", "changed", "revisions", "bytes", "sha256", "purpose", "trust"],
                "additionalProperties": False,
                "properties": {
                    "path": {"type": "string", "minLength": 1, "maxLength": 256},
                    "changed": {"type": "boolean"},
                    "revisions": {
                        "type": "array",
                        "maxItems": 64,
                        "items": {"type": "object", "additionalProperties": True},
                    },
                    "bytes": {"type": "integer", "minimum": 1},
                    "sha256": sha,
                    "purpose": {"type": "string", "minLength": 1, "maxLength": 80},
                    "trust": trust,
                },
            },
        ),
    ]


def main() -> None:
    tools_doc = json.loads(TOOLS.read_text(encoding="utf-8"))
    rows = tools_doc["tools"]
    names = [row["name"] for row in rows]
    if any(name in names for name in NAMES):
        raise SystemExit("parity tools already present")
    anchor = names.index("company_office_deliver")
    rows[anchor + 1 : anchor + 1] = tools()
    caps = json.loads(CAPS.read_text(encoding="utf-8"))
    office = next(item for item in caps["capabilities"] if item["id"] == "company.office")
    office["tools"].extend(NAMES)
    presets = json.loads(PRESETS.read_text(encoding="utf-8"))
    for preset in ("boot", "lab", "algo"):
        visible = presets["presets"][preset]["visible_tools"]
        at = visible.index("company_office_deliver")
        for offset, name in enumerate(NAMES, start=1):
            visible.insert(at + offset, name)
    for path, payload in ((TOOLS, tools_doc), (CAPS, caps), (PRESETS, presets)):
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print("inserted", ", ".join(NAMES))


if __name__ == "__main__":
    main()
