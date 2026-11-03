"""pptx slice gate: structured render, shape rewrite, B5 replay, honest caps.

Spec source: ``WPS-SUITE-PORTING`` §4.5 (L3) — structured layouts over full
page text boxes, WPS/PowerPoint-openable package, shape-level text rewrite
that fails loudly. The P1 ingestion module is the cross-check oracle for what
actually landed on disk, and the preview stubs re-derive their numbers from
the deck bytes the same way, so the §4.1 officecli bridge (stats page count,
shape enumeration, per-page screenshots, whole receipt refused on mismatch)
is pinned against deck truth without the vendored binary.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from company_agent import office_pptx
from company_agent.invoke import invoke

WORKSPACE_ROOT_ENV = "COMPANY_AGENT_TOOL_WORKSPACE"
PROJECT = "deck01"
CLI_ENV = "COMPANY_AGENT_OFFICECLI"
CLI_STUB = "officecli-stub.uqt"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_SLIDE_RE = re.compile(r"^ppt/slides/slide([0-9]+)\.xml$")
_A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
_P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"



def _workspace(tmp_path: Path, monkeypatch) -> Path:
    root = tmp_path / "mount"
    (root / PROJECT).mkdir(parents=True)
    monkeypatch.setenv(WORKSPACE_ROOT_ENV, str(root))
    return root / PROJECT


def _deck() -> dict:
    return {
        "slides": [
            {
                "kind": "title",
                "title": "季度演练汇报",
                "subtitle": "数据截至 2026-10-28",
            },
            {"kind": "agenda", "title": "议程", "bullets": ["背景", "数据", "结论"]},
            {"kind": "bullets", "title": "结论", "bullets": ["演练达标", "两条整改"]},
            {
                "kind": "two_column",
                "title": "对照",
                "left": ["左侧一条", "左侧两条"],
                "right": ["右侧一条"],
            },
            {
                "kind": "matrix",
                "title": "评分表",
                "matrix": [["指标", "结果"], ["可用性", "达标"], ["安全性", "达标"]],
            },
            {"kind": "checklist", "title": "验收项", "bullets": ["附件齐备", "签章有效"]},
        ]
    }


def _render(content: dict, name: str = "deck.pptx", **extra):
    args = {"project": PROJECT, "action": "render", "path": name, "content": content}
    args.update(extra)
    return invoke("company_office_pptx", "lab", args)


def _analyze(name: str = "deck.pptx"):
    return invoke("company_office_analyze", "lab", {"project": PROJECT, "path": name})


def test_render_structured_deck_and_oracle_matches(tmp_path: Path, monkeypatch) -> None:
    project = _workspace(tmp_path, monkeypatch)
    result = _render(_deck())
    assert result.status == "ok", result.error
    payload = result.payload
    assert payload["action"] == "render"
    assert payload["path"] == "deck01/deck.pptx"
    assert payload["slides"] == 6
    # title(2) + agenda(2) + bullets(2) + two_column(3) + matrix(标题框;表格不数) + checklist(2)
    assert payload["shapes"] == 12
    assert payload["applied"] == 0
    assert len(payload["sha256"]) == 64 and payload["bytes"] > 0
    assert payload["trust"] == "untrusted_reference_data"
    assert (project / "deck.pptx").is_file()

    oracle = _analyze()
    assert oracle.status == "ok", oracle.error
    texts = [item["text"] for item in oracle.payload["items"]]
    assert texts[0] == "季度演练汇报\n数据截至 2026-10-28"
    assert texts[1] == "议程\n1. 背景\n2. 数据\n3. 结论"
    assert "□ 附件齐备" in texts[5]


def test_render_is_deterministic_bytes(tmp_path: Path, monkeypatch) -> None:
    _workspace(tmp_path, monkeypatch)
    first = _render(_deck(), name="a.pptx")
    second = _render(_deck(), name="b.pptx")
    assert first.status == "ok" and second.status == "ok"
    assert first.payload["sha256"] == second.payload["sha256"]
    assert first.payload["bytes"] == second.payload["bytes"]


def test_render_refuses_existing_target_without_overwrite(tmp_path: Path, monkeypatch) -> None:
    _workspace(tmp_path, monkeypatch)
    first = _render(_deck())
    assert first.status == "ok", first.error
    again = _render(_deck())
    assert again.status == "error" and "已存在" in again.error
    overwrite = _render(_deck(), overwrite=True)
    assert overwrite.status == "ok", overwrite.error
    # 确定性字节:同内容重写得到同一 sha256。
    assert overwrite.payload["bytes"] == first.payload["bytes"]
    assert overwrite.payload["sha256"] == first.payload["sha256"]


def test_render_caps_and_shapes_refuse(tmp_path: Path, monkeypatch) -> None:
    _workspace(tmp_path, monkeypatch)
    many = {"slides": [{"kind": "bullets", "title": f"第{i}张", "bullets": ["一"]} for i in range(65)]}
    huge = _render(many)
    assert huge.status == "error" and "超过上限 64" in huge.error

    unknown = _render({"slides": [{"kind": "paper", "title": "x"}]})
    assert unknown.status == "error" and "kind 只支持" in unknown.error

    ragged = _render(
        {"slides": [{"kind": "matrix", "title": "x", "matrix": [["甲", "乙"], ["丙"]]}]}
    )
    assert ragged.status == "error" and "列数不一致" in ragged.error

    long_rows = _render({"slides": [{"kind": "bullets", "title": "x", "bullets": ["一"] * 9}]})
    assert long_rows.status == "error" and "超过上限 8" in long_rows.error

    empty_title = _render({"slides": [{"kind": "bullets", "title": "   ", "bullets": ["一"]}]})
    assert empty_title.status == "error" and "title 不能为空" in empty_title.error


def test_edit_rewrites_shape_text_and_oracle_sees(tmp_path: Path, monkeypatch) -> None:
    _workspace(tmp_path, monkeypatch)
    assert _render(_deck()).status == "ok"
    before = _analyze()

    result = invoke(
        "company_office_pptx",
        "lab",
        {
            "project": PROJECT,
            "action": "edit",
            "path": "deck.pptx",
            "edits": [{"slide": 3, "shape": 2, "text": "三条整改,其中一条关闭"}],
        },
    )
    assert result.status == "ok", result.error
    payload = result.payload
    assert payload["action"] == "edit" and payload["applied"] == 1
    assert payload["slides"] == 6 and payload["shapes"] == 12

    after = _analyze()
    assert after.status == "ok", after.error
    before_texts = [item["text"] for item in before.payload["items"]]
    after_texts = [item["text"] for item in after.payload["items"]]
    assert before_texts[2] == "结论\n演练达标\n两条整改"
    # shape 回写把该文本框折叠成单段;其余张不受影响。
    assert after_texts[2] == "结论\n三条整改,其中一条关闭"


def test_edit_refuses_whole_batch_on_bad_target(tmp_path: Path, monkeypatch) -> None:
    project = _workspace(tmp_path, monkeypatch)
    assert _render(_deck()).status == "ok"
    original = (project / "deck.pptx").read_bytes()
    bad = invoke(
        "company_office_pptx",
        "lab",
        {
            "project": PROJECT,
            "action": "edit",
            "path": "deck.pptx",
            "edits": [
                {"slide": 1, "shape": 1, "text": "新标题"},
                {"slide": 3, "shape": 9, "text": "不存在的形状"},
            ],
        },
    )
    assert bad.status == "error"
    assert "shape 9 不存在" in bad.error and "整批拒绝" in bad.error
    # all-or-nothing:第一处合法锚点也没有落盘
    assert (project / "deck.pptx").read_bytes() == original


def test_edit_input_guards(tmp_path: Path, monkeypatch) -> None:
    project = _workspace(tmp_path, monkeypatch)
    (project / "note.txt").write_bytes(b"hello")
    assert _render(_deck()).status == "ok"

    def _edit(edits, **extra):
        args = {"project": PROJECT, "action": "edit", "path": "deck.pptx", "edits": edits}
        args.update(extra)
        return invoke("company_office_pptx", "lab", args)

    newline = _edit([{"slide": 1, "shape": 1, "text": "两行\n文本"}])
    assert newline.status == "error" and "不接受换行" in newline.error

    with_content = _edit([{"slide": 1, "shape": 1, "text": "x"}], content={"slides": []})
    assert with_content.status == "error" and "content 只用于 render" in with_content.error

    no_shape = _edit([{"slide": 7, "shape": 1, "text": "x"}])
    assert no_shape.status == "error" and "slide 7 不存在" in no_shape.error

    with_overwrite = _edit(
        [{"slide": 1, "shape": 1, "text": "x"}], overwrite=True
    )
    assert with_overwrite.status == "error" and "不接受 overwrite" in with_overwrite.error

    text_file = invoke(
        "company_office_pptx",
        "lab",
        {
            "project": PROJECT,
            "action": "edit",
            "path": "note.txt",
            "edits": [{"slide": 1, "shape": 1, "text": "x"}],
        },
    )
    assert text_file.status == "error" and "只支持 .pptx" in text_file.error


def test_render_purity_and_edit_purity(tmp_path: Path, monkeypatch) -> None:
    _workspace(tmp_path, monkeypatch)
    with_edits = _render(_deck(), edits=[{"slide": 1, "shape": 1, "text": "x"}])
    assert with_edits.status == "error" and "edits 只用于 edit" in with_edits.error

    _render(_deck())
    with_content = invoke(
        "company_office_pptx",
        "lab",
        {
            "project": PROJECT,
            "action": "edit",
            "path": "deck.pptx",
            "edits": [{"slide": 1, "shape": 1, "text": "x"}],
            "content": {"slides": _deck()["slides"]},
        },
    )
    assert with_content.status == "error" and "content 只用于 render" in with_content.error


# ---------------------------------------------------------------- preview


def _fake_cli(tmp_path: Path, monkeypatch) -> Path:
    stub = tmp_path / CLI_STUB
    stub.write_bytes(b"stub")
    monkeypatch.setenv(CLI_ENV, str(stub))
    return stub


def _deck_rows(deck: Path) -> list[tuple[int, str]]:
    """(slide, joined a:t text) truth re-derived from the deck the stub sees."""

    entries: list[tuple[int, str]] = []
    with zipfile.ZipFile(deck) as package:
        for name in package.namelist():
            match = _SLIDE_RE.match(name)
            if match is not None:
                entries.append((int(match.group(1)), name))
        rows: list[tuple[int, str]] = []
        for number, name in sorted(entries):
            root = ET.fromstring(package.read(name))
            for sp in root.iter(f"{{{_P_NS}}}sp"):
                body = sp.find(f"{{{_P_NS}}}txBody")
                text = (
                    "".join(t.text or "" for t in body.iter(f"{{{_A_NS}}}t"))
                    if body is not None
                    else ""
                )
                rows.append((number, text))
    return rows


def _happy_runner(
    deck: Path, pages_override: int | None = None, png_bad: bool = False
):
    rows = _deck_rows(deck)
    pages = pages_override if pages_override is not None else len({s for s, _ in rows})

    def runner(command: list[str], _cwd: str) -> tuple[int, bytes]:
        # command: [engine, "view"|"query", deck, "stats"|"screenshot"|"shape", ...]
        if command[3] == "stats":
            return 0, json.dumps({"slides": pages}).encode("utf-8")
        if command[1] == "query":
            shapes = [
                {"path": f"/slide[{slide}]/box[{index}]", "text": text, "x": 0, "y": 0}
                for index, (slide, text) in enumerate(rows, start=1)
            ]
            return 0, json.dumps({"shapes": shapes}).encode("utf-8")
        out = Path(command[command.index("-o") + 1])
        out.write_bytes(b"not-a-png" if png_bad else PNG_MAGIC + b"fake shot")
        return 0, b""

    return runner


def test_preview_bridge_reports_pages_shapes_and_shots(tmp_path: Path, monkeypatch) -> None:
    project = _workspace(tmp_path, monkeypatch)
    rendered = _render(_deck())
    assert rendered.status == "ok", rendered.error
    _fake_cli(tmp_path, monkeypatch)
    monkeypatch.setattr(office_pptx, "_run", _happy_runner(project / "deck.pptx"))

    result = invoke(
        "company_office_pptx",
        "lab",
        {"project": PROJECT, "action": "preview", "path": "deck.pptx"},
    )
    assert result.status == "ok", result.error
    payload = result.payload
    assert payload["action"] == "preview"
    assert payload["slides"] == 6 and payload["shapes"] == 12 and payload["applied"] == 0
    assert payload["officecli"] == CLI_STUB
    deck_bytes = (project / "deck.pptx").read_bytes()
    assert payload["sha256"] == hashlib.sha256(deck_bytes).hexdigest()
    assert payload["bytes"] == len(deck_bytes)
    assert [shot["page"] for shot in payload["screenshots"]] == [1, 2, 3, 4, 5, 6]
    for shot in payload["screenshots"]:
        on_disk = project / shot["path"].split("/", 1)[1]
        raw = on_disk.read_bytes()
        assert raw.startswith(PNG_MAGIC) and shot["bytes"] == len(raw)
        assert shot["path"] == f"deck01/preview/deck/slide-{shot['page']}.png"
    detail = payload["shapes_detail"]
    assert detail[0] == {"slide": 1, "shape": 1, "text": "季度演练汇报"}
    assert detail[1] == {"slide": 1, "shape": 2, "text": "数据截至 2026-10-28"}
    assert detail[-1] == {"slide": 6, "shape": 2, "text": "□ 附件齐备□ 签章有效"}


def test_preview_replaces_its_own_shots_and_drops_stale(tmp_path: Path, monkeypatch) -> None:
    project = _workspace(tmp_path, monkeypatch)
    _fake_cli(tmp_path, monkeypatch)
    long_deck = {
        "slides": [{"kind": "bullets", "title": f"第{i}张", "bullets": ["一"]} for i in range(3)]
    }
    assert _render(long_deck).status == "ok"
    monkeypatch.setattr(office_pptx, "_run", _happy_runner(project / "deck.pptx"))
    first = invoke(
        "company_office_pptx",
        "lab",
        {"project": PROJECT, "action": "preview", "path": "deck.pptx"},
    )
    assert first.status == "ok", first.error
    shots_dir = project / "preview" / "deck"
    assert (shots_dir / "slide-3.png").is_file()

    assert (
        _render(
            {"slides": [{"kind": "bullets", "title": "只有一张", "bullets": ["一"]}]},
            overwrite=True,
        ).status
        == "ok"
    )
    monkeypatch.setattr(office_pptx, "_run", _happy_runner(project / "deck.pptx"))
    second = invoke(
        "company_office_pptx",
        "lab",
        {"project": PROJECT, "action": "preview", "path": "deck.pptx"},
    )
    assert second.status == "ok", second.error
    assert [shot["page"] for shot in second.payload["screenshots"]] == [1]
    assert (shots_dir / "slide-1.png").is_file()
    for stale in (2, 3):
        assert not (shots_dir / f"slide-{stale}.png").exists()


def test_preview_input_guards_refuse_before_the_bridge(tmp_path: Path, monkeypatch) -> None:
    project = _workspace(tmp_path, monkeypatch)
    (project / "note.txt").write_bytes(b"hello")
    assert _render(_deck()).status == "ok"
    monkeypatch.delenv(CLI_ENV, raising=False)

    def _preview(**extra):
        args = {"project": PROJECT, "action": "preview", "path": "deck.pptx"}
        args.update(extra)
        return invoke("company_office_pptx", "lab", args)

    edits = _preview(edits=[{"slide": 1, "shape": 1, "text": "x"}])
    assert edits.status == "error" and "edits 只用于 edit" in edits.error
    content = _preview(content={"slides": []})
    assert content.status == "error" and "content 只用于 render" in content.error
    overwrite = _preview(overwrite=True)
    assert overwrite.status == "error" and "不接受 overwrite" in overwrite.error
    text_file = invoke(
        "company_office_pptx",
        "lab",
        {"project": PROJECT, "action": "preview", "path": "note.txt"},
    )
    assert text_file.status == "error" and "只支持 .pptx" in text_file.error
    missing = invoke(
        "company_office_pptx",
        "lab",
        {"project": PROJECT, "action": "preview", "path": "absent.pptx"},
    )
    assert missing.status == "error" and "not readable" in missing.error
    assert not (project / "preview").exists()


def test_preview_refuses_without_officecli(tmp_path: Path, monkeypatch) -> None:
    project = _workspace(tmp_path, monkeypatch)
    assert _render(_deck()).status == "ok"
    monkeypatch.delenv(CLI_ENV, raising=False)
    monkeypatch.setattr(shutil, "which", lambda name: None)

    result = invoke(
        "company_office_pptx",
        "lab",
        {"project": PROJECT, "action": "preview", "path": "deck.pptx"},
    )
    assert result.status == "error"
    assert "未找到 officecli" in result.error and "不出替身" in result.error
    assert not (project / "preview").exists()


def test_preview_mismatches_refuse(tmp_path: Path, monkeypatch) -> None:
    project = _workspace(tmp_path, monkeypatch)
    assert _render(_deck()).status == "ok"
    deck = project / "deck.pptx"
    _fake_cli(tmp_path, monkeypatch)

    monkeypatch.setattr(office_pptx, "_run", _happy_runner(deck, pages_override=5))
    pages = invoke(
        "company_office_pptx",
        "lab",
        {"project": PROJECT, "action": "preview", "path": "deck.pptx"},
    )
    assert pages.status == "error" and "页数" in pages.error and "不一致" in pages.error
    assert not (project / "preview").exists()

    def one_short(command: list[str], _cwd: str) -> tuple[int, bytes]:
        if command[3] == "stats":
            return 0, json.dumps({"slides": 6}).encode("utf-8")
        if command[1] == "query":
            shapes = [
                {"path": f"/slide[{slide}]/box[{index}]", "text": text, "x": 0, "y": 0}
                for index, (slide, text) in enumerate(_deck_rows(deck)[:-1], start=1)
            ]
            return 0, json.dumps({"shapes": shapes}).encode("utf-8")
        raise AssertionError("shots must not run once enumeration refuses")

    monkeypatch.setattr(office_pptx, "_run", one_short)
    shapes = invoke(
        "company_office_pptx",
        "lab",
        {"project": PROJECT, "action": "preview", "path": "deck.pptx"},
    )
    assert shapes.status == "error" and "文本框" in shapes.error and "不一致" in shapes.error

    monkeypatch.setattr(office_pptx, "_run", lambda _cmd, _cwd: (0, b"not-json"))
    garbage = invoke(
        "company_office_pptx",
        "lab",
        {"project": PROJECT, "action": "preview", "path": "deck.pptx"},
    )
    assert garbage.status == "error" and "不是合法 JSON" in garbage.error

    monkeypatch.setattr(office_pptx, "_run", _happy_runner(deck, png_bad=True))
    bad_png = invoke(
        "company_office_pptx",
        "lab",
        {"project": PROJECT, "action": "preview", "path": "deck.pptx"},
    )
    assert bad_png.status == "error" and "不是合法 PNG" in bad_png.error


def _spy_never_runs(command: list[str], _cwd: str) -> tuple[int, bytes]:
    raise AssertionError("the binary must not run once a cap refuses")


def test_preview_slide_cap_refuses_before_the_bridge(tmp_path: Path, monkeypatch) -> None:
    project = _workspace(tmp_path, monkeypatch)
    _fake_cli(tmp_path, monkeypatch)
    built = []
    for number in range(1, 66):
        shape_xmls, texts, _sp = office_pptx._slide_shapes(
            {"kind": "bullets", "title": f"第{number}张", "bullets": ["一"]}, number
        )
        built.append((office_pptx.XML_HEAD + office_pptx._sld_document("".join(shape_xmls)), texts))
    (project / "big.pptx").write_bytes(office_pptx._package(built))
    monkeypatch.setattr(office_pptx, "_run", _spy_never_runs)

    big = invoke(
        "company_office_pptx",
        "lab",
        {"project": PROJECT, "action": "preview", "path": "big.pptx"},
    )
    assert big.status == "error" and "超过上限 64" in big.error
    assert not (project / "preview").exists()


def test_preview_shapes_cap_refuses_before_the_bridge(tmp_path: Path, monkeypatch) -> None:
    project = _workspace(tmp_path, monkeypatch)
    _fake_cli(tmp_path, monkeypatch)
    (project / "dense.pptx").write_bytes(
        office_pptx._package([(office_pptx.XML_HEAD + office_pptx._sld_document(""), ["x"])])
    )
    dense_root = ET.fromstring(
        office_pptx.XML_HEAD
        + f'<p:sld xmlns:a="{_A_NS}" xmlns:p="{_P_NS}"><p:cSld><p:spTree><p:nvGrpSpPr/><p:grpSpPr/>'
        + "".join(
            f"<p:sp><p:txBody><a:p><a:r><a:t>框{index}</a:t></a:r></a:p></p:txBody></p:sp>"
            for index in range(201)
        )
        + "</p:spTree></p:cSld></p:sld>"
    )

    def fake_load(package):
        numbers, _roots = _load_truth(package)
        return numbers, {1: dense_root}

    _load_truth = office_pptx._load_slides
    monkeypatch.setattr(office_pptx, "_load_slides", fake_load)
    monkeypatch.setattr(office_pptx, "_run", _spy_never_runs)

    dense = invoke(
        "company_office_pptx",
        "lab",
        {"project": PROJECT, "action": "preview", "path": "dense.pptx"},
    )
    assert dense.status == "error" and "超过枚举上限 200" in dense.error


def test_preview_detail_budget_refuses(tmp_path: Path, monkeypatch) -> None:
    _workspace(tmp_path, monkeypatch)
    assert _render(_deck()).status == "ok"
    monkeypatch.delenv(CLI_ENV, raising=False)
    long_row = "很长的文本" * 50
    rows = [(1, index, long_row) for index in range(1, 201)]
    clipped = [
        {"slide": 1, "shape": index, "text": long_row[: office_pptx._DETAIL_TEXT_CHARS]}
        for _slide, index, _row in rows
    ]
    assert (
        len(json.dumps(clipped, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        > office_pptx.DETAIL_BUDGET
    )
    monkeypatch.setattr(office_pptx, "_deck_shapes", lambda _roots: rows)

    budget = invoke(
        "company_office_pptx",
        "lab",
        {"project": PROJECT, "action": "preview", "path": "deck.pptx"},
    )
    assert budget.status == "error" and "回执预算" in budget.error


def test_preview_refuses_a_deck_mutated_mid_run(tmp_path: Path, monkeypatch) -> None:
    project = _workspace(tmp_path, monkeypatch)
    assert _render(_deck()).status == "ok"
    deck = project / "deck.pptx"
    _fake_cli(tmp_path, monkeypatch)
    rows = _deck_rows(deck)  # capture the pre-mutation truth for the enumeration gate

    def mutator(command: list[str], _cwd: str) -> tuple[int, bytes]:
        if command[3] == "stats":
            with deck.open("ab") as stream:  # a concurrent writer lands mid-run
                stream.write(b"corrupted-tail")
            return 0, json.dumps({"slides": 6}).encode("utf-8")
        if command[1] == "query":
            shapes = [
                {"path": f"/slide[{slide}]/box[{index}]", "text": text, "x": 0, "y": 0}
                for index, (slide, text) in enumerate(rows, start=1)
            ]
            return 0, json.dumps({"shapes": shapes}).encode("utf-8")
        out = Path(command[command.index("-o") + 1])
        out.write_bytes(PNG_MAGIC + b"shot")
        return 0, b""

    monkeypatch.setattr(office_pptx, "_run", mutator)
    result = invoke(
        "company_office_pptx",
        "lab",
        {"project": PROJECT, "action": "preview", "path": "deck.pptx"},
    )
    assert result.status == "error" and "并发修改" in result.error
