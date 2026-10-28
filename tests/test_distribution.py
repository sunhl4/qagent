from __future__ import annotations

import zipfile
from pathlib import Path


def test_wheel_contains_contracts_and_knowledge(built_wheel: Path) -> None:
    with zipfile.ZipFile(built_wheel) as archive:
        names = set(archive.namelist())
    assert any(name.endswith("share/unitqc-company-agent/contracts/tools.json") for name in names)
    assert any(name.endswith("share/unitqc-company-agent/contracts/capabilities.json") for name in names)
    assert any(name.endswith("share/unitqc-company-agent/contracts/results.json") for name in names)
    assert any(name.endswith("share/unitqc-company-agent/knowledge/quantum-capability.md") for name in names)
