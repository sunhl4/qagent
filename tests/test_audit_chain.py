"""P0 append-only HMAC-chained audit ledger."""

from __future__ import annotations

from pathlib import Path

import pytest

from company_agent.audit_chain import (
    KEY_ENV,
    LOG_ENV,
    AuditChainError,
    append,
    last_entry,
    verify,
)


@pytest.fixture()
def ledger(tmp_path: Path, monkeypatch) -> Path:
    log = tmp_path / "audit" / "chain.jsonl"
    monkeypatch.setenv(LOG_ENV, str(log))
    monkeypatch.setenv(KEY_ENV, "unit-test-audit-key-0123456789abcdef")
    return log


def test_append_requires_log_and_key(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv(LOG_ENV, raising=False)
    monkeypatch.setenv(KEY_ENV, "unit-test-audit-key-0123456789abcdef")
    with pytest.raises(AuditChainError):
        append("gate.deny")
    monkeypatch.setenv(LOG_ENV, str(tmp_path / "audit" / "chain.jsonl"))
    monkeypatch.delenv(KEY_ENV, raising=False)
    with pytest.raises(AuditChainError):
        append("gate.deny")
    monkeypatch.setenv(KEY_ENV, "short")
    with pytest.raises(AuditChainError):
        append("gate.deny")


def test_chain_appends_seq_and_links_back(ledger: Path) -> None:
    first = append("fence.deny", {"path": "../x", "reason": "越权路径拒绝"})
    second = append("fence.open", {"path": "notes.md", "reason": "围栏内读取"})
    assert first["seq"] == 1 and first["prev_hmac"] == "genesis"
    assert second["seq"] == 2 and second["prev_hmac"] == first["hmac"]
    assert second["hmac"] != second["prev_hmac"]
    result = verify()
    assert result == {"lines": 2, "intact": True, "first_bad_seq": 0}
    assert last_entry() == second


def test_verify_detects_a_tampered_detail(ledger: Path) -> None:
    append("fence.deny", {"path": "../x"})
    append("export.pdf", {"path": "contract.docx"})
    append("export.pdf", {"path": "brief.docx"})
    lines = ledger.read_text(encoding="utf-8").splitlines()
    lines[1] = lines[1].replace("contract.docx", "forged.docx")
    ledger.write_text("\n".join(lines) + "\n", encoding="utf-8")
    result = verify()
    assert result["intact"] is False
    assert result["first_bad_seq"] == 2
    assert result["lines"] == 3


def test_verify_detects_a_deleted_middle_line(ledger: Path) -> None:
    append("one")
    append("two")
    append("three")
    lines = ledger.read_text(encoding="utf-8").splitlines()
    del lines[1]
    ledger.write_text("\n".join(lines) + "\n", encoding="utf-8")
    result = verify()
    assert result["intact"] is False
    assert result["first_bad_seq"] == 2


def test_verify_detects_an_added_or_corrupt_line(ledger: Path) -> None:
    append("one")
    with ledger.open("ab") as handle:
        handle.write(b"{not json\n")
    result = verify()
    assert result["intact"] is False
    with pytest.raises(AuditChainError):
        last_entry()


def test_changing_the_key_breaks_the_chain(ledger: Path, monkeypatch) -> None:
    append("one")
    monkeypatch.setenv(KEY_ENV, "a-completely-different-key-value-42")
    result = verify()
    assert result["intact"] is False
    assert result["first_bad_seq"] == 1


def test_append_refuses_a_corrupt_head_and_non_object_details(ledger: Path) -> None:
    with pytest.raises(AuditChainError):
        append("event", "not an object")  # type: ignore[arg-type]
    append("one")
    append("two")
    lines = [line for line in ledger.read_text(encoding="utf-8").splitlines() if line]
    head = lines[-1].replace(lines[-1][:8], "abcdefgh")
    ledger.write_text(lines[0] + "\n" + head + "\n", encoding="utf-8")
    with pytest.raises(AuditChainError):
        append("three")


def test_events_survive_process_restart_with_a_fresh_reader(ledger: Path) -> None:
    append("a")
    append("b")
    assert last_entry()["seq"] == 2
    assert verify()["intact"] is True
