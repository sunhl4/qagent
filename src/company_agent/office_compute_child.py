"""The run_compute child runner (§4.9): curated namespace + whitelisted helpers.

Protocol: reads ``{"project":…, "source":…}`` as ONE stdin payload; the only
argv element is the workspace mount root. Writes ONE JSON line on stdout:

- success: ``{"ok": true, "result":…, "writes":[{"path","bytes"}], "charts":[…],
  "prints":[…], "prints_truncated":bool, "result_truncated":bool}``;
- user-code failure: ``{"ok": false, "message": "…"}``.

The user program sees a curated builtin set (no import machinery) and exactly
the whitelisted helpers; every read/write routes through
``company_agent.workspace_files`` and the bounded generators, so the fences
are the same ones every other office tool uses. Process isolation plus a
curated namespace is NOT an operating-system security boundary - documented
residual, the machine-level switch is the control. Caps: 200 files, 4MB total
written, result JSON 20KB, 40 printed lines, xlsx reads 5000x64, listing
2000 entries; overshoots refuse rather than truncate silently.
"""
from __future__ import annotations

import contextlib
import csv
import fnmatch
import json
import os
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from company_agent import (  # type: ignore  # noqa: E402
    office_chart,  # noqa: E402
    workspace_files,  # noqa: E402
)
from company_agent import office_create as _oc  # noqa: E402
from company_agent import office_ingest as _ingest  # noqa: E402

MAX_FILES = 200
MAX_WRITE_BYTES = 4_000_000
MAX_TEXT_CHARS = 400_000
MAX_READ_CHARS = 200_000
MAX_RESULT_JSON = 20_000
MAX_PRINTS = 40
MAX_PRINT_CHARS = 400
MAX_LISTED = 2_000
MAX_XLSX_ROWS = 5_000
MAX_XLSX_COLS = 64
_MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"

_printed: list[str] = []
_writes: list[dict[str, object]] = []
_charts: list[str] = []
_state = {"files": 0, "bytes": 0}
_ROOT: Path | None = None
_PROJECT: str = ""
_PRINTS_TRUNCATED = False


class _UserFailure(Exception):
    """User-program failure later rendered as an ``ok:false`` receipt."""


def _compound(relative: str) -> str:
    if not isinstance(relative, str) or not relative.strip() or relative != relative.strip():
        raise _UserFailure("路径必须是干净的字符串")
    compound = f"{_PROJECT}/{relative}"
    workspace_files._lexical(compound)
    return compound


def _child_path(relative: str) -> Path:
    resolved = workspace_files.resolve(_ROOT, _compound(relative))
    project_root = (_ROOT / _PROJECT).resolve()
    if not resolved.is_relative_to(project_root):
        raise _UserFailure(f"沙箱路径越过项目目录:{relative[:64]}")
    return resolved


def _relative_posix(target: Path) -> str:
    # 一律以项目根为基:脱离 _ROOT 解析差异,跨长短路径均稳定。
    return target.resolve().relative_to((_ROOT / _PROJECT).resolve()).as_posix()


# ---------------------------------------------------------------- helpers


def list_files(subdir: str = "", pattern: str = "") -> list[str]:
    """Bounded recursive listing of the project subtree (project-relative paths)."""

    base = _child_path(subdir or "")
    rows: list[str] = []
    stack = [base]
    while stack:
        current = stack.pop()
        try:
            entries = sorted(os.scandir(current), key=lambda item: item.name)
        except OSError as exc:
            raise _UserFailure(f"目录不可读:{str(exc)[:120]}") from exc
        for entry in entries:
            if entry.is_symlink():
                continue
            if entry.is_dir():
                stack.append(Path(entry.path))
                continue
            full = Path(entry.path).resolve().relative_to(_ROOT.resolve()).as_posix()
            shown = _relative_posix(Path(entry.path))
            if pattern and not fnmatch.fnmatchcase(full, pattern):
                continue
            if len(rows) >= MAX_LISTED:
                raise _UserFailure(f"目录条目超过 {MAX_LISTED} 上限:请用 pattern 收窄")
            rows.append(shown)
    return sorted(rows)


