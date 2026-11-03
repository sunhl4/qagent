"""One-shot contract patch for the WPS-suite porting pptx slice (L3 deliverable).

Appends ``company_office_pptx`` to ``company.office`` so the agent can generate
structured-layout .pptx decks (§4.5: agenda/bullets/two-column/matrix/checklist
over real textboxes, WPS/PowerPoint-openable, standard library only) and
rewrite shape text in place with a read-back B5 gate. Insertion anchors: end
of the contiguous office block in ``tools.json`` (after audit), append to the
capability tool list, and after ``company_office_audit`` in the fixed-presets
visibility order (boot/lab/algo; sign stays office-free). Every insertion
asserts absence first, so a parallel contract batch cannot be doubled by
re-running this script.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "contracts" / "tools.json"
CAPS = ROOT / "contracts" / "capabilities.json"
PRESETS = ROOT / "contracts" / "presets.json"

NEW_NAME = "company_office_pptx"


def tool_row() -> dict[str, object]:
    return {
        "name": NEW_NAME,
        "capability": "company.office",
        "operation": "office.pptx",
        "input_handles": [],
        "output_handles": [],
        "description": (
            "Structured pptx generation and in-place shape text rewrite for one project directory "
            "of the mounted workspace, the stdlib port of the §4.5 slice (no officecli, no "
            "conversion): action=render writes one .pptx from a slide array where each slide is a "
            "structured layout - title (heading plus optional subtitle), agenda (numbered), "
            "bullets, two_column, matrix (a real PowerPoint table, up to 6x6 cells), checklist "
            "(checkbox-prefixed) - over named textboxes at fixed 16:9 geometry, so the deck opens "
            "in WPS/PowerPoint with page structure a human can edit rather than one full-page "
            "text box; action=edit rewrites the visible text of one shape per edit addressed as "
            "slide/shape (1-based document order of p:sp textboxes only, tables excluded) and "
            "refuses an edit batch entirely when any target is invalid - all-or-nothing, never a "
            "silent skip; every written package is re-opened and per-shape texts are replayed "
            "against what was built before the receipt returns (the B5 gate), and a failed edit "
            "verification restores the original bytes; action=preview is the §4.1 officecli "
            "visual path: it needs the binary resolved through COMPANY_AGENT_OFFICECLI or the "
            "adjacent search and honestly refuses when it is absent, then bounds one headless "
            "run (180s, 4MB stdout, minimal env) to per-page screenshots into preview/<stem>/ "
            "plus the editable shape enumeration. Caps are refusals, never stand-ins: 64 "
            "slides, 4000 characters per shape text (newlines refuse for edit), 8 bullets per "
            "column, 6x6 matrix cells; the written file reuses the P0 fences with atomic "
            "temp+replace, overwrite needs an explicit argument. Standard library only; no "
            "quantum handles."
        ),
        "parameters": {
            "type": "object",
            "required": ["project", "action", "path"],
            "properties": {
                "project": {
                    "type": "string",
                    "pattern": "^[A-Za-z0-9_](?:[A-Za-z0-9_.-]*[A-Za-z0-9_-])?$",
                    "maxLength": 128,
                    "description": (
                        "Project directory inside the mounted workspace root; created on first "
                        "write; must be a direct child directory of it."
                    ),
                },
                "action": {
                    "type": "string",
                    "enum": ["edit", "preview", "render"],
                    "description": (
                        "render = generate the .pptx described by content; edit = rewrite "
                        "visible text of existing shapes described by edits."
                    ),
                },
                "path": {
                    "type": "string",
                    "pattern": "^[^\\\\:*?\"<>|\\u0000-\\u001f]{1,256}$",
                    "description": (
                        "Workspace path relative to the project directory: render takes the "
                        ".pptx to write (existing file refuses without overwrite), edit takes "
                        "the existing .pptx to rewrite."
                    ),
                },
                "content": {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": True,
                    "description": (
                        "render payload: {slides:[{kind:title|agenda|bullets|two_column|matrix|checklist, "
                        "title:string, subtitle?:string, bullets?:[string], left?:[string], right?:[string], "
                        "matrix?:[[string]]}]}. The adapter validates each shape and refuses overshoot; "
                        "agenda pairs 1..n prefixes, checklist prefixes a checkbox glyph, two_column needs "
                        "left and right, matrix needs a rectangular 1..6 x 1..6 grid."
                    ),
                },
                "edits": {
                    "type": "array",
                    "maxItems": 64,
                    "description": (
                        "edit payload: [{slide: 1..64, shape: >=1, text: <=4000 chars without newlines}] ; "
                        "slide/shape use the 1-based document order of p:sp textboxes the render action "
                        "produces and WPS reports."
                    ),
                    "items": {
                        "type": "object",
                        "required": ["slide", "shape", "text"],
                        "properties": {
                            "slide": {"type": "integer", "minimum": 1, "maximum": 64},
                            "shape": {"type": "integer", "minimum": 1},
                            "text": {"type": "string", "minLength": 0, "maxLength": 4000},
                        },
                        "additionalProperties": False,
                    },
                },
                "overwrite": {
                    "type": "boolean",
                    "default": False,
                    "description": (
                        "Replace an existing file on render; absent/false refuses with an "
                        "explicit error. Never applies to edit."
                    ),
                },
            },
            "additionalProperties": False,
        },
        "output": {
            "type": "object",
            "required": ["action", "path", "sha256", "bytes", "slides", "shapes", "applied", "trust"],
            "properties": {
                "action": {"type": "string", "enum": ["render", "edit", "preview"]},
                "path": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 256,
                    "description": "Workspace file path as project/relative compound.",
                },
                "sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$", "maxLength": 64},
                "bytes": {"type": "integer", "minimum": 1},
                "slides": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 64,
                    "description": "render: slides written. preview: page count from officecli stats.",
                },
                "shapes": {
                    "type": "integer",
                    "minimum": 0,
                    "description": "render/edit: total p:sp textboxes across the re-opened deck (tables excluded). preview: enumerated editable shapes.",
                },
                "applied": {
                    "type": "integer",
                    "minimum": 0,
                    "description": "render: 0. edit: number of edits whose replayed text matched. preview: 0.",
                },
                "officecli": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 80,
                    "description": "preview only: executable path as configured (basename at most); render/edit omit.",
                },
                "screenshots": {
                    "type": "array",
                    "maxItems": 64,
                    "description": "preview only: per-page PNG artifacts written under preview/<stem>/, page order 1..N.",
                    "items": {
                        "type": "object",
                        "required": ["page", "path", "bytes"],
                        "properties": {
                            "page": {"type": "integer", "minimum": 1, "maximum": 64},
                            "path": {"type": "string", "minLength": 1, "maxLength": 256},
                            "bytes": {"type": "integer", "minimum": 1},
                        },
                        "additionalProperties": False,
                    },
                },
                "shapes_detail": {
                    "type": "array",
                    "maxItems": 200,
                    "description": "preview only: editable shapes in document order as officecli reports them.",
                    "items": {
                        "type": "object",
                        "required": ["slide", "shape", "text"],
                        "properties": {
                            "slide": {"type": "integer", "minimum": 1},
                            "shape": {"type": "integer", "minimum": 1},
                            "text": {"type": "string", "minLength": 0, "maxLength": 200},
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
        raise RuntimeError(f"{NEW_NAME} already present; refusing a double pptx slice")
    audit_at = names.index("company_office_audit")
    rows[audit_at + 1 : audit_at + 1] = [tool_row()]

    caps = json.loads(CAPS.read_text(encoding="utf-8"))
    office = next(c for c in caps["capabilities"] if c["id"] == "company.office")
    if NEW_NAME in office["tools"]:
        raise RuntimeError(f"{NEW_NAME} already in capability; refusing a double pptx slice")
    office["tools"].append(NEW_NAME)

    presets = json.loads(PRESETS.read_text(encoding="utf-8"))
    for preset in ("boot", "lab", "algo"):
        visible = presets["presets"][preset]["visible_tools"]
        if NEW_NAME in visible:
            raise RuntimeError(f"{NEW_NAME} already visible in {preset}; refusing a double pptx slice")
        anchor_at = visible.index("company_office_audit")
        visible.insert(anchor_at + 1, NEW_NAME)

    for path, payload in ((TOOLS, tools), (CAPS, caps), (PRESETS, presets)):
        text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        path.write_text(text, encoding="utf-8", newline="\n")
    print("pptx slice patched:", NEW_NAME)


if __name__ == "__main__":
    main()
