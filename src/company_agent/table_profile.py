"""company.workflow bounded CSV table profiler (P3 data processing slice).

The tool takes one operator-supplied CSV snapshot (at most 64 data rows,
16 columns, 6000 bytes per contract) and derives typed columns with finite
numeric summaries. It never executes content, never calls out and treats
every cell as data; data-quality findings are flagged as integrity reasons
instead of errors, while structurally invalid arguments fail closed. This
module never imports the contract kernel and creates no model, session or
tool loops.
"""
from __future__ import annotations

import csv
import io
import math
import re
from collections.abc import Mapping
from typing import Any

MAX_TABLE_BYTES = 6000
MAX_ROWS = 64
MAX_COLUMNS = 16
MAX_CELL_BYTES = 256
_SPACE_PATTERN = re.compile(r"\s+")
_CELL_CONTROL = "\x00"


def _cell(value: str, reasons: list[str]) -> str:
    if _CELL_CONTROL in value or len(value.encode("utf-8", errors="replace")) > MAX_CELL_BYTES:
        reasons.append("cell_budget")
        return ""
    return value


def profile(args: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(args, Mapping):
        raise TypeError("table profile arguments must be an object")
    if not isinstance(args, dict):
        raise TypeError("table profile arguments must be a JSON object")
    unknown = set(args) - {"table", "delimiter"}
    if unknown:
        raise ValueError(f"table profile has unknown fields: {sorted(unknown)}")
    if not isinstance(args.get("table"), str):
        raise TypeError("table must be a string")
    if len(args["table"].encode("utf-8")) > MAX_TABLE_BYTES:
        raise ValueError("table exceeds the contract byte budget")
    delimiter = args.get("delimiter", ",")
    if delimiter not in {",", ";", "|", "\t"}:
        raise TypeError("delimiter must be one of ',', ';', '|', chr(9)")
    reader = csv.reader(io.StringIO(args["table"]), delimiter=str(delimiter))
    try:
        rows = [row for row in reader]
    except csv.Error as exc:
        raise ValueError("table is not parseable CSV") from exc
    if not rows:
        raise ValueError("table must contain a header row")
    reasons: list[str] = []
    header = [_cell(str(cell), reasons) for cell in rows[0]]
    if any(not name for name in header[:MAX_COLUMNS]):
        raise ValueError("header cells must be non-empty")
    if len(header) > MAX_COLUMNS:
        reasons.append("column_budget")
        header = header[:MAX_COLUMNS]
    header = [_SPACE_PATTERN.sub(" ", name).strip()[:64] for name in header]
    if len(set(header)) != len(header):
        reasons.append("duplicate_header")
    seen_rows = 0
    values: dict[int, list[float]] = {index: [] for index in range(len(header))}
    textual: set[int] = set()
    filled: dict[int, int] = dict.fromkeys(range(len(header)), 0)
    for row in rows[1:]:
        if seen_rows >= MAX_ROWS:
            reasons.append("row_budget")
            break
        seen_rows += 1
        cells = [_cell(str(item), reasons) for item in row]
        if len(row) != len(header):
            reasons.append("column_mismatch")
        for index, name in enumerate(header):
            if index >= len(cells) or header.count(name) > 1:
                continue
            raw = cells[index].strip()
            if raw == "":
                continue
            filled[index] += 1
            if index in textual:
                continue
            try:
                number = float(raw)
            except (ValueError, OverflowError):
                textual.add(index)
                continue
            if not math.isfinite(number):
                textual.add(index)
                continue
            values[index].append(number)
    columns = []
    numeric: list[dict[str, Any]] = []
    for index, name in enumerate(header):
        numbers = values[index]
        complete = seen_rows > 0 and filled[index] == seen_rows
        if index in textual or header.count(name) > 1 or not numbers or not complete:
            # Text columns: observed text, empty or partially filled cells,
            # duplicate headers and header-only tables all type as text.
            columns.append({"name": name, "kind": "text", "complete": complete})
            continue
        columns.append({"name": name, "kind": "numeric", "complete": True})
        total = sum(numbers)
        numeric.append({
            "name": name,
            "count": len(numbers),
            "min": min(numbers),
            "max": max(numbers),
            "mean": total / len(numbers),
        })
    return {
        "rows": seen_rows,
        "columns": columns,
        "numeric": numeric,
        "integrity": {"complete": not reasons, "reasons": list(dict.fromkeys(reasons))},
    }
