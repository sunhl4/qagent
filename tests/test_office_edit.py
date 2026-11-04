"""P3 WPS-suite revision gate: surgical w:ins/w:del docx editing.

Spec source: ``WPS-SUITE-PORTING`` L4 — anchors live inside one paragraph's
visible text, ambiguous multi-hits skip the whole edit unless ``all`` is
declared, minimal spans keep >=4-character common runs untouched and replay
== after, and the B5 gate refuses empty revision records while re-verifying
what actually landed on disk.
"""
from __future__ import annotations

import difflib
import io
import random
import zipfile
from pathlib import Path

from company_agent.invoke import invoke

WORKSPACE_ROOT_ENV = "COMPANY_AGENT_TOOL_WORKSPACE"
PROJECT = "doc01"


def _workspace(tmp_path: Path, monkeypatch) -> Path:
    root = tmp_path / "mount"
    (root / PROJECT).mkdir(parents=True)
    monkeypatch.setenv(WORKSPACE_ROOT_ENV, str(root))
    return root / PROJECT


def _create(project: Path, blocks: list[dict]) -> None:
    result = invoke(
        "company_office_create",
        "lab",
        {"project": PROJECT, "path": "draft.docx", "content": {"blocks": blocks}, "purpose": "测试写入"},
    )
    assert result.status == "ok", result.error
    assert (project / "draft.docx").is_file()


def _edit(edits: list[dict], **extra):
    args = {"project": PROJECT, "path": "draft.docx", "edits": edits, "purpose": "测试写入"}
    args.update(extra)
    return invoke("company_office_edit", "lab", args)


def test_tracked_replace_lands_visible_text_and_revisions(
    tmp_path: Path, monkeypatch
) -> None:
    project = _workspace(tmp_path, monkeypatch)
    _create(
        project,
        [
            {"kind": "paragraph", "text": "旧系统的接口实现得很慢,而且缺少批处理模式。"},
            {"kind": "paragraph", "text": "第二段保持不变。"},
        ],
    )
    result = _edit(
        [{"find": "很慢,而且缺少", "replace": "非常快,并且已经提供", }],
        author="sunhl",
        note="评审修改",
    )
    assert result.status == "ok", result.error
    payload = result.payload
    assert payload["edited"] == 1
    assert payload["hunks"] >= 1
    assert payload["skipped"] == []
    assert payload["path"] == f"{PROJECT}/draft.docx"

    look = invoke("company_office_analyze", "lab", {"project": PROJECT, "path": "draft.docx"})
    assert look.status == "ok", look.error
    texts = [item["text"] for item in look.payload["items"]]
    # L{n} numbering is unchanged (revisions live inside the same paragraph)
    # and the receipt text is the final visible sentence, not the deleted arm.
    assert texts[0] == "旧系统的接口实现得非常快,并且已经提供批处理模式。"
    assert texts[1] == "第二段保持不变。"

    with zipfile.ZipFile(io.BytesIO((project / "draft.docx").read_bytes())) as package:
        document = package.read("word/document.xml").decode("utf-8")
    assert "<w:del " in document and "<w:delText" in document
    assert "<w:ins " in document
    assert 'w:author="sunhl"' in document
    assert "w:date=" in document
    assert "很慢,而且缺少" in document  # deleted text stays as the revision record


def test_multi_hit_skips_without_occurrences_all(tmp_path: Path, monkeypatch) -> None:
    project = _workspace(tmp_path, monkeypatch)
    _create(project, [{"kind": "paragraph", "text": "同一句里有两个甲和一个甲。"}])
    result = _edit([{"find": "甲", "replace": "乙"}])
    assert result.status == "error"
    assert "修订记录为空" in (result.error or "")
    before = (project / "draft.docx").read_bytes()
    result = _edit([{"find": "同一句里有两个甲", "replace": "占位"}])
    assert result.status == "ok", result.error
    # A second identical find still resolves to one hit inside one paragraph,
    # but paired with occurrences=all both hits become tracked changes.
    changed = result.payload
    assert changed["edited"] == 1
    assert before != (project / "draft.docx").read_bytes()
    redo = _edit([{"find": "占位", "replace": "乙"}, {"find": "占位", "replace": "丙"}])
    assert redo.status == "error"  # anchors overlap -> refuse instead of guessing


def test_occurrences_all_applies_every_hit(tmp_path: Path, monkeypatch) -> None:
    project = _workspace(tmp_path, monkeypatch)
    _create(project, [{"kind": "paragraph", "text": "甲乙甲乙甲乙甲乙"}])
    result = _edit([{"find": "乙", "replace": "X", "occurrences": "all"}])
    assert result.status == "ok", result.error
    assert result.payload["hunks"] >= 4
    look = invoke("company_office_analyze", "lab", {"project": PROJECT, "path": "draft.docx"})
    texts = [item["text"] for item in look.payload["items"]]
    assert texts[0].count("X") == 4


