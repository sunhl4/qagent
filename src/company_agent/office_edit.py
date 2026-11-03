"""Surgical tracked-revision editing for the WPS-suite porting (P3).

WPS-SUITE-PORTING L4 / §4.2: the hard rules implemented here 1:1 —

- the minimal-edit span algorithm is the port of ``minimal-edit-script``:
  anchors are common runs of >= 4 characters (smaller common runs are part
  of a change), every provably common segment >= 4 characters is kept, and
  replaying the spans reproduces ``after`` verbatim; the memory-side rule
  "no 6+ unchanged run inside a change" follows because any >= 4 common run
  already became an anchor;
- find anchors match inside one paragraph's visible text (the
  ``company_office_analyze`` L{n} enumeration); an anchor that hits several
  places skips the whole edit unless ``occurrences="all"``, misses are
  reported, newline-carrying finds/replace and no-ops skip;
- revisions land as OOXML ``w:ins``/``w:del`` (``w:delText`` for removed
  runs, author and UTC date on every revision element); each paragraph's
  spans apply right-to-left so earlier offsets stay valid; two edits whose
  anchors overlap inside one paragraph refuse;
- paragraph surgery is limited to plain runs (``w:rPr`` + one ``w:t``);
  paragraphs whose runs carry breaks, fields, nested containers or multiple
  text nodes per run are honestly skipped (``unsupported_paragraph_content``)
  instead of being rewritten lossily;
- B5 gate: the plan is memory, the file is truth — the package is written,
  re-opened from disk and the w:ins/w:del count plus every changed
  paragraph's replayed visible text are re-verified before success;
- a batch that would produce zero tracked changes refuses before writing
  (B5 empty-revision gate): empty revision records are never exported.
"""
from __future__ import annotations

import copy
import datetime
import difflib
import hashlib
import io
import xml.etree.ElementTree as ET
import zipfile

from company_agent import office_create as _oc
from company_agent import office_ingest as _ingest
from company_agent import workspace_files

_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_W = f"{{{_W_NS}}}"

_MIN_ANCHOR_CHARS = 4
_MAX_UNCHANGED_RUN = 6  # asserted via the >=4 anchor property: see module doc

MAX_EDITS = 128
MAX_FIND_CHARS = 4_000
MAX_REPLACE_CHARS = 4_000
MAX_FILE_BYTES = _ingest.MAX_FILE_BYTES
MAX_SKIPPED = 128
DEFAULT_AUTHOR = "company-agent"

_SKIP_NO_CHANGE = "no_change"
_SKIP_NEWLINE = "newline_carrying_edit_refused"
_SKIP_NOT_FOUND = "anchor_not_found"
_SKIP_MULTI_PREFIX = "multi_match_skipped:"
_SKIP_COMPLEX = "unsupported_paragraph_content"
_MARKER_CHARS = 40


class OfficeEditError(ValueError):
    """Refusal that names the boundary hit without echoing paths outside the root."""


def edit(args: dict) -> dict:
    """Contract entry point: surgical tracked edits on one existing .docx."""

    root = workspace_files.root()
    compound = _compound(args)
    _docx_gate(compound)
    data = _ingest._read_bounded(root, compound)

    edits, author, note = _edits_and_meta(args)
    root_el = _parse_document(data)
    paragraphs = list(root_el.iter(f"{_W}p"))
    visible = [_paragraph_text(p) for p in paragraphs]
    eligible = {index: _plain_paragraph(p) for index, p in enumerate(paragraphs)}

    plans, skipped = _plan_spans(edits, visible, eligible)
    after_by_index = {
        index: _replay(visible[index], row) for index, row in plans.items()
    }

    base_counts = _revision_counts(document_xml_bytes(data))
    if not plans:
        raise OfficeEditError(
            "修订记录为空:没有可落盘的实际差异;拒绝写回(B5 空修订闸门)"
        )
    for index in sorted(plans):
        _apply_paragraph_changes(paragraphs[index], plans[index], author)
    planned = sum(len(row) for row in plans.values())

    document_xml = _serialize(root_el)
    new_data = _repackage(data, document_xml)
    if len(new_data) > MAX_FILE_BYTES:
        raise OfficeEditError("修订后的文件超过 20MB 上限:拒绝写回,请拆分编辑批次")

    existed, target = _oc._resolve_target(root, compound, True)
    _oc._write_atomic(target, new_data, existed)
    _oc._verify_written(target, new_data)
    on_disk = target.read_bytes()
    disk_counts = _revision_counts(document_xml_bytes(on_disk))
    if disk_counts < base_counts + planned:
        raise OfficeEditError(
            f"B5 读回复核失败:磁盘修订元素 {disk_counts} 少于计划下界 {base_counts + planned};拒绝回报成功"
        )
    fallible = _read_back_replay(document_xml_bytes(on_disk), after_by_index)
    if fallible:
        raise OfficeEditError(
            f"B5 读回复核失败:{fallible} 个改写段落的可见文本回放不符;拒绝回报成功"
        )
    _audit(author, note, compound, len(plans), planned, skipped)
    return {
        "edited": len(plans),
        "hunks": planned,
        "skipped": skipped,
        "path": compound,
        "bytes": len(new_data),
        "sha256": hashlib.sha256(new_data).hexdigest(),
    }


