from __future__ import annotations

from pathlib import Path

from qagent.adapters.boundaries import scan_import_lines
from qagent.adapters.contracts import ROOT
from qagent.services.ports import forbidden_import_roots


def scan_forbidden_imports(*, root: Path | None = None) -> list[str]:
    """Science packages must stay unwired. Hits are 'path:line:text'."""
    return scan_import_lines(root=root or ROOT, forbidden=forbidden_import_roots())
