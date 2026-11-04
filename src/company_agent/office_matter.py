"""Structured matter artifacts for the WPS-suite porting (P4.5).

WPS-SUITE-PORTING §4.15: timeline / chronology / mindmap as one project
artifact each, written to a FIXED project-root file per kind
(``project.company-<kind>.json``) so artifacts never drift into same-name
copies. The write disciplines taken from the reference implementation:

1. an empty payload (or a merge that would leave nothing) refuses to land,
   so existing reviewed work is never overwritten by nothing;
2. ``upsert`` merges by ``id`` or by ``date|title`` / ``date|fact``: rows
   the batch replaces take the incoming content unless the old row carries
   evidence anchors the incoming one lacks (a reviewed anchor is never
   dropped); untouched rows are retained; ``replace`` must be passed
   explicitly for a full redo;
3. the write is a same-directory temp file replaced atomically and
   re-verified by re-read (sha256 returned matches the disk bytes);
4. mindmaps regenerate as one whole root (the regen discipline), capped at
   six layers — deeper subtrees truncate with an explicit issue path and
   the node count refuses beyond 512.

Dates accept six formats (2026-03-01, 2026/3/1, 2026年3月1日, 2026-03,
2026年3月, 2026年) and normalize to ``sort_key`` + ``display_date``;
unrecognizable dates become issues and the item is dropped, never guessed.
Evidence refs (path/line_ref/quote) are syntactically cleaned; the receipt
counts anchored versus unanchored items so missing evidence is named, not
hidden (the deeper validation is company_office_validate's gate).
"""
from __future__ import annotations

import hashlib
import json
import re

from company_agent import office_create as _oc
from company_agent import office_purpose, workspace_files

SCHEMA_VERSION = 1

MAX_ITEMS = 200
MAX_NODES = 512
MAX_DEPTH = 6
MAX_TEXT_CHARS = 4_000
MAX_PEOPLE = 20
MAX_EVIDENCE = 8
MAX_FILE_BYTES = 2_000_000

KIND_FILE = {
    "timeline": "project.company-timeline.json",
    "chronology": "project.company-chronology.json",
    "mindmap": "project.company-mindmap.json",
}

_DATE_YMD = re.compile(r"^(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})日?$")
_DATE_YM = re.compile(r"^(\d{4})[-/年](\d{1,2})月?$")
_DATE_Y = re.compile(r"^(\d{4})年$")


class OfficeMatterError(ValueError):
    """Refusal that names the boundary hit without echoing paths outside the root."""


def matter(args: dict) -> dict:
    """Contract entry point: fixed-file matter artifact update."""

    purpose = office_purpose.take(args)
    root = workspace_files.root()
    project = args.get("project")
    if not isinstance(project, str) or not project.strip() or project != project.strip():
        raise OfficeMatterError("project is invalid")
    if len(project.encode("utf-8")) > workspace_files.MAX_PATH_BYTES:
        raise OfficeMatterError("project exceeds the workspace path bound")
    workspace_files._lexical(project)
    kind = args.get("kind")
    if kind not in KIND_FILE:
        raise OfficeMatterError("kind 只支持 timeline / chronology / mindmap")
    mode = args.get("mode", "upsert")
    if mode not in ("upsert", "replace"):
        raise OfficeMatterError("mode 只支持 upsert / replace")
    data = args.get("data")
    if not isinstance(data, dict):
        raise OfficeMatterError("data 必须是对象")

    compound = f"{project}/{KIND_FILE[kind]}"
    existing = _existing_document(root, compound, mode)
    issues: list[dict[str, str]] = []
    if kind == "mindmap":
        merged, counts = _merge_mindmap(kind, data, existing, issues, mode)
    else:
        merged, counts = _merge_rows(kind, data, existing, issues, mode)
    item_count, anchored, unanchored = counts
    if not merged:
        raise OfficeMatterError(
            "载荷为空或合并后无有效条目:拒绝空写回;如需整份重做请显式传 mode=replace 并给出内容"
        )
    content_key = "events" if kind == "timeline" else ("entries" if kind == "chronology" else "root")
    payload = {"schemaVersion": SCHEMA_VERSION, "kind": kind, content_key: merged}
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    data_bytes = (serialized + "\n").encode("utf-8")
    changed = existing is None or existing["raw"] != data_bytes
    if not changed:
        # 达到同一份落定结果:不空写回,报告事实即可(读取方仍可核 sha256)。
        raise OfficeMatterError("本次内容与既有文件完全一致:拒绝重复写回(空写回禁令)")
    existed, target = _oc._resolve_target(root, compound, True)
    _oc._write_atomic(target, data_bytes, existed)
    _oc._verify_written(target, data_bytes)
    office_purpose.audit(
        "office_matter", purpose, {"path": compound, "kind": kind, "mode": mode}
    )
    receipt = {
        "kind": kind,
        "path": compound,
        "mode": mode,
        "changed": changed,
        "item_count": item_count,
        "anchored_count": anchored,
        "unanchored_count": unanchored,
        "issues": issues,
        "bytes": len(data_bytes),
        "sha256": hashlib.sha256(data_bytes).hexdigest(),
    }
    year_from, year_to = _year_span(merged if isinstance(merged, list) else [])
    if year_from:
        receipt["year_from"] = year_from
        receipt["year_to"] = year_to
    notes: list[str] = []
    if unanchored:
        notes.append(f"有 {unanchored} 项没有出处，请补充 evidence 后再次 upsert")
    if kind == "mindmap" and isinstance(merged, dict):
        svg = _mindmap_svg(merged)
        if len(svg) <= 20_000:
            receipt["svg"] = svg
        else:
            notes.append("思维导图超出回执篇幅，未内嵌 SVG")
    if notes:
        receipt["note"] = "；".join(notes)[:200]
    return receipt


