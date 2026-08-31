from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping

from qagent.adapters.contracts import ROOT

_BUILTIN = ROOT / "handbooks"
_EXCERPT_CAP = 400
_MAX_HITS = 8
_TEXT_SUFFIXES = {".md", ".txt"}


def _folders() -> list[tuple[str, Path]]:
    found: list[tuple[str, Path]] = [("handbook", _BUILTIN)]
    raw = os.environ.get("QAGENT_KNOWLEDGE_PATH") or ""
    for item in raw.split(os.pathsep):
        text = item.strip()
        if text:
            found.append(("knowledge", Path(text)))
    return found


def _tokens(query: str) -> list[str]:
    return [part for part in query.split() if part]


def _file_matches(blob: str, query: str) -> bool:
    if not query:
        return True
    if query in blob:
        return True
    parts = _tokens(query)
    return bool(parts) and all(part in blob for part in parts)


def _first_match_index(blob: str, query: str) -> int:
    if not query:
        return 0
    found = blob.find(query)
    if found >= 0:
        return found
    earliest = -1
    for part in _tokens(query):
        pos = blob.find(part)
        if pos >= 0 and (earliest < 0 or pos < earliest):
            earliest = pos
    return max(earliest, 0)


def _excerpt(text: str, query: str, cap: int = _EXCERPT_CAP) -> str:
    if len(text) <= cap:
        return text
    start = max(0, _first_match_index(text.lower(), query) - cap // 2)
    if start + cap > len(text):
        start = max(0, len(text) - cap)
    return text[start : start + cap]


class WiredDocs:
    """Local handbook / knowledge search. Short excerpts only."""

    def search(self, args: Mapping[str, Any]) -> dict[str, Any]:
        query = str(args.get("query") or "").strip().lower()
        hits: list[dict[str, str]] = []
        knowledge_roots = 0
        for kind, folder in _folders():
            if kind == "knowledge":
                knowledge_roots += 1
            if not folder.is_dir():
                continue
            for path in folder.rglob("*"):
                if not path.is_file() or path.suffix.lower() not in _TEXT_SUFFIXES:
                    continue
                text = path.read_text(encoding="utf-8")
                blob = text.lower()
                if not _file_matches(blob, query):
                    continue
                hits.append(
                    {
                        "path": str(path.relative_to(folder)),
                        "text": _excerpt(text, query),
                        "source": kind,
                    }
                )
                if len(hits) >= _MAX_HITS:
                    return {"hits": hits, "empty": False}
        if hits:
            return {"hits": hits, "empty": False}
        if knowledge_roots and not any(
            folder.is_dir() and any(folder.iterdir())
            for kind, folder in _folders()
            if kind == "knowledge"
        ):
            return {"hits": [], "empty": True, "detail": "知识库是空的。没有这条。"}
        return {"hits": [], "empty": True, "detail": "没有这条。不会出网乱抓。"}
