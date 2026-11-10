"""Offline TeX indexing for one paper source tree.

The function reads text it is given. It does not open a network connection,
expand arbitrary macros, or crop figures.
"""

from __future__ import annotations

import io
import re
import tarfile
from pathlib import Path
from typing import Any

MAX_ARCHIVE_BYTES = 2_000_000
MAX_FILES = 40
MAX_MEMBER_BYTES = 500_000
ALLOWED_SUFFIXES = frozenset({
    ".tex", ".bib", ".sty", ".cls", ".pdf", ".png", ".eps", ".csv", ".md", ".txt",
})
_SOURCE_KINDS = frozenset({"arxiv_src", "jats", "html", "pdf_text", "figure_asset"})
_KNOWN_COMMANDS = frozenset({
    "alpha", "approx", "bar", "beta", "binom", "cdot", "cdots", "cos", "cosh",
    "cot", "delta", "det", "dim", "displaystyle", "epsilon", "exp", "frac",
    "gamma", "ge", "geq", "hat", "infty", "int", "ker", "label", "lambda",
    "ldots", "le", "left", "leq", "limits", "ln", "log", "mathbf", "mathcal",
    "mathit", "mathrm", "max", "min", "mp", "mu", "ne", "neq", "nu", "omega",
    "operatorname", "overline", "partial", "pi", "pm", "prod", "qquad", "quad",
    "rank", "right", "rightarrow", "scriptstyle", "sigma", "sin", "sinh",
    "sqrt", "sum", "tan", "tanh", "text", "theta", "tilde", "times", "to",
    "underline", "vec", "lesssim", "gtrsim",
})
_ENV = re.compile(r"\\begin\{(equation|align)\}(.*?)\\end\{\1\}", re.DOTALL)
_LABEL = re.compile(r"\\label\{([A-Za-z0-9:_-]+)\}")
_INCLUDE = re.compile(r"\\includegraphics(?:\[[^\]]*\])?\{([^{}]+)\}")
_INPUT = re.compile(r"\\(?:input|include)\{([^{}]+)\}")
_COMMAND = re.compile(r"\\([A-Za-z]+)")
_GITHUB = re.compile(r"https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
_SUPPLEMENT = re.compile(r"(supplement|appendix|(?:^|[-_])si(?:[-_.]|$))", re.IGNORECASE)
_LEDGER_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$")
_PAPER_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class LiteratureSourceError(ValueError):
    """A source tree or archive cannot be indexed."""


def index_tex(
    text: str, *, paper_id: str, version: str, source_kind: str = "arxiv_src",
) -> dict[str, Any]:
    """Extract labeled formulas, figure paths, code URLs, and supplement names."""

    if not _PAPER_ID.fullmatch(paper_id) or not _PAPER_ID.fullmatch(version):
        raise LiteratureSourceError("source identity is invalid")
    if source_kind not in _SOURCE_KINDS:
        raise LiteratureSourceError("source identity is invalid")
    if not isinstance(text, str):
        raise LiteratureSourceError("source text is invalid")
    sample = text[:500_000]
    formulas: list[dict[str, Any]] = []
    seen_labels: set[str] = set()
    for match in _ENV.finditer(sample):
        body = match.group(2).strip()
        label_match = _LABEL.search(body)
        if label_match is None or not body:
            continue
        label = label_match.group(1)
        if label in seen_labels:
            continue
        seen_labels.add(label)
        ledger_id = label if _LEDGER_ID.fullmatch(label) else f"F{len(formulas) + 1}"
        formulas.append({
            "ledger_id": ledger_id,
            "paper_id": paper_id,
            "source_kind": source_kind,
            "version": version,
            "anchor": label,
            "tex": body[:4000],
            "role": _role(label, body),
            "fidelity": _fidelity(body),
        })
        if len(formulas) >= 64:
            break
    figures = _unique(_safe_paths(_INCLUDE.findall(sample)), limit=32)
    supplements = _unique(
        [name.strip() for name in _INPUT.findall(sample) if _SUPPLEMENT.search(Path(name).name)],
        limit=32,
    )
    code_urls = _unique(_GITHUB.findall(sample), limit=8)
    return {
        "formulas": formulas,
        "figures": figures,
        "supplements": supplements,
        "code_urls": code_urls,
    }


def inspect_archive(payload: bytes) -> dict[str, Any]:
    """List a tar archive after rejecting links, escapes, and unexpected suffixes."""

    if not isinstance(payload, (bytes, bytearray)) or len(payload) > MAX_ARCHIVE_BYTES:
        raise LiteratureSourceError("archive rejected")
    try:
        archive = tarfile.open(fileobj=io.BytesIO(bytes(payload)), mode="r:*")
    except (tarfile.TarError, OSError) as exc:
        raise LiteratureSourceError("archive rejected") from exc
    names: list[str] = []
    total = 0
    with archive:
        for member in archive.getmembers():
            if member.isdir():
                continue
            if member.issym() or member.islnk() or not member.isfile():
                raise LiteratureSourceError("archive rejected")
            name = _member_name(member.name)
            if member.size > MAX_MEMBER_BYTES:
                raise LiteratureSourceError("archive rejected")
            total += int(member.size)
            names.append(name)
            if len(names) > MAX_FILES or total > MAX_ARCHIVE_BYTES:
                raise LiteratureSourceError("archive rejected")
    return {"files": len(names), "bytes": total, "names": names}


def extract_archive(payload: bytes, dest: Path) -> dict[str, int]:
    """Write an inspected archive into ``dest`` without using archive paths raw."""

    report = inspect_archive(payload)
    allowed = set(report["names"])
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(bytes(payload)), mode="r:*") as archive:
        for member in archive.getmembers():
            if not member.isfile():
                continue
            name = _member_name(member.name)
            if name not in allowed:
                raise LiteratureSourceError("archive rejected")
            stream = archive.extractfile(member)
            if stream is None:
                raise LiteratureSourceError("archive rejected")
            data = stream.read(MAX_MEMBER_BYTES + 1)
            if len(data) > MAX_MEMBER_BYTES:
                raise LiteratureSourceError("archive rejected")
            target = dest.joinpath(*name.split("/"))
            if target.is_symlink():
                raise LiteratureSourceError("archive rejected")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
    return {"files": report["files"], "bytes": report["bytes"]}