def read_text(relative: str, limit: int = MAX_READ_CHARS) -> str:
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= MAX_READ_CHARS:
        raise _UserFailure(f"read_text limit 必须是 1..{MAX_READ_CHARS}")
    with workspace_files.open_file(_ROOT, _compound(relative)) as stream:
        ceiling = max(1_000, limit) * 4
        data = stream.read(ceiling + 1)
    if len(data) > ceiling:
        raise _UserFailure(f"read_text 超过 {limit} 字符上限:请分窗读取")
    try:
        text = data.decode("utf-8")
    except UnicodeError as exc:
        raise _UserFailure("文件不是 UTF-8,拒绝读入") from exc
    if len(text) > limit:
        raise _UserFailure(f"read_text 超过 {limit} 字符上限:请分窗读取")
    return text


def read_table(relative: str) -> list[list[object]]:
    suffix = Path(relative).suffix.casefold()
    if suffix == ".csv":
        text = read_text(relative)
        return [[_clean(cell) for cell in row] for row in csv.reader(text.splitlines()) if row]
    if suffix in {".txt", ".md"}:
        return [[line] for line in read_text(relative).splitlines()]
    if suffix == ".json":
        payload = json.loads(read_text(relative))
        if not isinstance(payload, list):
            raise _UserFailure("read_table 的 JSON 需要是数组")
        rows: list[list[object]] = []
        for row in payload[:MAX_XLSX_ROWS]:
            if isinstance(row, list):
                rows.append([_clean(cell) for cell in row[:MAX_XLSX_COLS]])
            elif isinstance(row, dict):
                rows.append([_clean(value) for value in row.values()])
            else:
                rows.append([_clean(row)])
        if len(payload) > MAX_XLSX_ROWS:
            raise _UserFailure(f"read_table 超过 {MAX_XLSX_ROWS} 行上限")
        return rows
    if suffix == ".xlsx":
        return _xlsx_rows(relative)
    raise _UserFailure("read_table 只支持 .csv .json .txt .md .xlsx")


def _clean(value: object) -> object:
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        return value[:1_000]
    return str(value)[:1_000]


def _xlsx_rows(relative: str) -> list[list[object]]:
    with workspace_files.open_file(_ROOT, _compound(relative)) as stream:
        data = stream.read(_ingest.MAX_FILE_BYTES + 1)
    if len(data) > _ingest.MAX_FILE_BYTES:
        raise _UserFailure("xlsx 超过 20MB 摄取上限")
    try:
        package, shared, entries = _ingest._xlsx_book(data)
    except (_ingest.OfficeIngestError, ET.ParseError, zipfile.BadZipFile) as exc:
        raise _UserFailure(f"xlsx 无法解析:{str(exc)[:120]}") from exc
    if not entries:
        raise _UserFailure("xlsx 没有工作表")
    target = entries[0][2].lstrip("/")
    if not target.startswith("xl/"):
        target = "xl/" + target
    try:
        sheet = ET.fromstring(package.read(target))
    except (KeyError, ET.ParseError) as exc:
        raise _UserFailure("工作表数据实体无法解析") from exc
    rows: list[list[object]] = []
    for number, row in enumerate(sheet.iter(f"{_MAIN}row"), start=1):
        if number > MAX_XLSX_ROWS:
            raise _UserFailure(f"read_table 超过 {MAX_XLSX_ROWS} 行上限")
        cells = [_clean(_ingest._xlsx_cell_value(cell, shared)) for cell in row[:MAX_XLSX_COLS]]
        rows.append(cells)
    return rows


