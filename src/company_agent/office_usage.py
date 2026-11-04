"""Read cache fields a provider already returned. Never invent counts."""
from __future__ import annotations

from typing import Any


def parse_usage(usage: object) -> dict[str, Any]:
    """Map one usage object to fixed / cached / uncached.

    ``observed`` is ``absent`` when neither cache field is an integer.
    """

    empty = {"observed": "absent", "fixed": None, "cached": None, "uncached": None}
    if not isinstance(usage, dict):
        return empty
    cached = usage.get("prompt_cache_hit_tokens")
    if not isinstance(cached, int):
        details = usage.get("prompt_tokens_details")
        cached = details.get("cached_tokens") if isinstance(details, dict) else None
    if not isinstance(cached, int) or cached < 0:
        return empty
    prompt = usage.get("prompt_tokens")
    if not isinstance(prompt, int) or prompt < 0:
        return {"observed": "present", "fixed": None, "cached": cached, "uncached": None}
    return {
        "observed": "present",
        "fixed": prompt,
        "cached": cached,
        "uncached": max(0, prompt - cached),
    }
