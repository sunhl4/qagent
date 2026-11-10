"""Workspace literature tools.

One call searches one injected result page or fetches and indexes one paper.
Receipts contain counts and identifiers. Source text stays in the workspace.
"""

from __future__ import annotations

import json
import re
import shutil
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from company_agent import workspace_files
from company_agent.literature_source import (
    LiteratureSourceError,
    copy_source_tree,
    extract_archive,
    index_tex,
)

_SOURCES = ("arxiv", "openalex", "semantic_scholar", "crossref", "europe_pmc")
_PAPER_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_SOURCE_KINDS = frozenset({"arxiv_src", "jats", "html", "pdf_text", "figure_asset"})
_PAGE = 12
_MAX_IDS = 60


class LiteratureError(ValueError):
    """A literature tool cannot complete with the given workspace input."""


def search(args: Mapping[str, Any]) -> dict[str, Any]:
    records = _search_records(str(args["fixture"]))
    year_from = args.get("year_from")
    grouped = {source: [] for source in _SOURCES}
    seen: set[str] = set()
    for record in records:
        if year_from is not None and "year" in record and int(record["year"]) < int(year_from):
            continue
        paper_id = str(record["paper_id"])
        if paper_id in seen:
            continue
        seen.add(paper_id)
        grouped[str(record["source"])].append(paper_id)
    paper_ids: list[str] = []
    sources: list[dict[str, Any]] = []
    truncated = False
    for source in _SOURCES:
        found = grouped[source]
        kept = found[:_PAGE]
        source_truncated = len(found) > _PAGE
        truncated = truncated or source_truncated
        paper_ids.extend(kept)
        sources.append({
            "source": source,
            "returned": len(kept),
            "truncated": source_truncated,
        })
    paper_ids = paper_ids[:_MAX_IDS]
    return {
        "exhaustive": False,
        "citation_hops": 1,
        "returned": len(paper_ids),
        "paper_ids": paper_ids,
        "truncated": truncated,
        "sources": sources,
    }


def fetch(args: Mapping[str, Any]) -> dict[str, Any]:
    paper_id = _paper_id(args.get("paper_id"))
    root = workspace_files.root()
    fixture = workspace_files.resolve(root, str(args["fixture"]))
    destination = _reset_dir(root, f"literature/{paper_id}/source")
    try:
        if fixture.is_file():
            payload = fixture.read_bytes()
            copied = extract_archive(payload, destination)
        elif fixture.is_dir():
            copied = copy_source_tree(fixture, destination)
        else:
            raise LiteratureError("fixture is invalid")
    except LiteratureSourceError as exc:
        raise LiteratureError("archive rejected") from exc
    except OSError as exc:
        raise LiteratureError("fixture is invalid") from exc
    if copied["files"] <= 0:
        raise LiteratureError("fixture is invalid")
    version = _version(destination)
    source_kind = _source_kind(destination)
    _write_json(root, f"literature/{paper_id}/meta.json", {
        "paper_id": paper_id,
        "source_kind": source_kind,
        "version": version,
        "files": copied["files"],
        "bytes": copied["bytes"],
    })
    return {
        "paper_id": paper_id,
        "source_kind": source_kind,
        "version": version,
        "files": copied["files"],
        "bytes": copied["bytes"],
    }