# ---------------------------------------------------------------- kinds


def _merge_rows(
    kind: str, data: dict, existing: dict | None, issues: list, mode: str
) -> tuple[list, tuple[int, int, int]]:
    label = "events" if kind == "timeline" else "entries"
    text_key = "title" if kind == "timeline" else "fact"
    rows = data.get(label)
    if not isinstance(rows, list):
        raise OfficeMatterError(f"data.{label} 必须是数组")
    if len(rows) > MAX_ITEMS:
        raise OfficeMatterError(f"data.{label} 超过 {MAX_ITEMS} 条上限:拒绝")

    incoming: dict[str, dict] = {}
    for offset, row in enumerate(rows):
        marker = f"{label}[{offset}]"
        cleaned = _clean_item(kind, row, marker, issues)
        if cleaned is None:
            continue
        key = cleaned.pop("_key")
        anchored = bool(cleaned.get("evidence"))
        incoming[key] = {"row": cleaned, "anchored": anchored}

    prior: list[tuple[str, dict]] = []
    if existing is not None:
        prior = _prior_rows(existing["parsed"], label, text_key)
    if mode == "upsert" and not incoming:
        raise OfficeMatterError(
            f"{label} 没有一条有效条目可合并:拒绝空写回;如需整份重做请显式传 mode=replace"
        )

    merged: list[dict] = []
    matched: set[str] = set()
    for key, old in prior:
        incoming_row = incoming.get(key)
        if incoming_row is None:
            merged.append(old)
            continue
        matched.add(key)
        if old.get("evidence") and not incoming_row["anchored"]:
            issues.append(
                {
                    "path": key[:64],
                    "reason": "旧条有出处而新条没有:保留旧条(upsert 不清空已审锚)",
                }
            )
            merged.append(old)
        else:
            merged.append(incoming_row["row"])
    for key, incoming_row in incoming.items():
        if key not in matched:
            merged.append(incoming_row["row"])
    anchored = sum(1 for row in merged if row.get("evidence"))
    return merged, (len(merged), anchored, len(merged) - anchored)


def _prior_rows(parsed: dict | None, label: str, text_key: str) -> list[tuple[str, dict]]:
    rows = []
    if not isinstance(parsed, dict):
        return rows
    stored = parsed.get(label)
    if not isinstance(stored, list):
        return rows
    for offset, row in enumerate(stored):
        if not isinstance(row, dict) or not isinstance(row.get(text_key), str):
            continue
        key = str(row.get("id") or f"{row.get('date')}|{row.get(text_key)}")
        rows.append((key, row))
    return rows


