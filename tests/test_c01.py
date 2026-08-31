"""C-01: 3080 customer copy. Text assertions on html/js only; no browser."""

from __future__ import annotations

import re
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHELL = ROOT / "apps" / "customer-shell"
_ROOMS = ("实验室", "写算法", "签收台", "三房间")
_WALLS = ("Finder", "工作区门槛", "dsh-workspace", "dsh-web", "workspace chrome")


def _read(name: str) -> str:
    return (SHELL / name).read_text(encoding="utf-8")


def _blob() -> str:
    return _read("index.html") + _read("app.js") + _read("app.css")


def test_no_recipe_name_wall() -> None:
    html = _read("index.html")
    js = _read("app.js")
    css = _read("app.css")
    blob = html + js + css
    assert "a2_chem_pes" not in blob
    assert "a2_spin_shadow" not in blob
    assert "a1_closed_loop" not in blob
    assert "qem_triad" not in blob
    assert "不必报内部配方名" in html
    assert "你想做什么？" in js
    assert "先接上你们的本地模型" not in js
    assert "<select" not in html
    assert 'id="recipe"' not in html
    assert "PES" not in html


def test_inbox_and_approve_kept() -> None:
    html = _read("index.html")
    js = _read("app.js")
    assert "在办" in html
    assert 'id="inbox"' in html
    assert "批准上机" in js
    assert 'send("批准")' in js
    assert "先不上机" in js
    assert 'send("先不批")' in js
    assert "btn-twin" not in html
    assert "btn-twin" not in js


def test_no_finder_workspace_or_rooms() -> None:
    html = _read("index.html")
    js = _read("app.js")
    css = _read("app.css")
    blob = html + js + css
    for word in _WALLS:
        assert word not in blob
    for word in _ROOMS:
        assert word not in blob
    assert "sidebar.brand" not in html
    assert "sidebar.brand" not in css


def test_hpc_secret_password_not_painted() -> None:
    html = _read("index.html")
    js = _read("app.js")
    match = re.search(
        r'<input id="hpc_secret"[^>]*>',
        html,
    )
    assert match, "hpc_secret input missing"
    tag = match.group(0)
    assert 'type="password"' in tag
    assert 'placeholder="已保存"' in tag
    assert "hpc_secret" not in js.split("const FIELDS")[1].split("]")[0]
    assert 'el.value = ""' in js
    assert 'el.placeholder = "已保存"' in js
    assert "row.hpc_secret" not in js
    assert "row.llm_api_key" not in js
    assert "row.quantum_secret" not in js
    assert "本地大模型" in html
    assert "qdata_home" in html
    assert "staff-pack" in html


def main() -> int:
    failed = 0
    for name, fn in (
        ("no_recipe_name_wall", test_no_recipe_name_wall),
        ("inbox_and_approve_kept", test_inbox_and_approve_kept),
        ("no_finder_workspace_or_rooms", test_no_finder_workspace_or_rooms),
        ("hpc_secret_password_not_painted", test_hpc_secret_password_not_painted),
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