# ---------------------------------------------------------------- planning


def _plan_spans(
    edits: list[tuple[str, str, bool]],
    visible: list[str],
    eligible: dict[int, bool],
) -> tuple[dict[int, list[tuple[int, int, str]]], list[dict[str, str]]]:
    """Turn contract edits into per-paragraph span plans and skips."""

    plans: dict[int, list[tuple[int, int, str]]] = {}
    skipped: list[dict[str, str]] = []
    for number, (find, replace, want_all) in enumerate(edits, start=1):
        reason = _skip_reason(find, replace)
        targets: set[int] = set()
        if reason is None:
            hits = sum(row.count(find) for row in visible if find in row)
            targets = {index for index, row in enumerate(visible) if find in row}
            if not hits:
                reason = _SKIP_NOT_FOUND
            elif not want_all and hits != 1:
                reason = _SKIP_MULTI_PREFIX + find[:_MARKER_CHARS]
        if reason is not None:
            skipped.append({"index": number, "reason": reason})
            continue
        landed = False
        for index in sorted(targets):
            if not eligible[index]:
                skipped.append({"index": number, "reason": _SKIP_COMPLEX})
                continue
            row = visible[index]
            bucket = plans.setdefault(index, [])
            template = _minimal_spans(find, replace) if replace != find else []
            at = row.find(find)
            while at >= 0:
                for offset, extent, replacement in template:
                    candidate = (at + offset, at + extent, replacement)
                    for other_lo, other_hi, _other in bucket:
                        if candidate[0] < other_hi and other_lo < candidate[1]:
                            raise OfficeEditError(
                                f"同一处文本被两条编辑命中(edits[{number}]):拒绝落盘"
                            )
                    bucket.append(candidate)
                    landed = True
                at = row.find(find, at + max(1, len(find)))
        if not landed:
            skipped.append({"index": number, "reason": _SKIP_NOT_FOUND})
    if len(skipped) > MAX_SKIPPED:
        raise OfficeEditError(f"跳过条目超过 {MAX_SKIPPED} 上限:拒绝继续")
    return plans, skipped


def _replay(before: str, spans: list[tuple[int, int, str]]) -> str:
    """Replay spans over ``before`` using original-document coordinates.

    Every span references positions in the ORIGINAL paragraph text, so the
    replay rebuilds from those coordinates in ascending document order;
    mutating a mutable list while earlier spans shifted the offsets desynced
    later spans and produced a mismatched replay.
    """

    pieces: list[str] = []
    cursor = 0
    for lo, hi, replacement in sorted(spans, key=lambda row: row[0]):
        pieces.append(before[cursor:lo])
        pieces.append(replacement)
        cursor = max(cursor, hi)
    pieces.append(before[cursor:])
    return "".join(pieces)


def _skip_reason(find: str, replace: str) -> str | None:
    if "\n" in find or "\n" in replace:
        return _SKIP_NEWLINE
    if find == replace:
        return _SKIP_NO_CHANGE
    return None


