"""Company.latex workspace adapter (phase 1) executed inside the Agent kernel.

Every operation stays inside the bounded DSH workspace directory that the
plugin forwards through ``COMPANY_AGENT_TOOL_WORKSPACE``. File editing is
exact-anchor based with content-version guards, compilation drives the local
TeX engines directly without shell escape, snapshots (checkpoint/diff/revert)
stay inside the project directory, and ``pull``/``push`` delegate to the
bounded ``latex_sync`` GitLab adapter. Diagnostics are bounded and failures
are honest. This module never imports the contract kernel and creates no
model or tool loops.
"""
from __future__ import annotations

import difflib
import hashlib
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path, PurePosixPath

MAX_FILES = 96
MAX_SCAN_FILES = 500
MAX_CHECKPOINTS = 12
MAX_SNAPSHOT_FILES = 300
MAX_SNAPSHOT_TOTAL = 50_000_000
SNAPSHOT_DIRNAME = ".latex-snapshots"
MAX_FILE_BYTES = 2_000_000
MAX_WINDOW_LINES = 120
DEFAULT_WINDOW_LINES = 40
LINE_CHARS = 240
MAX_EDIT_TARGETS = 8
MAX_EDITS_PER_FILE = 16
FILE_BYTES_MAX = 50_000_000
ENGINE_TIMEOUT_MAX = 90
MAX_PASSES = 5

PROJECT_PATTERN = re.compile(r"^[A-Za-z0-9_](?:[A-Za-z0-9_.-]*[A-Za-z0-9_-])?$")
PATH_PATTERN = re.compile(
    r"^(?!.*(?:^|/)\.\.(?:/|$))"
    r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*\.(?:tex|bib|cls|sty|bst)$"
)
VERSION_PREFIX = "sha256:"
DOCUMENTCLASS_PATTERN = re.compile(r"^[^%\n]*\\documentclass\b")
BEGIN_PATTERN = re.compile(r"\\begin\{([A-Za-z*]+)\}")
END_PATTERN = re.compile(r"\\end\{([A-Za-z*]+)\}")
LABEL_PATTERN = re.compile(r"\\label\{([^{}]{1,120})\}")
REF_PATTERN = re.compile(r"\\(?:auto|page|eq|C|c)?ref\{([^{}]{1,120})\}")
CITE_PATTERN = re.compile(r"\\(?:no)?cite[tp]?(?:\[[^\]]*\])?\{([^{}]{1,240})\}")
INPUT_PATTERN = re.compile(r"\\(?:input|include)\{([^{}]{1,120})\}")
BIB_KEY_PATTERN = re.compile(r"@\w+\s*\{\s*([^,\s{}]{1,120})\s*,")
ENGINE_ERROR_LINE = re.compile(r"^(.*\.(?:tex|cls|sty|bib)):(\d+):(.{1,160})$")
ENGINE_BANG_LINE = re.compile(r"^! .{1,160}")
OUTPUT_WRITTEN = re.compile(r"Output written on .*?\.pdf \((\d+) pages?(?:, \d+ bytes)?\)\.")
RERUN_HINT = re.compile(r"Rerun to get|Label\(s\) may have changed")
UNDEFINED_REFERENCES = re.compile(r"There were undefined (?:references|citations)")
BIBDATA_HINT = re.compile(r"\\bibdata\{")

SOURCE_SUFFIXES = (".tex", ".bib", ".cls", ".sty", ".bst")
GRAPHIC_SUFFIXES = (".pdf", ".png", ".jpg", ".jpeg", ".eps")
CLASS_SUFFIXES = (".cls", ".sty")
ENGINES = ("pdflatex", "xelatex", "lualatex")


class WorkspaceError(ValueError):
    """Bounded workspace failure; messages stay free of absolute paths."""


def _workspace_root() -> Path:
    configured = re.sub(r"[\x00-\x1f]", "", os.environ.get("COMPANY_AGENT_TOOL_WORKSPACE", "")).strip()
    if not configured or not os.path.isabs(configured):
        raise WorkspaceError("latex workspace is not configured")
    root = Path(configured)
    if root.is_symlink() or not root.is_dir():
        raise WorkspaceError("latex workspace is not available")
    return root.resolve()


