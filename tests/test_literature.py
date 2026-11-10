from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from company_agent.invoke import invoke
from company_agent.literature import LiteratureError, clock_gate
from company_agent.literature_card import draft_scale_card

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "literature"
TOOLS = (
    "company_literature_search",
    "company_literature_fetch",
    "company_literature_index",
)
FORBIDDEN = (
    "company_research_run",
    "hpc_submit",
    "quantum_device_run",
    "algorithm.run",
)


def test_literature_adapter_does_not_name_run_or_submit_tools() -> None:
    for name in ("literature.py", "literature_source.py", "literature_card.py"):
        text = (ROOT / "src" / "company_agent" / name).read_text(encoding="utf-8")
        for token in FORBIDDEN:
            assert token not in text


def test_search_fetch_and_index_return_counts_without_tex(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("COMPANY_AGENT_TOOL_WORKSPACE", str(tmp_path))
    records = {
        "records": [
            {"paper_id": "demo1", "source": "arxiv", "year": 2024},
            {"paper_id": "old1", "source": "openalex", "year": 1990},
            *({"paper_id": f"s{index}", "source": "semantic_scholar", "year": 2024} for index in range(13)),
        ]
    }
    (tmp_path / "search.json").write_text(json.dumps(records), encoding="utf-8")
    shutil.copytree(FIXTURE, tmp_path / "paper")
    searched = invoke("company_literature_search", "lab", {
        "query": "synthetic source",
        "fixture": "search.json",
        "year_from": 2000,
    })
    assert searched.status == "ok"
    assert searched.payload["exhaustive"] is False
    assert searched.payload["citation_hops"] == 1
    assert "old1" not in searched.payload["paper_ids"]
    assert searched.payload["truncated"] is True
    semantic = next(item for item in searched.payload["sources"] if item["source"] == "semantic_scholar")
    assert semantic["returned"] == 12
    assert "synthetic source" not in json.dumps(searched.payload)

    fetched = invoke("company_literature_fetch", "lab", {"paper_id": "demo1", "fixture": "paper"})
    assert fetched.status == "ok"
    assert fetched.payload == {
        "paper_id": "demo1",
        "source_kind": "arxiv_src",
        "version": "v1",
        "files": fetched.payload["files"],
        "bytes": fetched.payload["bytes"],
    }
    assert fetched.payload["files"] >= 3
    assert "\\approx" not in json.dumps(fetched.payload)

    indexed = invoke("company_literature_index", "lab", {"paper_id": "demo1"})
    assert indexed.status == "ok"
    payload = indexed.payload
    assert payload["formula_ids"] == ["eq:energy", "eq:bound", "eq:macro"]
    assert payload["formula_count"] == 3
    assert payload["attachment_count"] == 2
    assert payload["code_count"] == 1
    assert payload["platform_metric_eligible"] is False
    assert payload["clock_admitted"] is False
    encoded = json.dumps(payload)
    assert "\\begin" not in encoded
    assert "\\approx" not in encoded
    assert "github.com" not in encoded
    ledger = json.loads((tmp_path / "literature" / "demo1" / "formula-ledger.json").read_text(encoding="utf-8"))
    by_anchor = {entry["anchor"]: entry for entry in ledger["entries"]}
    assert "\\approx" in by_anchor["eq:energy"]["tex"]
    assert "\\lesssim" in by_anchor["eq:bound"]["tex"]
    assert by_anchor["eq:macro"]["fidelity"] == "macro_unexpanded"
    gate = clock_gate(payload)
    assert gate["admitted"] is False


def test_ineligible_index_is_not_sent_to_research_run(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("COMPANY_AGENT_TOOL_WORKSPACE", str(tmp_path))
    monkeypatch.setenv("COMPANY_AGENT_RESEARCH_STATE", str(tmp_path / "clock"))
    called: list[str] = []

    def refuse(*_args, **_kwargs):
        called.append("run")
        raise AssertionError("literature index must stay outside the research clock")

    monkeypatch.setattr("company_agent.research_clock.run_spec", refuse)
    shutil.copytree(FIXTURE, tmp_path / "paper")
    fetched = invoke("company_literature_fetch", "lab", {"paper_id": "demo1", "fixture": "paper"})
    indexed = invoke("company_literature_index", "lab", {"paper_id": "demo1"})
    assert fetched.status == "ok"
    assert indexed.status == "ok"
    assert clock_gate(indexed.payload)["admitted"] is False
    compiled = invoke("company_research_compile", "lab", {
        "tenant_id": "team-a",
        "experiment_id": "exp-val",
        "task_id": "task-val",
        "project_id": "proj-1",
        "hypothesis": "the internal baseline stays inside tolerance",
        "falsifier": "val_loss moves by more than the tolerance",
        "baseline_name": "recorded",
        "baseline_source": "internal",
        "baseline_metric": 1.0,
        "baseline_reproduced": True,
        "changed_path": "src/train/scheduler.py",
        "primary_metric": "val_loss",
        "direction": "minimize",
        "resource_type": "cpu",
        "max_cost": 1,
        "max_attempts": 1,
    })
    assert compiled.status == "ok"
    assert compiled.payload["primary_metric"] == "val_loss"
    assert called == []


def test_fetch_rejects_archive_escape(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("COMPANY_AGENT_TOOL_WORKSPACE", str(tmp_path))
    import io
    import tarfile

    payload = io.BytesIO()
    with tarfile.open(fileobj=payload, mode="w:gz") as archive:
        data = b"nope"
        info = tarfile.TarInfo("../escape.tex")
        info.size = len(data)
        archive.addfile(info, io.BytesIO(data))
    (tmp_path / "escape.tar.gz").write_bytes(payload.getvalue())
    result = invoke("company_literature_fetch", "lab", {"paper_id": "demo1", "fixture": "escape.tar.gz"})
    assert result.status == "error"
    assert result.error == "archive rejected"
    assert not (tmp_path / "escape.tex").exists()


def test_visibility_and_bad_envelope(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("COMPANY_AGENT_TOOL_WORKSPACE", str(tmp_path))
    (tmp_path / "search.json").write_text(
        json.dumps({"records": [{"paper_id": "demo1", "source": "arxiv"}]}),
        encoding="utf-8",
    )
    search_args = {"query": "bounded", "fixture": "search.json"}
    calls = {
        "company_literature_search": search_args,
        "company_literature_fetch": {"paper_id": "demo1", "fixture": "search.json"},
        "company_literature_index": {"paper_id": "demo1"},
    }
    for preset in ("boot", "sign"):
        for tool, args in calls.items():
            result = invoke(tool, preset, args)
            assert result.status == "denied", (preset, tool, result.status, result.error)
    assert invoke("company_literature_fetch", "algo", {"paper_id": "demo1", "fixture": "search.json"}).status == "denied"
    assert invoke("company_literature_search", "algo", search_args).status == "ok"
    assert invoke("company_literature_index", "algo", {"paper_id": "missing"}).status == "error"
    extra = invoke("company_literature_search", "lab", {**search_args, "note": "extra"})
    assert extra.status == "error"
    unknown = invoke("company_literature_missing", "lab", {})
    assert unknown.status == "denied"


def test_scale_card_opens_a_new_handoff(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("COMPANY_AGENT_RESEARCH_STATE", str(tmp_path / "clock"))
    monkeypatch.setenv("COMPANY_AGENT_WORK_ITEM_DB", str(tmp_path / "work.sqlite3"))
    local = {
        "tenant_id": "team-a",
        "experiment_id": "exp-local",
        "task_id": "task-local",
        "project_id": "proj-1",
        "hypothesis": "warmup lowers validation loss",
        "falsifier": "the metric does not improve",
        "baseline_name": "recorded",
        "baseline_source": "internal",
        "baseline_metric": 1.0,
        "baseline_reproduced": True,
        "baseline_train_time_seconds": 3600,
        "changed_path": "src/train/scheduler.py",
        "primary_metric": "val_loss",
        "direction": "minimize",
        "resource_type": "cpu",
        "max_cost": 1,
        "max_attempts": 1,
        "idempotency_key": "local-1",
    }
    draft = draft_scale_card(
        local,
        experiment_id="exp-scale",
        idempotency_key="scale-1",
        hypothesis="more nodes keep the same validation loss",
        falsifier="the metric moves outside tolerance",
    )
    assert draft["experiment_id"] == "exp-scale"
    assert draft["idempotency_key"] == "scale-1"
    assert draft["resource_type"] == "hpc"
    assert draft["primary_metric"] == "val_loss"
    assert draft["baseline_reproduced"] is False
    assert "baseline_train_time_seconds" not in draft
    assert "hpc_submit" not in json.dumps(draft)

    human = {**draft, "baseline_reproduced": True}
    compiled = invoke(
        "company_research_compile",
        "lab",
        {key: value for key, value in human.items() if key != "idempotency_key"},
    )
    assert compiled.status == "ok", compiled.error
    assert compiled.payload["approval_required"] is True
    assert compiled.payload["primary_metric"] == "val_loss"
    result = invoke("company_research_run", "lab", human, approved=True)
    assert result.status == "ok", result.error
    assert result.payload["next_tool"] == "hpc_submit"
    assert result.payload["approval_still_required"] is True
    assert result.payload["resource_type"] == "hpc"


def test_scale_card_stays_inside_the_experiment_card() -> None:
    local = {
        "tenant_id": "team-a",
        "experiment_id": "exp-local",
        "task_id": "task-local",
        "hypothesis": "warmup lowers validation loss",
        "falsifier": "the metric does not improve",
        "baseline_name": "recorded",
        "baseline_source": "internal",
        "baseline_metric": 1.0,
        "baseline_reproduced": True,
        "baseline_train_time_seconds": 3600,
        "changed_path": " src/train/scheduler.py ",
        "primary_metric": "val_loss",
        "direction": "minimize",
        "resource_type": "gpu",
        "max_cost": 1,
        "max_attempts": 1,
        "idempotency_key": "local-1",
        "min_seeds": 3,
    }
    def open_card(
        card: dict[str, object] | None = None,
        hypothesis: str = "more nodes keep the same validation loss",
    ) -> dict[str, object]:
        return draft_scale_card(
            local if card is None else card,
            experiment_id="exp-scale",
            idempotency_key="scale-1",
            hypothesis=hypothesis,
            falsifier="the metric moves outside tolerance",
        )

    draft = open_card()
    assert draft["changed_path"] == "src/train/scheduler.py"
    assert draft["min_seeds"] == 3
    assert "project_id" not in draft
    assert "baseline_train_time_seconds" not in draft
    assert draft["baseline_reproduced"] is False

    with pytest.raises(LiteratureError, match="research cost"):
        open_card({**local, "max_cost": 0})
    with pytest.raises(LiteratureError, match="local baseline"):
        open_card({**local, "resource_type": "qpu"})
    with pytest.raises(LiteratureError, match="changed_path"):
        open_card({**local, "changed_path": "src/../secret.py"})
    with pytest.raises(LiteratureError, match="new hypothesis"):
        open_card(hypothesis="Warmup lowers validation loss")
