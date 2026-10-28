#!/usr/bin/env python3
"""Run the golden LaTeX toolchain matrix and record compile fidelity evidence.

Phase-0 gate of the company LaTeX workspace plan: prove the local TeX toolchain
compiles the golden project set cleanly and deterministically, and honestly
report every dimension it cannot reproduce, before any ``company.latex``
contract is drafted. Engines are driven directly (no latexmk dependency),
shell escape stays disabled, and this script is never imported at runtime.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GOLDEN_ROOT = ROOT / "tests" / "latex" / "golden"
REFERENCE_ROOT = ROOT / "tests" / "latex" / "references"
REPORT_FORMAT = "company-agent-latex-matrix/1"
TOOLCHAIN_FORMAT = "company-agent-latex-toolchain/1"
DEFAULT_TIMEOUT = 75
MAX_PASSES = 5
TEXT_OVERLAP_THRESHOLD = 0.9
ERROR_LIMIT = 8
ERROR_CHARS = 200

ENGINES = ("pdflatex", "xelatex", "lualatex")
SUPPORT_TOOLS = ("bibtex", "biber", "pdftotext", "latexmk")
BACKEND_TOOLS = {"bibtex": "bibtex", "biber": "biber"}
PROBED_PACKAGES = {
    "fontspec": "fontspec.sty",
    "ctex": "ctexart.cls",
    "biblatex": "biblatex.sty",
    "tikz": "tikz.sty",
    "pgfplots": "pgfplots.sty",
    "hyperref": "hyperref.sty",
    "booktabs": "booktabs.sty",
}
MANIFEST_KEYS = {
    "backend", "compiler", "contains", "description", "id", "main", "pages_min",
    "packages", "purpose",
}
ENGINE_FLAGS = ("-interaction=nonstopmode", "-file-line-error", "-no-shell-escape")
PAGES_PATTERN = re.compile(r"Output written on .*?\.pdf \((\d+) pages?(?:, \d+ bytes)?\)\.")
RERUN_PATTERN = re.compile(r"Rerun to get|Label\(s\) may have changed")
UNDEFINED_PATTERN = re.compile(r"There were undefined (?:references|citations)")
TEX_LIVE_YEAR = re.compile(r"TeX Live (\d{4})")


class MatrixError(RuntimeError):
    """Raised when the matrix cannot be built or executed as specified."""


def _run(command: list[str], cwd: Path | None, timeout: int) -> subprocess.CompletedProcess[str]:
    """Run one bounded command without a shell; problems surface as exceptions."""
    try:
        return subprocess.run(
            command, cwd=None if cwd is None else str(cwd), capture_output=True, text=True,
            timeout=timeout, check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError(command[0]) from exc
    except OSError as exc:
        raise MatrixError(f"tool launch failed: {command[0]}") from exc


def _version_of(tool: str) -> dict:
    option = "-v" if tool == "pdftotext" else "--version"
    try:
        result = _run([tool, option], None, 20)
    except (TimeoutError, MatrixError):
        return {"available": False, "version": "", "texlive_year": None}
    lines = (result.stdout or result.stderr).splitlines()
    first = next((line.strip()[:120] for line in lines
                  if line.strip() and "error" not in line.casefold()), "")
    match = TEX_LIVE_YEAR.search(first)
    return {"available": True, "version": first,
            "texlive_year": int(match.group(1)) if match else None}


def toolchain() -> dict:
    engines = {tool: _version_of(tool) for tool in ENGINES}
    support = {tool: _version_of(tool) for tool in SUPPORT_TOOLS}
    packages = []
    for name, probe in sorted(PROBED_PACKAGES.items()):
        try:
            result = _run(["kpsewhich", probe], None, 20)
        except (TimeoutError, MatrixError):
            result = None
        packages.append(
            {"name": name, "probe": probe, "available": result is not None and result.returncode == 0}
        )
    return {"engines": engines, "support": support, "packages": packages}


def _validate_manifest(data: object, directory: Path) -> None:
    name = directory.name
    if not isinstance(data, dict) or set(data) != MANIFEST_KEYS:
        raise MatrixError(f"{name}: manifest fields must be exactly {sorted(MANIFEST_KEYS)}")
    if data["id"] != name or not re.fullmatch(r"[a-z0-9-]+", str(data["id"])):
        raise MatrixError(f"{name}: manifest id must equal the directory name")
    if data["compiler"] not in ENGINES:
        raise MatrixError(f"{name}: compiler must be one of {ENGINES}")
    if data["backend"] is not None and data["backend"] not in BACKEND_TOOLS:
        raise MatrixError(f"{name}: backend must be null or one of {sorted(BACKEND_TOOLS)}")
    main = Path(str(data["main"]))
    if main.is_absolute() or ".." in main.parts:
        raise MatrixError(f"{name}: main must stay inside the project directory")
    if not (directory / main).is_file():
        raise MatrixError(f"{name}: main file missing")
    if main.suffix != ".tex" or not main.name.isascii():
        raise MatrixError(f"{name}: main must be a plain .tex path")
    if not isinstance(data["packages"], list) or any(row not in PROBED_PACKAGES for row in data["packages"]):
        raise MatrixError(f"{name}: packages must be probed names from {sorted(PROBED_PACKAGES)}")
    contains = data["contains"]
    if (
        not isinstance(contains, list) or not contains
        or any(not isinstance(item, str) or len(item) < 3 for item in contains)
    ):
        raise MatrixError(f"{name}: contains must hold nonempty strings of at least 3 characters")
    if type(data["pages_min"]) is not int or not 0 <= data["pages_min"] <= 500:
        raise MatrixError(f"{name}: pages_min must be an integer in [0, 500]")
    for field in ("purpose", "description"):
        if not isinstance(data[field], str) or len(data[field]) < 8:
            raise MatrixError(f"{name}: {field} must be a descriptive string")


def load_manifests() -> list[tuple[Path, dict]]:
    if not GOLDEN_ROOT.is_dir():
        raise MatrixError("golden root is missing")
    rows: list[tuple[Path, dict]] = []
    seen: set[str] = set()
    for directory in sorted(path for path in GOLDEN_ROOT.iterdir() if path.is_dir()):
        manifest_path = directory / "project.json"
        if not manifest_path.is_file():
            raise MatrixError(f"{directory.name}: missing project.json")
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise MatrixError(f"{directory.name}: unreadable manifest") from exc
        _validate_manifest(data, directory)
        if data["id"] in seen:
            raise MatrixError(f"duplicate golden id {data['id']}")
        seen.add(str(data["id"]))
        rows.append((directory, data))
    if not rows:
        raise MatrixError("golden set is empty")
    return rows


def _missing_requirements(project: dict, tools: dict) -> list[str]:
    missing: list[str] = []
    if not tools["engines"][project["compiler"]]["available"]:
        missing.append(f"engine:{project['compiler']}")
    available = {row["name"]: row["available"] for row in tools["packages"]}
    for name in project["packages"]:
        if not available.get(name, False):
            missing.append(f"package:{name}")
    backend = project["backend"]
    if backend and not tools["support"][BACKEND_TOOLS[str(backend)]]["available"]:
        missing.append(f"tool:{BACKEND_TOOLS[str(backend)]}")
    return sorted(missing)


def _log_errors(text: str) -> list[str]:
    errors: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("!") or "Emergency stop" in stripped or "Fatal error" in stripped:
            errors.append(stripped[:ERROR_CHARS])
            if len(errors) >= ERROR_LIMIT:
                break
    return errors


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text)).casefold()


def _text_tokens(text: str) -> set[str]:
    return set(re.findall(r"\w+", _normalise(text)))


def _extract_text(pdf: Path, output: Path, timeout: int) -> str | None:
    try:
        result = _run(["pdftotext", "-q", pdf.name, str(output.resolve())], pdf.parent, timeout)
    except (TimeoutError, MatrixError):
        return None
    if result.returncode != 0:
        return None
    try:
        return output.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _parity(
    project: dict, pages: int | None, build_text: str | None, scratch: Path, timeout: int,
) -> dict:
    directory = REFERENCE_ROOT / str(project["id"])
    meta_path = directory / "meta.json"
    reference_pdf = directory / "reference.pdf"
    if not (meta_path.is_file() and reference_pdf.is_file()):
        return {"state": "missing", "pages": None, "text": None}
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"state": "invalid", "pages": None, "text": None}
    shape_ok = (
        isinstance(meta, dict)
        and set(meta) == {"compiler", "texlive", "pages"}
        and isinstance(meta["compiler"], str)
        and isinstance(meta["texlive"], str)
        and type(meta["pages"]) is int
    )
    if not shape_ok:
        return {"state": "invalid", "pages": None, "text": None}
    pages_match = bool(pages is not None and pages == meta["pages"])
    overlap: float | None = None
    text_match: bool | None = None
    if build_text is not None:
        reference_text = _extract_text(reference_pdf, scratch / "reference.txt", timeout)
        if reference_text is not None:
            build_tokens = _text_tokens(build_text)
            reference_tokens = _text_tokens(reference_text)
            union = build_tokens | reference_tokens
            overlap = round(len(build_tokens & reference_tokens) / len(union), 4) if union else 1.0
            text_match = overlap >= TEXT_OVERLAP_THRESHOLD
    if meta["compiler"] != project["compiler"]:
        state = "compiler_mismatch"
    elif not pages_match:
        state = "pages_mismatch"
    elif text_match is False:
        state = "text_mismatch"
    elif text_match is None:
        state = "match_text_unchecked"
    else:
        state = "match"
    return {
        "state": state,
        "pages": {"expected": meta["pages"], "actual": pages, "match": pages_match},
        "text": {"overlap": overlap, "match": text_match, "threshold": TEXT_OVERLAP_THRESHOLD},
    }


def _finalise(row: dict, text: str, build_text: str | None, pdf_exists: bool) -> None:
    pages_match = PAGES_PATTERN.search(text)
    row["pages"] = int(pages_match.group(1)) if pages_match else None
    row["warnings"] = len(re.findall(r"LaTeX Warning", text))
    row["warnings"] += len(re.findall(r"Missing character", text))
    errors = _log_errors(text)
    row["errors"] = errors
    problems: list[str] = []
    if failure := row.get("engine_failure"):
        problems.append(str(failure))
    elif not pages_match:
        problems.append("no_pdf_output")
    elif UNDEFINED_PATTERN.search(text):
        problems.append("undefined_references")
    elif RERUN_PATTERN.search(text):
        problems.append("rerun_unresolved")
    elif errors:
        problems.append("compile_errors")
    if not problems and pdf_exists:
        if build_text is None:
            row["text_check"] = "unavailable"
        else:
            missing_content = [
                item for item in row["contains"] if _normalise(item) not in _normalise(build_text)
            ]
            if missing_content:
                row["text_check"] = "failed"
                problems.append("content_mismatch:" + "+".join(missing_content))
            else:
                row["text_check"] = "passed"
    if problems:
        row["status"] = "failure"
        row["reason"] = ";".join(problems)
    else:
        row["status"] = "success"
        row["reason"] = None


def compile_project(
    source: Path, project: dict, workdir: Path, tools: dict, args,
) -> dict:
    row: dict = {
        "id": project["id"], "compiler": project["compiler"], "main": project["main"],
        "backend": project["backend"], "contains": list(project["contains"]),
        "status": "failure", "reason": None, "pages": None, "passes": 0, "warnings": 0,
        "errors": [], "backend_status": None, "engine_failure": None,
        "text_check": "skipped", "parity": {"state": "missing", "pages": None, "text": None},
        "duration_ms": 0,
    }
    if missing := _missing_requirements(project, tools):
        row["status"] = "unconfigured_project"
        row["reason"] = "missing:" + ",".join(missing)
        row["duration_ms"] = 0
        return row
    build = workdir / str(project["id"])
    if build.exists():
        raise MatrixError(f"{project['id']}: workdir collision")
    shutil.copytree(source, build)
    pdf = build / (Path(project["main"]).stem + ".pdf")
    log = build / (Path(project["main"]).stem + ".log")
    backend_status = None
    started = datetime.now(UTC)
    failure: str | None = None
    console_tail = ""

    def debug(message: str) -> None:
        if os.environ.get("LATEX_MATRIX_DEBUG"):
            print(f"debug [{project['id']}]: {message}")

    def latest_log() -> str:
        try:
            return log.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""

    def run_engine() -> str:
        nonlocal failure, console_tail
        row["passes"] += 1
        try:
            result = subprocess.run(
                [project["compiler"], *ENGINE_FLAGS, project["main"]],
                cwd=str(build), capture_output=True, text=True, timeout=args.timeout, check=False,
            )
        except subprocess.TimeoutExpired:
            failure = "timeout"
            _pass_text = latest_log()
            debug(f"pass={row['passes']} TIMEOUT log_bytes={len(_pass_text)}")
            return _pass_text
        if result.returncode != 0:
            failure = f"engine_exit_{result.returncode}"
        _pass_text = latest_log()
        console_tail = "\n".join(result.stdout.splitlines()[-6:])
        debug(
            f"pass={row['passes']} rc={result.returncode} log_bytes={len(_pass_text)}"
            f" output_line={bool(PAGES_PATTERN.search(_pass_text))} fail={failure}"
        )
        return _pass_text

    text = run_engine()
    stem = Path(project["main"]).stem
    if failure is None and project["backend"] is not None:
        tool = BACKEND_TOOLS[str(project["backend"])]
        try:
            backend_result = _run([tool, stem], build, args.timeout)
        except TimeoutError:
            failure = "backend_timeout"
        except MatrixError:
            failure = "backend_launch_failed"
        else:
            backend_status = {0: "ok", 1: "warnings"}.get(backend_result.returncode, "errors")
            if backend_status == "errors":
                failure = f"backend_exit_{backend_result.returncode}"
            text = latest_log()
            debug(
                f"backend={tool} rc={backend_result.returncode}"
                f" status={backend_status} log_bytes={len(text)}"
            )
        if failure is None:
            text = run_engine()
    while failure is None and row["passes"] < MAX_PASSES and RERUN_PATTERN.search(text):
        text = run_engine()
    build_text = None
    pdf_exists = pdf.is_file()
    if failure and not row["errors"] and console_tail:
        row["errors"] = [line[:ERROR_CHARS] for line in console_tail.splitlines() if line.strip()][-3:]
    if pdf_exists and tools["support"]["pdftotext"]["available"]:
        build_text = _extract_text(pdf, build / "extract.txt", args.timeout)
    row["backend_status"] = backend_status
    _finalise(row, text, build_text, pdf_exists)
    row.pop("engine_failure", None)
    row["parity"] = _parity(project, row["pages"], build_text, build, args.timeout)
    if row["status"] == "success" and row["parity"]["state"] in {
        "invalid", "compiler_mismatch", "pages_mismatch", "text_mismatch",
    }:
        row["status"] = "failure"
        row["reason"] = f"parity_{row['parity']['state']}"
    row["duration_ms"] = int((datetime.now(UTC) - started).total_seconds() * 1000)
    return row


def run_matrix(args) -> tuple[list[dict], dict]:
    tools = toolchain()
    rows = load_manifests()
    if args.project:
        known = {project["id"] for _, project in rows}
        unknown = sorted(set(args.project) - known)
        if unknown:
            raise MatrixError(f"unknown project filter: {unknown}")
        rows = [(source, project) for source, project in rows if project["id"] in set(args.project)]
    results: list[dict] = []
    if args.keep:
        workdir = Path(tempfile.mkdtemp(prefix="latex-golden-matrix-"))
        print(f"workdir kept: {workdir}")
    else:
        holder = tempfile.TemporaryDirectory(prefix="latex-golden-matrix-")
        workdir = Path(holder.name)
    try:
        for source, project in rows:
            row = compile_project(source, project, workdir, tools, args)
            results.append(row)
            marker = "PASS" if row["status"] == "success" else row["status"].upper()[:4]
            print(
                f"{marker} {row['id']} pages={row['pages']} passes={row['passes']}"
                f" {row['reason'] or row['status']} {row['duration_ms']}ms"
            )
    finally:
        if not args.keep:
            shutil.rmtree(workdir, ignore_errors=True)
    missing_engines = sorted(
        engine for engine in {row["compiler"] for row in results}
        if not tools["engines"][engine]["available"]
    )
    summary = {
        "selected": len(results),
        "success": sum(row["status"] == "success" for row in results),
        "failure": sum(row["status"] == "failure" for row in results),
        "unconfigured_project": sum(row["status"] == "unconfigured_project" for row in results),
        "missing_engines": missing_engines,
    }
    print(
        f"summary: success={summary['success']} failure={summary['failure']}"
        f" unconfigured_project={summary['unconfigured_project']}"
        f" missing_engines={','.join(missing_engines) or '-'}"
    )
    return results, {"toolchain": tools, "summary": summary}


def _report(args, results: list[dict], context: dict) -> dict:
    return {
        "format": REPORT_FORMAT,
        "version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "mode": {
            "gate": bool(args.gate), "skip_unconfigured": bool(args.skip_unconfigured),
            "selected": sorted(row["id"] for row in results),
        },
        "policy": {"shell_escape": "disabled", "engine_driver": "direct"},
        "toolchain": context["toolchain"],
        "projects": results,
        "summary": context["summary"],
    }


def _gate_exit(results: list[dict], skip_unconfigured: bool) -> int:
    unconfigured = [row for row in results if row["status"] == "unconfigured_project"]
    failures = [(row["id"], row["reason"]) for row in results if row["status"] == "failure"]
    if unconfigured and not skip_unconfigured:
        details = [f"{row['id']}({row['reason']})" for row in unconfigured]
        print(f"toolchain incomplete: {'; '.join(details)}")
        print(
            "hint: install the missing TeX components, e.g. Debian/Ubuntu:"
            " sudo apt-get install latexmk biber texlive-bibtex-extra"
        )
        return 2
    for project_id, reason in failures:
        print(f"failure: {project_id}: {reason}")
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--detect", action="store_true", help="print toolchain JSON and exit")
    parser.add_argument("--gate", action="store_true", help="apply strict gate exit codes")
    parser.add_argument("--skip-unconfigured", action="store_true",
                        help="gate: do not fail on unconfigured projects")
    parser.add_argument("--output", type=Path, help="write the report JSON to a new absolute path")
    parser.add_argument("--project", action="append", help="run only the named golden project")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="seconds per engine pass")
    parser.add_argument("--keep", action="store_true", help="keep the compile workdir")
    parser.add_argument("--workdir", type=Path, help="use this directory instead of a temp dir")
    args = parser.parse_args(argv)
    if args.output is not None and not args.output.is_absolute():
        parser.error("output path must be absolute")
    try:
        if args.detect:
            rows = load_manifests()
            tools = toolchain()
            payload = {
                "format": TOOLCHAIN_FORMAT,
                "version": 1,
                "engines_ok": all(tools["engines"][engine]["available"] for engine in ENGINES),
                "toolchain": tools,
                "projects": [
                    {"id": project["id"], "compiler": project["compiler"],
                     "backend": project["backend"], "packages": list(project["packages"])}
                    for _, project in rows
                ],
            }
            print(json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False))
            return 0
        results, context = run_matrix(args)
        report = _report(args, results, context)
        if args.output is not None:
            if args.output.exists():
                raise MatrixError(f"output exists: {args.output}")
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("x", encoding="utf-8") as stream:
                json.dump(report, stream, sort_keys=True, separators=(",", ":"), allow_nan=False)
                stream.write("\n")
            print(f"report written: {args.output}")
        if args.gate:
            return _gate_exit(results, args.skip_unconfigured)
        unconfigured = context["summary"]["unconfigured_project"]
        missing_engines = context["summary"]["missing_engines"]
        if missing_engines or unconfigured:
            return 2
        return 1 if context["summary"]["failure"] else 0
    except MatrixError as exc:
        print(f"latex matrix error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