def copy_source_tree(source: Path, dest: Path) -> dict[str, int]:
    """Copy a regular-file source tree using the same suffix and size bounds."""

    files = 0
    total = 0
    dest.mkdir(parents=True, exist_ok=True)
    for path in sorted(source.rglob("*")):
        if path.is_symlink():
            raise LiteratureSourceError("archive rejected")
        if not path.is_file():
            continue
        relative = path.relative_to(source).as_posix()
        name = _member_name(relative)
        data = path.read_bytes()
        if len(data) > MAX_MEMBER_BYTES:
            raise LiteratureSourceError("archive rejected")
        total += len(data)
        files += 1
        if files > MAX_FILES or total > MAX_ARCHIVE_BYTES:
            raise LiteratureSourceError("archive rejected")
        target = dest.joinpath(*name.split("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    return {"files": files, "bytes": total}


def _role(label: str, tex: str) -> str:
    folded = f"{label} {tex}".casefold()
    if any(word in folded for word in ("update", "iterate")):
        return "update"
    if "complexity" in folded:
        return "complexity"
    if any(word in folded for word in ("objective", "loss", "minimize")):
        return "objective"
    if any(token in tex for token in ("\\lesssim", "\\gtrsim", "\\leq", "\\geq", "\\le", "\\ge")):
        return "constraint"
    if "result" in label.casefold():
        return "reported_result"
    return "definition"


def _fidelity(tex: str) -> str:
    unknown = set(_COMMAND.findall(tex)) - _KNOWN_COMMANDS
    if unknown:
        return "macro_unexpanded"
    return "copied"


def _safe_paths(paths: list[str]) -> list[str]:
    kept: list[str] = []
    for raw in paths:
        candidate = raw.strip()
        if not candidate or "\\" in candidate or candidate.startswith("/") or ":" in candidate:
            continue
        parts = candidate.split("/")
        if any(part in {"", ".", ".."} or part.startswith("~") for part in parts):
            continue
        kept.append(candidate)
    return kept


def _unique(items: list[str], *, limit: int) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
        if len(result) >= limit:
            break
    return result


def _member_name(name: str) -> str:
    raw = name.replace("\\", "/").lstrip("/")
    while raw.startswith("./"):
        raw = raw[2:]
    if not raw or raw.endswith("/"):
        raise LiteratureSourceError("archive rejected")
    parts = raw.split("/")
    if any(part in {"", ".", ".."} or part.startswith("~") or ":" in part for part in parts):
        raise LiteratureSourceError("archive rejected")
    suffix = Path(parts[-1]).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise LiteratureSourceError("archive rejected")
    if len(raw.encode("utf-8")) > 200:
        raise LiteratureSourceError("archive rejected")
    return raw