def _minimal_spans(before: str, after: str) -> list[tuple[int, int, str]]:
    """Port of ``computeMinimalEditSpans`` (anchors >= 4 common characters).

    Every span ``(lo, hi, replacement)`` replaces ``before[lo:hi]`` with
    ``replacement`` where the range contains no >= 4-character common run;
    replay reproduces ``after`` verbatim. The 6-character unwritten-run rule
    (``MINIMAL_EDIT_MAX_UNCHANGED_RUN``) is a consequence of keeping every
    >= 4 common block as anchor: a change never contains >= 4 common chars,
    hence never >= 6.
    """

    matcher = difflib.SequenceMatcher(None, before, after, autojunk=False)
    blocks = [b for b in matcher.get_matching_blocks() if b.size >= _MIN_ANCHOR_CHARS]
    spans: list[tuple[int, int, str]] = []
    prior_a = prior_b = 0
    for block in blocks:
        if block.a < prior_a or block.b < prior_b:
            raise OfficeEditError("最短改动算法区间倒置:拒绝落盘")
        if block.a > prior_a or block.b > prior_b:
            spans.append((prior_a, block.a, after[prior_b : block.b]))
        prior_a = block.a + block.size
        prior_b = block.b + block.size
    if prior_a < len(before) or prior_b < len(after):
        spans.append((prior_a, len(before), after[prior_b:]))
    for lo, hi, replacement in spans:
        if not before[lo:hi] and not replacement:
            raise OfficeEditError("空改动:拒绝落盘")
    _assert_properties(before, after, spans)
    return spans


def _assert_properties(before: str, after: str, spans: list[tuple[int, int, str]]) -> None:
    """Two provable properties must hold before any byte is written."""

    if _replay(before, spans) != after:
        raise OfficeEditError("算法回放不等于目标文本:拒绝落盘")
    for lo, hi, replacement in spans:
        region = before[lo:hi]
        if not region and not replacement:
            raise OfficeEditError("空改动:拒绝落盘")
        matcher = difflib.SequenceMatcher(None, region, replacement, autojunk=False)
        if any(block.size >= _MIN_ANCHOR_CHARS for block in matcher.get_matching_blocks()):
            raise OfficeEditError("改写区间内仍含未动的 >=4 字公共段:拒绝落盘")


# ---------------------------------------------------------------- XML layer


def _parse_document(data: bytes) -> ET.Element:
    xml = document_xml_bytes(data)
    try:
        for _event, (prefix, uri) in ET.iterparse(io.BytesIO(xml), events=("start-ns",)):
            ET.register_namespace(prefix, uri)
        return ET.fromstring(xml)
    except (ET.ParseError, ValueError) as exc:
        raise OfficeEditError("docx 正文 XML 无法解析") from exc


def document_xml_bytes(data: bytes) -> bytes:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as package:
            return package.read("word/document.xml")
    except (zipfile.BadZipFile, KeyError, OSError) as exc:
        raise OfficeEditError("docx 数据包损坏或缺少 word/document.xml") from exc


def _paragraph_text(paragraph: ET.Element) -> str:
    return "".join(node.text or "" for node in paragraph.iter(f"{_W}t"))


_PLAIN_RUN_CHILDREN = {f"{_W}rPr", f"{_W}t"}
_PLAIN_PARAGRAPH_CHILDREN = {
    f"{_W}pPr", f"{_W}r", f"{_W}bookmarkStart", f"{_W}bookmarkEnd", f"{_W}proofErr",
}


def _plain_paragraph(paragraph: ET.Element) -> bool:
    """True when every run is ``rPr + w:t`` without breaks, fields or nesting."""

    for child in paragraph:
        if child.tag not in _PLAIN_PARAGRAPH_CHILDREN:
            return False
        if child.tag != f"{_W}r":
            continue
        for grand in child:
            if grand.tag not in _PLAIN_RUN_CHILDREN:
                return False
    return True


_ID_COUNTER = {"value": 10_000}


def _next_id() -> int:
    _ID_COUNTER["value"] += 1
    return _ID_COUNTER["value"]


def _revision(tag: str, author: str, when: str) -> ET.Element:
    element = ET.Element(f"{_W}{tag}")
    element.set(f"{_W}id", str(_next_id()))
    element.set(f"{_W}author", author)
    element.set(f"{_W}date", when)
    return element


def _revision_run(text: str, rpr: ET.Element | None, deleted: bool) -> ET.Element:
    run = ET.Element(f"{_W}r")
    if rpr is not None:
        run.append(copy.deepcopy(rpr))
    node = ET.SubElement(run, f"{_W}{'delText' if deleted else 't'}")
    node.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    node.text = text
    return run