def index(args: Mapping[str, Any]) -> dict[str, Any]:
    paper_id = _paper_id(args.get("paper_id"))
    root = workspace_files.root()
    try:
        meta_path = workspace_files.resolve(root, f"literature/{paper_id}/meta.json")
        source = workspace_files.resolve(root, f"literature/{paper_id}/source")
    except workspace_files.WorkspaceFileError as exc:
        raise LiteratureError("paper is not fetched") from exc
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise LiteratureError("paper is not fetched") from exc
    source_kind = meta.get("source_kind")
    version = meta.get("version")
    if source_kind not in _SOURCE_KINDS or not isinstance(version, str) or not _PAPER_ID.fullmatch(version):
        raise LiteratureError("paper is not fetched")
    indexed = index_tex(_read_tex(source), paper_id=paper_id, version=version, source_kind=source_kind)
    formulas = indexed["formulas"]
    attachments = _attachments(indexed, paper_id=paper_id, version=version, source_kind=source_kind)
    code_entries = _code_entries(indexed, paper_id=paper_id, version=version, source_kind=source_kind)
    _write_json(root, f"literature/{paper_id}/formula-ledger.json", {"entries": formulas})
    _write_json(root, f"literature/{paper_id}/attachment-ledger.json", {"entries": attachments})
    _write_json(root, f"literature/{paper_id}/code-ledger.json", {"entries": code_entries})
    formula_ids = [entry["ledger_id"] for entry in formulas]
    return {
        "paper_id": paper_id,
        "source_kind": source_kind,
        "version": version,
        "formula_count": len(formulas),
        "attachment_count": len(attachments),
        "code_count": len(code_entries),
        "formula_ids": formula_ids[:32],
        "truncated": len(formula_ids) > 32,
        "platform_metric_eligible": False,
        "clock_admitted": False,
    }


_CARD_FIELDS = (
    "experiment_id",
    "hypothesis",
    "falsifier",
    "baseline_name",
    "baseline_source",
    "baseline_metric",
    "primary_metric",
    "metric_kind",
    "metric_unit",
    "direction",
    "resource_type",
    "changed_path",
)


