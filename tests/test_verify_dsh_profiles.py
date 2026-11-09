from __future__ import annotations

import copy
import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "verify_dsh_profiles",
    ROOT / "scripts/verify_dsh_profiles.py",
)
assert SPEC and SPEC.loader
VERIFY = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = VERIFY
SPEC.loader.exec_module(VERIFY)


def test_verifier_rejects_invalid_startup_timeout() -> None:
    for value in ("0", "-1", "nan", "301"):
        with pytest.raises(SystemExit) as caught:
            VERIFY.main(["--startup-seconds", value])
        assert caught.value.code == 2


def test_failure_classifier_distinguishes_primary_categories() -> None:
    assert VERIFY.classify_failure("dsh: plugin tree failed to load") == "plugin_error"
    assert VERIFY.classify_failure("agent-preset/invalid: failed to mount") == "plugin_error"
    assert VERIFY.classify_failure("DeepSeek API key credential is missing") == "credential_error"
    assert VERIFY.classify_failure("address already in use") == "startup_error"


def test_profile_contract_requires_physical_minimal_omissions() -> None:
    full = VERIFY.REQUIRED["company-agent"]
    minimal = VERIFY.REQUIRED["company-agent-minimal"]
    forbidden = VERIFY.FORBIDDEN["company-agent-minimal"]
    assert "company-agent-device" in full
    assert "subagent-codex" in full
    assert "permissionMode: never" in full
    assert "inheritsParentContext: false" in full
    assert "tool-subagent-codex" in VERIFY.FORBIDDEN["company-agent"]
    assert "provider: codex" in VERIFY.FORBIDDEN["company-agent"]
    assert "presets/standard" in VERIFY.FORBIDDEN["company-agent"]
    assert "company-agent-device" not in minimal
    assert "company-agent-device" in forbidden
    assert "subagent-codex" in forbidden


def test_preset_report_requires_exact_rejection_codes(tmp_path: Path) -> None:
    payload = {
        "roster": [{"id": "company-agent", "trust": "system"}],
        "authorable": False, "copyError": "agent-preset/read-only",
        "switchError": "agent-preset/not-found", "selected": "company-agent",
        "toolsUnchanged": True,
    }
    path = tmp_path / (VERIFY.VERIFY_REPORT + ".presets")
    path.write_text(json.dumps(payload))
    VERIFY.check_preset_report(tmp_path)
    for key, value in (
        ("copyError", "unexpected_error"), ("switchError", "agent-preset/locked"),
        ("switchError", None), ("selected", "standard"), ("toolsUnchanged", False),
        ("authorable", 0), ("roster", [{"id": "company-agent", "trust": "user"}]),
    ):
        path.write_text(json.dumps({**payload, key: value}))
        with pytest.raises(RuntimeError, match="did not pass"):
            VERIFY.check_preset_report(tmp_path)
    path.write_text('{"authorable":false,"authorable":true}')
    with pytest.raises(RuntimeError, match="no valid report"):
        VERIFY.check_preset_report(tmp_path)


def test_session_rpc_rejects_failed_preset_assembly(monkeypatch, tmp_path: Path) -> None:
    class FakeResponse:
        headers = {}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self, _size=-1):
            return b""

    class FakeOpener:
        def open(self, request, timeout):
            del timeout
            if isinstance(request, str):
                return FakeResponse()
            body = json.loads(request.data)
            payload = {
                "type": "server-response",
                "rpcId": body["rpcId"],
                "result": {
                    "ok": False,
                    "error": {
                        "code": "agent-preset/invalid",
                        "message": "composition must be a top-level list",
                    },
                },
            }
            response = FakeResponse()
            response.read = lambda _size=-1: json.dumps(payload).encode()
            return response

    monkeypatch.setattr(VERIFY.urllib.request, "build_opener", lambda *_args: FakeOpener())

    with pytest.raises(RuntimeError, match="agent-preset/invalid"):
        VERIFY.check_session(
            3081,
            "http://127.0.0.1:3081/?token=abcdefghijklmnop",
            "company-agent",
            tmp_path,
        )


