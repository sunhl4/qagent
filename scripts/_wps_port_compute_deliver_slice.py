"""One-shot contract patch for the run_compute + delivery naming slices.

Adds two tools to ``company.office`` from the MeWork full-reproduction plan:

- ``company_office_compute`` (§4.9 ``run_compute``): the batch-aggregation
  sandbox. A source block (<=80k chars) runs in a *separate interpreter
  process* with a curated builtin set and a whitelisted helper API scoped to
  ONE project directory of the mounted workspace: list_files / read_text /
  read_table(.xlsx|.csv|.json|.md lines) / stats / write_text / write_table
  (spreadsheet output through the bounded generation rules) / emit_chart
  (the deterministic declarative chart). print is captured; no imports, no
  network, no outside-tree paths. Aggregate budgets and a 30s runtime ceiling;
  the machine-level switch ``COMPANY_AGENT_COMPUTE_ALLOW`` must be set or the
  call honestly refuses (high-security deployments keep it off);
- ``company_office_deliver`` (§3.7/§4.3): delivery naming. Copies one
  workspace file into the project ``deliverables/`` directory as
  ``<title>_<UTCYYYYMMDD>_<NN>.<ext>`` (title defaults to the source stem,
  NN scans the existing sequence 01..99), atomic copy, never overwrites the
  source or an existing delivery, sha256 receipt.

Insertion anchors: end of the contiguous office block in ``tools.json`` (after
``company_office_open``), append to the capability tool list, and after
``company_office_open`` in the fixed-presets visibility order (boot/lab/algo;
sign stays office-free). Every insertion asserts absence first.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "contracts" / "tools.json"
CAPS = ROOT / "contracts" / "capabilities.json"
PRESETS = ROOT / "contracts" / "presets.json"

NEW_NAMES = ["company_office_compute", "company_office_deliver"]
_SHA = {
    "type": "string",
    "pattern": "^[0-9a-f]{64}$",
    "maxLength": 64,
}
_PATH_256 = "Workspace file path."


def _project_schema() -> dict[str, object]:
    return {
        "type": "string",
        "pattern": "^[A-Za-z0-9_](?:[A-Za-z0-9_.-]*[A-Za-z0-9_-])?$",
        "maxLength": 128,
        "description": (
            "Project directory inside the mounted workspace root; must be a direct child "
            "directory of it; the compute sandbox sees exactly this subtree."
        ),
    }


def _path_schema(desc: str) -> dict[str, object]:
    return {
        "type": "string",
        "pattern": "^[^\\\\:*?\"<>|\\u0000-\\u001f]{1,256}$",
        "description": desc,
    }


def compute_row() -> dict[str, object]:
    return {
        "name": "company_office_compute",
        "capability": "company.office",
        "operation": "office.compute",
        "input_handles": [],
        "output_handles": [],
        "description": (
            "Batch aggregation sandbox (the run_compute port) for ONE project directory of the "
            "mounted workspace: source code runs in a separate interpreter process with a "
            "curated builtin set and these whitelisted helpers only - list_files(pattern?), "
            "read_text(path), read_table(path .xlsx/.csv/.json/.txt/.md), stats(rows_or_column), "
            "write_text(path,text,overwrite?), write_table(rows,path,overwrite?,sheet_name?), "
            "emit_chart(spec,overwrite?), and a captured print. No imports, no getattr through "
            "dunders by convention, no network, no paths outside the project subtree; every "
            "read and write reuses the workspace fences, the write budget caps 200 files and "
            "4MB per run, xlsx writes follow the spreadsheet caps, and the whole run stops at "
            "30s or 80k source chars with an explicit refusal. The adapter re-verifies every "
            "written file by re-read and reports sha256. Requires the machine-level switch "
            "COMPANY_AGENT_COMPUTE_ALLOW=1: without it the call refuses honestly, keeping "
            "high-security deployments free of any code evaluation. Process isolation and "
            "curated namespaces are not an operating-system security boundary; that is a "
            "documented residual, and the switch is the control."
        ),
        "parameters": {
            "type": "object",
            "required": ["project", "source"],
            "properties": {
                "project": _project_schema(),
                "source": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 80_000,
                    "description": (
                        "The batch program: whitelisted helpers + curated builtins; "
                        "print(...) is captured."
                    ),
                },
            },
            "additionalProperties": False,
        },
        "output": {
            "type": "object",
            "required": [
                "result", "written", "charts", "prints",
                "prints_truncated", "elapsed_ms", "sha256_writes",
            ],
            "properties": {
                "result": {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": True,
                    "description": (
                        "Whatever the source assigned to RESULT (bounded 20KB JSON); "
                        "empty object when absent."
                    ),
                },
                "written": {
                    "type": "array",
                    "maxItems": 200,
                    "items": {
                        "type": "object",
                        "required": ["path", "bytes", "sha256"],
                        "properties": {
                            "path": {"type": "string", "minLength": 1, "maxLength": 256},
                            "bytes": {"type": "integer", "minimum": 1},
                            "sha256": _SHA,
                        },
                        "additionalProperties": False,
                    },
                },
                "charts": {
                    "type": "array",
                    "maxItems": 64,
                    "items": {"type": "string", "minLength": 1, "maxLength": 256},
                    "description": "Chart artifact paths (json+svg pairs count once) the sandbox emitted.",
                },
                "prints": {
                    "type": "array",
                    "maxItems": 40,
                    "items": {"type": "string", "minLength": 0, "maxLength": 400},
                },
                "prints_truncated": {"type": "boolean"},
                "elapsed_ms": {"type": "integer", "minimum": 0},
                "sha256_writes": {
                    "type": "array",
                    "maxItems": 200,
                    "items": _SHA,
                    "description": "Re-read fingerprints of the written files in the same order as written.",
                },
                "trust": {"type": "string", "const": "untrusted_reference_data"},
            },
            "additionalProperties": False,
        },
    }


def deliver_row() -> dict[str, object]:
    return {
        "name": "company_office_deliver",
        "capability": "company.office",
        "operation": "office.deliver",
        "input_handles": [],
        "output_handles": [],
        "description": (
            "Delivery naming for one workspace file (the MeWork present/named-deliverable "
            "port): the file is copied atomically into the project-level deliverables/ "
            "directory as <title>_<UTC YYYYMMDD>_<NN>.<ext>, where title defaults to the "
            "source stem (stripped of old date stamps like _20260101 or _20260101_02), NN is "
            "the next free two-digit sequence for that title and date, 1..99, and 99 breaks "
            "the tool honestly. The source file is never touched; an existing delivery name "
            "is never overwritten; the receipt carries project/relative paths only. Copy "
            "size cap 20MB. Standard library only."
        ),
        "parameters": {
            "type": "object",
            "required": ["project", "path"],
            "properties": {
                "project": _project_schema(),
                "path": _path_schema(
                    "Existing source file relative to the project directory; deliverable "
                    "kinds: .doc .docx .xls .xlsx .ppt .pptx .wps .et .dps .pdf .txt .md "
                    ".csv .json .png .jpg .jpeg."
                ),
                "title": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 60,
                    "description": (
                        "Delivery title; defaults to the source stem after stripping old "
                        "date stamps; forbids path separators."
                    ),
                },
            },
            "additionalProperties": False,
        },
        "output": {
            "type": "object",
            "required": ["source", "path", "sequence", "bytes", "sha256"],
            "properties": {
                "source": {"type": "string", "minLength": 1, "maxLength": 256, "description": _PATH_256},
                "path": {"type": "string", "minLength": 1, "maxLength": 256, "description": _PATH_256},
                "sequence": {"type": "integer", "minimum": 1, "maximum": 99},
                "bytes": {"type": "integer", "minimum": 1},
                "sha256": _SHA,
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
            raise RuntimeError(f"{name} already present; refusing a double slice")
    anchor = names.index("company_office_open")
    rows[anchor + 1 : anchor + 1] = [compute_row(), deliver_row()]

    caps = json.loads(CAPS.read_text(encoding="utf-8"))
    office = next(c for c in caps["capabilities"] if c["id"] == "company.office")
    for name in NEW_NAMES:
        if name in office["tools"]:
            raise RuntimeError(f"{name} already in capability; refusing a double slice")
    office["tools"].extend(NEW_NAMES)

    presets = json.loads(PRESETS.read_text(encoding="utf-8"))
    for preset in ("boot", "lab", "algo"):
        visible = presets["presets"][preset]["visible_tools"]
        at = visible.index("company_office_open")
        for name in NEW_NAMES:
            if name in visible:
                raise RuntimeError(f"{name} already visible in {preset}; refusing a double slice")
        visible[at + 1 : at + 1] = NEW_NAMES

    for path, payload in ((TOOLS, tools), (CAPS, caps), (PRESETS, presets)):
        text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        path.write_text(text, encoding="utf-8", newline="\n")
    print("compute/deliver slice patched:", ",".join(NEW_NAMES))


if __name__ == "__main__":
    main()
