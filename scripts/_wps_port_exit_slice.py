"""One-shot contract patch for the WPS-suite porting exit slice (P5+P6, L6/L7).

Appends two tools to ``company.office`` for the delivery/host exit of the full
MeWork reproduction: ``company_office_convert`` (P5: docx->pdf and doc->docx
through an explicit local LibreOffice/soffice engine, or an operator-wired
.converter program for .doc; hard-fail honestly when neither exists, sibling
delivery naming that never overwrites, converter lease, three-way output
verification) and ``company_office_open`` (P6: hand one workspace file to the
desktop's WPS association or the explicit startfile mode; registry-located
launcher, audit line, human failure text, never a silent system-default
fallback). Insertion anchors: end of the contiguous office block in
``tools.json`` (after pptx), append to the capability tool list, and after
``company_office_pptx`` in the fixed-presets visibility order (boot/lab/algo;
sign stays office-free). Every insertion asserts absence first.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "contracts" / "tools.json"
CAPS = ROOT / "contracts" / "capabilities.json"
PRESETS = ROOT / "contracts" / "presets.json"

NEW_NAMES = ["company_office_convert", "company_office_open"]
_SHA = {
    "type": "string",
    "pattern": "^[0-9a-f]{64}$",
    "maxLength": 64,
}
_PATH_256 = "Workspace file path as project/relative compound."


def _project_schema() -> dict[str, object]:
    return {
        "type": "string",
        "pattern": "^[A-Za-z0-9_](?:[A-Za-z0-9_.-]*[A-Za-z0-9_-])?$",
        "maxLength": 128,
        "description": (
            "Project directory inside the mounted workspace root; must be a direct child "
            "directory of it."
        ),
    }


def _path_schema(description: str) -> dict[str, object]:
    return {
        "type": "string",
        "pattern": "^[^\\\\:*?\"<>|\\u0000-\\u001f]{1,256}$",
        "description": description,
    }


def convert_row() -> dict[str, object]:
    return {
        "name": "company_office_convert",
        "capability": "company.office",
        "operation": "office.convert",
        "input_handles": [],
        "output_handles": [],
        "description": (
            "Local conversion inside one project directory of the mounted workspace, the L6 "
            "exit of the suite: .docx becomes a sibling .pdf and .doc becomes a sibling .docx "
            "through an explicitly configured headless LibreOffice (COMPANY_AGENT_SOFFICE, or "
            "soffice/libreoffice found on PATH); no engine found is a hard, honest failure - "
            "never a stand-in copy, nothing is uploaded anywhere. The converter holds a bounded "
            "lease so two tasks cannot fight over soffice; the child runs with a whitelisted "
            "environment, arrayed arguments and bounded stdout, and the produced file must "
            "pass the three-way check (exists, non-empty, right magic bytes and for docx an "
            "openable package with word/document.xml). Output naming stays next to the source "
            "as <stem>.<ext>, then <stem>_01.._99; overwriting the source is impossible by "
            "construction. 20MB input cap with honest refusal; no OCR, no template execution, "
            "no quantum handles."
        ),
        "parameters": {
            "type": "object",
            "required": ["project", "path"],
            "properties": {
                "project": _project_schema(),
                "path": _path_schema(
                    "Source path relative to the project directory; must be .docx (to pdf) "
                    "or .doc (to docx); any other suffix refuses."
                ),
                "overwrite": {
                    "type": "boolean",
                    "default": False,
                    "description": (
                        "Left absent/false the tool picks the next free sibling name; true "
                        "allows replacing an existing <stem>.<ext> sibling of the same kind, "
                        "never the source itself."
                    ),
                },
            },
            "additionalProperties": False,
        },
        "output": {
            "type": "object",
            "required": ["convert", "source", "path", "bytes", "sha256", "engine", "overwrote"],
            "properties": {
                "convert": {"type": "string", "enum": ["pdf", "docx"]},
                "source": {"type": "string", "minLength": 1, "maxLength": 256, "description": _PATH_256},
                "path": {"type": "string", "minLength": 1, "maxLength": 256, "description": _PATH_256},
                "bytes": {"type": "integer", "minimum": 1},
                "sha256": _SHA,
                "engine": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 64,
                    "description": "Executable basename explicitly used, e.g. soffice.exe.",
                },
                "overwrote": {
                    "type": "boolean",
                    "description": "True when an existing same-name sibling was replaced via overwrite.",
                },
            },
            "additionalProperties": False,
        },
    }


def open_row() -> dict[str, object]:
    return {
        "name": "company_office_open",
        "capability": "company.office",
        "operation": "office.open",
        "input_handles": [],
        "output_handles": [],
        "description": (
            "Desktop exit for one workspace file, the §5.1 host integration ported to the "
            "Windows deployment: the file is opened with WPS through the current file "
            "association (registry-checked launcher must be WPS/Kingsoft, otherwise the call "
            "fails with a human message instead of silently falling back), or with the "
            "explicitly configured startfile mode when the operator prefers the system "
            "association. Launching requires COMPANY_AGENT_OPEN_WPS=wps|startfile to be set "
            "in the local environment - absent configuration is an honest refusal, not a "
            "surprise launch. Allowed kinds are bounded to office/pdf/text/old-binary "
            "suffixes; every launch (and every failure) carries an audit line when the "
            "ledger is configured. Bounded receipt: no machine paths beyond the workspace "
            "compound, launcher reduced to its basename. Standard library only."
        ),
        "parameters": {
            "type": "object",
            "required": ["project", "path"],
            "properties": {
                "project": _project_schema(),
                "path": _path_schema(
                    "Existing workspace file relative to the project directory; office/pdf/"
                    "text/old-binary suffixes only (.doc .docx .xls .xlsx .ppt .pptx .wps "
                    ".et .dps .pdf .txt .md); anything else refuses."
                ),
                "note": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 120,
                    "description": (
                        "One-line reason for the audit ledger when COMPANY_AGENT_AUDIT_* is "
                        "configured; missing ledger skips the line without changing the open."
                    ),
                },
            },
            "additionalProperties": False,
        },
        "output": {
            "type": "object",
            "required": ["path", "engine", "launcher", "audited"],
            "properties": {
                "path": {"type": "string", "minLength": 1, "maxLength": 256, "description": _PATH_256},
                "engine": {"type": "string", "enum": ["wps", "startfile"]},
                "launcher": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 64,
                    "description": "Executable basename actually launched; startfile reduces to 'shell'.",
                },
                "audited": {
                    "type": "boolean",
                    "description": (
                        "True when the ledger line was written; audit config missing means "
                        "false and the open still happened."
                    ),
                },
            },
            "additionalProperties": False,
        },
    }


def main() -> None:
    tools = json.loads(TOOLS.read_text(encoding="utf-8"))
    rows = tools["tools"]
    names = [row["name"] for row in rows]
    for name in NEW_NAMES:
        if name in names:
            raise RuntimeError(f"{name} already present; refusing a double exit slice")
    pptx_at = names.index("company_office_pptx")
    rows[pptx_at + 1 : pptx_at + 1] = [convert_row(), open_row()]

    caps = json.loads(CAPS.read_text(encoding="utf-8"))
    office = next(c for c in caps["capabilities"] if c["id"] == "company.office")
    for name in NEW_NAMES:
        if name in office["tools"]:
            raise RuntimeError(f"{name} already in capability; refusing a double exit slice")
    office["tools"].extend(NEW_NAMES)

    presets = json.loads(PRESETS.read_text(encoding="utf-8"))
    for preset in ("boot", "lab", "algo"):
        visible = presets["presets"][preset]["visible_tools"]
        anchor_at = visible.index("company_office_pptx")
        for name in NEW_NAMES:
            if name in visible:
                raise RuntimeError(f"{name} already visible in {preset}; refusing a double exit slice")
        visible[anchor_at + 1 : anchor_at + 1] = NEW_NAMES

    for path, payload in ((TOOLS, tools), (CAPS, caps), (PRESETS, presets)):
        text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        path.write_text(text, encoding="utf-8", newline="\n")
    print("exit slice patched:", ",".join(NEW_NAMES))


if __name__ == "__main__":
    main()