def test_live_model_catalog_requires_company_routes() -> None:
    value = {
        "routableProviders": ["deepseek-official", "company-local", "company-relay"],
        "groups": [
            {"id": "deepseek-official", "models": [{"id": "fixture-official"}]},
            {"id": "company-local", "models": [{"id": "deepseek-chat"}]},
            {"id": "company-relay", "models": [{"id": "fixture-relay"}]},
        ],
        "failures": [],
    }
    VERIFY.check_model_catalog({"ok": True, "value": value}, "company-agent")
    # Config-string matches alone previously passed even when the picker was unverified.
    for mutation in ("missing", "unroutable", "empty", "failed", "duplicate"):
        broken = copy.deepcopy(value)
        if mutation == "missing":
            broken["groups"].pop()
        elif mutation == "unroutable":
            broken["routableProviders"].remove("company-relay")
        elif mutation == "empty":
            broken["groups"][-1]["models"] = []
        elif mutation == "failed":
            broken["failures"] = [{"id": "company-relay"}]
        else:
            broken["groups"].append(broken["groups"][-1])
        with pytest.raises(RuntimeError, match="native model catalog"):
            VERIFY.check_model_catalog({"ok": True, "value": broken}, "company-agent")
    with pytest.raises(RuntimeError, match="minimal model catalog"):
        VERIFY.check_model_catalog({"ok": True, "value": value}, "company-agent-minimal")
    minimal = copy.deepcopy(value)
    minimal["groups"] = minimal["groups"][:1]
    minimal["routableProviders"] = ["deepseek-official"]
    VERIFY.check_model_catalog({"ok": True, "value": minimal}, "company-agent-minimal")
    for malformed in ({"ok": False}, {"ok": True, "value": {}}, {"ok": True, "value": None}):
        with pytest.raises(RuntimeError, match="native model catalog"):
            VERIFY.check_model_catalog(malformed, "company-agent")


