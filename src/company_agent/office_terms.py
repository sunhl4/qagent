"""Terminology suggestions for tracked edits (§4.2).

The function only proposes find/replace pairs. Landing them is still
``company_office_edit``. A quoted definition or a parenthetical alias of one
of the 27 role words becomes a suggestion; nothing is written here.
"""
from __future__ import annotations

import re

ROLES: tuple[str, ...] = (
    "甲方",
    "乙方",
    "丙方",
    "丁方",
    "委托方",
    "受托方",
    "出让方",
    "受让方",
    "买方",
    "卖方",
    "出租方",
    "承租方",
    "贷款人",
    "借款人",
    "保证人",
    "抵押人",
    "出质人",
    "债权人",
    "债务人",
    "申请人",
    "被申请人",
    "原告",
    "被告",
    "第三人",
    "证人",
    "鉴定人",
    "代理人",
)

_DEFINED = re.compile(r"[“\"]([\u4e00-\u9fffA-Za-z0-9]{2,40})[”\"]")
_ALIAS = re.compile(r"([\u4e00-\u9fff]{2,12})（([\u4e00-\u9fff]{2,12})）")


def suggest(text: str) -> list[dict[str, str]]:
    """Return find/replace suggestions. Empty input yields an empty list."""

    if not isinstance(text, str) or not text:
        return []
    rows: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    defined = {match.group(1) for match in _DEFINED.finditer(text)}
    for match in _ALIAS.finditer(text):
        term, alias = match.group(1), match.group(2)
        if term in ROLES or alias in ROLES or term in defined:
            _add(rows, seen, alias, term, "括号别名")
    for role in ROLES:
        if role in defined and text.count(role) > 1:
            continue
        if role in text and role not in defined:
            for term in defined:
                if term != role and role in text:
                    _add(rows, seen, role, term, "角色词对齐引号定义")
                    break
    return rows[:64]


def _add(rows: list[dict[str, str]], seen: set[tuple[str, str]], find: str, replace: str, note: str) -> None:
    if not find or find == replace or (find, replace) in seen:
        return
    seen.add((find, replace))
    rows.append({"find": find, "replace": replace, "note": note})