def _resolve_project(project: object) -> Path:
    if not isinstance(project, str) or not PROJECT_PATTERN.fullmatch(project):
        raise WorkspaceError("project has an invalid name")
    root = _workspace_root()
    candidate = root / project
    if candidate.is_symlink() or not candidate.is_dir():
        raise WorkspaceError("project is not available in the workspace")
    resolved = candidate.resolve(strict=True)
    if resolved.parent != root or resolved.name != project:
        raise WorkspaceError("project escapes the workspace")
    return resolved


def _source_target(project_dir: Path, path: object) -> Path:
    if not isinstance(path, str) or not PATH_PATTERN.fullmatch(path):
        raise WorkspaceError("file path has an invalid format")
    if any(part in {"", ".", ".."} for part in PurePosixPath(path).parts):
        raise WorkspaceError("file path escapes the project")
    target = project_dir / path
    if target.is_symlink() or not target.is_file():
        raise WorkspaceError("file is not available in the project")
    resolved = target.resolve(strict=True)
    if resolved.is_symlink() or not resolved.is_relative_to(project_dir.resolve()):
        raise WorkspaceError("file escapes the project")
    if resolved.suffix.casefold() not in SOURCE_SUFFIXES:
        raise WorkspaceError("file suffix is not a managed LaTeX source")
    if resolved.stat().st_size > MAX_FILE_BYTES:
        raise WorkspaceError("file exceeds the bounded workspace size")
    return target


def _file_version(target: Path) -> str:
    digest = hashlib.sha256()
    size = 0
    with target.open("rb") as stream:
        while chunk := stream.read(1_000_000):
            size += len(chunk)
            if size > MAX_FILE_BYTES:
                raise WorkspaceError("file exceeds the bounded workspace size")
            digest.update(chunk)
    return VERSION_PREFIX + digest.hexdigest()


def _read_text(target: Path) -> str:
    try:
        return target.read_text(encoding="utf-8")
    except UnicodeError as exc:
        raise WorkspaceError("file is not UTF-8 text") from exc
    except OSError as exc:
        raise WorkspaceError("file could not be read") from exc


def _atomic_write(target: Path, content: str) -> None:
    descriptor, temp_name = tempfile.mkstemp(dir=target.parent, prefix=".company-edit-", suffix=".tmp")
    temp_path = Path(temp_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content.encode("utf-8"))
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temp_path, target.stat().st_mode)
        try:
            os.replace(temp_path, target)
        except OSError:
            # Windows write filters may reject rename/move operations that lay
            # down a text-like final file; clear the target and fall back to a
            # direct write of the fully written temp payload.
            if target.exists():
                target.unlink()
            target.write_bytes(temp_path.read_bytes())
            temp_path.unlink(missing_ok=True)
    except OSError as exc:
        temp_path.unlink(missing_ok=True)
        raise WorkspaceError("file could not be written") from exc


def _apply_anchor(text: str, quote: str, replacement: str, occurrence: object) -> str:
    count = text.count(quote)
    if count == 0:
        raise WorkspaceError("edit anchor is stale: quote not found in current content")
    if count > 1 and occurrence is None:
        raise WorkspaceError(f"edit anchor is ambiguous: {count} matches; pass occurrence")
    matching = occurrence if occurrence is not None else 1
    if not isinstance(matching, int) or isinstance(matching, bool) or not 1 <= matching <= count:
        raise WorkspaceError(f"edit occurrence must be an integer in [1, {count}]")
    index = -1
    for _ in range(matching):
        index = text.index(quote, index + 1)
    return text[:index] + replacement + text[index + len(quote):]


