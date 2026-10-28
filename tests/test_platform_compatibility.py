"""Opt-in compatibility gate against the actual sibling platform, never a science SDK import."""
from __future__ import annotations

import json
import os
import selectors
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

import pytest

from company_agent.invoke import invoke

ROOT = Path(__file__).resolve().parents[1]
PLATFORM_SOURCE = os.environ.get("COMPANY_AGENT_PLATFORM_SOURCE")
pytestmark = pytest.mark.platform_compatibility


def test_real_platform_http_catalog_execution_and_persistence(tmp_path, monkeypatch):
    assert PLATFORM_SOURCE, "explicit COMPANY_AGENT_PLATFORM_SOURCE required for dual-repository gate"
    source = Path(PLATFORM_SOURCE).resolve(strict=True)
    assert (
        (source / "src/uniqon/adapters/company_agent_provider.py").is_file()
        or (source / "src/company_quantum/adapters/company_agent_provider.py").is_file()
    ), "platform adapter must exist under uniqon or company_quantum"
    # The platform lives in its own process. Agent runtime imports remain independent.
    process = subprocess.Popen(
        [sys.executable, str(ROOT / "tests/fixtures/platform-provider.py"), str(tmp_path / "assets.sqlite3")],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(source / "src"), "PYTHONDONTWRITEBYTECODE": "1"},
    )
    try:
        with selectors.DefaultSelector() as ready:
            ready.register(process.stdout, selectors.EVENT_READ)
            assert ready.select(timeout=15), "platform fixture did not become ready"
        line = process.stdout.readline()
        assert line, "platform fixture exited before becoming ready"
        url = json.loads(line)["url"]
        monkeypatch.setenv("COMPANY_QUANTUM_PLATFORM_INVOKE_URL", url)
        monkeypatch.setenv("COMPANY_QUANTUM_PLATFORM_TOKEN", "synthetic-agent-contract-token-a")

        def call(tool, arguments):
            return asdict(invoke(tool, "algo", arguments))

        query = "external.agent-contract-fixture"
        first = call("quantum_algorithm_catalog", {"query": query, "limit": 1})
        assert first["status"] == "ok", first
        page = first["payload"]
        assert page["complete"] is False and len(page["next_cursor"]) <= 256
        assert [(row["version"], row["runnable"]) for row in page["algorithms"]] == [("1.0", True)]
        second = call("quantum_algorithm_catalog", {"cursor": page["next_cursor"]})
        assert second["status"] == "ok", second
        assert [(row["version"], row["runnable"]) for row in second["payload"]["algorithms"]] == [
            ("2.0", False)
        ]
        assert call("quantum_algorithm_catalog", {
            "cursor": page["next_cursor"], "query": "changed-query",
        })["status"] == "error"
        base = {"algorithm": page["algorithms"][0]["id"], "component_version": "1.0",
                "catalog_version": page["catalog_version"], "parameters": {"count": 2}}
        for patch in ({"component_version": "2.0"}, {"catalog_version": "cat_stale"},
                      {"parameters": {"count": 5}}, {"parameters": {"unexpected": True}}):
            assert call("quantum_algorithm_run", {**base, **patch})["status"] == "error"
        run = call("quantum_algorithm_run", base)
        assert run["status"] == "ok", run
        asset = run["payload"]["asset_id"]
        circuit = run["payload"]["circuit_id"]
        assert run["payload"]["summary"]["metrics"]["items"][0]["value"] == 2
        assert call("quantum_asset_get", {"asset_id": asset})["status"] == "ok"
        metrics = call("quantum_asset_metrics", {"asset_id": asset})
        assert metrics["status"] == "ok", metrics
        assert metrics["payload"]["summary"]["metrics"]["items"][0]["value"] == 2
        # The managed analysis template consumes the fetched platform table.
        audit = call("company_analysis_render", {
            "template": "metric-summary", "metrics": metrics["payload"]["summary"]["metrics"],
        })
        assert audit["status"] == "ok" and audit["payload"]["status"] == "complete"
        assert call("quantum_circuit_export", {"asset_id": asset})["payload"]["circuit_id"] == circuit
        assert call("quantum_asset_list", {})["payload"]["assets"][0]["asset_id"] == asset
        assert "synthetic-opaque" not in json.dumps(run)

        added = call("quantum_algorithm_catalog", {"query": "external.agent-contract-added"})
        assert added["status"] == "ok", added
        extra = added["payload"]
        assert call("quantum_algorithm_run", {
            **base, "algorithm": extra["algorithms"][0]["id"], "catalog_version": extra["catalog_version"],
        })["status"] == "ok"
        monkeypatch.setenv("COMPANY_QUANTUM_PLATFORM_TOKEN", "synthetic-agent-contract-token-b")
        assert call("quantum_asset_get", {"asset_id": asset})["status"] == "error"
        assert call("quantum_asset_metrics", {"asset_id": asset})["status"] == "error"
        assert call("quantum_algorithm_run", base)["status"] == "error"
        assert call("quantum_asset_list", {})["payload"]["assets"] == []
        monkeypatch.setenv("COMPANY_QUANTUM_PLATFORM_TOKEN", "invalid-synthetic-token")
        assert call("quantum_algorithm_catalog", {})["status"] == "error"
        output, error = process.communicate(input="stop\n", timeout=10)
        assert process.returncode == 0, error
        counters = json.loads(output)
        assert counters == {"executions": 2, "authorizations": 3, "persisted": 2, "reopen_matches": True}
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate(timeout=5)
