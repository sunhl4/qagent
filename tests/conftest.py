"""Build once per pytest worker, entirely outside the source workspace."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
from hypothesis.configuration import set_hypothesis_home_dir

@pytest.fixture()
def make_symlink():
    """Create a symlink, skipping on Windows hosts without symlink privilege.

    The fail-closed symlink gates require ``os.symlink``; on Windows that needs
    developer mode or admin rights, so the environment cannot express the
    fixture rather than the kernel being wrong.
    """

    def factory(target, link, **kwargs) -> None:
        try:
            os.symlink(target, link, **kwargs)
        except OSError as exc:
            if os.path.islink(link) or link.exists():
                raise
            pytest.skip(f"symlink creation unavailable on this host: {exc}")

    return factory


ROOT = Path(__file__).resolve().parents[1]


def hermetic_env(**overrides: str) -> dict[str, str]:
    """A hermetic child env that keeps OS-critical variables.

    On Windows, replacing the environment wholesale drops ``SystemRoot``,
    and Node aborts at process init (``ncrypto::CSPRNG``) without it. POSIX
    keeps a bare hermetic PATH; Windows inherits the parent PATH (PATH is
    not used by the parent to resolve ``node``) and re-attaches SystemRoot.
    """

    if os.name == "nt":
        env = {"PATH": os.environ.get("PATH", "")}
        env["SystemRoot"] = os.environ.get("SystemRoot", "")
        env["windir"] = os.environ.get("windir", "")
        env.update({k: v for k, v in overrides.items() if v is not None})
        return env
    env = {"PATH": "/usr/bin:/bin"}
    env.update({k: v for k, v in overrides.items() if v is not None})
    return env


@pytest.fixture(autouse=True)
def isolated_receipt_store(monkeypatch, tmp_path_factory) -> None:
    """Keep the durable receipt ledger out of both HOME and every test tmp_path.

    Receipts stay outside tmp_path so a directory inside the store root can
    never leak into tests that scan tmp_path as a knowledge root or file tree.
    """

    store = tmp_path_factory.mktemp("company-receipts", numbered=True) / "receipts"
    monkeypatch.setenv("COMPANY_AGENT_RECEIPT_DIR", str(store))


def pytest_configure(config) -> None:
    # Hypothesis caches Unicode data even with its example database disabled.
    storage = tempfile.TemporaryDirectory(prefix="company-properties-")
    set_hypothesis_home_dir(storage.name)

    def cleanup() -> None:
        set_hypothesis_home_dir(None)
        storage.cleanup()

    config.add_cleanup(cleanup)


@pytest.fixture(scope="session")
def built_wheel(tmp_path_factory) -> Path:
    temporary = tmp_path_factory.mktemp("company-wheel")
    source = temporary / "source"
    source.mkdir()
    for name in ("src", "contracts", "knowledge"):
        shutil.copytree(ROOT / name, source / name,
                        ignore=shutil.ignore_patterns("__pycache__", "*.egg-info"))
    for name in ("pyproject.toml", "README.md"):
        shutil.copy2(ROOT / name, source / name)
    output = temporary / "wheels"
    subprocess.run([sys.executable, "-m", "build", "--wheel", "--no-isolation", "--outdir", str(output)],
                   cwd=source, check=True, capture_output=True, text=True, timeout=120)
    wheels = list(output.glob("*.whl"))
    assert len(wheels) == 1
    return wheels[0]
