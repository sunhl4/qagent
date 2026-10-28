"""Read-only quotation audit for all H drafts, including those not yet registered.

This audit deliberately does not mark projects complete. Version, anchor and
coverage gates belong to validate_evidence.py. Exact relocation suggestions are
reported, never applied; ambiguous text must be reviewed manually.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from validate_evidence import BASE, QUOTE

EXTRA_ROOTS = {
    11: [Path('/tmp/oss-letta-ai-letta-code')],
    30: [Path('/tmp/oss-daytonaio-daytona-v0.190.0')],
    57: [Path('/tmp/oss-otel-semconv-genai')],
}


def audit() -> dict:
    projects = json.loads((BASE / 'projects.json').read_text())['projects']
    errors = []
    checked = 0
    missing = []
    document_names = []
    for project in projects:
        ident = project['id']
        docs = sorted(BASE.glob(f'H{ident:02d}-*.md'))
        if len(docs) != 1:
            missing.append({'id': ident, 'documents': len(docs)})
            continue
        document = docs[0]
        document_names.append(document.name)
        content = document.read_text()
        roots = [Path('/tmp/oss-' + project['repo'].replace('/', '-'))]
        roots.extend(EXTRA_ROOTS.get(ident, []))
        for match in QUOTE.finditer(content):
            checked += 1
            start, end, relative, quoted = int(match[1]), int(match[2]), match[3], match[4]
            if Path(relative).is_absolute() or '..' in Path(relative).parts:
                errors.append({'doc': document.name, 'path': relative, 'error': 'unsafe path'})
                continue
            actual = []
            suggestions = []
            valid = False
            for root in roots:
                source = root / relative
                if not source.is_file():
                    continue
                lines = source.read_text().splitlines()
                if 1 <= start <= end <= len(lines) and '\n'.join(lines[start-1:end]) == quoted:
                    valid = True
                needle = quoted.splitlines()
                for offset in range(len(lines) - len(needle) + 1):
                    if lines[offset:offset + len(needle)] == needle:
                        suggestions.append({'source': str(root), 'start': offset + 1, 'end': offset + len(needle)})
                if 1 <= start <= end <= len(lines):
                    actual.append({'source': str(root), 'text_at_claimed_lines': '\n'.join(lines[start-1:end])})
            if not valid:
                errors.append({'doc': document.name, 'path': relative, 'claimed': [start, end], 'exact_matches': suggestions, 'actual': actual})
    return {'scope': 'draft quotation audit, not project completion', 'documents': len(projects) - len(missing), 'document_names': document_names, 'quotations': checked, 'missing_or_duplicate_documents': missing, 'errors': errors, 'passed': not errors and not missing}


if __name__ == '__main__':
    result = audit()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result['passed'] else 1)
