"""C-01l: ELN face paints Chinese kind labels. Text on js only. Does not claim G0/G2."""

from __future__ import annotations

import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHELL = ROOT / "apps" / "customer-shell"
NOTE = ROOT / "docs" / "execution" / "C-01l_eln_label.md"
_ROOMS = ("实验室", "写算法", "签收台", "三房间")
_WALLS = ("Finder", "工作区门槛", "dsh-workspace", "dsh-web", "workspace chrome")
_CLAIM_PASS = (
    "G0 已通过",
    "G2 已通过",
    "G0 passed",
    "G2 passed",
    "Pennylane 已接线",
)
_KINDS = (
    ("recipe_pin", "配方钉住"),
    ("estimate", "估计"),
    ("twin_signoff", "签收"),
    ("b3", "B3"),
    ("assignment", "交办"),
    ("claim_blocked", "未认领"),
)
_MAP_KEYS = (
    "qagent/recipe_pin",
    "qagent/estimate",
    "qagent/twin_signoff",
    "qagent/b3",
    "qagent/assignment",
    "qagent/claim_blocked",
)


def _read(name: str) -> str:
    return (SHELL / name).read_text(encoding="utf-8")


def _js() -> str:
    return _read("app.js")


def _between(start: str, end: str) -> str:
    return _js().split(start)[1].split(end)[0]


def _kind_map() -> str:
    return _between("const ELN_KIND_MAP", "function elnType")


def _eln_type() -> str:
    return _between("function elnType", "function elnKindLabel")


def _kind_label() -> str:
    return _between("function elnKindLabel", "function elnAssignmentId")


def _paint_eln() -> str:
    return _between("function paintEln", "async function refreshInbox")


def _refresh() -> str:
    return _between("async function refreshInbox", "function addMessage")


def test_kind_label_has_chinese() -> None:
    label = _kind_label()
    for internal, chinese in _KINDS:
        assert internal in label
        assert chinese in label
        assert label.index(internal) < label.index(chinese)
    assert "return kind" in label


def test_paint_eln_uses_label_not_raw_kind() -> None:
    paint = _paint_eln()
    assert "elnKindLabel" in paint
    assert "elnType" in paint
    assert "typeEl.textContent = elnKindLabel" in paint
    assert "typeEl.textContent = kind" not in paint
    assert "twin_id" not in paint
    assert "row.twin_id" not in paint
    assert "row.columns" not in paint
    assert "ask.args" not in paint


def test_kind_map_keeps_english_keys() -> None:
    types = _kind_map()
    eln_type = _eln_type()
    for key in _MAP_KEYS:
        assert key in types
    for internal, _chinese in _KINDS:
        assert f"{internal}: \"{internal}\"" in types or f"{internal}: '{internal}'" in types
        assert internal in types
    assert "ELN_KIND_MAP[raw]" in eln_type
    assert "配方钉住" not in types
    assert "twin_id" not in types
    assert "twin_id" not in eln_type


def test_keeps_get_eln_and_no_columns() -> None:
    js = _js()
    refresh = _refresh()
    assert "/api/eln" in refresh
    assert 'method: "GET"' in refresh
    assert "paintEln" in refresh
    assert "row.columns" not in js.split("function paintEln")[1].split("async function refreshInbox")[0]
    assert "ask.args" not in _paint_eln()
    assert "row.columns" not in _paint_eln()


def test_refuses_to_claim_wired_or_g2() -> None:
    blob = _read("index.html") + _js() + _read("app.css") + NOTE.read_text(encoding="utf-8")
    for phrase in _CLAIM_PASS:
        assert phrase not in blob, phrase


def test_note_exists() -> None:
    assert NOTE.is_file(), NOTE
    text = NOTE.read_text(encoding="utf-8")
    assert "C-01l" in text
    assert "不算 G2" in text
    assert "中文种类" in text
    assert "不算接线" in text
    assert "配方钉住" in text
    assert "未认领" in text
    assert "Pennylane 已接线" not in text


def test_no_rooms_or_finder_or_fourth_handle() -> None:
    js = _js()
    html = _read("index.html")
    blob = html + js + _read("app.css")
    for word in _ROOMS:
        assert word not in blob
    for word in _WALLS:
        assert word not in blob
    assert "ionstack_twin_run" not in js
    assert "btn-twin" not in html
    assert "btn-twin" not in js
    assert "<select" not in html


def main() -> int:
    failed = 0
    for name, fn in (
        ("kind_label_has_chinese", test_kind_label_has_chinese),
        ("paint_eln_uses_label_not_raw_kind", test_paint_eln_uses_label_not_raw_kind),
        ("kind_map_keeps_english_keys", test_kind_map_keeps_english_keys),
        ("keeps_get_eln_and_no_columns", test_keeps_get_eln_and_no_columns),
        ("refuses_to_claim_wired_or_g2", test_refuses_to_claim_wired_or_g2),
        ("note_exists", test_note_exists),
        ("no_rooms_or_finder_or_fourth_handle", test_no_rooms_or_finder_or_fourth_handle),
    ):
        try:
            fn()
            print(f"ok  {name}")
        except Exception:
            failed += 1
            print(f"FAIL {name}")
            traceback.print_exc()
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
