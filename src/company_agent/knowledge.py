from __future__ import annotations

import hashlib
import json
import os
import re
import time
from collections.abc import Iterator, Mapping
from importlib import metadata
from itertools import islice
from pathlib import Path, PurePosixPath
from typing import Any

from company_agent.jsonutil import loads as strict_json_loads

_TEXT_SUFFIXES = {".md", ".txt"}
_MAX_KNOWLEDGE_FILE_BYTES = 1_000_000
_MAX_KNOWLEDGE_FILES = 10_000
_MAX_KNOWLEDGE_ENTRIES = 20_000
_MAX_KNOWLEDGE_TOTAL_BYTES = 16_000_000
_MAX_KNOWLEDGE_DEPTH = 32
_REGISTRY_FIELDS = {"file", "sha256", "audience", "approved", "revoked", "expires_epoch"}
_REGISTRY_PATH_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,511}")
_PRESET_AUDIENCE = {"boot": "internal", "lab": "internal", "algo": "internal", "sign": "public"}


def _load_registry(root: Path) -> dict[str, dict[str, Any]] | None:
    """Admission registry per knowledge root; valid-but-absent means legacy mode."""

    try:
        raw = (root / "registry.json").read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise RuntimeError("knowledge registry is unavailable") from exc
    try:
        payload = strict_json_loads(raw)
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        raise RuntimeError("knowledge registry is invalid") from exc
    if (not isinstance(payload, dict) or set(payload) != {"version", "entries"}
        or payload.get("version") != "1.0.0"):
        raise RuntimeError("knowledge registry is invalid")
    entries = payload.get("entries")
    if not isinstance(entries, list) or any(not isinstance(entry, dict) for entry in entries):
        raise RuntimeError("knowledge registry is invalid")
    file_ids = {entry.get("file") for entry in entries if isinstance(entry, dict)}
    if len(entries) > 512 or len(entries) != len(file_ids):
        raise RuntimeError("knowledge registry is invalid")
    mapping: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if set(entry) != _REGISTRY_FIELDS:
            raise RuntimeError("knowledge registry is invalid")
        file_path = entry["file"]
        if (
            not isinstance(file_path, str)
            or not _REGISTRY_PATH_PATTERN.fullmatch(file_path)
            or ".." in file_path.split("/")
            or not PurePosixPath(file_path).as_posix() == file_path
            or not file_path.endswith(tuple(sorted(_TEXT_SUFFIXES)))
        ):
            raise RuntimeError("knowledge registry is invalid")
        sha = entry["sha256"]
        audience = entry["audience"]
        approved = entry["approved"]
        revoked = entry["revoked"]
        expires = entry["expires_epoch"]
        if (
            not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{64}", sha)
            or audience not in {"public", "internal"}
            or not isinstance(approved, bool) or not isinstance(revoked, bool)
            or (expires is not None and (
                not isinstance(expires, int) or isinstance(expires, bool) or not 0 <= expires <= 2**53 - 1
            ))
        ):
            raise RuntimeError("knowledge registry is invalid")
        mapping[file_path] = {
            "file": file_path, "sha256": sha, "audience": audience,
            "approved": approved, "revoked": revoked, "expires_epoch": expires,
        }
    return mapping


def registry_status(root: Path) -> dict[str, bool]:
    """Governance status for operator-facing checks; never an authorization source."""

    try:
        _load_registry(root)
    except RuntimeError:
        valid = False
    else:
        valid = True
    return {"present": (root / "registry.json").is_file(), "valid": valid}


def _walk_files(root: Path, budget: list[int], reasons: set[str]) -> Iterator[Path]:
    """Bound enumeration, reporting incomplete coverage without disclosing paths."""

    pending = [(root, 0)]
    while pending:
        if budget[0] <= 0:
            reasons.add("entry_budget")
            return
        directory, depth = pending.pop()
        try:
            with os.scandir(directory) as iterator:
                entries = list(islice(iterator, budget[0]))
                # One lookahead distinguishes exact exhaustion from truncation.
                if next(iterator, None) is not None:
                    reasons.add("entry_budget")
            budget[0] -= len(entries)
            for entry in sorted(entries, key=lambda item: item.name):
                if entry.is_symlink():
                    continue
                if entry.is_dir(follow_symlinks=False):
                    if depth < _MAX_KNOWLEDGE_DEPTH:
                        pending.append((Path(entry.path), depth + 1))
                    else:
                        reasons.add("depth_limit")
                elif entry.is_file(follow_symlinks=False):
                    yield Path(entry.path)
        except OSError:
            reasons.add("read_error")


