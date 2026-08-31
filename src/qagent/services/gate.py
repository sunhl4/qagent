from __future__ import annotations

_APPROVE = frozenset({"批准", "同意", "批准上机", "同意上机"})
_REJECT = frozenset({"拒绝", "先不批", "先不要", "不要"})


def classify(message: str) -> str:
    """Approve / reject / empty / run. Not an agent loop."""
    text = (message or "").strip()
    if not text:
        return "empty"
    if text in _APPROVE or text.startswith("批准"):
        return "approve"
    if text in _REJECT or text.startswith("拒绝") or text.startswith("先不"):
        return "reject"
    return "run"