def _merge_mindmap(
    kind: str, data: dict, existing: dict | None, issues: list, mode: str
):
    """Mindmap regenerates as one whole root (the regen discipline)."""

    root = data.get("root")
    if not isinstance(root, dict):
        raise OfficeMatterError("data.root 必须是对象:mindmap 按再生纪律整树重写")
    counter = {"nodes": 0}

    def build(node: dict, depth: int, marker: str) -> dict:
        if counter["nodes"] >= MAX_NODES:
            raise OfficeMatterError(f"mindmap 节点数超过 {MAX_NODES} 上限:拒绝")
        counter["nodes"] += 1
        label = node.get("label")
        if not isinstance(label, str) or not label.strip() or len(label) > MAX_TEXT_CHARS or any(ord(c) < 32 for c in label):
            raise OfficeMatterError(f"{marker}.label 必须是 1..{MAX_TEXT_CHARS} 字符且不含控制字符")
        cleaned: dict = {"label": label}
        identity = node.get("id")
        if identity is not None:
            if not isinstance(identity, str) or not identity.strip() or len(identity) > 64 or any(ord(c) < 32 for c in identity):
                raise OfficeMatterError(f"{marker}.id 形态无效:拒绝")
            cleaned["id"] = identity
        kind_value = node.get("kind")
        if kind_value is not None:
            if kind_value not in {"issue", "fact", "party", "evidence", "other"}:
                raise OfficeMatterError(f"{marker}.kind 不在允许集内:拒绝")
            cleaned["kind"] = kind_value
        cleaned["evidence"] = _clean_evidence(node.get("evidence"), marker, issues)
        cleaned["children"] = []
        children = node.get("children")
        if children is None:
            return cleaned
        if not isinstance(children, list):
            raise OfficeMatterError(f"{marker}.children 必须是数组")
        if depth >= MAX_DEPTH:
            issues.append(
                {"path": marker, "reason": f"超过 {MAX_DEPTH} 层上限:该子树截断并在回执命名"}
            )
            return cleaned
        for child_offset, child in enumerate(children):
            child_marker = f"{marker}.children[{child_offset}]"
            if counter["nodes"] >= MAX_NODES:
                issues.append({"path": child_marker, "reason": f"节点数超过 {MAX_NODES} 上限:剩余子树截断"})
                break
            if not isinstance(child, dict):
                issues.append({"path": child_marker, "reason": "节点必须是对象:丢弃"})
                continue
            try:
                cleaned["children"].append(build(child, depth + 1, child_marker))
            except OfficeMatterError as exc:
                issues.append({"path": child_marker, "reason": str(exc)[:190]})
        return cleaned
    merged = build(root, 1, "root")
    nodes, anchored = _count_anchored(merged)
    return merged, (nodes, anchored, nodes - anchored)


def _count_anchored(node: dict) -> tuple[int, int]:
    total, anchored = 1, (1 if node.get("evidence") else 0)
    for child in node.get("children") or []:
        child_total, child_anchored = _count_anchored(child)
        total += child_total
        anchored += child_anchored
    return total, anchored


def _existing_document(root, compound: str, mode: str) -> dict | None:
    try:
        resolved = workspace_files.resolve(root, compound)
    except workspace_files.WorkspaceFileError:
        return None
    if not resolved.is_file():
        return None
    if resolved.stat().st_size > MAX_FILE_BYTES:
        raise OfficeMatterError("既有 matter 文件超过 2MB 上限:拒绝读取")
    with workspace_files.open_file(root, compound) as stream:
        raw = stream.read(MAX_FILE_BYTES + 1)
    if len(raw) > MAX_FILE_BYTES:
        raise OfficeMatterError("既有 matter 文件超过 2MB 上限:拒绝读取")
    if mode == "replace":
        return None
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeError, ValueError) as exc:
        raise OfficeMatterError("既有 matter 文件不是合法 JSON:拒绝静默合并") from exc
    if not isinstance(parsed, dict):
        raise OfficeMatterError("既有 matter 文件形状无效:拒绝静默合并")
    return {"raw": raw, "parsed": parsed}


# ---------------------------------------------------------------- items