def query_terms(query: str) -> tuple[str, ...]:
    """Small deterministic CJK bigram expansion, not semantic retrieval."""

    words = list(dict.fromkeys(part.casefold() for part in query.split() if part))
    if len(words) > 64:
        raise ValueError("query contains too many terms")
    if any(len(word.encode("utf-8")) > 256 for word in words):
        raise ValueError("query contains an invalid term")
    expanded = list(words)
    for source, target in (("审批", "批准"), ("仿真", "模拟")):
        if source in query:
            expanded.append(target)
    for run in re.findall(r"[\u4e00-\u9fff]+|[a-zA-Z_][a-zA-Z0-9_-]*", query.casefold()):
        if re.fullmatch(r"[\u4e00-\u9fff]+", run):
            expanded.extend(run[index:index + 2] for index in range(len(run) - 1))
        else:
            expanded.append(run)
    return tuple(dict.fromkeys(expanded))[:128]


def _workspace_knowledge_root() -> Path | None:
    package_dir = Path(__file__).resolve().parent
    workspace = package_dir.parents[1]
    candidate = workspace / "knowledge"
    if package_dir.parent.name == "src" and (workspace / "pyproject.toml").is_file():
        return candidate
    return None


def _installed_knowledge_root() -> Path | None:
    try:
        distribution = metadata.distribution("unitqc-company-agent")
    except metadata.PackageNotFoundError:
        return None
    for file in distribution.files or ():
        text = str(file).replace("\\", "/")
        if text.endswith("share/unitqc-company-agent/knowledge/quantum-capability.md"):
            candidate = Path(distribution.locate_file(file)).parent
            # The METADATA path is anchored at the dist-info folder, which for
            # data files two levels below the install prefix (pip --target)
            # resolves outside the layout; only an existing tree counts, and a
            # miss falls back to the prefix locator below.
            if (candidate / "quantum-capability.md").is_file():
                return candidate
    return None


def _installed_prefix_knowledge_root() -> Path | None:
    package_dir = Path(__file__).resolve().parent
    for parent in (package_dir.parent, *package_dir.parents):
        candidate = parent / "share" / "unitqc-company-agent" / "knowledge"
        if (candidate / "quantum-capability.md").is_file():
            return candidate
    return None


def _notes_dir() -> Path | None:
    configured = str(os.environ.get("COMPANY_AGENT_RESEARCH_STATE") or "").strip()
    path = Path(configured).expanduser() if configured else Path.home() / ".dsh" / "research-clock"
    if not path.is_absolute():
        return None
    return path / "notes"


def write_note(args: Mapping[str, Any]) -> dict[str, Any]:
    experiment_id = args.get("experiment_id")
    stop_reason = args.get("stop_reason")
    sentence = args.get("sentence")
    if not isinstance(experiment_id, str) or not isinstance(stop_reason, str):
        raise ValueError("knowledge note is invalid")
    if not isinstance(sentence, str) or not sentence.strip() or "\n" in sentence or "\r" in sentence:
        raise ValueError("sentence is invalid")
    folder = _notes_dir()
    if folder is None:
        raise ValueError("research state path must be absolute")
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{experiment_id}.md"
    path.write_text(
        f"# {experiment_id}\n\nstop_reason: {stop_reason}\n\n{sentence.strip()}\n",
        encoding="utf-8",
    )
    return {"ok": True, "experiment_id": experiment_id}


