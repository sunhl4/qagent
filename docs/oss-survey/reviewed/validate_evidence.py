"""Read-only validation for the OSS source-review evidence bundle.

Run: python3 docs/oss-survey/reviewed/validate_evidence.py
No network calls, source execution, or generated file writes are performed.
A passing result validates provenance/quotation structure, not product safety.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from collections import Counter
from pathlib import Path

BASE = Path(__file__).resolve().parent
WORKSPACE = BASE.parents[2]
QUOTE = re.compile(r"^```(\d+):(\d+):([^\n]+)\n(.*?)\n```", re.MULTILINE | re.DOTALL)
KINDS = {"implementation", "test", "license", "spec"}


def safe_path(root: Path, path: str) -> Path:
    relative = Path(path)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"not a safe relative path: {path}")
    result = (root / relative).resolve()
    if not result.is_relative_to(root.resolve()):
        raise ValueError(f"path leaves source root: {path}")
    return result


def git_head(root: Path) -> str:
    dirty = subprocess.check_output(
        ["git", "-C", str(root), "status", "--porcelain", "--untracked-files=no"],
        text=True, stderr=subprocess.DEVNULL,
    ).strip()
    if dirty:
        raise ValueError(f"tracked source files changed after checkout: {root}")
    return subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
    ).strip()


def validate(*, partial: bool = False) -> dict:
    expected = {p["id"]: p for p in json.loads((BASE / "projects.json").read_text())["projects"]}
    errors: list[str] = []
    warnings: list[str] = []
    rows: list[dict] = []
    manifests = sorted(BASE.glob("evidence-*.json"))
    for manifest in manifests:
        try:
            value = json.loads(manifest.read_text())
            if not isinstance(value, list):
                raise ValueError("evidence manifest must be an array")
            rows.extend(value)
        except (OSError, ValueError, TypeError) as exc:
            errors.append(f"{manifest.name}: {exc}")
    ids = [row.get("id") for row in rows]
    duplicates = [ident for ident, count in Counter(ids).items() if count > 1]
    if duplicates:
        errors.append(f"duplicate project ids: {duplicates}")
    missing = sorted(set(expected) - set(ids))
    if missing and not partial:
        errors.append(f"missing project ids: {missing}")
    if set(ids) - set(expected):
        errors.append(f"unknown project ids: {set(ids) - set(expected)}")
    head_cache: dict[Path, str] = {}
    text_cache: dict[Path, list[str]] = {}
    anchor_count = 0
    quote_count = 0
    verified_docs: list[str] = []
    source_heads: dict[str, str] = {}
    evidence_hashes: dict[str, str] = {}
    for row in rows:
        ident = row.get("id")
        label = f"H{ident:02d}" if isinstance(ident, int) else str(ident)
        prefix = len(errors)
        try:
            if row["repo"] != expected[ident]["repo"]:
                raise ValueError("repository does not match fixed project list")
            if row["verification"] != "static-source-review":
                raise ValueError("verification level must be explicit")
            if not row.get("license_summary") or not row.get("commit_date"):
                raise ValueError("license summary and commit date are required")
            doc = safe_path(WORKSPACE, row["doc"])
            if not doc.is_relative_to(BASE) or not doc.name.startswith(label + "-"):
                raise ValueError("document must be this project's reviewed/Hxx file")
            content = doc.read_text()
            if row["commit"] not in content:
                errors.append(f"{label}: document does not record full source SHA")
            sources = [{"repo": row["repo"], "clone_path": row["clone_path"], "commit": row["commit"]}]
            sources.extend(row.get("sources", []))
            roots: dict[str, Path] = {}
            for source in sources:
                root = Path(source["clone_path"]).resolve()
                if not re.fullmatch(r"[0-9a-f]{40}", source["commit"]):
                    raise ValueError(f"invalid source SHA: {source['commit']}")
                if root not in head_cache:
                    head_cache[root] = git_head(root)
                if head_cache[root] != source["commit"]:
                    raise ValueError(f"source version drift for {source['repo']}")
                roots[source["repo"]] = root
                source_heads[str(root)] = source["commit"]
            main_root = roots[row["repo"]]
            anchors = row["evidence"]
            identities = [(anchor.get("source_repo", row["repo"]), anchor.get("path"), anchor.get("start"), anchor.get("end")) for anchor in anchors]
            if len(identities) != len(set(identities)):
                errors.append(f"{label}: duplicate evidence anchors")
            if len(set(identities)) < 6:
                errors.append(f"{label}: fewer than six distinct evidence anchors")
            kinds = Counter(anchor.get("kind") for anchor in anchors)
            if set(kinds) - KINDS:
                errors.append(f"{label}: unknown evidence kinds")
            if kinds["implementation"] + kinds["spec"] < 3:
                errors.append(f"{label}: fewer than three implementation/spec anchors")
            if not kinds["license"]:
                if not row.get("license_gap"):
                    errors.append(f"{label}: missing license evidence or explicit license_gap")
                else:
                    warnings.append(f"{label}: upstream license gap: {row['license_gap']}")
            if not kinds["test"]:
                if not row.get("test_gap"):
                    errors.append(f"{label}: missing test evidence or explicit test_gap")
                else:
                    warnings.append(f"{label}: upstream test gap: {row['test_gap']}")
            for anchor in anchors:
                root = roots.get(anchor.get("source_repo", row["repo"]))
                if root is None:
                    raise ValueError(f"undeclared evidence source: {anchor.get('source_repo')}")
                path = safe_path(root, anchor["path"])
                if path not in text_cache:
                    text_cache[path] = path.read_text().splitlines()
                start, end = anchor["start"], anchor["end"]
                if not (type(start) is int and type(end) is int and 1 <= start <= end <= len(text_cache[path])):
                    raise ValueError(f"invalid evidence lines: {anchor['path']}:{start}-{end}")
                if not anchor.get("note"):
                    raise ValueError("evidence explanation is required")
                snippet = "\n".join(text_cache[path][start - 1:end])
                key = f"{label}:{anchor.get('source_repo', row['repo'])}:{anchor['path']}:{start}-{end}"
                evidence_hashes[key] = hashlib.sha256(snippet.encode()).hexdigest()
                anchor_count += 1
            quotes = list(QUOTE.finditer(content))
            if not quotes:
                errors.append(f"{label}: no source quotation")
            for match in quotes:
                start, end = int(match[1]), int(match[2])
                name, quoted = match[3].strip(), match[4]
                candidates = []
                for root in dict.fromkeys([main_root, *roots.values()]):
                    try:
                        path = safe_path(root, name)
                        if path.exists() and path.is_file():
                            if path not in text_cache:
                                text_cache[path] = path.read_text().splitlines()
                            candidates.append(text_cache[path])
                    except ValueError:
                        pass
                if not any(1 <= start <= end <= len(lines) and "\n".join(lines[start-1:end]) == quoted for lines in candidates):
                    errors.append(f"{label}: quotation mismatch: {name}:{start}-{end}")
                quote_count += 1
            if len(errors) == prefix:
                verified_docs.append(row["doc"])
        except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError) as exc:
            errors.append(f"{label}: {exc}")
    return {
        "scope": "static source evidence validation; not runtime acceptance",
        "expected_projects": len(expected),
        "manifest_projects": len(rows),
        "unique_project_ids": len(set(ids)),
        "missing_project_ids": missing,
        "validated_documents": len(verified_docs),
        "evidence_anchors": anchor_count,
        "source_quotations": quote_count,
        "source_snapshots": len(source_heads),
        "errors": errors,
        "warnings": warnings,
        "passed": not errors and not missing,
        "evidence_digest": hashlib.sha256(json.dumps(evidence_hashes, sort_keys=True).encode()).hexdigest(),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--partial", action="store_true", help="Check received manifests while work is ongoing")
    args = parser.parse_args()
    report = validate(partial=args.partial)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(1 if report["errors"] else 0)