def _clean_item(kind: str, row: object, marker: str, issues: list) -> dict | None:
    if not isinstance(row, dict):
        issues.append({"path": marker, "reason": "条目必须是对象:丢弃"})
        return None
    text_key = "title" if kind == "timeline" else "fact"
    text = row.get(text_key)
    if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT_CHARS or any(ord(c) < 32 for c in text):
        issues.append({"path": marker, "reason": f"{text_key} 缺失或超限:拒绝猜测,丢弃"})
        return None
    cleaned: dict = {text_key: text}
    identity = row.get("id")
    if identity is not None:
        if (
            not isinstance(identity, str)
            or not identity.strip()
            or len(identity) > 64
            or any(ord(c) < 32 for c in identity)
        ):
            issues.append({"path": marker, "reason": "id 形态无效:丢弃该条"})
            return None
        cleaned["id"] = identity
    if kind == "timeline":
        kind_value = row.get("kind")
        if kind_value is not None:
            if kind_value not in {"fact", "procedure", "dispute", "evidence", "other"}:
                issues.append({"path": marker, "reason": "kind 不在允许集内:丢弃"})
                return None
            cleaned["kind"] = kind_value
        summary = row.get("summary")
        if summary is not None:
            if not isinstance(summary, str) or len(summary) > MAX_TEXT_CHARS or any(ord(c) < 32 for c in summary):
                issues.append({"path": marker, "reason": "summary 形态无效:该条丢弃"})
                return None
            cleaned["summary"] = summary
    else:
        people = row.get("people")
        if people is not None:
            if (
                not isinstance(people, list)
                or len(people) > MAX_PEOPLE
                or any(not isinstance(p, str) or not p.strip() or len(p) > 64 or any(ord(c) < 32 for c in p) for p in people)
            ):
                issues.append({"path": marker, "reason": "people 形态无效:该条丢弃"})
                return None
            cleaned["people"] = people
    date_value = row.get("date")
    if not isinstance(date_value, str) or not date_value.strip() or len(date_value) > 64:
        issues.append({"path": marker, "reason": "date 缺失或形态无效:拒绝猜测,丢弃"})
        return None
    normalized = _normalize_date(date_value)
    if normalized is None:
        issues.append({"path": marker, "reason": "日期无法识别(拒绝猜测):该条丢弃"})
        return None
    cleaned["date"] = date_value
    cleaned["sort_key"] = normalized["sort_key"]
    cleaned["display_date"] = normalized["display_date"]
    cleaned["evidence"] = _clean_evidence(row.get("evidence"), marker, issues)
    cleaned["_key"] = str(
        identity if identity is not None and identity != "" else f"{date_value}|{text}"
    )
    return cleaned


def _normalize_date(raw: str) -> dict[str, str] | None:
    text = raw.strip()
    match = _DATE_YMD.match(text)
    if match is not None:
        year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))
        if not (1 <= month <= 12 and 1 <= day <= 31):
            return None
        return {
            "sort_key": f"{year:04d}{month:02d}{day:02d}",
            "display_date": f"{year} 年 {month} 月 {day} 日",
        }
    match = _DATE_YM.match(text)
    if match is not None:
        year, month = int(match.group(1)), int(match.group(2))
        if not 1 <= month <= 12:
            return None
        return {
            "sort_key": f"{year:04d}{month:02d}00",
            "display_date": f"{year} 年 {month} 月",
        }
    match = _DATE_Y.match(text)
    if match is not None:
        year = int(match.group(1))
        return {"sort_key": f"{year:04d}0000", "display_date": f"{year} 年"}
    return None


def _clean_evidence(raw: object, marker: str, issues: list) -> list[dict[str, str]]:
    if raw is None:
        return []
    if not isinstance(raw, list) or len(raw) > MAX_EVIDENCE:
        issues.append({"path": marker, "reason": f"evidence 列表形态无效或超过 {MAX_EVIDENCE} 条上限:作废引用"})
        return []
    rows: list[dict[str, str]] = []
    for ref in raw:
        if not isinstance(ref, dict):
            issues.append({"path": marker, "reason": "evidence 条目必须是对象:作废该引用"})
            continue
        path_value = ref.get("path")
        if (
            not isinstance(path_value, str)
            or not path_value.strip()
            or len(path_value) > 256
            or "\\" in path_value
            or path_value.startswith("/")
            or ".." in path_value.split("/")
        ):
            issues.append({"path": marker, "reason": "evidence.path 形态无效:作废该引用"})
            continue
        entry: dict[str, str] = {"path": path_value}
        line_ref = ref.get("line_ref")
        if line_ref is not None:
            if not isinstance(line_ref, str) or not line_ref.strip() or len(line_ref) > 64:
                issues.append({"path": marker, "reason": "evidence.line_ref 形态无效:作废该引用"})
                continue
            entry["line_ref"] = line_ref
        quote = ref.get("quote")
        if quote is not None:
            if not isinstance(quote, str) or len(quote) > 4000:
                issues.append({"path": marker, "reason": "evidence.quote 形态无效:作废该引用"})
                continue
            entry["quote"] = quote
        rows.append(entry)
    return rows