def roots() -> tuple[tuple[str, Path], ...]:
    workspace = _workspace_knowledge_root()
    installed = None if workspace is not None else (
        _installed_knowledge_root() or _installed_prefix_knowledge_root()
    )
    rows: list[tuple[str, Path]] = []
    if workspace is not None and workspace.is_dir():
        rows.append(("builtin", workspace))
    elif installed is not None and installed.is_dir():
        rows.append(("builtin", installed))
    else:
        raise RuntimeError("Company Agent knowledge is not installed")
    enabled = os.environ.get("COMPANY_AGENT_ENABLE_CONFIGURED_KNOWLEDGE", "").strip() == "1"
    configured = str(os.environ.get("COMPANY_AGENT_KNOWLEDGE_PATH") or "").split(os.pathsep)
    for index, item in enumerate(configured, start=1):
        if enabled and item.strip():
            raw_item = item.strip()
            if "\x00" in raw_item:
                raise ValueError("COMPANY_AGENT_KNOWLEDGE_PATH contains an invalid entry")
            candidate = Path(raw_item).expanduser()
            if candidate.is_symlink():
                raise ValueError("COMPANY_AGENT_KNOWLEDGE_PATH entries must not be symlinks")
            if not candidate.is_absolute():
                raise ValueError("COMPANY_AGENT_KNOWLEDGE_PATH entries must be absolute")
            if not candidate.is_dir():
                raise ValueError("COMPANY_AGENT_KNOWLEDGE_PATH entries must be directories")
            rows.append((f"configured-{index}", candidate))
    notes = _notes_dir()
    if notes is not None and notes.is_dir():
        rows.append(("notes", notes))
    roots_seen: set[Path] = set()
    unique_rows: list[tuple[str, Path]] = []
    for root_id, root in rows:
        try:
            identity = root.expanduser().resolve(strict=False)
        except OSError:
            identity = root.expanduser().absolute()
        if identity in roots_seen:
            continue
        if any(parent in roots_seen for parent in identity.parents):
            continue
        roots_seen.add(identity)
        unique_rows.append((root_id, root))
    return tuple(unique_rows)