def draft_card(args: Mapping[str, Any]) -> dict[str, Any]:
    """Field names and formula anchors from an indexed paper. No new search and no clock."""
    paper_id = _paper_id(args.get("paper_id"))
    root = workspace_files.root()
    try:
        path = workspace_files.resolve(root, f"literature/{paper_id}/formula-ledger.json")
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (workspace_files.WorkspaceFileError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise LiteratureError("paper is not indexed") from exc
    entries = payload.get("entries") if isinstance(payload, dict) else None
    if not isinstance(entries, list):
        raise LiteratureError("paper is not indexed")
    anchors: list[str] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        anchor = entry.get("anchor") or entry.get("ledger_id")
        if not isinstance(anchor, str) or not anchor or len(anchor) > 80:
            continue
        anchors.append(anchor)
        if len(anchors) == 8:
            break
    return {
        "paper_id": paper_id,
        "baseline_reproduced": False,
        "idempotency_key": "",
        "fields": list(_CARD_FIELDS),
        "anchors": anchors,
    }


def clock_gate(index_result: Mapping[str, Any]) -> dict[str, Any]:
    """Keep an index receipt out of the research clock.

    Eligible and ineligible literature metrics both stay here. A later experiment
    card is a separate call with its own metric.
    """

    if index_result.get("platform_metric_eligible") is not False or index_result.get("clock_admitted") is not False:
        return {"admitted": False, "reason": "literature index stays outside the research clock"}
    return {"admitted": False, "reason": "literature index stays outside the research clock"}


def _search_records(fixture: str) -> list[dict[str, Any]]:
    try:
        path = workspace_files.resolve(workspace_files.root(), fixture)
        data = path.read_bytes()
    except (workspace_files.WorkspaceFileError, OSError) as exc:
        raise LiteratureError("fixture is invalid") from exc
    if len(data) > 200_000:
        raise LiteratureError("fixture is invalid")
    try:
        payload = json.loads(data)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise LiteratureError("fixture is invalid") from exc
    records = payload.get("records") if isinstance(payload, dict) else None
    if not isinstance(records, list):
        raise LiteratureError("fixture is invalid")
    checked: list[dict[str, Any]] = []
    for record in records:
        if not isinstance(record, dict):
            raise LiteratureError("fixture is invalid")
        paper_id = record.get("paper_id")
        source = record.get("source")
        if not isinstance(paper_id, str) or _PAPER_ID.fullmatch(paper_id) is None:
            raise LiteratureError("fixture is invalid")
        if source not in _SOURCES:
            raise LiteratureError("fixture is invalid")
        item = {"paper_id": paper_id, "source": source}
        if "year" in record:
            year = record["year"]
            if isinstance(year, bool) or not isinstance(year, int):
                raise LiteratureError("fixture is invalid")
            item["year"] = year
        checked.append(item)
    return checked


def _paper_id(value: object) -> str:
    if not isinstance(value, str) or _PAPER_ID.fullmatch(value) is None:
        raise LiteratureError("paper_id is invalid")
    return value


def _reset_dir(root: Path, relative: str) -> Path:
    target = _child(root, relative)
    if target.exists():
        if target.is_symlink() or not target.resolve().is_relative_to(root.resolve()):
            raise LiteratureError("workspace path is invalid")
        shutil.rmtree(target)
    target.mkdir(parents=True)
    return target


def _child(root: Path, relative: str) -> Path:
    parts = relative.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise LiteratureError("workspace path is invalid")
    current = root
    for part in parts:
        if current.is_symlink():
            raise LiteratureError("workspace path is invalid")
        current = current / part
    parent = current.parent
    parent.mkdir(parents=True, exist_ok=True)
    anchor = current if current.exists() else parent
    if anchor.is_symlink() or not anchor.resolve().is_relative_to(root.resolve()):
        raise LiteratureError("workspace path is invalid")
    return current


def _write_json(root: Path, relative: str, payload: Mapping[str, Any]) -> None:
    target = _child(root, relative)
    if target.is_symlink():
        raise LiteratureError("workspace path is invalid")
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _version(source: Path) -> str:
    path = source / "VERSION.txt"
    if not path.is_file() or path.is_symlink():
        return "fixture"
    try:
        line = path.read_text(encoding="utf-8").splitlines()[0].strip()
    except (OSError, UnicodeError, IndexError):
        return "fixture"
    if _PAPER_ID.fullmatch(line) is None:
        return "fixture"
    return line


def _source_kind(source: Path) -> str:
    suffixes = {path.suffix.lower() for path in source.rglob("*") if path.is_file() and not path.is_symlink()}
    if ".tex" in suffixes:
        return "arxiv_src"
    return "pdf_text"


def _read_tex(source: Path) -> str:
    chunks: list[str] = []
    used = 0
    for path in sorted(source.rglob("*")):
        if path.is_symlink():
            raise LiteratureError("archive rejected")
        if not path.is_file() or path.suffix.lower() != ".tex":
            continue
        try:
            data = path.read_bytes()
        except OSError as exc:
            raise LiteratureError("fixture is invalid") from exc
        if used + len(data) > 500_000:
            break
        used += len(data)
        chunks.append(data.decode("utf-8", errors="replace"))
    return "\n".join(chunks)


def _attachments(
    indexed: Mapping[str, Any], *, paper_id: str, version: str, source_kind: str,
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for index, name in enumerate(indexed["figures"], start=1):
        entries.append(_attachment(
            f"fig-{index}", name, "figure", paper_id=paper_id, version=version, source_kind=source_kind,
        ))
    for index, name in enumerate(indexed["supplements"], start=1):
        entries.append(_attachment(
            f"sup-{index}", name, "proof", paper_id=paper_id, version=version, source_kind=source_kind,
        ))
    return entries


def _attachment(
    attachment_id: str, name: str, kind: str, *, paper_id: str, version: str, source_kind: str,
) -> dict[str, Any]:
    return {
        "attachment_id": attachment_id,
        "paper_id": paper_id,
        "source_kind": source_kind,
        "version": version,
        "kind": kind,
        "name": name,
        "parsed": False,
        "anchor": name,
    }


def _code_entries(
    indexed: Mapping[str, Any], *, paper_id: str, version: str, source_kind: str,
) -> list[dict[str, Any]]:
    urls = list(indexed["code_urls"])
    if not urls:
        return [{
            "code_id": "code-1",
            "paper_id": paper_id,
            "source_kind": source_kind,
            "version": version,
            "availability": "none",
            "url": None,
            "commit": None,
            "license": None,
            "missing_information": ["code"],
        }]
    return [
        {
            "code_id": f"code-{index}",
            "paper_id": paper_id,
            "source_kind": source_kind,
            "version": version,
            "availability": "third_party",
            "url": url,
            "commit": None,
            "license": None,
            "missing_information": ["commit"],
        }
        for index, url in enumerate(urls, start=1)
    ]
