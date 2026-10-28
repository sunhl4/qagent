from __future__ import annotations

import json
import os

import pytest

from company_agent.access_runtime import access_environment, start_gateways, stop_gateways
from company_agent.invoke import invoke


def test_private_workspace_settings_feed_both_connections(tmp_path):
    config = tmp_path / "workspace.json"
    config.write_text(json.dumps({"hpcUser": "saved-user", "hpcHost": "saved.example",
                                  "cloudKey": "private-fixture", "cloudApi": "http://cloud.example:8003"}))
    env = access_environment({"COMPANY_AGENT_DEPLOYMENT_MODE": "development",
                              "UQC_WORKSPACE_CONFIG": str(config), "HPC_USER": "old-user"})
    assert env["COMPANY_AGENT_HPC_USER"] == "saved-user"
    assert env["COMPANY_AGENT_HPC_HOST"] == "saved.example"
    assert env["UQC_CLOUD_API_KEY"] == "private-fixture"
    assert "COMPANY_AGENT_HPC_TOKEN" not in env


def test_local_gateways_are_development_only():
    with pytest.raises(ValueError):
        access_environment({"COMPANY_AGENT_DEPLOYMENT_MODE": "production"})


def test_explicit_provider_configuration_is_preserved(monkeypatch):
    env = {"COMPANY_AGENT_HPC_INVOKE_URL": "https://authorized.example/invoke",
           "COMPANY_AGENT_HPC_USER": "user", "COMPANY_AGENT_HPC_HOST": "login.example"}
    assert start_gateways(env) == []
    assert env["COMPANY_AGENT_HPC_INVOKE_URL"] == "https://authorized.example/invoke"


def test_managed_gateways_reach_real_kernel_contracts(monkeypatch):
    from company_agent import cloud, hpc_ssh

    for key in ("COMPANY_AGENT_HPC_INVOKE_URL", "COMPANY_AGENT_CLOUD_INVOKE_URL"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(hpc_ssh, "run_ssh", lambda *_args, **_kw: hpc_ssh.SshResult("", "", 0, False))
    monkeypatch.setattr(cloud, "worker", lambda *_args: {"provider": "uqc-cloud", "devices": []})
    env = {"COMPANY_AGENT_HPC_USER": "fixture-user", "COMPANY_AGENT_HPC_HOST": "fixture.example",
           "UQC_CLOUD_API_KEY": "private-fixture", "UQC_CLOUD_API_BASE_URL": "http://fixture.example:8003",
           "UQC_CLOUD_PROBE_PYTHON": "/usr/bin/python3"}
    original = dict(os.environ)
    servers = start_gateways(env)
    try:
        assert len(servers) == 2
        assert invoke("hpc_queue", "lab", {}).status == "ok"
        assert invoke("quantum_cloud_devices", "lab", {}).status == "ok"
        assert env["COMPANY_AGENT_HPC_TOKEN"] != env["COMPANY_AGENT_CLOUD_TOKEN"]
        assert env["COMPANY_AGENT_HPC_INVOKE_URL"].startswith("http://127.0.0.1:")
    finally:
        stop_gateways(servers)
        os.environ.clear()
        os.environ.update(original)