def _project_files(project_dir: Path) -> list[tuple[str, Path]]:
    rows: list[tuple[str, Path]] = []
    for path in sorted(project_dir.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(project_dir).as_posix()
        if relative.startswith(".latex-build/") or "/.latex-build/" in relative:
            continue
        if relative.startswith(SNAPSHOT_DIRNAME + "/") or "/" + SNAPSHOT_DIRNAME + "/" in relative:
            continue
        if len(rows) >= MAX_SCAN_FILES:
            break
        rows.append((relative, path))
    return rows


def structure(args: dict) -> dict:
    project_dir = _resolve_project(args.get("project"))
    complete = True
    rows = []
    candidate_tex: list[tuple[int, str]] = []
    for relative, path in _project_files(project_dir):
        if len(rows) >= MAX_FILES:
            complete = False
            break
        suffix = path.suffix.casefold()
        kind = "other"
        if suffix in CLASS_SUFFIXES:
            kind = "class"
        elif suffix == ".tex":
            kind = "tex"
        elif suffix == ".bib":
            kind = "bib"
        elif suffix in GRAPHIC_SUFFIXES:
            kind = "graphics"
        rows.append({
            "path": relative, "bytes": min(path.stat().st_size, FILE_BYTES_MAX), "kind": kind,
        })
        if kind == "tex":
            try:
                head = path.read_text(encoding="utf-8", errors="ignore")[:8000]
            except OSError:
                head = ""
            if DOCUMENTCLASS_PATTERN.search(head):
                candidate_tex.append((relative.count("/"), relative))
    main_file = ""
    if candidate_tex:
        candidate_tex.sort()
        preferred = [name for _, name in candidate_tex if Path(name).name == "main.tex"]
        main_file = (preferred or [candidate_tex[0][1]])[0]
    return {
        "project": args.get("project"),
        "main_file": main_file,
        "files": rows,
        "complete": complete,
    }


def read_window(args: dict) -> dict:
    project_dir = _resolve_project(args.get("project"))
    target = _source_target(project_dir, args.get("path"))
    text = _read_text(target)
    lines = text.splitlines()
    total = max(len(lines), 1)
    start_line = args.get("start_line")
    line_count = args.get("line_count")
    if start_line is None:
        actual_start = 1
    elif isinstance(start_line, int) and not isinstance(start_line, bool) and 1 <= start_line <= total:
        actual_start = start_line
    else:
        raise WorkspaceError("start_line is out of range")
    if line_count is None:
        take = DEFAULT_WINDOW_LINES
    elif (isinstance(line_count, int) and not isinstance(line_count, bool)
          and 1 <= line_count <= MAX_WINDOW_LINES):
        take = line_count
    else:
        raise WorkspaceError("line_count is out of range")
    window = lines[actual_start - 1:actual_start - 1 + take]
    rows = [
        {"line": actual_start + offset, "text": row_text[:LINE_CHARS]}
        for offset, row_text in enumerate(window, start=0)
    ]
    beyond_window = actual_start - 1 + take < len(lines)
    cut = any(len(row_text) > LINE_CHARS for row_text in window)
    return {
        "project": args.get("project"),
        "path": args.get("path"),
        "version": _file_version(target),
        "start_line": actual_start,
        "lines": rows,
        "truncated": bool(beyond_window or cut),
    }


def _single_edit_plan(args: dict, project_dir: Path) -> tuple[str, Path, str, str, int]:
    path = args.get("path")
    base_version = args.get("base_version")
    edits = args.get("edits")
    if not isinstance(base_version, str) or not base_version.startswith(VERSION_PREFIX):
        raise WorkspaceError("base_version is missing or malformed")
    target = _source_target(project_dir, path)
    version = _file_version(target)
    if base_version != version:
        raise WorkspaceError(f"file version conflict: current content version is {version}")
    text = _read_text(target)
    if not isinstance(edits, list) or not edits:
        raise WorkspaceError("edits must be a non-empty list")
    if len(edits) > MAX_EDITS_PER_FILE:
        raise WorkspaceError("too many edits for one file")
    planned = text
    count = 0
    for edit in edits:
        if not isinstance(edit, dict):
            raise WorkspaceError("edit rows must be objects")
        quote = edit.get("quote")
        replacement = edit.get("replacement")
        occurrence = edit.get("occurrence")
        if not isinstance(quote, str) or len(quote) < 8 or len(quote.encode("utf-8")) > 2000:
            raise WorkspaceError("edit quote is missing or too large")
        if not isinstance(replacement, str) or len(replacement.encode("utf-8")) > 24000:
            raise WorkspaceError("edit replacement is missing or too large")
        planned = _apply_anchor(planned, quote, replacement, occurrence)
        count += 1
    if planned == text:
        raise WorkspaceError("edit produced no change")
    return str(path), target, version, planned, count


def edit(args: dict) -> dict:
    project_dir = _resolve_project(args.get("project"))
    path, target, base_version, planned, count = _single_edit_plan(args, project_dir)
    _atomic_write(target, planned)
    return {
        "project": args.get("project"),
        "path": path,
        "base_version": base_version,
        "version": _file_version(target),
        "applied": count,
        "bytes": target.stat().st_size,
    }


def batch_edit(args: dict) -> dict:
    project_dir = _resolve_project(args.get("project"))
    files = args.get("files") if isinstance(args.get("files"), list) else []
    if not files or len(files) > MAX_EDIT_TARGETS:
        raise WorkspaceError("batch must contain between 1 and 8 files")
    rows: list[tuple[str, Path, str, str, int]] = []
    seen: set[str] = set()
    for row in files:
        if not isinstance(row, dict):
            raise WorkspaceError("batch rows must be objects")
        path = str(row.get("path") or "")
        if path in seen:
            raise WorkspaceError("batch contains duplicate file targets")
        seen.add(path)
        rows.append(_single_edit_plan(row, project_dir))
    results = []
    for path, target, base_version, planned, count in rows:
        _atomic_write(target, planned)
        results.append({
            "path": path,
            "base_version": base_version,
            "version": _file_version(target),
            "applied": count,
            "bytes": target.stat().st_size,
        })
    result: dict = {
        "project": args.get("project"),
        "applied_files": len(results),
        "results": results,
    }
    if isinstance(args.get("message"), str) and args["message"].strip():
        result["message"] = args["message"].strip()[:200]
    return result


def _env_findings(lines: list[str], file: str, findings: list, stop: int) -> None:
    stack: list[tuple[str, int]] = []
    for number, line in enumerate(lines, start=1):
        if len(findings) >= stop:
            return
        for match in BEGIN_PATTERN.finditer(line):
            stack.append((match.group(1), number))
        for match in END_PATTERN.finditer(line):
            name = match.group(1)
            if stack and stack[-1][0] == name:
                stack.pop()
            else:
                findings.append({
                    "file": file,
                    "line": number,
                    "code": "env_pair",
                    "message": f"\\end{{{name}}} has no matching \\begin"[:200],
                })
    for name, number in stack:
        if len(findings) >= stop:
            return
        findings.append({
            "file": file,
            "line": number,
            "code": "env_pair",
            "message": f"\\begin{{{name}}} was never closed"[:200],
        })


def check(args: dict) -> dict:
    project_dir = _resolve_project(args.get("project"))
    sources = [
        (relative, path) for relative, path in _project_files(project_dir)
        if path.suffix.casefold() in {".tex", ".bib"}
    ]
    content: dict[str, str] = {}
    for relative, path in sources:
        try:
            content[relative] = path.read_text(encoding="utf-8", errors="ignore")[:MAX_FILE_BYTES]
        except OSError:
            content[relative] = ""
    labels: dict[str, str] = {}
    bib_keys: set[str] = set()
    for relative, text in content.items():
        if relative.endswith(".bib"):
            bib_keys.update(match.group(1) for match in BIB_KEY_PATTERN.finditer(text))
            continue
        for match in LABEL_PATTERN.finditer(text):
            labels.setdefault(match.group(1), relative)
    findings: list[dict] = []
    stop = 32
    for relative, text in content.items():
        if not relative.endswith(".tex") or len(findings) >= stop:
            continue
        _env_findings(text.splitlines(), relative, findings, stop)
        for pattern, code, slot in (
            (REF_PATTERN, "ref_target", "has no \\label in the project"),
            (CITE_PATTERN, "cite_key", "is missing from project bibliographies"),
            (INPUT_PATTERN, "input_missing", "does not resolve inside the project"),
        ):
            if len(findings) >= stop:
                break
            for match in pattern.finditer(text):
                if len(findings) >= stop:
                    break
                spoken = text.count("\n", 0, match.start()) + 1
                if code == "cite_key":
                    for key in match.group(1).split(","):
                        key = key.strip()[:120]
                        if key and key not in bib_keys:
                            findings.append({
                                "file": relative, "line": spoken, "code": code,
                                "message": f"citation '{key}' {slot}"[:200],
                            })
                elif code == "input_missing":
                    wanted = match.group(1).strip()
                    candidate = wanted if wanted.endswith(".tex") else wanted + ".tex"
                    if (project_dir / candidate).is_file():
                        continue
                    findings.append({
                        "file": relative, "line": spoken, "code": code,
                        "message": f"input '{wanted}' {slot}"[:200],
                    })
                else:
                    target = match.group(1)
                    if target not in labels:
                        findings.append({
                            "file": relative, "line": spoken, "code": code,
                            "message": f"reference '{target}' {slot}"[:200],
                        })
    return {
        "project": args.get("project"),
        "findings": findings[:32],
        "files_scanned": len(content),
        "complete": len(findings) < stop,
    }


def _engine_log_errors(text: str) -> list:
    rows = []
    consumed = 0
    for line in text.splitlines():
        if consumed >= 8:
            break
        numbered = ENGINE_ERROR_LINE.match(line)
        bang = ENGINE_BANG_LINE.match(line)
        if numbered:
            source, line_no, body = numbered.groups()
            rows.append({
                "file": PurePosixPath(source).name,
                "line": min(int(line_no), 1_000_000),
                "text": body.strip()[:200],
            })
            consumed += 1
        elif bang and not rows:
            rows.append({"file": "", "line": 0, "text": line.strip()[:200]})
            consumed += 1
    return rows


def _log_text(build_dir: Path, log_rel: str) -> str:
    try:
        return (build_dir / log_rel).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _autodetect_main(project_dir: Path) -> str:
    candidates: list[tuple[int, str]] = []
    for relative, path in _project_files(project_dir):
        if not relative.endswith(".tex"):
            continue
        try:
            head = path.read_text(encoding="utf-8", errors="ignore")[:8000]
        except OSError:
            continue
        if DOCUMENTCLASS_PATTERN.search(head):
            candidates.append((relative.count("/"), relative))
    if not candidates:
        raise WorkspaceError("no main .tex with \\documentclass was found in the project")
    candidates.sort()
    preferred = [name for _, name in candidates if Path(name).name == "main.tex"]
    return (preferred or [candidates[0][1]])[0]


def _stage_sources(project_dir: Path, build_dir: Path) -> None:
    (project_dir / ".latex-build").mkdir(parents=True, exist_ok=True)
    build_dir.mkdir(parents=True)
    for relative, source in _project_files(project_dir):
        destination = build_dir / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def compile(args: dict) -> dict:
    project_dir = _resolve_project(args.get("project"))
    engine = args.get("engine") if isinstance(args.get("engine"), str) else "pdflatex"
    if engine not in ENGINES:
        raise WorkspaceError("engine is not supported")
    timeout = args.get("timeout_seconds")
    timeout = timeout if isinstance(timeout, int) and not isinstance(timeout, bool) else 90
    if not 5 <= timeout <= ENGINE_TIMEOUT_MAX:
        raise WorkspaceError("timeout_seconds is out of range")
    main = args.get("main") or _autodetect_main(project_dir)
    _source_target(project_dir, main)
    main_path = PurePosixPath(str(main))
    main_rel = main_path.as_posix()
    main_stem_rel = main_path.with_suffix("").as_posix()
    main_log_rel = main_path.with_suffix(".log").as_posix()
    main_pdf_rel = main_path.with_suffix(".pdf").as_posix()
    build_sub = main_stem_rel.replace("/", "_")

    build_rel = f".latex-build/{engine}/{build_sub}"
    build_dir = project_dir / ".latex-build" / engine / build_sub
    if build_dir.exists():
        shutil.rmtree(build_dir)
    _stage_sources(project_dir, build_dir)

    failure: str | None = None
    passes = 0
    text = ""
    started = time.monotonic()

    def run_engine() -> str:
        nonlocal passes, failure
        passes += 1
        try:
            result = subprocess.run(
                [engine, "-interaction=nonstopmode", "-file-line-error", "-no-shell-escape", main_rel],
                cwd=str(build_dir), capture_output=True, text=True, timeout=timeout, check=False,
            )
        except subprocess.TimeoutExpired:
            failure = "compile timeout"
            return _log_text(build_dir, main_log_rel)
        except OSError:
            failure = "engine launch failed"
            return _log_text(build_dir, main_log_rel)
        if result.returncode != 0:
            failure = f"engine exit {result.returncode}"
        return _log_text(build_dir, main_log_rel)

    text = run_engine()
    if failure is None:
        aux_rel = main_path.with_suffix(".aux").as_posix()
        aux = build_dir / aux_rel
        if aux.is_file():
            aux_text = aux.read_text(encoding="utf-8", errors="ignore")[:MAX_FILE_BYTES]
            if BIBDATA_HINT.search(aux_text):
                try:
                    backend = subprocess.run(
                        ["bibtex", main_stem_rel], cwd=str(build_dir), capture_output=True, text=True,
                        timeout=min(timeout, 45), check=False,
                    )
                except (subprocess.TimeoutExpired, OSError):
                    failure = "bibtex stage failed"
                else:
                    if backend.returncode >= 2:
                        failure = f"bibtex exit {backend.returncode}"
                    text = run_engine()
    while failure is None and passes < MAX_PASSES and RERUN_HINT.search(text):
        text = run_engine()
    written = OUTPUT_WRITTEN.search(text)
    if failure is None and written is None:
        failure = "no PDF output"
    elif failure is None and UNDEFINED_REFERENCES.search(text):
        failure = "undefined references remain"
    elif failure is None and RERUN_HINT.search(text):
        failure = "rerun hints remain"
    status = "failure" if failure is not None else "success"
    pages = int(written.group(1)) if written is not None else 0
    warnings = len(re.findall(r"LaTeX Warning", text)) + len(re.findall(r"Missing character", text))
    artifact_rel = f"{build_rel}/{main_pdf_rel}"
    if not (build_dir / main_pdf_rel).is_file():
        artifact_rel = ""
        status = "failure"
    elapsed_ms = int((time.monotonic() - started) * 1000)
    return {
        "project": args.get("project"),
        "main": main,
        "engine": engine,
        "status": status,
        "pages": max(0, min(pages, 100_000)),
        "errors": [] if status == "success" else _engine_log_errors(text)[:8],
        "warnings": min(max(warnings, 0), 10_000),
        "artifact": artifact_rel,
        "duration_ms": min(max(elapsed_ms, 0), 1_000_000),
    }



def _snapshot_root(project_dir: Path) -> Path:
    return project_dir / SNAPSHOT_DIRNAME


def _snapshot_ids(project_dir: Path) -> list[str]:
    root = _snapshot_root(project_dir)
    if not root.is_dir():
        return []
    ids = [path.name for path in root.iterdir() if path.is_dir() and not path.is_symlink()]
    ids.sort()
    if len(ids) > MAX_CHECKPOINTS:
        # Oldest checkpoints rotate out of the bounded store.
        for stale in ids[: len(ids) - MAX_CHECKPOINTS]:
            shutil.rmtree(root / stale, ignore_errors=True)
        ids = ids[-MAX_CHECKPOINTS:]
    return ids


def _snapshot_dir(project_dir: Path, checkpoint: str) -> Path:
    return _snapshot_root(project_dir) / checkpoint


def _copy_managed_sources(project_dir: Path, destination: Path) -> tuple[int, int]:
    destination.mkdir(parents=True, exist_ok=True)
    copied = 0
    total = 0
    for relative, source in _project_files(project_dir):
        if source.suffix.casefold() not in SOURCE_SUFFIXES:
            continue
        if copied >= MAX_SNAPSHOT_FILES or total + source.stat().st_size > MAX_SNAPSHOT_TOTAL:
            raise WorkspaceError("snapshot exceeds the bounded workspace size")
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied += 1
        total += source.stat().st_size
    return copied, total


def checkpoint(args: dict) -> dict:
    project_dir = _resolve_project(args.get("project"))
    note = args.get("note")
    timestamp = time.strftime("%Y%m%d%H%M%S", time.gmtime())
    digest = hashlib.sha256(str(time.time_ns()).encode("utf-8")).hexdigest()[:6]
    checkpoint_id = f"chk-{timestamp}-{digest}"
    copied, total = _copy_managed_sources(project_dir, _snapshot_dir(project_dir, checkpoint_id))
    if copied == 0:
        shutil.rmtree(_snapshot_dir(project_dir, checkpoint_id), ignore_errors=True)
        raise WorkspaceError("no managed latex sources to snapshot")
    if isinstance(note, str) and note.strip():
        (_snapshot_dir(project_dir, checkpoint_id) / "note.txt").write_text(
            note.strip()[:200] + "\n", encoding="utf-8"
        )
    _snapshot_ids(project_dir)  # rotate beyond the bounded checkpoint budget
    return {"project": args.get("project"), "checkpoint": checkpoint_id, "files": copied, "bytes": total}


def _lines_of(path: Path) -> list[str]:
    try:
        return path.read_text(encoding="utf-8").splitlines()
    except UnicodeError:
        return path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError as exc:
        raise WorkspaceError("file could not be read") from exc


def diff(args: dict) -> dict:
    project_dir = _resolve_project(args.get("project"))
    ids = _snapshot_ids(project_dir)
    if not ids:
        raise WorkspaceError("no checkpoint to compare against")
    latest = ids[-1]
    base = _snapshot_dir(project_dir, latest)
    wanted = args.get("path")
    wanted_path = None
    wanted_suffixes = None
    if wanted is not None:
        wanted_path = _source_target(project_dir, wanted)
        wanted_relative = wanted_path.relative_to(project_dir).as_posix()
        wanted_suffixes = {wanted_relative}
    rows = []
    added_total = 0
    removed_total = 0
    complete = True
    for relative, current in _project_files(project_dir):
        if current.suffix.casefold() not in SOURCE_SUFFIXES:
            continue
        if wanted_suffixes is not None and relative not in wanted_suffixes:
            continue
        old = base / relative
        if len(rows) >= MAX_FILES:
            complete = False
            break
        old_lines = _lines_of(old) if old.is_file() else []
        new_lines = _lines_of(current)
        added = removed = 0
        preview = ""
        if old_lines != new_lines:
            matcher = difflib.SequenceMatcher(None, old_lines, new_lines, autojunk=False)
            for opcode in matcher.get_opcodes():
                if opcode[0] == "equal":
                    continue
                added += opcode[4] - opcode[3]
                removed += opcode[2] - opcode[1]
            for opcode in matcher.get_opcodes():
                if opcode[0] != "equal" and not preview:
                    preview = "\n".join(new_lines[opcode[3]:opcode[4]])[:200]
                    break
        added_total += added
        removed_total += removed
        if added or removed:
            rows.append({"path": relative, "added": added, "removed": removed, "preview": preview})
    return {
        "project": args.get("project"),
        "checkpoint": latest,
        "added": added_total,
        "removed": removed_total,
        "files": rows,
        "complete": complete,
    }


def revert(args: dict) -> dict:
    project_dir = _resolve_project(args.get("project"))
    target = args.get("target")
    ids = _snapshot_ids(project_dir)
    if target not in ids:
        raise WorkspaceError("checkpoint target is not available")
    restored = 0
    changed = 0
    base = _snapshot_dir(project_dir, str(target))
    for source in sorted(base.rglob("*")):
        if not source.is_file() or source.is_symlink():
            continue
        if source.name == "note.txt":
            continue
        relative = source.relative_to(base).as_posix()
        destination = project_dir / PurePosixPath(relative)
        if destination.is_file() and destination.stat().st_size == source.stat().st_size \
                and destination.read_bytes() == source.read_bytes():
            restored += 1
            continue
        if source.suffix.casefold() not in SOURCE_SUFFIXES:
            continue
        _atomic_write(destination, source.read_text(encoding="utf-8"))
        restored += 1
        changed += 1
    if restored == 0:
        raise WorkspaceError("checkpoint has no restorable managed files")
    return {
        "project": args.get("project"),
        "checkpoint": str(target),
        "restored": min(restored, 960),
        "changed": min(changed, 960),
    }


def pull(args: dict) -> dict:
    from company_agent import latex_sync

    project_dir = _resolve_project(args.get("project"))
    return latex_sync.pull_into(project_dir, args.get("repo"))


def push(args: dict) -> dict:
    from company_agent import latex_sync

    project_dir = _resolve_project(args.get("project"))
    return latex_sync.push_from(project_dir, _managed_commit_files(project_dir), args)


def overleaf_pull(args: dict) -> dict:
    from company_agent import overleaf_sync

    project_dir = _resolve_project(args.get("project"))
    return overleaf_sync.pull_into(project_dir, args, _overleaf_pull_backup(project_dir))


def _overleaf_pull_backup(project_dir: Path):
    """Return a callback that snapshots exactly the pre-pull local content.

    The Overleaf adapter determines which existing files an overwrite pull
    would replace; this callback stores those bytes inside the standard
    snapshot store so a checkpoint-style backup exists before any local edit
    is replaced."""

    def backup(diverged: list[tuple[str, bytes]]) -> str:
        timestamp = time.strftime("%Y%m%d%H%M%S", time.gmtime())
        digest = hashlib.sha256(str(time.time_ns()).encode("utf-8")).hexdigest()[:6]
        checkpoint_id = f"chk-{timestamp}-{digest}"
        destination = _snapshot_dir(project_dir, checkpoint_id)
        try:
            copied = 0
            total = 0
            for relative, payload in diverged:
                if not isinstance(relative, str) or any(part in {"", ".", ".."} for part in relative.split("/")):
                    raise WorkspaceError("snapshot path is invalid")
                if copied >= MAX_SNAPSHOT_FILES or total + len(payload) > MAX_SNAPSHOT_TOTAL:
                    raise WorkspaceError("snapshot exceeds the bounded workspace size")
                target = destination / PurePosixPath(relative)
                if target.resolve().is_relative_to(destination.resolve()):
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(payload)
                    copied += 1
                    total += len(payload)
            if copied == 0:
                raise WorkspaceError("no managed latex sources to snapshot")
            note_file = destination / "note.txt"
            note_file.write_text("pre-overleaf-pull backup of locally modified files\n", encoding="utf-8")
            _snapshot_ids(project_dir)  # rotate beyond the bounded checkpoint budget
        except WorkspaceError:
            shutil.rmtree(destination, ignore_errors=True)
            raise
        except OSError:
            shutil.rmtree(destination, ignore_errors=True)
            raise WorkspaceError("snapshot could not be written") from None
        return checkpoint_id

    return backup


def overleaf_push(args: dict) -> dict:
    from company_agent import overleaf_sync

    project_dir = _resolve_project(args.get("project"))
    rows = _managed_commit_files(project_dir)
    return overleaf_sync.push_from(project_dir, rows, args)


def overleaf_status(args: dict) -> dict:
    from company_agent import overleaf_sync

    project_dir = _resolve_project(args.get("project"))
    return overleaf_sync.status_of(project_dir, args)


_ARTIFACT_PATTERN = re.compile(
    r"^(?!.*(?:^|/)\.\.(?:/|$))\.latex-build/[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*\.pdf$"
)
_MAX_ISSUE_IID = 9_999_999


def issue_pdf_note(args: dict) -> dict:
    """Attach one compiled PDF build artifact to a plan-hub GitLab issue.

    Transportation is provided by the bounded plan-hub client (shared
    fail-closed mapping); the workspace only verifies the artifact lives
    inside ``.latex-build`` and stays inside the bounded upload size. Nothing
    on the disk or the remote is ever deleted; the human approval is routed
    through the standard latex write gate before this function runs."""

    from company_agent import plan_hub

    project_dir = _resolve_project(args.get("project"))
    repo = plan_hub._project(args.get("repo"))
    iid = args.get("issue_iid")
    if not isinstance(iid, int) or isinstance(iid, bool) or not 1 <= iid <= _MAX_ISSUE_IID:
        raise WorkspaceError("issue iid is invalid")
    artifact = args.get("artifact")
    if not isinstance(artifact, str) or not _ARTIFACT_PATTERN.fullmatch(artifact):
        raise WorkspaceError("artifact path is invalid")
    target = project_dir.joinpath(*artifact.split("/"))
    if target.is_symlink() or not target.is_file():
        raise WorkspaceError("artifact is not available in the project")
    resolved = target.resolve(strict=True)
    if resolved.is_symlink() or not resolved.is_relative_to(project_dir.resolve()):
        raise WorkspaceError("artifact escapes the project")
    payload = target.read_bytes()
    if len(payload) > plan_hub.MAX_UPLOAD_BYTES:
        raise WorkspaceError("artifact exceeds the bounded upload size")
    note = args.get("note")
    if not isinstance(note, str) or not note.strip() or len(note.encode("utf-8")) > 400:
        raise WorkspaceError("note text is invalid")
    link = plan_hub.upload_project_file(repo, resolved.name, payload)
    note_payload = plan_hub._request(
        "POST",
        f"/api/v4/projects/{plan_hub._api_path(repo)}/issues/{iid}/notes",
        body={"body": note.strip() + "\n\nPDF attachment: " + link},
    )
    if not isinstance(note_payload, dict):
        raise WorkspaceError("plan hub returned an unexpected note shape")
    note_id = note_payload.get("id")
    if not isinstance(note_id, int) or note_id < 1:
        raise WorkspaceError("plan hub returned an invalid note id")
    return {
        "project": args.get("project"),
        "repo": repo,
        "issue_iid": iid,
        "note_id": note_id,
        "attachment": link,
    }


def _managed_commit_files(project_dir: Path) -> list[tuple[str, Path]]:
    rows = [(relative, path) for relative, path in _project_files(project_dir)
            if path.suffix.casefold() in SOURCE_SUFFIXES or path.suffix.casefold() in GRAPHIC_SUFFIXES]
    return rows

