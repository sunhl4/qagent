"""Golden LaTeX matrix gates: structure always, real toolchain only by explicit opt-in."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "latex_golden_matrix.py"
GOLDEN = ROOT / "tests" / "latex" / "golden"
REFERENCES = ROOT / "tests" / "latex" / "references"

MANIFEST_KEYS = {
    "backend", "compiler", "contains", "description", "id", "main", "pages_min",
    "packages", "purpose",
}
COMPILERS = ("pdflatex", "xelatex", "lualatex")
BACKENDS = (None, "bibtex", "biber")
PROBED_PACKAGES = {
    "fontspec", "ctex", "biblatex", "tikz", "pgfplots", "hyperref", "booktabs",
}
META_KEYS = {"compiler", "texlive", "pages"}


def manifests() -> list[tuple[Path, dict]]:
    rows = []
    for directory in sorted(path for path in GOLDEN.iterdir() if path.is_dir()):
        rows.append((directory, json.loads((directory / "project.json").read_text(encoding="utf-8"))))
    return rows


def test_golden_set_manifests_are_fully_specified() -> None:
    seen: set[str] = set()
    assert manifests(), "golden set must not be empty"
    for directory, data in manifests():
        assert set(data) == MANIFEST_KEYS, directory.name
        assert data["id"] == directory.name and data["id"] not in seen
        seen.add(data["id"])
        assert data["compiler"] in COMPILERS
        assert data["backend"] in BACKENDS
        assert (directory / data["main"]).is_file()
        for name in data["packages"]:
            assert name in PROBED_PACKAGES
        assert data["contains"] and all(isinstance(item, str) for item in data["contains"])
        assert type(data["pages_min"]) is int and data["pages_min"] >= 0
        assert len(data["purpose"]) >= 8 and len(data["description"]) >= 8


def test_golden_sources_stay_shell_escape_free_and_source_only() -> None:
    for directory, _ in manifests():
        for path in directory.rglob("*"):
            if path.is_dir():
                continue
            relative = path.relative_to(directory).as_posix()
            assert path.suffix in {".tex", ".bib", ".json"}, relative
            assert not path.name.endswith(".pdf"), relative
            text = path.read_text(encoding="utf-8").casefold()
            assert "\\write18" not in text, relative
            assert "shell-escape" not in text, relative
            assert "shell_escape" not in text, relative


def test_matrix_script_compiles_and_stays_stdlib_only() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    compile(source, str(SCRIPT), "exec")
    assert "import requests" not in source
    assert "import numpy" not in source


def test_harness_detect_reports_honest_toolchain() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--detect"], cwd=ROOT,
        capture_output=True, text=True, timeout=180, check=False,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["format"] == "company-agent-latex-toolchain/1"
    tools = payload["toolchain"]
    assert set(tools) == {"engines", "support", "packages"}
    assert set(tools["engines"]) == set(COMPILERS)
    for row in (*tools["engines"].values(), *tools["support"].values()):
        assert set(row) == {"available", "version", "texlive_year"}
        assert isinstance(row["available"], bool)
        assert isinstance(row["version"], str)
    names = {row["name"] for row in tools["packages"]}
    assert names == PROBED_PACKAGES
    assert payload["engines_ok"] == all(tools["engines"][name]["available"] for name in COMPILERS)
    assert [entry["id"] for entry in payload["projects"]] == [row[1]["id"] for row in manifests()]


def test_reference_layout_is_valid_when_present() -> None:
    if not REFERENCES.is_dir():
        return
    for directory in sorted(path for path in REFERENCES.iterdir() if path.is_dir()):
        meta_path = directory / "meta.json"
        assert (directory / "reference.pdf").is_file(), directory.name
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        assert set(meta) == META_KEYS, directory.name
        assert type(meta["pages"]) is int and meta["pages"] > 0
        assert isinstance(meta["compiler"], str) and isinstance(meta["texlive"], str)


def test_opt_in_markers_stay_deselected_from_default_scopes() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "not platform_compatibility and not latex_toolchain" in pyproject
    assert "latex_toolchain:" in pyproject
    acceptance = (ROOT / "scripts" / "acceptance_pytest.py").read_text(encoding="utf-8")
    assert '"latex_toolchain"' in acceptance
    verifier = (ROOT / "scripts" / "verify_acceptance.py").read_text(encoding="utf-8")
    assert '"latex_toolchain"' in verifier


@pytest.mark.latex_toolchain
def test_golden_matrix_passes_strict_gate_when_selected() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--gate"], cwd=ROOT,
        capture_output=True, text=True, timeout=1200, check=False,
    )
    if result.returncode == 2:
        pytest.fail(f"LaTeX toolchain incomplete for the golden gate: {result.stdout.strip()[-400:]}")
    assert result.returncode == 0, result.stdout[-800:]
