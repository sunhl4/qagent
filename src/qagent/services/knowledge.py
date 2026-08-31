from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from qagent.adapters.contracts import ROOT

_FOLDERS = (ROOT / "handbooks", ROOT / "knowledge")
_SUFFIXES = {".md", ".txt"}
_CAP = 8


def _tokens(text: str) -> set[str]:
    return {part.lower() for part in text.replace("/", " ").split() if len(part) > 1}


def lookup(query: str) -> dict[str, Any]:
    """Keyword overlap over handbooks + knowledge. Does not change tool schema."""
    wanted = _tokens(query)
    extra = str(os.environ.get("QAGENT_KNOWLEDGE_PATH") or "").strip()
    folders = list(_FOLDERS)
    if extra:
        folders.append(Path(extra))
    ranked: list[tuple[int, dict[str, str]]] = []
    for folder in folders:
        if not folder.is_dir():
            continue
        for path in folder.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in _SUFFIXES:
                continue
            text = path.read_text(encoding="utf-8")
            have = _tokens(path.name + " " + text[:4000])
            score = len(wanted & have) if wanted else 1
            if not score:
                continue
            ranked.append(
                (
                    score,
                    {
                        "path": str(path.relative_to(folder)),
                        "source": folder.name,
                    },
                )
            )
    ranked.sort(key=lambda item: (-item[0], item[1]["path"]))
    hits = [row for _score, row in ranked[:_CAP]]
    return {"hits": hits, "empty": not hits}
