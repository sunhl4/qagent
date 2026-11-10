from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOTS = (
    ".github",
    "src",
    "packages",
    "profiles",
    "contracts",
    "runtime",
    "scripts",
    "skills",
    "docs",
    "knowledge",
    "tests",
)
ROOT_TEXT_FILES = ("AGENTS.md", "README.md", "package.json", "pins.json", "pyproject.toml")
TEXT_SUFFIXES = {".py", ".js", ".mjs", ".ts", ".json", ".yml", ".yaml", ".sh", ".md", ".toml"}
OLD_AGENT = "q" + "agent"
OLD_DATA = "q" + "data"
OLD_CHEM = "q" + "chem"
OLD_QISKIT = "qis" + "kit"
OLD_CIRQ = "ci" + "rq"
OLD_PENNYLANE = "penny" + "lane"
OLD_VIBE = "q" + "vibe"
OLD_NAMES = (OLD_AGENT, OLD_DATA, OLD_CHEM, OLD_QISKIT, OLD_CIRQ, OLD_PENNYLANE, OLD_VIBE)
LEGACY_TOKENS = (
    OLD_AGENT,
    OLD_DATA,
    OLD_CHEM,
    "ionstack" + "_twin_run",
    OLD_QISKIT + "_",
    OLD_CIRQ + "_",
    OLD_PENNYLANE + "_",
    OLD_VIBE,
    "job" + "_id",
)
FORBIDDEN_PATHS = (
    f"src/{OLD_AGENT}",
    f"profiles/{OLD_AGENT}",
    f"profiles/{OLD_AGENT}-minimal",
    "contracts/eval",
    "contracts/events",
    "contracts/slots.json",
    "seams",
    "contracts/ports.json",
    "contracts/handoff",
    "contracts/engines",
    f"packages/{OLD_AGENT}-bundle",
    f"packages/{OLD_AGENT}-policy",
    "apps/customer-shell",
    "docs/execution",
    "handbooks",
    "wrappers",
)
GENERATED_TOP_LEVEL = {".pytest_cache", ".ruff_cache", ".hypothesis", ".gate-tmp"}
FORBIDDEN_RUNTIME_NAMES = {".profile-start", ".credentials.yaml"}
ALLOWED_TOP_LEVEL = {
    ".git",
    ".github",
    ".gitignore",
    "AGENTS.md",
    "README.md",
    "apps",  # TEMPORARY: company-workspace presentation experiment; not an M1 deliverable.
    "contracts",
    "desktop",
    "docs",
    "knowledge",
    "package.json",
    "packages",
    "pins.json",
    "profiles",
    "pyproject.toml",
    "research-layer",
    "resources",
    "runtime",
    "scripts",
    "skills",
    "src",
    "tests",
    "view",
}
ALLOWED_SOURCE_CHILDREN = {
    "src": {"company_agent"},
    "packages": {
        "company-agent-policy",
        "company-agent-core",
        "company-agent-quantum",
        "company-agent-hpc",
        "company-agent-device",
        "company-agent-latex",
        "company-agent-office",
        "company-agent-plan",
        "company-agent-research",
        "company-agent-literature",
    },
    "profiles": {"company-agent", "company-agent-minimal"},
    "runtime": set(),
}


def _source_files():
    for name in ROOT_TEXT_FILES:
        path = ROOT / name
        if path.is_file():
            yield path
    for name in SOURCE_ROOTS:
        root = ROOT / name
        for path in root.rglob("*"):
            if "node_modules" in path.parts or path.suffix not in TEXT_SUFFIXES:
                continue
            try:
                regular = path.is_file()
            except OSError:
                # A damaged or unmountable artifact cannot be a text source.
                continue
            if not regular:
                continue
            # Machine evidence includes external repository paths and command identities,
            # not active imports/tool names. Continue scanning prose and executable sources.
            if path.suffix == ".json" and path.is_relative_to(ROOT / "docs/evidence"):
                continue
            # The oss-survey archive reports surveyed upstream projects under their
            # real upstream names; those facts are not legacy company architecture.
            if path.is_relative_to(ROOT / "docs" / "oss-survey"):
                continue
            # Conversation history narrates the recovered copy paths and prior
            # repository names; narrative records are not active architecture.
            if path.is_relative_to(ROOT / "docs") and path.name.startswith("conversation-log-"):
                continue
            yield path