def stats(rows: list[list[object]]) -> dict[str, object]:
    """Column counts plus numeric min/max/sum/mean for tabular rows."""

    if not isinstance(rows, list) or not rows:
        raise _UserFailure("stats 需要非空 rows(与 read_table 输出同形)")
    counted = rows[:MAX_XLSX_ROWS]
    width = min(
        max((len(row) for row in counted if isinstance(row, list)), default=0),
        MAX_XLSX_COLS,
    )
    report: dict[str, object] = {"rows": len(counted), "columns": width, "columns_detail": {}}
    detail = report["columns_detail"]
    for index in range(width):
        values: list[float] = []
        blanks = 0
        for row in counted:
            if not isinstance(row, list) or index >= len(row):
                blanks += 1
                continue
            value = row[index]
            if isinstance(value, bool) or value is None:
                blanks += 1
            elif isinstance(value, (int, float)):
                values.append(float(value))
            elif isinstance(value, str):
                try:
                    values.append(float(value))
                except ValueError:
                    blanks += 1
        column: dict[str, object] = {"count": len(values), "blank": blanks}
        if values:
            column.update(
                {
                    "min": min(values),
                    "max": max(values),
                    "sum": round(sum(values), 6),
                    "mean": round(sum(values) / len(values), 6),
                }
            )
        detail[f"column{index}"] = column
    return report


def write_text(relative: str, text: str, overwrite: bool = False) -> str:
    if not isinstance(text, str):
        raise _UserFailure("write_text text 必须是字符串")
    encoded = text.encode("utf-8")
    if len(encoded) > MAX_TEXT_CHARS:
        raise _UserFailure(f"write_text 超过 {MAX_TEXT_CHARS} 字符上限")
    _accounted(len(encoded))
    existed, target = _oc._resolve_target(_ROOT, _compound(relative), bool(overwrite))
    _oc._write_atomic(target, encoded, existed)
    _oc._verify_written(target, encoded)
    _accounted(len(encoded))
    _writes.append({"path": _relative_posix(target), "bytes": len(encoded)})
    return _relative_posix(target)


def write_table(
    rows: list[list[object]],
    relative: str,
    overwrite: bool = False,
    sheet_name: str = "Sheet1",
) -> str:
    if not isinstance(rows, list) or not rows:
        raise _UserFailure("write_table 需要非空 rows")
    clean = [[_clean(cell) for cell in row] for row in rows]
    payload = _oc._xlsx_package({"sheets": [{"name": sheet_name, "rows": clean}]})
    relative = relative if relative.endswith(".xlsx") else relative + ".xlsx"
    _accounted(len(payload))
    existed, target = _oc._resolve_target(_ROOT, _compound(relative), bool(overwrite))
    _oc._write_atomic(target, payload, existed)
    _oc._verify_written(target, payload)
    _accounted(len(payload))
    _writes.append({"path": _relative_posix(target), "bytes": len(payload)})
    return _relative_posix(target)


def emit_chart(spec: object, overwrite: bool = False) -> dict[str, object]:
    receipt = office_chart.chart(
        {
            "project": _PROJECT,
            "spec": spec,
            "overwrite": bool(overwrite),
            "purpose": "沙箱出图",
        }
    )
    _accounted(2)
    _charts.append(str(receipt["json_path"]))
    return {"path": receipt["json_path"], "svg": receipt["svg_path"], "chart_id": receipt["chart_id"]}


def _accounted(payload_bytes: int) -> None:
    _state["files"] += 1
    _state["bytes"] += payload_bytes
    if _state["files"] > MAX_FILES:
        raise _UserFailure(f"本次运行写入文件数超 {MAX_FILES} 上限:请拆批")
    if _state["bytes"] > MAX_WRITE_BYTES:
        raise _UserFailure("本次运行写入总字节超 4MB 上限:请拆批")


def _capture_print(*values: object) -> None:
    global _PRINTS_TRUNCATED
    if len(_printed) >= MAX_PRINTS:
        _PRINTS_TRUNCATED = True
        return
    text = " ".join(str(value) for value in values)[:MAX_PRINT_CHARS]
    _printed.append(text)


