from __future__ import annotations

from typing import Any

from qagent.adapters.contracts import CONTRACTS, load_json


def load_error_catalog() -> dict[str, Any]:
    return load_json(CONTRACTS / "errors.json")
