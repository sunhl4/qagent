"""Validate navigation and local code quotations in the survey documentation.

Read-only, offline; does not execute business code or access providers.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

from validate_evidence import QUOTE, WORKSPACE

ROOT = Path(__file__).resolve().parent.parent
LINK = re.compile(r"(?<!!)\[[^\]]*\]\(([^\s)]+)(?:\s+[^)]*)?\)")
HTML_ANCHOR = re.compile(r'<a\s+(?:id|name)=["\']([^"\']+)["\']')


def validate_navigation() -> dict:
    errors: list[str] = []
    checked_links = 0
    local_quotes = 0
    documents = sorted(ROOT.glob("*.md")) + sorted((ROOT / "reviewed").glob("*.md"))
    for document in documents:
        text = document.read_text()
        for match in LINK.finditer(text):
            target = match[1]
            url = urlsplit(target)
            if url.scheme or target.startswith("//") or "`" in target or "{" in target:
                continue
            path_text = unquote(url.path)
            if path_text.startswith("/"):
                destination = Path(path_text)
            else:
                destination = document.parent / path_text if path_text else document
            destination = destination.resolve()
            if not destination.exists():
                errors.append(f"{document.name}: broken link: {target}")
                continue
            if url.fragment.startswith("project-"):
                anchors = set(HTML_ANCHOR.findall(destination.read_text()))
                if url.fragment not in anchors:
                    errors.append(f"{document.name}: missing project anchor: {target}")
            checked_links += 1
        if document.parent == ROOT:
            for match in QUOTE.finditer(text):
                start, end = int(match[1]), int(match[2])
                path = WORKSPACE / match[3]
                if not path.is_file():
                    errors.append(f"{document.name}: unknown local source: {match[3]}")
                    continue
                lines = path.read_text().splitlines()
                if not (1 <= start <= end <= len(lines)) or "\n".join(lines[start-1:end]) != match[4]:
                    errors.append(f"{document.name}: local quotation mismatch: {match[3]}:{start}-{end}")
                local_quotes += 1
    index = ROOT / "reviewed" / "README.zh-CN.md"
    if index.exists():
        anchors = set(HTML_ANCHOR.findall(index.read_text()))
        wanted = {f"project-{i:02d}" for i in range(1, 58)}
        if missing := wanted - anchors:
            errors.append(f"index missing project anchors: {sorted(missing)}")
    else:
        errors.append("reviewed project index missing")
    return {
        "scope": "survey navigation and local source quotations",
        "documents": len(documents), "checked_local_links": checked_links,
        "local_source_quotations": local_quotes, "errors": errors, "passed": not errors,
    }


if __name__ == "__main__":
    report = validate_navigation()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["passed"] else 1)