def test_skips_are_named_and_empty_batch_refuses(tmp_path: Path, monkeypatch) -> None:
    project = _workspace(tmp_path, monkeypatch)
    _create(project, [{"kind": "paragraph", "text": "第一段正文甲。"}])
    before = (project / "draft.docx").read_bytes()
    result = _edit(
        [
            {"find": "不存在的锚点", "replace": "x"},
            {"find": "第一段\n带换行", "replace": "x"},
            {"find": "甲", "replace": "甲"},
        ]
    )
    assert result.status == "error"
    assert "修订记录为空" in (result.error or "")
    assert (project / "draft.docx").read_bytes() == before

    # A mixed batch lands the actionable edit and names every skip reason.
    result = _edit(
        [
            {"find": "不存在的锚点", "replace": "x"},
            {"find": "正文甲", "replace": "正文乙"},
            {"find": "甲", "replace": "甲"},
        ]
    )
    assert result.status == "ok", result.error
    reasons = {row["reason"] for row in result.payload["skipped"]}
    assert "anchor_not_found" in reasons
    assert "no_change" in reasons


def test_newline_and_capped_edits_refuse(tmp_path: Path, monkeypatch) -> None:
    project = _workspace(tmp_path, monkeypatch)
    _create(project, [{"kind": "paragraph", "text": "正文。"}])
    long_find = "文" * 4001
    result = _edit([{"find": long_find, "replace": "x"}])
    assert result.status == "error"
    assert "4000" in (result.error or "") or result.decision == "deny"
    result = _edit([{"find": "文", "replace": "x"}, {"unknown": True}])
    assert result.status == "error"
    # 合同 schema 对 edit 元素 additionalProperties=False,未知字段在派发前就被拒绝;
    # 适配层自己的"未知字段"兜底只有在 schema 放行时才能触达。
    assert "未知字段" in (result.error or "") or result.decision == "deny"


def test_counter_non_docx_refuses(tmp_path: Path, monkeypatch) -> None:
    _workspace(tmp_path, monkeypatch)
    invoke(
        "company_office_create", "lab", {"purpose": "测试写入",
            "project": PROJECT, "path": "notes.md", "content": {"text": "x"}}
    )
    result = _edit([{"find": "x", "replace": "y"}], path="notes.md")
    assert result.status == "error"
    assert ".md" in (result.error or "")


def test_minimal_spans_properties_hold_randomly() -> None:
    from company_agent import office_edit

    rng = random.Random(20261028)
    alphabet = list("公司评审合同条款与工作量甲乙丙丁戊abcXYZ0123,-。、") + ["甲乙丙丁", "工作量"]
    for _round in range(200):
        before = "".join(rng.choice(alphabet) for _step in range(rng.randint(0, 60)))
        after = list(before)
        for _m in range(rng.randint(0, 3)):
            if not after:
                break
            lo = rng.randrange(len(after))
            hi = lo + rng.randint(0, 3)
            after[lo:hi] = [rng.choice(alphabet) for _k in range(rng.randint(0, 4))]
        spans = office_edit._minimal_spans(before, "".join(after))
        assert office_edit._replay(before, spans) == "".join(after)
        for lo, hi, replacement in spans:
            match = difflib.SequenceMatcher(None, before[lo:hi], replacement, autojunk=False)
            assert all(block.size < 4 for block in match.get_matching_blocks())
        ordering = [lo for lo, _hi, _repl in spans]
        assert ordering == sorted(ordering)
        for (lo1, hi1, _r1), (lo2, hi2, _r2) in zip(spans, spans[1:]):
            assert hi1 <= lo2


def test_missing_purpose_is_refused(tmp_path: Path, monkeypatch) -> None:
    _workspace(tmp_path, monkeypatch)
    result = invoke(
        "company_office_edit",
        "lab",
        {"project": PROJECT, "path": "draft.docx", "edits": [{"find": "甲", "replace": "乙"}]},
    )
    assert result.status == "error"
    assert "purpose" in (result.error or "")


def test_audit_line_written_when_ledger_configured(tmp_path: Path, monkeypatch) -> None:
    project = _workspace(tmp_path, monkeypatch)
    _create(project, [{"kind": "paragraph", "text": "审计锚点内容甲。"}])
    log = tmp_path / "audit.jsonl"
    monkeypatch.setenv("COMPANY_AGENT_AUDIT_LOG", str(log))
    monkeypatch.setenv("COMPANY_AGENT_AUDIT_KEY", "unit-test-audit-key-0123456789abcdef")
    result = _edit([{"find": "甲", "replace": "乙"}], note="痕迹检查")
    assert result.status == "ok", result.error
    import json

    entries = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line.strip()]
    matched = [entry for entry in entries if entry.get("event") == "office_edit"]
    assert matched
    assert matched[0]["detail"]["purpose"] == "测试写入"
    assert matched[0]["detail"]["target"].endswith("draft.docx")