_NODE_H = 30
_ROW_GAP = 10
_COL_GAP = 32


def _year_span(rows: list) -> tuple[str, str]:
    years = [
        str(row.get("sort_key") or "")[:4]
        for row in rows
        if isinstance(row, dict) and str(row.get("sort_key") or "")[:4].isdigit()
    ]
    if not years:
        return "", ""
    return min(years), max(years)


def _mindmap_svg(root: dict) -> str:
    """Deterministic left-to-right layout. Same tree, same SVG."""

    boxes = _mindmap_boxes(root)
    if not boxes:
        return ""
    width = max(box["x"] + box["w"] for box in boxes) + 8
    height = max(box["y"] + _NODE_H for box in boxes) + 8
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">'
    ]
    for box in boxes:
        if box["parent"] is not None:
            parent = boxes[box["parent"]]
            x1 = parent["x"] + parent["w"]
            y1 = parent["y"] + _NODE_H // 2
            x2 = box["x"]
            y2 = box["y"] + _NODE_H // 2
            parts.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#94a3b8"/>')
    for box in boxes:
        dash = ' stroke-dasharray="4 3"' if box["missing"] else ""
        title = _xml_text(box["label"])
        if box["missing"]:
            title += " · 待补出处"
        label = _xml_text(box["label"][:24])
        parts.append("<g>")
        parts.append(f"<title>{title}</title>")
        parts.append(
            f'<rect x="{box["x"]}" y="{box["y"]}" width="{box["w"]}" height="{_NODE_H}"'
            f' rx="4" fill="#ffffff" stroke="#334155"{dash}/>'
        )
        parts.append(
            f'<text x="{box["x"] + 8}" y="{box["y"] + 20}" font-size="12">{label}</text>'
        )
        parts.append("</g>")
    parts.append("</svg>")
    return "".join(parts)


def _mindmap_boxes(root: dict) -> list[dict]:
    measured = _measure_node(root)
    widths: dict[int, int] = {}

    def columns(node: dict, depth: int) -> None:
        widths[depth] = max(widths.get(depth, 0), node["w"])
        for child in node["children"]:
            columns(child, depth + 1)

    columns(measured, 0)
    boxes: list[dict] = []

    def place(node: dict, depth: int, y: int, parent: int | None) -> int:
        x = sum(widths[level] + _COL_GAP for level in range(depth))
        index = len(boxes)
        boxes.append(
            {
                "label": node["label"],
                "x": x,
                "y": y,
                "w": widths[depth],
                "missing": node["missing"],
                "parent": parent,
            }
        )
        cursor = y
        direct: list[int] = []
        for child in node["children"]:
            direct.append(place(child, depth + 1, cursor, index))
            cursor += child["subtree_h"] + _ROW_GAP
        if direct:
            top = boxes[direct[0]]["y"]
            bottom = boxes[direct[-1]]["y"] + _NODE_H
            boxes[index]["y"] = top + (bottom - top - _NODE_H) // 2
        return index

    place(measured, 0, 0, None)
    return boxes


def _measure_node(node: dict) -> dict:
    label = str(node.get("label") or "")
    units = sum(2 if ord(char) > 127 else 1 for char in label)
    width = max(72, min(220, units * 7 + 16))
    children = [_measure_node(child) for child in node.get("children") or [] if isinstance(child, dict)]
    if children:
        subtree = sum(child["subtree_h"] for child in children) + _ROW_GAP * (len(children) - 1)
    else:
        subtree = _NODE_H
    return {
        "label": label,
        "w": width,
        "subtree_h": max(subtree, _NODE_H),
        "missing": not node.get("evidence"),
        "children": children,
    }


def _xml_text(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