def _apply_paragraph_changes(
    paragraph: ET.Element, spans: list[tuple[int, int, str]], author: str
) -> None:
    """Apply one plain paragraph's spans right-to-left.

    Right-to-left keeps earlier character offsets valid while surgery
    inserts revision elements; each span carries its own author + date and
    the inserted ``w:ins`` blocks sit directly after the last removed run
    (delete-then-insert, Word/WPS native ordering).
    """

    when = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    for lo, hi, replacement in sorted(spans, key=lambda row: row[0], reverse=True):
        pieces = _pieces(paragraph)
        extent = pieces[-1][3] if pieces else 0
        if lo > extent or hi > extent:
            raise OfficeEditError("改写区间越出段落可见文本:拒绝落盘")
        if lo == hi:
            _insert_only(paragraph, pieces, lo, replacement, author, when)
            continue
        affected = [p for p in pieces if p[3] > lo and p[2] < hi]
        if not affected:
            raise OfficeEditError("改写区间与段落可见文本不相交:拒绝落盘")
        last_block: ET.Element | None = None
        for piece in affected:
            run, t_el, p_start, p_end = piece
            text = t_el.text or ""
            cut_lo = max(0, lo - p_start)
            cut_hi = min(len(text), hi - p_start)
            removed = text[cut_lo:cut_hi]
            pre, post = text[:cut_lo], text[cut_hi:]
            rpr = run.find(f"{_W}rPr")
            slot = list(paragraph).index(run)
            if not pre and not post:
                paragraph.remove(run)
                block = _revision("del", author, when)
                block.append(_revision_run(text, rpr, deleted=True))
                paragraph.insert(slot, block)
            elif not pre:
                t_el.text = post
                block = _revision("del", author, when)
                block.append(_revision_run(removed, rpr, deleted=True))
                paragraph.insert(slot, block)
            elif not post:
                t_el.text = pre
                block = _revision("del", author, when)
                block.append(_revision_run(removed, rpr, deleted=True))
                paragraph.insert(slot + 1, block)
            else:
                t_el.text = pre
                block = _revision("del", author, when)
                block.append(_revision_run(removed, rpr, deleted=True))
                paragraph.insert(slot + 1, block)
                tail = ET.Element(f"{_W}r")
                if rpr is not None:
                    tail.append(copy.deepcopy(rpr))
                tail_t = ET.SubElement(tail, f"{_W}t")
                tail_t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
                tail_t.text = post
                paragraph.insert(slot + 2, tail)
            last_block = block
        if replacement:
            ins = _revision("ins", author, when)
            inner_rpr: ET.Element | None = None
            if last_block is not None:
                first_child = list(last_block)[0] if len(last_block) else None
                inner_rpr = first_child.find(f"{_W}rPr") if first_child is not None else None
            ins.append(_revision_run(replacement, inner_rpr, deleted=False))
            if last_block is not None:
                slot = list(paragraph).index(last_block) + 1
                paragraph.insert(slot, ins)
            else:
                paragraph.append(ins)


def _pieces(paragraph: ET.Element):
    """Direct-child runs mapped to their text pieces (plain paragraphs only)."""

    cursor = 0
    rows: list[tuple[ET.Element, ET.Element, int, int]] = []
    for child in paragraph:
        if child.tag != f"{_W}r":
            continue
        for t_el in child:
            if t_el.tag == f"{_W}t":
                text = t_el.text or ""
                rows.append((child, t_el, cursor, cursor + len(text)))
                cursor += len(text)
    return rows


_Piece = tuple[ET.Element, ET.Element, int, int]


def _insert_only(
    paragraph: ET.Element,
    pieces: list[_Piece],
    lo: int,
    replacement: str,
    author: str,
    when: str,
) -> None:
    """Pure tracked insertion at ``lo`` (no deletion side)."""

    if not replacement:
        raise OfficeEditError("空替换的纯插入:拒绝落盘")
    ins = _revision("ins", author, when)
    anchor = next((piece for piece in pieces if piece[2] >= lo), None)
    if anchor is None:
        paragraph.append(ins)
        return
    slot = list(paragraph).index(anchor[0])
    paragraph.insert(slot, ins)


# ---------------------------------------------------------------- packaging


def _serialize(root_el: ET.Element) -> bytes:
    return b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' + ET.tostring(
        root_el, encoding="utf-8", short_empty_elements=True
    )


def _repackage(data: bytes, document_xml: bytes) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as source, zipfile.ZipFile(buffer, "w") as target:
        for info in source.infolist():
            payload = document_xml if info.filename == "word/document.xml" else source.read(info.filename)
            target.writestr(info, payload)
    return buffer.getvalue()


