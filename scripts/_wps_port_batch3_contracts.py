"""One-shot contract patch for the WPS-suite porting batch 3 (P3/P4/P4.5).

Adds the L4/L5 slices to ``company.office`` in the fixed order contracts ->
catalog expectations -> presets, exactly like every previous batch:
5 tools (compare/edit/validate/chart/matter), capability tools list 2->7,
boot/lab/algo visibility grows by the same 5 tools, sign stays office-free.
Run once; idempotence is left to review on purpose (re-running duplicates
nothing because every insertion asserts absence first).
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "contracts" / "tools.json"
CAPS = ROOT / "contracts" / "capabilities.json"
PRESETS = ROOT / "contracts" / "presets.json"

_PROJECT = {
    "type": "string",
    "pattern": "^[A-Za-z0-9_](?:[A-Za-z0-9_.-]*[A-Za-z0-9_-])?$",
    "maxLength": 128,
    "description": "Project directory inside the mounted workspace root; must be a direct child directory of it.",
}
_PATH = {
    "type": "string",
    "pattern": "^[^\\\\:*?\"<>|\\u0000-\\u001f]{1,256}$",
    "description": "Workspace path relative to the project directory; forward slashes only, no .. segments, no absolute paths.",
}
_SHA = {
    "type": "string",
    "pattern": "^[0-9a-f]{64}$",
    "maxLength": 64,
}
_TRUST = {"type": "string", "const": "untrusted_reference_data"}


def _path_256(text: str) -> dict[str, object]:
    return {"type": "string", "minLength": 1, "maxLength": 256, "description": text}


def tool_rows() -> list[dict[str, object]]:
    compare = {
        "name": "company_office_compare",
        "capability": "company.office",
        "operation": "office.compare",
        "input_handles": [],
        "output_handles": [],
        "description": (
            "Read-only line-level comparison for two same-kind files inside a project directory of the mounted "
            "workspace: .txt/.md lines or .docx visible paragraphs (the company_office_analyze L{n} anchors). "
            "Bounded to 4000 units per side: more refuses instead of comparing a stand-in; the receipt carries "
            "exact added/removed line counts, at most 40 hunk samples with an explicit truncated flag and 200 "
            "characters per shown line. Mixed kinds, unsupported kinds, non-UTF-8 text and corrupt packages fail "
            "closed; no conversion, no OCR, no external calls, no quantum handles."
        ),
        "parameters": {
            "type": "object",
            "required": ["project", "file_a", "file_b"],
            "properties": {
                "project": _PROJECT,
                "file_a": _PATH,
                "file_b": _PATH,
            },
            "additionalProperties": False,
        },
        "output": {
            "type": "object",
            "required": [
                "kind", "file_a", "file_b", "sha256_a", "sha256_b",
                "identical", "added", "removed", "hunks", "truncated", "trust",
            ],
            "properties": {
                "kind": {"type": "string", "enum": ["text", "docx"]},
                "file_a": _path_256("Workspace file path of side A as project/relative compound."),
                "file_b": _path_256("Workspace file path of side B as project/relative compound."),
                "sha256_a": _SHA,
                "sha256_b": _SHA,
                "identical": {"type": "boolean", "description": "True when both sides produce the same unit sequence."},
                "added": {"type": "integer", "minimum": 0, "description": "Lines present in B and absent in A."},
                "removed": {"type": "integer", "minimum": 0, "description": "Lines present in A and absent in B."},
                "hunks": {
                    "type": "array",
                    "maxItems": 40,
                    "items": {
                        "type": "object",
                        "required": ["index", "kind", "at_a", "at_b", "before", "after"],
                        "properties": {
                            "index": {"type": "integer", "minimum": 1},
                            "kind": {"type": "string", "enum": ["changed", "added", "removed"]},
                            "at_a": {"type": "integer", "minimum": 0, "description": "1-based first A unit of the hunk, 0 when the hunk only adds."},
                            "at_b": {"type": "integer", "minimum": 0, "description": "1-based first B unit of the hunk, 0 when the hunk only removes."},
                            "before": {"type": "array", "maxItems": 8, "items": {"type": "string", "minLength": 0, "maxLength": 200}},
                            "after": {"type": "array", "maxItems": 8, "items": {"type": "string", "minLength": 0, "maxLength": 200}},
                        },
                        "additionalProperties": False,
                    },
                },
                "truncated": {"type": "boolean", "description": "True when more than 40 hunks existed."},
                "trust": _TRUST,
            },
            "additionalProperties": False,
        },
    }

    edit = {
        "name": "company_office_edit",
        "capability": "company.office",
        "operation": "office.edit",
        "input_handles": [],
        "output_handles": [],
        "description": (
            "Surgical tracked-changes editing for one existing .docx inside a project directory of the mounted "
            "workspace: each edit matches its find text inside a single paragraph's visible text, the before/after "
            "pair is reduced to minimal edit spans (common runs of 4+ characters stay untouched, no 6+ unchanged "
            "run inside a change), and the result lands as standard w:ins/w:del revisions with the given author "
            "and UTC date, so Word/WPS show Word-native accept/reject tracks. Anchors that miss are reported, "
            "anchors that hit more than once skip the whole edit unless occurrences=all, unchanged and "
            "newline-carrying finds/replace skip, and an edit batch that produces no tracked change refuses "
            "without writing anything. The written package is re-opened and the on-disk w:ins/w:del counts plus "
            "every changed paragraph's replayed visible text are re-verified before success (the B5 gate). "
            "Standard library only, atomic temp+replace write with sha256 re-verified by re-read, cap overshoot "
            "(128 edits, 4000 chars per find/replace) refuses; no conversion, no template execution, no external "
            "calls, no quantum handles."
        ),
        "parameters": {
            "type": "object",
            "required": ["project", "path", "edits"],
            "properties": {
                "project": _PROJECT,
                "path": dict(
                    _PATH,
                    description=(
                        "Existing .docx path relative to the project directory; any other suffix refuses. "
                        "Revisions need an existing package: create one with company_office_create first."
                    ),
                ),
                "edits": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 128,
                    "items": {
                        "type": "object",
                        "required": ["find", "replace"],
                        "properties": {
                            "find": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": 4000,
                                "description": "Anchor text searched inside one paragraph's visible text; newlines are never part of it.",
                            },
                            "replace": {
                                "type": "string",
                                "maxLength": 4000,
                                "description": "Replacement text; empty means a tracked deletion. Newlines refuse.",
                            },
                            "occurrences": {
                                "type": "string",
                                "enum": ["all"],
                                "description": "Absent: an anchor hitting more than once in the document skips this edit. Present as all: every hit in every paragraph becomes a tracked change.",
                            },
                        },
                        "additionalProperties": False,
                    },
                },
                "author": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 64,
                    "default": "company-agent",
                    "description": "Revision author written on every w:ins/w:del of this batch.",
                },
                "note": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 120,
                    "description": "One-line reason for the audit ledger when COMPANY_AGENT_AUDIT_* is configured; missing ledger skips the line without changing the edit.",
                },
            },
            "additionalProperties": False,
        },
        "output": {
            "type": "object",
            "required": ["edited", "hunks", "skipped", "path", "bytes", "sha256"],
            "properties": {
                "edited": {"type": "integer", "minimum": 1, "description": "Edits that landed tracked changes."},
                "hunks": {"type": "integer", "minimum": 1, "description": "Total minimal-edit spans written."},
                "skipped": {
                    "type": "array",
                    "maxItems": 128,
                    "items": {
                        "type": "object",
                        "required": ["index", "reason"],
                        "properties": {
                            "index": {"type": "integer", "minimum": 1},
                            "reason": {"type": "string", "minLength": 1, "maxLength": 120},
                        },
                        "additionalProperties": False,
                    },
                },
                "path": _path_256("Workspace file path as project/relative compound."),
                "bytes": {"type": "integer", "minimum": 1, "maximum": 20000000},
                "sha256": _SHA,
            },
            "additionalProperties": False,
        },
    }

    validate = {
        "name": "company_office_validate",
        "capability": "company.office",
        "operation": "office.validate",
        "input_handles": [],
        "output_handles": [],
        "description": (
            "Evidence-anchor gate for one project directory of the mounted workspace: every reference carries a "
            "workspace file, a locator (L paragraph/line, P pdf page, S sheet!A1 cell) and the exact quote, and "
            "the tool re-reads the files and answers PASSED/FAILED/INCOMPLETE deterministically. Missing or "
            "mismatched fingerprints, missing files, unparsable locators and quote mismatches are FAILED; "
            "locators the bounded parsers do not implement (ranges such as S!A1:B2 and L ranges on structured "
            "kinds, non-text kinds) and empty quotes are INCOMPLETE, never a guess; PASSED only when every "
            "reference resolves. Docx paragraph anchors and pdf page anchors follow company_office_analyze "
            "numbering exactly. Bounded to 128 references, 128 source fingerprints, 4000 characters per quote; "
            "no external calls, no quantum handles."
        ),
        "parameters": {
            "type": "object",
            "required": ["project", "references"],
            "properties": {
                "project": _PROJECT,
                "references": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 128,
                    "items": {
                        "type": "object",
                        "required": ["id", "path", "line_ref", "quote"],
                        "properties": {
                            "id": {"type": "string", "minLength": 1, "maxLength": 64},
                            "path": _PATH,
                            "line_ref": {"type": "string", "minLength": 1, "maxLength": 64, "description": "L12, L12-L14, P3 or S quarterly!B4; anything else is an unparsable-locator issue."},
                            "quote": {"type": "string", "minLength": 0, "maxLength": 4000, "description": "Visible text expected at the locator; empty is INCOMPLETE."},
                        },
                        "additionalProperties": False,
                    },
                },
                "sources": {
                    "type": "array",
                    "maxItems": 128,
                    "description": "Content fingerprints the references must match; a referenced path missing here is FAILED (fingerprint_missing).",
                    "items": {
                        "type": "object",
                        "required": ["path", "sha256"],
                        "properties": {
                            "path": _PATH,
                            "sha256": _SHA,
                        },
                        "additionalProperties": False,
                    },
                },
            },
            "additionalProperties": False,
        },
        "output": {
            "type": "object",
            "required": ["status", "total", "passed", "failed", "incomplete", "issues", "trust"],
            "properties": {
                "status": {"type": "string", "enum": ["PASSED", "FAILED", "INCOMPLETE"]},
                "total": {"type": "integer", "minimum": 1, "maximum": 128},
                "passed": {"type": "integer", "minimum": 0, "maximum": 128},
                "failed": {"type": "integer", "minimum": 0, "maximum": 128},
                "incomplete": {"type": "integer", "minimum": 0, "maximum": 128},
                "issues": {
                    "type": "array",
                    "maxItems": 128,
                    "items": {
                        "type": "object",
                        "required": ["id", "code"],
                        "properties": {
                            "id": {"type": "string", "minLength": 1, "maxLength": 64},
                            "code": {"type": "string", "minLength": 1, "maxLength": 64, "description": "fingerprint_missing | fingerprint_mismatch | file_missing | file_unreadable | locator_unparsable | locator_out_of_range | quote_mismatch | quote_empty | kind_unsupported"},
                            "detail": {"type": "string", "maxLength": 200},
                        },
                        "additionalProperties": False,
                    },
                },
                "trust": _TRUST,
            },
            "additionalProperties": False,
        },
    }

    chart = {
        "name": "company_office_chart",
        "capability": "company.office",
        "operation": "office.chart",
        "input_handles": [],
        "output_handles": [],
        "description": (
            "Declarative chart artifact inside one project directory of the mounted workspace: bar/line/"
            "stacked_bar/pie specs render to a deterministic standalone SVG (same spec in, same bytes out) "
            "written next to the canonical spec JSON under artifacts/charts/<chart_id>.json and .svg, so the "
            "user reviews the semantic spec, not pixels. chart_id is the first 16 hex of the canonical spec "
            "digest. Standard library only, atomic temp+replace writes re-verified by re-read, existing files "
            "refuse without overwrite=true, cap overshoot (64 categories, 8 series, 64 values per series, "
            "series/category length mismatch, 800KB svg, pie with more than one series) refuses; no computation "
            "libraries, no network, no quantum handles."
        ),
        "parameters": {
            "type": "object",
            "required": ["project", "spec"],
            "properties": {
                "project": _PROJECT,
                "spec": {
                    "type": "object",
                    "required": ["title", "type", "categories", "series"],
                    "properties": {
                        "title": {"type": "string", "minLength": 1, "maxLength": 200},
                        "type": {"type": "string", "enum": ["bar", "line", "stacked_bar", "pie"]},
                        "unit": {"type": "string", "maxLength": 32},
                        "source": {"type": "string", "maxLength": 200},
                        "notes": {"type": "string", "maxLength": 400},
                        "categories": {"type": "array", "minItems": 1, "maxItems": 64, "items": {"type": "string", "minLength": 0, "maxLength": 60}},
                        "series": {
                            "type": "array",
                            "minItems": 1,
                            "maxItems": 8,
                            "items": {
                                "type": "object",
                                "required": ["name", "values"],
                                "properties": {
                                    "name": {"type": "string", "minLength": 1, "maxLength": 60},
                                    "values": {"type": "array", "minItems": 1, "maxItems": 64, "items": {"type": "number"}},
                                },
                                "additionalProperties": False,
                            },
                        },
                    },
                    "additionalProperties": False,
                },
                "overwrite": {"type": "boolean", "default": False},
            },
            "additionalProperties": False,
        },
        "output": {
            "type": "object",
            "required": [
                "chart_id", "json_path", "svg_path", "bytes_json", "bytes_svg",
                "sha256_json", "sha256_svg", "overwrote",
            ],
            "properties": {
                "chart_id": {"type": "string", "pattern": "^[0-9a-f]{16}$", "maxLength": 16},
                "json_path": _path_256("Canonical spec JSON path as project/relative compound."),
                "svg_path": _path_256("Deterministic SVG path as project/relative compound."),
                "bytes_json": {"type": "integer", "minimum": 1},
                "bytes_svg": {"type": "integer", "minimum": 1, "maximum": 800000},
                "sha256_json": _SHA,
                "sha256_svg": _SHA,
                "overwrote": {"type": "boolean"},
            },
            "additionalProperties": False,
        },
    }

    matter = {
        "name": "company_office_matter",
        "capability": "company.office",
        "operation": "office.matter",
        "input_handles": [],
        "output_handles": [],
        "description": (
            "Structured matter artifacts for one project directory of the mounted workspace, the industry-neutral "
            "port of the MeWork project extensions: kind=timeline writes the fixed file project.company-timeline."
            "json (events with date/title/evidence), kind=chronology writes project.company-chronology.json "
            "(entries with date/fact/people/evidence), kind=mindmap writes project.company-mindmap.json (root, "
            "six layers, deeper subtrees truncate with an explicit issue). Upsert merges by id or by the "
            "date|title / date|fact key and keeps an existing anchored item when the incoming one has no "
            "evidence; replace must be passed explicitly for a full redo; an empty payload or an all-empty merge "
            "refuses to overwrite existing work. Dates accept 2026-03-01, 2026/3/1, 2026年3月1日, 2026-03, "
            "2026年3月 and 2026年; unknown dates become issues and the item is dropped instead of guessed. "
            "Receipts count anchored versus unanchored items so missing evidence is named, not hidden. Standard "
            "library only, atomic write re-verified by re-read, cap overshoot (200 events/entries, 512 nodes, "
            "4000 chars per text field) refuses; no external calls, no quantum handles."
        ),
        "parameters": {
            "type": "object",
            "required": ["project", "kind", "data"],
            "properties": {
                "project": _PROJECT,
                "kind": {"type": "string", "enum": ["timeline", "chronology", "mindmap"]},
                "mode": {"type": "string", "enum": ["upsert", "replace"], "default": "upsert"},
                "data": {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": True,
                    "description": "timeline -> {events:[{id?,date,title,summary?,kind?,evidence?:[{path,line_ref?,quote?}]}]}; chronology -> {entries:[{id?,date,fact,people?,evidence?:[...]}]}; mindmap -> {root:{id?,label,kind?,children:[...]}}. The adapter validates each shape and refuses overshoot.",
                },
            },
            "additionalProperties": False,
        },
        "output": {
            "type": "object",
            "required": [
                "kind", "path", "mode", "changed", "item_count",
                "anchored_count", "unanchored_count", "issues", "bytes", "sha256",
            ],
            "properties": {
                "kind": {"type": "string", "enum": ["timeline", "chronology", "mindmap"]},
                "path": _path_256("Fixed artifact path as project/relative compound."),
                "mode": {"type": "string", "enum": ["upsert", "replace"]},
                "changed": {"type": "boolean"},
                "item_count": {"type": "integer", "minimum": 1},
                "anchored_count": {"type": "integer", "minimum": 0},
                "unanchored_count": {"type": "integer", "minimum": 0},
                "issues": {
                    "type": "array",
                    "maxItems": 128,
                    "items": {
                        "type": "object",
                        "required": ["path", "reason"],
                        "properties": {
                            "path": {"type": "string", "minLength": 1, "maxLength": 80, "description": "Item position such as events[3] or root.children[0].children[2]."},
                            "reason": {"type": "string", "minLength": 1, "maxLength": 200},
                        },
                        "additionalProperties": False,
                    },
                },
                "bytes": {"type": "integer", "minimum": 1},
                "sha256": _SHA,
            },
            "additionalProperties": False,
        },
    }

    return [compare, edit, validate, chart, matter]


NEW_NAMES = [row["name"] for row in tool_rows()]


def main() -> None:
    tools = json.loads(TOOLS.read_text(encoding="utf-8"))
    rows = tools["tools"]
    names = [row["name"] for row in rows]
    for name in NEW_NAMES:
        if name in names:
            raise RuntimeError(f"{name} already present; refusing a double batch")
    office_analyze_at = names.index("company_office_analyze")
    rows[office_analyze_at + 1 + 1 : office_analyze_at + 1 + 1] = tool_rows()

    caps = json.loads(CAPS.read_text(encoding="utf-8"))
    office = next(c for c in caps["capabilities"] if c["id"] == "company.office")
    for name in NEW_NAMES:
        if name in office["tools"]:
            raise RuntimeError(f"{name} already in capability; refusing a double batch")
    office["tools"][1:1] = NEW_NAMES

    presets = json.loads(PRESETS.read_text(encoding="utf-8"))
    for preset in ("boot", "lab", "algo"):
        visible = presets["presets"][preset]["visible_tools"]
        anchor_at = visible.index("company_office_create")
        for name in NEW_NAMES:
            if name in visible:
                raise RuntimeError(f"{name} already visible in {preset}; refusing a double batch")
        visible[anchor_at + 1 : anchor_at + 1] = NEW_NAMES

    for path, payload in ((TOOLS, tools), (CAPS, caps), (PRESETS, presets)):
        text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        path.write_text(text, encoding="utf-8", newline="\n")
    print("contracts patched:", ",".join(NEW_NAMES))


if __name__ == "__main__":
    main()
