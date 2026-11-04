"""Analysis table with a provenance column and a source sheet (§3.6 / §4.4)."""
from __future__ import annotations

import contextlib
import hashlib
import json
import re

from company_agent import audit_chain, workspace_files
from company_agent import office_create as _oc
from company_agent import office_files as _files

_COLUMN_TYPES = {"text", "number", "date", "single_select"}
_MAX_SETTLED_ROWS = 200


class OfficeReviewError(ValueError):
    """Refusal that names the boundary hit."""


def review_table(args: dict) -> dict:
    workspace = workspace_files.root()
    purpose = _files._purpose(args)
    compound = _oc._compound(args)
    if not compound.casefold().endswith(".xlsx"):
        raise OfficeReviewError("分析表只写入 .xlsx")
    table_id = _table_id(args)
    columns = args.get("columns")
    if not isinstance(columns, list) or not columns or len(columns) > 32:
        raise OfficeReviewError("columns 必须是 1..32 列")
    project = compound.split("/", 1)[0]
    previous = _previous_columns(workspace, project, table_id) if table_id else {}
    cleared: list[str] = []
    normalized: list[dict] = []
    width: int | None = None
    header: list[str] = []
    body: list[list[str]] = []
    provenance = [["column", "row", "lineRef", "summary"]]
    for column in columns:
        if not isinstance(column, dict):
            raise OfficeReviewError("每一列必须是对象")
        name = _oc._check_text(column.get("name"), "column.name", 64)
        kind = column.get("type", "text")
        if kind not in _COLUMN_TYPES:
            raise OfficeReviewError("列类型只接受 text、number、date、single_select")
        prompt = column.get("prompt", "")
        if prompt is None:
            prompt = ""
        prompt = _oc._check_text(prompt, "column.prompt", 500)
        cells = column.get("cells")
        if not isinstance(cells, list) or not cells:
            raise OfficeReviewError(f"列 {name} 需要 cells")
        if table_id and len(cells) > _MAX_SETTLED_ROWS:
            raise OfficeReviewError(f"分析表落定行数超过 {_MAX_SETTLED_ROWS}:拒绝,请拆分")
        prior = previous.get(name)
        drop = prior is not None and (prior.get("type") != kind or prior.get("prompt") != prompt)
        if drop:
            cleared.append(name)
        if width is None:
            width = len(cells)
            body = [[] for _cell in cells]
        elif len(cells) != width:
            raise OfficeReviewError("各列行数必须一致")
        header.extend([name, f"{name}_依据"])
        kept: list[dict[str, str]] = []
        for index, cell in enumerate(cells):
            if not isinstance(cell, dict):
                raise OfficeReviewError("单元格必须是对象")
            if drop:
                value, line_ref, summary = "", "", "列定义已变更，结果已清空"
            else:
                value = _oc._check_text(cell.get("value"), "value", 1000)
                line_ref = _oc._check_text(cell.get("line_ref"), "line_ref", 64)
                summary = _oc._check_text(cell.get("summary"), "summary", 200)
            body[index].extend([value, f"{line_ref}：{summary}"])
            provenance.append([name, str(index + 1), line_ref, summary])
            kept.append({"value": value, "line_ref": line_ref, "summary": summary})
        normalized.append({"name": name, "type": kind, "prompt": prompt, "cells": kept})
    data = _oc._xlsx_package(
        {
            "sheets": [
                {"name": "分析", "rows": [header, *body]},
                {"name": "出处", "rows": provenance},
            ]
        }
    )
    existed, target = _oc._resolve_target(workspace, compound, _oc._overwrite(args))
    _oc._write_atomic(target, data, existed)
    _oc._verify_written(target, data)
    with contextlib.suppress(audit_chain.AuditChainError):
        audit_chain.append(
            "office_review_table",
            {"purpose": purpose, "path": compound, "rows": width or 0},
        )
    payload = {
        "path": compound,
        "rows": width or 0,
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "trust": "untrusted_reference_data",
    }
    if table_id:
        settled = _write_settled(workspace, project, table_id, compound, normalized)
        payload["settled"] = settled
        payload["cleared"] = cleared
    return payload


def _table_id(args: dict) -> str:
    value = args.get("table_id")
    if value is None:
        return ""
    if not isinstance(value, str) or re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value) is None:
        raise OfficeReviewError("table_id 必须是 1..64 位字母、数字、下划线或连字符")
    return value


def _previous_columns(root, project: str, table_id: str) -> dict[str, dict]:
    compound = f"{project}/analysis_tables/{table_id}.ana.json"
    try:
        path = workspace_files.resolve(root, compound)
    except workspace_files.WorkspaceFileError:
        return {}
    if not path.is_file():
        return {}
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    rows = document.get("columns") if isinstance(document, dict) else None
    if not isinstance(rows, list):
        return {}
    found: dict[str, dict] = {}
    for row in rows:
        if isinstance(row, dict) and isinstance(row.get("name"), str):
            found[row["name"]] = row
    return found


def _write_settled(root, project: str, table_id: str, xlsx: str, columns: list[dict]) -> str:
    directory = f"{project}/analysis_tables"
    ana = f"{directory}/{table_id}.ana.json"
    document = {
        "schemaVersion": 1,
        "tableId": table_id,
        "xlsx": xlsx,
        "columns": [
            {"name": column["name"], "type": column["type"], "prompt": column["prompt"]}
            for column in columns
        ],
    }
    _write_json(root, ana, document)
    width = len(columns[0]["cells"]) if columns else 0
    for index in range(width):
        cells = {column["name"]: column["cells"][index]["value"] for column in columns}
        lines = [
            {
                "column": column["name"],
                "ref": column["cells"][index]["line_ref"],
                "summary": column["cells"][index]["summary"],
                "contentSha256": hashlib.sha256(column["cells"][index]["value"].encode("utf-8")).hexdigest(),
            }
            for column in columns
        ]
        record = str(index + 1)
        _write_json(root, f"{directory}/{table_id}.row.{record}.json", {"recordId": record, "cells": cells})
        _write_json(root, f"{directory}/{table_id}.source.{record}.json", {"rowId": record, "lines": lines})
    return ana


def _write_json(root, compound: str, document: dict) -> None:
    raw = (json.dumps(document, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
    existed, target = _oc._resolve_target(root, compound, True)
    _oc._write_atomic(target, raw, existed)
    _oc._verify_written(target, raw)