def search(args: Mapping[str, Any], *, preset: str = "lab") -> dict[str, Any]:
    if not isinstance(args, Mapping):
        raise TypeError("knowledge search arguments must be an object")
    if not isinstance(args, dict):
        raise TypeError("knowledge search arguments must be a JSON object")
    audience = _PRESET_AUDIENCE.get(str(preset))
    if audience is None:
        raise TypeError(f"unknown knowledge preset {str(preset)!r}")
    unknown = set(args) - {"query"}
    if unknown:
        raise ValueError(f"knowledge search has unknown fields: {sorted(unknown)}")
    if not isinstance(args.get("query"), str):
        raise TypeError("query must be a string")
    if len(args["query"]) > 1000:
        raise ValueError("query exceeds the contract length limit")
    query = args["query"].strip()
    if not query:
        raise ValueError("query is required")
    terms = query_terms(query)
    if any(not term or len(term.encode("utf-8")) > 256 for term in terms):
        raise ValueError("query contains an invalid term")
    if any("\x00" in term for term in terms):
        raise ValueError("query contains invalid characters")
    reasons: set[str] = set()
    hits: list[dict[str, str]] = []
    scanned_files = 0
    scanned_bytes = 0
    entry_budget = [_MAX_KNOWLEDGE_ENTRIES]
    for root_id, root in roots():
        if not isinstance(root, Path):
            raise ValueError("knowledge root must be a pathlib.Path")
        if not re.fullmatch(r"(?:builtin|notes|configured-[1-9][0-9]*)", root_id):
            raise ValueError("knowledge root id is invalid")
        try:
            registry = _load_registry(root)
        except RuntimeError:
            # A broken governance layer fails closed: no search over that root.
            reasons.add("registry_invalid")
            continue
        if not root.is_dir():
            reasons.add("read_error")
            continue
        try:
            root_resolved = root.resolve(strict=True)
        except OSError:
            reasons.add("read_error")
            continue
        for path in _walk_files(root, entry_budget, reasons):
            try:
                is_file = path.is_file()
                is_symlink = path.is_symlink()
            except OSError:
                reasons.add("read_error")
                continue
            if not is_file or is_symlink or path.suffix.casefold() not in _TEXT_SUFFIXES:
                continue
            if scanned_files >= _MAX_KNOWLEDGE_FILES:
                reasons.add("file_budget")
                break
            if scanned_bytes >= _MAX_KNOWLEDGE_TOTAL_BYTES:
                reasons.add("byte_budget")
                break
            try:
                resolved = path.resolve(strict=True)
                if not resolved.is_relative_to(root_resolved):
                    continue
                initial = resolved.stat()
                size = initial.st_size
                if size > _MAX_KNOWLEDGE_FILE_BYTES:
                    reasons.add("oversized_file")
                    continue
                if scanned_bytes + size > _MAX_KNOWLEDGE_TOTAL_BYTES:
                    reasons.add("byte_budget")
                    continue
                scanned_files += 1
                with resolved.open("rb") as stream:
                    read_limit = min(_MAX_KNOWLEDGE_FILE_BYTES, _MAX_KNOWLEDGE_TOTAL_BYTES - scanned_bytes)
                    raw = stream.read(read_limit + 1)
                scanned_bytes += len(raw)
                final = resolved.stat()
                if (len(raw) != size or len(raw) > _MAX_KNOWLEDGE_FILE_BYTES
                    or (initial.st_ino, initial.st_mtime_ns, initial.st_ctime_ns, initial.st_size)
                    != (final.st_ino, final.st_mtime_ns, final.st_ctime_ns, final.st_size)):
                    reasons.add("changed_file")
                    continue
                text = raw.decode("utf-8")
                relative = resolved.relative_to(root_resolved)
            except (OSError, UnicodeError, ValueError):
                reasons.add("read_error")
                continue
            # Admission gate: with a valid registry present, only approved,
            # non-revoked, unexpired, digest-current and audience-permitted
            # entries may be searched at all; everything else is skipped
            # silently (the reason vocabulary stays inventory-level metadata).
            if registry is not None:
                entry = registry.get(relative.as_posix())
                if entry is None:
                    reasons.add("unregistered")
                    continue
                if entry["revoked"]:
                    reasons.add("revoked")
                    continue
                if not entry["approved"]:
                    reasons.add("unapproved")
                    continue
                if entry["expires_epoch"] is not None and int(time.time()) > entry["expires_epoch"]:
                    reasons.add("expired")
                    continue
                if hashlib.sha256(raw).hexdigest() != entry["sha256"]:
                    # Source updated without re-approval: the index must not
                    # serve stale content under a registered identity.
                    reasons.add("stale_hash")
                    continue
                if entry["audience"] != "public" and audience == "public":
                    reasons.add("audience_filtered")
                    continue
            source = f"{root_id}:{relative.as_posix()}"
            if len(source) > 512 or len(path.stem) > 256:
                reasons.add("metadata_limit")
                continue
            # Scan admitted source content too; forbidden text outside the selected
            # passage must not turn a polluted document into an apparently safe hit.
            from company_agent.sanitize import validate_output_content

            validate_output_content(text, reference=True)
            lowered = text.casefold()
            if not any(term in lowered for term in terms):
                continue
            # Fixed overlapping passages prevent long-document term frequency from
            # overwhelming a concise source. Keep one best passage per document.
            passages = [text[start:start + 600] for start in range(0, len(text), 480)]
            scored = [(sum(min(part.casefold().count(term), 3) for term in terms), index, part)
                      for index, part in enumerate(passages)]
            score, _, passage = max(scored, key=lambda item: (item[0], -item[1]))
            snippet = " ".join(passage.split())[:600]
            hits.append(
                {
                    "source": source,
                    "title": path.stem,
                    "version": "sha256:" + hashlib.sha256(raw).hexdigest(),
                    "snippet": snippet,
                    "score": str(score),
                }
            )
            hits.sort(key=lambda row: (-int(row["score"]), row["source"]))
            del hits[8:]
    from company_agent.sanitize import validate_output_content

    for row in hits:
        validate_output_content(row, reference=True)
    return {
        "trust": "untrusted_reference_data",
        "query": query, "hits": hits,
        "scan": {"complete": not reasons, "reasons": sorted(reasons),
                 "entries": _MAX_KNOWLEDGE_ENTRIES - entry_budget[0],
                 "files": scanned_files, "bytes": scanned_bytes},
    }