def test_config_timeout_is_classified(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(VERIFY, "write_session_probe", lambda *_args: None)
    monkeypatch.setattr(
        VERIFY.subprocess,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(VERIFY.subprocess.TimeoutExpired("dsh", 60)),
    )
    result = VERIFY.check_config(Path("/tmp/node"), Path("/tmp/dsh"), "company-agent", tmp_path)
    assert result == VERIFY.CheckResult(
        "company-agent",
        "config_error",
        "configuration expansion timed out",
    )


def test_tool_report_rejects_invalid_shape(tmp_path: Path) -> None:
    (tmp_path / VERIFY.VERIFY_REPORT).write_text(
        json.dumps({"actual": None, "expected": [], "extra": [], "missing": []}),
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="invalid report shape"):
        VERIFY.check_tool_report(tmp_path)


def test_verifier_builds_exact_tool_probe_per_profile() -> None:
    for profile, expected_count in (("company-agent", 85), ("company-agent-minimal", 27)):
        with VERIFY.profile_home(profile) as temporary:
            home = Path(temporary)
            VERIFY.write_session_probe(home, profile)
            patch = (home / VERIFY.VERIFY_PATCH).read_text(encoding="utf-8")
            assert "company-agent-verify-session-probe" in patch
            assert "company_capabilities" in patch
            assert ("quantum_device_run" in patch) is (profile == "company-agent")
            source = (home / VERIFY.VERIFY_PROBE).read_text(encoding="utf-8")
            assert "ctx.tools.schemas(agent)" in source
            expected = json.loads(patch.split("expected: ", 1)[1].splitlines()[0])
            assert len(expected) == expected_count
            builtins = {
                "read", "write", "edit", "read_image", "glob", "grep", "web_search",
                "todo_write", "present",
            }
            if profile == "company-agent":
                assert builtins <= set(expected)
                assert expected[-1] == "skill"
            else:
                assert builtins.isdisjoint(expected)


@pytest.mark.posix_permissions  # 非法组合拒绝探针要跑 POSIX 的 start_runtime.sh
def test_verifier_reports_provider_readiness_without_exposing_values(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        VERIFY,
        "runtime_paths",
        lambda: (Path("/tmp/node"), Path("/tmp/dsh")),
    )
    monkeypatch.setattr(Path, "is_file", lambda _self: True)
    monkeypatch.setattr(VERIFY.os, "access", lambda *_args: True)
    monkeypatch.setattr(
        VERIFY,
        "verify",
        lambda profile, _node, _entry, _seconds, _preset: VERIFY.CheckResult(profile, "ok", "healthy"),
    )
    monkeypatch.setenv("COMPANY_AGENT_SIMULATOR_INVOKE_URL", "https://secret.example/invoke")
    monkeypatch.setenv("COMPANY_AGENT_SIMULATOR_TOKEN", "secret-provider-token")
    assert VERIFY.main(["--profile", "company-agent-minimal"]) == 0
    output = capsys.readouterr().out
    assert "science_providers: configured: COMPANY_AGENT_SIMULATOR_INVOKE_URL" in output
    assert "secret.example" not in output
    assert "secret-provider-token" not in output


def test_verifier_fails_when_session_reports_credential_error(monkeypatch, capsys) -> None:
    monkeypatch.setattr(VERIFY, "runtime_paths", lambda: (Path("/tmp/node"), Path("/tmp/dsh")))
    monkeypatch.setattr(Path, "is_file", lambda _self: True)
    monkeypatch.setattr(VERIFY.os, "access", lambda *_args: True)
    monkeypatch.setattr(
        VERIFY,
        "verify",
        lambda profile, *_args: VERIFY.CheckResult(profile, "credential_error", "no model route"),
    )
    assert VERIFY.main(["--profile", "company-agent-minimal"]) == 1
    output = capsys.readouterr().out
    assert "credential_error" in output
    assert "startup is healthy" not in output


def test_verifier_scrubs_internal_authorization_environment(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("COMPANY_AGENT_APPROVAL_CONTEXT", "dsh")
    monkeypatch.setenv("COMPANY_AGENT_ENABLE_CONFIGURED_KNOWLEDGE", "1")
    monkeypatch.setenv("COMPANY_AGENT_KNOWLEDGE_PATH", "/tmp/private")
    monkeypatch.setenv("COMPANY_AGENT_DEMO_UI", "1")
    monkeypatch.setenv("COMPANY_AGENT_CONTRACTS_DIR", "/tmp/unmanaged-contracts")
    monkeypatch.setenv("COMPANY_AGENT_DEVICE_TOKEN", "private-fixture")
    monkeypatch.setenv("COMPANY_AGENT_DEVICE_INVOKE_URL", "https://device.invalid/invoke")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "private-fixture")
    monkeypatch.setenv("COMPANY_RELAY_API_KEY", "private-fixture")
    env = VERIFY.base_environment(tmp_path, Path("/tmp/dsh"), "company-agent")
    assert "COMPANY_AGENT_APPROVAL_CONTEXT" not in env
    assert "COMPANY_AGENT_ENABLE_CONFIGURED_KNOWLEDGE" not in env
    assert "COMPANY_AGENT_KNOWLEDGE_PATH" not in env
    assert "COMPANY_AGENT_DEMO_UI" not in env
    assert "COMPANY_AGENT_DEVICE_TOKEN" not in env
    assert "COMPANY_AGENT_DEVICE_INVOKE_URL" not in env
    assert "DEEPSEEK_API_KEY" not in env
    assert "COMPANY_RELAY_API_KEY" not in env
    assert env["COMPANY_AGENT_CONTRACTS_DIR"] == str(ROOT / "contracts")
    assert Path(env["COMPANY_AGENT_PYTHON"]).is_absolute()


def test_session_wait_retries_connection_refusal_until_success(monkeypatch, tmp_path: Path) -> None:
    class FakeProcess:
        def poll(self):
            return None

    attempts = iter((OSError("connection refused"), "session-ok"))

    def fake_check_session(*_args):
        outcome = next(attempts)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    monkeypatch.setattr(VERIFY, "check_session", fake_check_session)
    monkeypatch.setattr(VERIFY.time, "sleep", lambda _seconds: None)
    session_id, error = VERIFY.wait_for_session(
        FakeProcess(),
        3081,
        "http://127.0.0.1:3081/?token=abcdefghijklmnop",
        "company-agent",
        tmp_path,
        VERIFY.time.monotonic() + 1,
    )
    assert session_id == "session-ok"
    assert error is None


def test_session_wait_stops_when_runtime_exits(monkeypatch, tmp_path: Path) -> None:
    class FakeProcess:
        def poll(self):
            return 1

    monkeypatch.setattr(
        VERIFY,
        "check_session",
        lambda *_args: (_ for _ in ()).throw(OSError("connection refused")),
    )
    session_id, error = VERIFY.wait_for_session(
        FakeProcess(),
        3081,
        "http://127.0.0.1:3081/?token=abcdefghijklmnop",
        "company-agent",
        tmp_path,
        VERIFY.time.monotonic() + 1,
    )
    assert session_id is None
    assert error == "connection refused"


def test_runtime_paths_use_isolated_pinned_node(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("COMPANY_AGENT_RUNTIME_DIR", str(tmp_path))
    monkeypatch.delenv("COMPANY_AGENT_NODE", raising=False)
    monkeypatch.delenv("COMPANY_AGENT_DSH_ENTRY", raising=False)
    node, entry = VERIFY.runtime_paths()
    assert node == (tmp_path / "node_modules/node/bin/node").resolve()
    assert entry == (tmp_path / "node_modules/@deepseek-ai/dsh/lib/bin.js").resolve()


def test_verifier_uses_isolated_profile_copy() -> None:
    with VERIFY.profile_home("company-agent-minimal") as temporary:
        home = Path(temporary)
        copied = home / "profiles/company-agent-minimal"
        preset = home / ".agent-presets/company-agent"
        assert copied.is_dir()
        assert preset.is_dir()
        assert (preset / "agent.cordis.yml").is_file()
        assert {path.name for path in (home / "skills").iterdir()} == {
            "company-knowledge",
            "company-docs-research",
            "company-office-matter",
            "company-software-development",
        }
        assert copied.resolve() != (ROOT / "profiles/company-agent-minimal").resolve()
        assert (copied / "package.json").is_file()
        assert (copied / "node_modules/@unitqc/company-agent-quantum").exists()
        assert not (copied / "node_modules/@unitqc/company-agent-device").exists()
        assert os.path.commonpath([str(home), str(copied)]) == str(home)