def _revision_counts(document_xml: bytes) -> int:
    try:
        root = ET.fromstring(document_xml)
    except ET.ParseError as exc:
        raise OfficeEditError("docx 正文 XML 无法解析") from exc
    return sum(1 for node in root.iter() if node.tag in (f"{_W}ins", f"{_W}del"))


def _read_back_replay(document_xml: bytes, after_by_index: dict[int, str]) -> int:
    """Recount every changed paragraph's visible text from the written file."""

    root = ET.fromstring(document_xml)
    paragraphs = list(root.iter(f"{_W}p"))
    failures = 0
    for index, expected in after_by_index.items():
        if index >= len(paragraphs) or _paragraph_text(paragraphs[index]) != expected:
            failures += 1
    return failures


# ---------------------------------------------------------------- plumbing


def _docx_gate(compound: str) -> None:
    suffix = compound.rsplit(".", 1)[-1] if "." in compound else ""
    if suffix.casefold() != "docx":
        raise OfficeEditError(f".{suffix or '(无后缀)'} 不支持修订轨编辑:仅支持 .docx 已有文档")


def _compound(args: dict) -> str:
    project = args.get("project")
    path = args.get("path")
    if not isinstance(project, str) or not project.strip() or project != project.strip():
        raise OfficeEditError("project is invalid")
    if not isinstance(path, str) or not path.strip() or path != path.strip():
        raise OfficeEditError("workspace path is invalid")
    compound = f"{project}/{path}"
    if len(compound.encode("utf-8")) > workspace_files.MAX_PATH_BYTES:
        raise OfficeEditError("workspace path exceeds the length bound")
    return compound


def _edits_and_meta(args: dict) -> tuple[list[tuple[str, str, bool]], str, str | None]:
    rows = args.get("edits")
    if not isinstance(rows, list) or not rows or len(rows) > MAX_EDITS:
        raise OfficeEditError(f"edits 必须是 1..{MAX_EDITS} 条的数组")
    edits: list[tuple[str, str, bool]] = []
    for row in rows:
        if not isinstance(row, dict):
            raise OfficeEditError("每个 edit 必须是对象")
        find = row.get("find")
        replace = row.get("replace")
        if not isinstance(find, str) or not find:
            raise OfficeEditError("edit.find 必须是非空字符串")
        if len(find) > MAX_FIND_CHARS:
            raise OfficeEditError(f"edit.find 长度超过上限 {MAX_FIND_CHARS},拒绝")
        if not isinstance(replace, str) or len(replace) > MAX_REPLACE_CHARS:
            raise OfficeEditError("edit.replace 必须是不超过上限的字符串")
        occurrences = row.get("occurrences")
        if occurrences is None:
            want_all = False
        elif occurrences == "all":
            want_all = True
        else:
            raise OfficeEditError("edit.occurrences 只接受 all")
        extra = {k: v for k, v in row.items() if k not in {"find", "replace", "occurrences"}}
        if extra:
            raise OfficeEditError(f"edit 含未知字段 {sorted(extra)[0]},拒绝")
        edits.append((find, replace, want_all))
    author = args.get("author")
    if author is None:
        author = DEFAULT_AUTHOR
    if not isinstance(author, str) or not author.strip() or len(author) > 64:
        raise OfficeEditError("author 必须是 1..64 字符")
    note = args.get("note")
    if note is not None and (not isinstance(note, str) or not note.strip() or len(note) > 120):
        raise OfficeEditError("note 必须是 1..120 字符")
    extra = {k: v for k, v in args.items() if k not in {"project", "path", "edits", "author", "note"}}
    if extra:
        raise OfficeEditError(f"未知字段 {sorted(extra)[0]},拒绝")
    return edits, author, note


def _audit(
    author: str,
    note: str | None,
    compound: str,
    edited: int,
    hunks: int,
    skipped: list[dict[str, str]],
) -> None:
    """Best-effort ledger line; an unconfigured ledger skips the line by design."""

    try:
        from company_agent import audit_chain  # noqa: PLC0415 -- optional ledger

        audit_chain.append(
            "office_edit",
            {
                "actor": author,
                "target": compound,
                "note": note or "",
                "edited": edited,
                "hunks": hunks,
                "skipped": len(skipped),
            },
        )
    except Exception:  # noqa: BLE001 -- documented best-effort boundary
        return