SAFE_BUILTINS: dict[str, object] = {
    "True": True,
    "False": False,
    "None": None,
    "abs": abs,
    "all": all,
    "any": any,
    "bool": bool,
    "bytes": bytes,
    "dict": dict,
    "enumerate": enumerate,
    "float": float,
    "int": int,
    "isinstance": isinstance,
    "len": len,
    "list": list,
    "map": map,
    "max": max,
    "min": min,
    "range": range,
    "reversed": reversed,
    "round": round,
    "set": set,
    "sorted": sorted,
    "str": str,
    "sum": sum,
    "tuple": tuple,
    "zip": zip,
    "filter": filter,
    "print": _capture_print,
    "ValueError": ValueError,
    "TypeError": TypeError,
    "KeyError": KeyError,
    "IndexError": IndexError,
    "ZeroDivisionError": ZeroDivisionError,
    "ArithmeticError": ArithmeticError,
    "RuntimeError": RuntimeError,
    "Exception": Exception,
    "StopIteration": StopIteration,
}


def main() -> int:
    global _ROOT, _PROJECT
    with contextlib.suppress(AttributeError):
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    try:
        # 归一路径:父进程传来的可能是 8.3 短名,字符比较会误判逃逸。
        _ROOT = Path(sys.argv[1]).resolve()
        payload = json.loads(sys.stdin.read())
        _PROJECT = str(payload.get("project") or "")
        source = payload.get("source")
    except (IndexError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "message": f"runner 输入无效:{exc!r}"[:180]}, ensure_ascii=False))
        return 2
    try:
        workspace_files._lexical(_PROJECT)
        if not (_ROOT / _PROJECT).is_dir():
            raise _UserFailure(f"project 目录 {_PROJECT!r} 不存在或不是目录")
        if not isinstance(source, str) or not source.strip():
            raise _UserFailure("source 必须是非空程序文本")
        import math  # noqa: PLC0415 -- curated values handed to the namespace
        import re  # noqa: PLC0415 -- curated values handed to the namespace

        namespace: dict[str, object] = dict(SAFE_BUILTINS)
        # exec 会在 __builtins__ 缺席时注入真实 builtins:必须显式钉住受限集。
        namespace["__builtins__"] = dict(SAFE_BUILTINS)
        namespace.update(
            {
                "list_files": list_files,
                "read_text": read_text,
                "read_table": read_table,
                "stats": stats,
                "write_text": write_text,
                "write_table": write_table,
                "emit_chart": emit_chart,
                "math": math,
                "re": re,
            }
        )
        try:
            exec(source, namespace)  # noqa: S102 -- the sandbox IS this curated exec
        except Exception as exc:  # noqa: BLE001 -- user program surface
            # _UserFailure(预算/围栏)与普通程序异常同位处理:都是该次失败的真相。
            message = str(exc) if isinstance(exc, _UserFailure) else (
                f"沙箱程序异常 {type(exc).__name__}: {str(exc)[:160]}"
            )
            print(json.dumps({"ok": False, "message": message}, ensure_ascii=False))
            return 0
        result = namespace.get("RESULT", {})
        serialized = json.dumps(result, ensure_ascii=False, default=str)
        truncated = False
        if len(serialized) > MAX_RESULT_JSON:
            serialized = json.dumps({"truncated": True}, ensure_ascii=False)
            truncated = True
        for row in _writes:
            row["bytes"] = (_ROOT / _PROJECT / str(row["path"])).stat().st_size
        print(
            json.dumps(
                {
                    "ok": True,
                    "result": json.loads(serialized),
                    "result_truncated": truncated,
                    "writes": _writes,
                    "charts": list(_charts),
                    "prints": _printed[:MAX_PRINTS],
                    "prints_truncated": _PRINTS_TRUNCATED,
                },
                ensure_ascii=False,
            )
        )
        return 0
    except Exception as exc:  # noqa: BLE001 -- runner envelope
        if isinstance(exc, _UserFailure):
            message = str(exc)
        else:
            message = f"沙箱错误 {type(exc).__name__}: {str(exc)[:160]}"
        print(json.dumps({"ok": False, "message": message}, ensure_ascii=False))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
