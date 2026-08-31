from __future__ import annotations

import os
from pathlib import Path


def _home(env_name: str) -> Path | None:
    raw = os.environ.get(env_name)
    if not raw:
        return None
    return Path(raw)


def qdata_python() -> str | None:
    override = os.environ.get("QAGENT_QDATA_PYTHON")
    if override:
        return override
    home = _home("QAGENT_QDATA_HOME")
    if home is None:
        return None
    candidate = home / ".venv" / "bin" / "python"
    return str(candidate) if candidate.is_file() else None


def qdata_bin() -> str | None:
    override = os.environ.get("QAGENT_QDATA_BIN")
    if override:
        return override
    home = _home("QAGENT_QDATA_HOME")
    if home is None:
        return None
    candidate = home / ".venv" / "bin" / "qdata"
    return str(candidate) if candidate.is_file() else None


def qdata_url() -> str | None:
    raw = os.environ.get("QAGENT_QDATA_URL")
    return raw.rstrip("/") if raw else None


def qdata_probe_url() -> str:
    return qdata_url() or "http://127.0.0.1:8787"


def qchem_python() -> str | None:
    override = os.environ.get("QAGENT_QCHEM_PYTHON")
    if override:
        return override
    home = _home("QAGENT_QCHEM_HOME")
    if home is None:
        return None
    candidate = home / ".venv" / "bin" / "python"
    return str(candidate) if candidate.is_file() else None


def qchem_bin() -> str | None:
    override = os.environ.get("QAGENT_QCHEM_BIN")
    if override:
        return override
    home = _home("QAGENT_QCHEM_HOME")
    if home is None:
        return None
    candidate = home / ".venv" / "bin" / "qchem-run"
    return str(candidate) if candidate.is_file() else None


def qchem_parity_bin() -> str | None:
    override = os.environ.get("QAGENT_QCHEM_PARITY_BIN")
    if override:
        return override
    home = _home("QAGENT_QCHEM_HOME")
    if home is None:
        return None
    candidate = home / ".venv" / "bin" / "qchem-export-parity"
    return str(candidate) if candidate.is_file() else None


def qchem_bin_requested() -> str | None:
    """Path the operator pointed at, even if the file is missing."""
    override = os.environ.get("QAGENT_QCHEM_BIN")
    if override:
        return override
    home = _home("QAGENT_QCHEM_HOME")
    if home is None:
        return None
    return str(home / ".venv" / "bin" / "qchem-run")


def qchem_parity_bin_requested() -> str | None:
    """Parity CLI path the operator pointed at, even if missing."""
    override = os.environ.get("QAGENT_QCHEM_PARITY_BIN")
    if override:
        return override
    home = _home("QAGENT_QCHEM_HOME")
    if home is None:
        return None
    return str(home / ".venv" / "bin" / "qchem-export-parity")


def ionstack_python() -> str | None:
    override = os.environ.get("QAGENT_IONSTACK_PYTHON")
    if override:
        return override
    home = _home("QAGENT_IONSTACK_HOME")
    if home is None:
        return None
    candidate = home / ".venv" / "bin" / "python"
    return str(candidate) if candidate.is_file() else None