def test_legacy_names_are_absent_from_active_architecture() -> None:
    hits: list[str] = []
    this_file = Path(__file__).resolve()
    # `slurm_job_id` is a real scheduler environment variable recorded in the
    # cluster journal; the legacy ban targets the old agent's job_id vocabulary,
    # not the SLURM identity, so the looked-behind spelling is exempt.
    for path in _source_files():
        if path.resolve() == this_file:
            continue
        text = path.read_text(encoding="utf-8").casefold()
        for token in LEGACY_TOKENS:
            if token != "job_id" and token in text:
                hits.append(f"{path.relative_to(ROOT)}:{token}")
            elif token == "job_id":
                for match in re.finditer("job_id", text):
                    if not text[max(0, match.start() - 6):match.start()].endswith("slurm_"):
                        hits.append(f"{path.relative_to(ROOT)}:{token}")
                        break
    assert hits == []


def test_machine_evidence_exception_does_not_hide_active_sources(tmp_path, monkeypatch):
    monkeypatch.setattr(sys.modules[__name__], "ROOT", tmp_path)
    directory = tmp_path / "docs/evidence"
    directory.mkdir(parents=True)
    for name in ("identity.json", "guide.md", "probe.py"):
        (directory / name).write_text("synthetic input")
    source = tmp_path / "contracts"
    source.mkdir()
    (source / "tools.json").write_text("{}")
    paths = {path.relative_to(tmp_path).as_posix() for path in _source_files()}
    assert paths == {"docs/evidence/guide.md", "docs/evidence/probe.py", "contracts/tools.json"}


def test_legacy_paths_are_physically_absent() -> None:
    assert [path for path in FORBIDDEN_PATHS if (ROOT / path).exists()] == []


def test_only_company_architecture_roots_remain() -> None:
    forbidden_runtime = [
        str(path.relative_to(ROOT))
        for path in ROOT.rglob("*")
        if "node_modules" not in path.parts
        and ".dsh-home" not in path.parts
        and (path.name in FORBIDDEN_RUNTIME_NAMES or path.name.startswith(".profile-start."))
    ]
    assert forbidden_runtime == []
    actual = {
        path.name
        for path in ROOT.iterdir()
        if not path.name.startswith(".dsh-")
        and path.name not in GENERATED_TOP_LEVEL
        and not path.name.endswith(".egg-info")
        and not path.name.startswith("pytest-cache-files-")
    }
    assert not (ROOT / "build").exists()
    assert not (ROOT / "dist").exists()
    assert not list((ROOT / "src").glob("*.egg-info"))
    assert actual <= ALLOWED_TOP_LEVEL
    for parent, expected in ALLOWED_SOURCE_CHILDREN.items():
        actual_children = {
            path.name
            for path in (ROOT / parent).iterdir()
            if path.is_dir()
            and path.name not in {"__pycache__", "node_modules"}
            and not path.name.endswith(".egg-info")
        }
        assert actual_children == expected
    assert {path.name for path in (ROOT / "contracts").iterdir() if path.is_file()} == {
        "tools.json",
        "capabilities.json",
        "providers.json",
        "policy.json",
        "presets.json",
        "results.json",
        "templates.json",
        "skills.json",
        "tenants.json",
        "budgets.json",
        "superagent.json",
    }


def test_no_legacy_named_files_or_directories() -> None:
    legacy_name = re.compile(
        rf"(?:^|[-_.])({'|'.join(re.escape(name) for name in OLD_NAMES)})(?:$|[-_.])",
        re.I,
    )
    hits = []
    for path in ROOT.rglob("*"):
        if any(part in {".git", "node_modules", ".dsh-home"} for part in path.parts):
            continue
        # The oss-survey archive names surveyed upstreams as published; keep its
        # file names out of the active-architecture legacy scan.
        if path.is_relative_to(ROOT / "docs" / "oss-survey"):
            continue
        if legacy_name.search(path.name):
            hits.append(str(path.relative_to(ROOT)))
    assert hits == []
