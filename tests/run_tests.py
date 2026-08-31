"""Stdlib runner so the skeleton tests work without pytest."""

from __future__ import annotations

import json
import os
import shutil
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from qagent.adapters.contracts import ROOT as QROOT
from qagent.adapters.contracts import load_eval_cases, load_product_eval_cases, load_slots, load_tool_catalog
from qagent.services.boundaries import scan_forbidden_imports
from qagent.services.engines import list_engines
from qagent.services.fill import FillSlotError, fill
from qagent.models.eln import EVENT_CLAIM_BLOCKED
from qagent.services.eln import read_eln
from qagent.adapters import ionstack as ionstack_adapter
from qagent.adapters.ionstack import WiredIonstack
from qagent.models.handles import HANDLE_TWIN
from qagent.models.gov import GOV_EVAL_IDS
from qagent.services.eval_run import DEFAULT_CIRCUIT, DEFAULT_EVAL_IDS, run_evals
from qagent.services.invoke import invoke
from qagent.services.policy import decide
from qagent.services.company import company_payload
from qagent.services.ports import load_port_methods
from qagent.services.slots import empty_slots
from qagent.services.vibe_path import GOLDEN_STEPS, run_vibe_path


def check(name: str, fn) -> None:
    fn()
    print(f"ok  {name}")


def test_policy() -> None:
    assert decide("qdata_run_recipe", "lab", {"name": "foo_bar"}) == "deny"
    assert decide("qdata_run_recipe", "lab", {"name": "a2_chem_pes"}) == "allow"
    assert decide("ionstack_twin_run", "lab", {"shots": 10_000_000}) == "ask"
    assert decide("ionstack_twin_run", "lab", {"shots": 1000}) == "ask"
    assert decide("ionstack_twin_run", "algo", {"shots": 1000}) == "deny"
    assert decide("cal_edit", "lab", {}) == "deny"
    assert decide("qdata_dequant_gate", "lab", {"force_verdict": "quantum_wins"}) == "deny"
    assert decide("ionstack_twin_identity", "lab", {}) == "allow"
    assert decide("subagent_codex", "lab", {}) == "deny"
    assert decide("subagent_codex", "algo", {}) == "allow"
    assert decide("qdata_run_recipe", "customer", {}) == "deny"
    assert decide("qagent_list_engines", "lab", {}) == "allow"
    assert decide("qiskit_aer_run", "lab", {"shots": 100}) == "allow"
    assert decide("qiskit_aer_run", "lab", {"claim_twin_id": True}) == "deny"
    assert decide("qiskit_ibm_run", "lab", {}) == "deny"
    assert decide("qagent_list_engines", "boot", {}) == "allow"
    assert decide("ionstack_twin_run", "boot", {"shots": 8}) == "deny"


def test_contracts() -> None:
    for spec in load_tool_catalog():
        assert spec.schema["name"] == spec.name
        assert spec.schema.get("parameters")
        assert spec.schema.get("output")
    ids = [c.id for c in load_eval_cases()]
    assert ids[:21] == [f"E{i:02d}" for i in range(1, 22)]
    assert "E22" in ids
    assert set(GOV_EVAL_IDS) <= set(ids)
    assert "E23" not in ids
    implemented = {c.id for c in load_eval_cases() if c.status == "implemented"}
    assert implemented == set(DEFAULT_EVAL_IDS)
    e22 = next(c for c in load_eval_cases() if c.id == "E22")
    assert e22.status == "empty"
    slot_ids = {s.id for s in load_slots()}
    for case in load_eval_cases():
        assert case.slot in slot_ids, case.id
    for spec in load_tool_catalog():
        assert spec.slot in slot_ids, spec.name
    est = next(s for s in load_tool_catalog() if s.name == "ionstack_compile_estimate")
    assert "ok" in est.schema["forbidden_output_keys"]
    job = next(s for s in load_tool_catalog() if s.name == "qdata_get_job")
    assert "bitstrings" in job.schema["forbidden_output_keys"]
    aer = next(s for s in load_tool_catalog() if s.name == "qiskit_aer_run")
    assert "twin_id" in aer.schema["forbidden_output_keys"]
    assert aer.schema["output"]["properties"]["provenance"]["const"] == "aer"
    identity = next(s for s in load_tool_catalog() if s.name == "ionstack_twin_identity")
    assert "twin_id" in identity.schema["forbidden_output_keys"]
    assert "twin_id" not in identity.schema["output"]["required"]


def test_engines() -> None:
    five = ["qdata", "qchem", "ionstack", "route", "qiskit"]
    ids = [e.id for e in list_engines()]
    assert ids[:5] == five
    assert set(five) <= set(ids)
    qiskit = next(e for e in list_engines() if e.id == "qiskit")
    assert "qiskit_aer_run" in qiskit.tools
    assert "twin_id" not in qiskit.identity_fields
    route = next(e for e in list_engines() if e.id == "route")
    assert route.status == "wired"
    assert route.tools == ["ionstack_compile_estimate"]
    assert all(e.status == "wired" for e in list_engines())


def test_ports() -> None:
    hidden_url = os.environ.pop("QAGENT_QDATA_URL", None)
    mapped = {row.tool for row in load_port_methods()}
    for spec in load_tool_catalog():
        assert spec.name in mapped, spec.name
    listed = invoke("qagent_list_engines", "lab", {})
    assert listed.status == "ok"
    assert listed.payload is not None
    assert listed.payload.get("active_preset") in {"boot", "lab", "algo", "sign"}
    hidden_home = os.environ.pop("QAGENT_QDATA_HOME", None)
    hidden_bin = os.environ.pop("QAGENT_QDATA_BIN", None)
    try:
        recipe = invoke("qdata_run_recipe", "lab", {"name": "a2_chem_pes"})
    finally:
        if hidden_home is None:
            os.environ.pop("QAGENT_QDATA_HOME", None)
        else:
            os.environ["QAGENT_QDATA_HOME"] = hidden_home
        if hidden_bin is None:
            os.environ.pop("QAGENT_QDATA_BIN", None)
        else:
            os.environ["QAGENT_QDATA_BIN"] = hidden_bin
    assert recipe.status == "ok"
    assert recipe.payload is not None
    assert recipe.payload.get("asset_id")
    assert recipe.payload["summary"]["source"] == "qagent-local-card"
    identity = invoke("ionstack_twin_identity", "lab", {})
    assert identity.status == "ok"
    assert identity.payload is not None
    assert HANDLE_TWIN not in identity.payload
    assert "live" in identity.payload
    asked = invoke("ionstack_twin_run", "lab", {"shots": 1000})
    assert asked.status == "needs_ask"
    pinned = invoke(
        "qagent_pin_circuit",
        "lab",
        {"source": "logical", "logical": {"n_qubits": 2}, "asset_id": "a-test"},
    )
    assert pinned.status == "ok"
    assert pinned.payload is not None
    assert "twin_id" not in pinned.payload
    for row in run_evals(*[f"E{i:02d}" for i in range(1, 22)]):
        assert row.ok, f"{row.id}: {row.detail}"
    assert scan_forbidden_imports() == []
    invoke("qiskit_aer_run", "lab", {"circuit_id": "c1", "shots": 8, "claim_twin_id": True})
    assert any(row.get("type") == EVENT_CLAIM_BLOCKED for row in read_eln())
    asked = invoke(
        "ionstack_twin_run",
        "lab",
        {"mode": "signoff", "shots": 32, "circuit": DEFAULT_CIRCUIT},
    )
    assert asked.status == "needs_ask"
    assert HANDLE_TWIN not in (asked.payload or {})
    previous = os.environ.get("QAGENT_TWIN_URL")
    os.environ["QAGENT_TWIN_URL"] = "http://127.0.0.1:1"
    try:
        dead = invoke(
            "ionstack_twin_run",
            "lab",
            {"mode": "signoff", "shots": 32, "circuit": DEFAULT_CIRCUIT},
            approved=True,
        )
    finally:
        if previous is None:
            os.environ.pop("QAGENT_TWIN_URL", None)
        else:
            os.environ["QAGENT_TWIN_URL"] = previous
    assert dead.status == "error"
    assert HANDLE_TWIN not in (dead.payload or {})
    seen: list[dict] = []
    original_http = ionstack_adapter.try_http_json

    def _record_http(method, path, body=None):
        seen.append(dict(body or {}))
        return None

    ionstack_adapter.try_http_json = _record_http
    try:
        try:
            WiredIonstack().twin_run(
                {"mode": "signoff", "shots": 32, "circuit": DEFAULT_CIRCUIT}
            )
        except RuntimeError as exc:
            assert "no local twin_id" in str(exc)
        else:
            raise AssertionError("expected RuntimeError when Twin REST is down")
    finally:
        ionstack_adapter.try_http_json = original_http
    assert len(seen) == 1
    assert seen[0]["mode"] == "signoff"
    if hidden_url is None:
        os.environ.pop("QAGENT_QDATA_URL", None)
    else:
        os.environ["QAGENT_QDATA_URL"] = hidden_url


def test_company_shell() -> None:
    payload = company_payload()
    assert payload["company"]["short_name"] == "幺正量子"
    assert payload["company"]["legal_name"] == "合肥市幺正量子科技有限公司"
    ids = [item["id"] for item in payload["matrix"]]
    assert "qagent" in ids
    assert "knowledge" in ids
    assert "cloud" in ids
    five = ["qdata", "qchem", "ionstack", "route", "qiskit"]
    engine_ids = [e["id"] for e in payload["engines"]]
    assert engine_ids[:5] == five
    assert set(five) <= set(engine_ids)
    path = run_vibe_path("lab", shots=1000, approved=False)
    assert path["status"] == "needs_ask"
    assert path["tool"] == "ionstack_twin_run"
    assert [step["tool"] for step in path["steps"]][:6] == list(GOLDEN_STEPS[:6])
    assert path["handles"].get("aer_leaked_twin_id") is None
    if path["handles"].get("aer_provenance"):
        assert path["handles"]["aer_provenance"] == "aer"
    assert path["handles"].get("makespan_ns")
    assert HANDLE_TWIN not in path["handles"]
    brand = QROOT / "packages/qagent-brand/lib/client.js"
    assert brand.exists()
    text = brand.read_text(encoding="utf-8")
    assert "@qccd/qagent-brand" in text
    assert "幺正量子" in text
    assert "sidebar.brand.mark" in text
    assert "MutationObserver" not in text
    patch = (QROOT / "profiles/qagent/cordis.patch.yml").read_text(encoding="utf-8")
    assert "/Users/" not in patch
    assert "@qccd/qagent-policy" in patch
    from qagent.adapters import qiskit as qiskit_adapter
    from qagent.adapters.qiskit import WiredQiskit
    from qagent.adapters.preset import active_preset, set_active_preset
    from qagent.entrypoints.debug_gate import approved_allowed, bind_allowed

    original_interop = qiskit_adapter.call_interop
    qiskit_adapter.call_interop = lambda *_a, **_k: {"twin_id": "twin_leak", "counts": {"00": 1}}
    try:
        try:
            WiredQiskit().aer_run({"circuit_id": "c1", "shots": 8})
        except RuntimeError as exc:
            assert "leaked" in str(exc)
        else:
            raise AssertionError("expected Aer leak to raise")
    finally:
        qiskit_adapter.call_interop = original_interop

    assert approved_allowed({}, False) is True
    assert approved_allowed({}, True) is False
    previous_token = os.environ.get("QAGENT_SHELL_TOKEN")
    os.environ["QAGENT_SHELL_TOKEN"] = "secret-token"
    try:
        assert approved_allowed({"X-QAGENT-DEBUG-TOKEN": "secret-token"}, True)
        assert approved_allowed({"Authorization": "Bearer secret-token"}, True) is True
        assert approved_allowed({"X-QAGENT-DEBUG-TOKEN": "nope"}, True) is False
        assert bind_allowed("0.0.0.0") is True
    finally:
        if previous_token is None:
            os.environ.pop("QAGENT_SHELL_TOKEN", None)
        else:
            os.environ["QAGENT_SHELL_TOKEN"] = previous_token
    assert bind_allowed("127.0.0.1") is True
    if not os.environ.get("QAGENT_SHELL_TOKEN"):
        assert bind_allowed("0.0.0.0") is False

    preset_file = ROOT / ".qagent" / "p2-preset-test"
    previous_file = os.environ.get("QAGENT_PRESET_FILE")
    previous_preset = os.environ.get("QAGENT_PRESET")
    os.environ["QAGENT_PRESET_FILE"] = str(preset_file)
    try:
        set_active_preset("algo")
        assert active_preset() == "algo"
        switched = invoke("qagent_list_engines", "lab", {"preset": "sign"})
        assert switched.status == "ok"
        assert switched.payload["active_preset"] == "sign"
    finally:
        if previous_file is None:
            os.environ.pop("QAGENT_PRESET_FILE", None)
        else:
            os.environ["QAGENT_PRESET_FILE"] = previous_file
        if previous_preset is None:
            os.environ.pop("QAGENT_PRESET", None)
        else:
            os.environ["QAGENT_PRESET"] = previous_preset
        try:
            preset_file.unlink()
        except OSError:
            pass


def test_workbench() -> None:
    from qagent.entrypoints.shell_http import dispatch
    from qagent.models.assignment import (
        SOURCE_LOCAL_CARD,
        Assignment,
        AssignmentError,
        can_sign,
        signoff_handles,
    )
    from qagent.models.handles import HANDLE_TWIN
    from qagent.services.assignment import approve, create, fork, run

    assert can_sign({HANDLE_TWIN: "twin_x"}, [SOURCE_LOCAL_CARD]) is False
    assert HANDLE_TWIN not in signoff_handles({HANDLE_TWIN: "twin_x"}, [SOURCE_LOCAL_CARD])
    try:
        Assignment(
            assignment_id="asg_bad",
            room="lab",
            brief="",
            recipe="a2_chem_pes",
            shots=8,
            status="signed",
            handles={},
            sources=[SOURCE_LOCAL_CARD],
        )
    except AssignmentError as exc:
        assert "unsigned" in str(exc)
    else:
        raise AssertionError("local-card must not look signed")

    path = ROOT / ".qagent" / "test-assignments-workbench.jsonl"
    previous = os.environ.get("QAGENT_ASSIGNMENTS_FILE")
    hidden_url = os.environ.pop("QAGENT_QDATA_URL", None)
    os.environ["QAGENT_ASSIGNMENTS_FILE"] = str(path)
    try:
        if path.exists():
            path.unlink()
        created = create(room="lab", brief="扫 PES", shots=32)
        ran = run(created.assignment_id)
        assert ran.status == "needs_ask"
        signoff = ran.to_dict()["signoff"]
        assert signoff["eligible"] is False
        assert HANDLE_TWIN not in signoff["handles"]
        assert SOURCE_LOCAL_CARD in ran.sources
        forked = fork(ran.assignment_id)
        assert HANDLE_TWIN not in forked.handles
        assert "qccd-twin" not in forked.sources
        assert forked.status == "draft"
        circuit_before = ran.handles.get("circuit_id")
        asset_before = ran.handles.get("asset_id")
        assert ran.ask and ran.ask.get("tool") == "ionstack_twin_run"
        previous_twin = os.environ.get("QAGENT_TWIN_URL")
        os.environ["QAGENT_TWIN_URL"] = "http://127.0.0.1:1"
        try:
            resumed = approve(ran.assignment_id)
        finally:
            if previous_twin is None:
                os.environ.pop("QAGENT_TWIN_URL", None)
            else:
                os.environ["QAGENT_TWIN_URL"] = previous_twin
        assert resumed.handles.get("circuit_id") == circuit_before
        assert resumed.handles.get("asset_id") == asset_before
        assert HANDLE_TWIN not in resumed.handles
        from qagent.entrypoints.shell_http import dispatch as http_dispatch
        code, rec = http_dispatch("GET", f"/api/assignments/{ran.assignment_id}/receipt")
        assert code == 200
        assert rec["kind"] == "qagent/receipt"
        assert rec["schema"] == "qagent.receipt/v1"
        assert "compile" in rec["lanes"] or "prepare" in rec["lanes"]
        assert rec["receipt_hash"].startswith("sha256:")
        assert "body" not in rec
        assert rec["handles"].get("circuit_id") == circuit_before
        code, verified = http_dispatch("POST", "/api/receipts/verify", rec)
        assert code == 200 and verified["ok"] is True
        tampered = dict(rec)
        tampered["shots"] = 1
        code, bad = http_dispatch("POST", "/api/receipts/verify", tampered)
        assert code == 200 and bad["ok"] is False
        code, filtered = http_dispatch("GET", "/api/assignments?status=needs_ask")
        assert code == 200
        assert all(row["status"] == "needs_ask" for row in filtered["assignments"])
        code, pre = http_dispatch("GET", f"/api/assignments/{ran.assignment_id}/preflight")
        assert code == 200
        assert "checks" in pre
        other = create(room="lab", brief="cancel-me", shots=8)
        other_run = run(other.assignment_id)
        code, cancelled = http_dispatch("POST", f"/api/assignments/{other_run.assignment_id}/cancel", {})
        assert code == 200
        assert cancelled["status"] == "rejected"
        assert "error" not in cancelled
        assert "columns" not in cancelled
        from qagent.adapters.assignment_store import AssignmentStore
        from qagent.models.assignment import SOURCE_TWIN, Assignment
        from qagent.services.assignment import cancel
        sealed = Assignment(
            assignment_id="asg_sealed",
            room="sign",
            brief="sealed",
            recipe="a2_chem_pes",
            shots=8,
            status="signed",
            handles={HANDLE_TWIN: "twin_sealed"},
            sources=[SOURCE_TWIN],
        )
        AssignmentStore().put(sealed)
        try:
            cancel("asg_sealed")
        except AssignmentError as exc:
            assert "cannot be cancelled" in str(exc)
        else:
            raise AssertionError("signed assignment must not cancel")
        rec_path = ROOT / ".qagent" / "test-receipt.json"
        rec_path.write_text(json.dumps(rec), encoding="utf-8")
        import subprocess

        verify = subprocess.run(
            [sys.executable, str(QROOT / "scripts/verify_receipt.py"), str(rec_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert verify.returncode == 0, verify.stdout + verify.stderr
        rec_path.unlink(missing_ok=True)
        algo = create(room="algo", brief="spi")
        algo_run = run(algo.assignment_id)
        assert HANDLE_TWIN not in algo_run.handles
        assert algo_run.status in {"draft", "failed"}

        code, health = dispatch("GET", "/api/health")
        assert code == 200
        assert "twin_live" in health
        assert "qdata_live" in health
        code, listed = dispatch("GET", "/api/assignments")
        assert code == 200
        assert any(row["assignment_id"] == created.assignment_id for row in listed["assignments"])
        code, forbidden = dispatch(
            "POST",
            f"/api/assignments/{created.assignment_id}/approve",
            {},
            {},
        )
        assert code == 403

        os.environ["QAGENT_QDATA_URL"] = "http://127.0.0.1:1"
        dead = invoke("qdata_submit_job", "lab", {"kind": "surrogate", "payload": {}})
        assert dead.status == "error"
        assert "job_id" not in (dead.payload or {})
    finally:
        if previous is None:
            os.environ.pop("QAGENT_ASSIGNMENTS_FILE", None)
        else:
            os.environ["QAGENT_ASSIGNMENTS_FILE"] = previous
        if hidden_url is None:
            os.environ.pop("QAGENT_QDATA_URL", None)
        else:
            os.environ["QAGENT_QDATA_URL"] = hidden_url
        try:
            path.unlink()
        except OSError:
            pass

    html = (QROOT / "apps/customer-shell/index.html").read_text(encoding="utf-8")
    js = (QROOT / "apps/customer-shell/app.js").read_text(encoding="utf-8")
    start_ui = (QROOT / "scripts/start_ui.sh").read_text(encoding="utf-8")
    start_runtime = (QROOT / "scripts/start_runtime.sh").read_text(encoding="utf-8")
    assert "产品矩阵" not in html
    assert "调试页" not in html
    assert "公司知识库路径" in html
    assert "实验室" not in html and "写算法" not in html and "签收台" not in html
    assert "本地大模型" in html
    assert "设置" in html
    assert "/api/workplace" in js
    assert "/api/chat" in js
    assert "批准上机" in js
    assert "/api/chat/status" in js
    assert "tool-cards" in js
    assert "llm_pool" in html
    assert "btn-twin" not in js
    assert "shell_cli" in start_ui
    assert "dsh --profile" not in start_ui
    assert "3081" in start_runtime
    assert (QROOT / "scripts/start_qdata.sh").is_file()


def test_chat() -> None:
    from qagent.adapters.dsh_session import DshSessionClient
    from qagent.entrypoints.shell_http import dispatch
    from qagent.services.agent import reset_agent
    from qagent.services.chat import classify, reset_chat, turn
    from qagent.services.workplace import save_workplace

    assert classify("批准") == "approve"
    assert classify("先估计氢分子，先不上机") == "run"
    chat_src = (QROOT / "src/qagent/services/chat.py").read_text(encoding="utf-8")
    assert "def _loop" not in chat_src
    assert "OpenAICompatClient" not in chat_src
    assert "from qagent.services.agent import" not in chat_src

    folder = ROOT / ".qagent" / "test-agent-home"
    folder.mkdir(parents=True, exist_ok=True)
    previous = {
        "QAGENT_WORKPLACE_FILE": os.environ.get("QAGENT_WORKPLACE_FILE"),
        "QAGENT_SECRETS_FILE": os.environ.get("QAGENT_SECRETS_FILE"),
        "QAGENT_AGENT_THREAD": os.environ.get("QAGENT_AGENT_THREAD"),
        "QAGENT_DSH_ENV_FILE": os.environ.get("QAGENT_DSH_ENV_FILE"),
        "QAGENT_DSH_URL": os.environ.get("QAGENT_DSH_URL"),
        "QAGENT_DSH_SESSION_FILE": os.environ.get("QAGENT_DSH_SESSION_FILE"),
        "QAGENT_SHELL_TOKEN": os.environ.get("QAGENT_SHELL_TOKEN"),
    }
    os.environ["QAGENT_WORKPLACE_FILE"] = str(folder / "workplace.json")
    os.environ["QAGENT_SECRETS_FILE"] = str(folder / "secrets.json")
    os.environ["QAGENT_AGENT_THREAD"] = str(folder / "thread.json")
    os.environ["QAGENT_DSH_ENV_FILE"] = str(folder / "dsh.env")
    os.environ["QAGENT_DSH_URL"] = "http://127.0.0.1:9"
    os.environ["QAGENT_DSH_SESSION_FILE"] = str(folder / "dsh-session.json")
    os.environ["QAGENT_SHELL_TOKEN"] = "agent-test"
    try:
        reset_agent()
        code, cold = dispatch("POST", "/api/chat", {"message": "扫氢分子势能面"})
        assert code == 200
        assert "设置" in cold["reply"]
        assert cold.get("ready") is False
        assert "assignment" not in cold
        code, saved = dispatch(
            "PUT",
            "/api/workplace",
            {
                "llm_base_url": "http://127.0.0.1:9/v1",
                "llm_model": "unitqc-local",
                "llm_api_key": "secret-should-not-echo",
                "knowledge_path": str(folder),
            },
            {"X-QAGENT-DEBUG-TOKEN": "agent-test"},
        )
        assert code == 200
        assert saved["ready"] is True
        code, status = dispatch("GET", "/api/workplace")
        assert code == 200
        assert status["workplace"]["llm_model"] == "unitqc-local"
        dumped = json.dumps(status)
        assert "secret-should-not-echo" not in dumped
        assert status["workplace"]["has_llm_key"] is True

        reset_agent()
        save_workplace({"llm_base_url": "http://127.0.0.1:9/v1", "llm_model": "unitqc-local"})

        def transport(method: str, payload: dict) -> dict:
            if method == "session.create":
                return {"result": {"ok": True, "value": {"sessionId": "sess_chat"}}}
            if method == "session.prompt":
                return {"result": {"ok": True, "value": {"accepted": True}}}
            if method == "session.history":
                return {
                    "result": {
                        "ok": True,
                        "value": {
                            "events": [
                                {"event": {"type": "turn/start", "data": {}}},
                                {
                                    "event": {
                                        "type": "tool/call",
                                        "data": {"name": "qagent_list_engines", "callId": "c1"},
                                    }
                                },
                                {
                                    "event": {
                                        "type": "assistant/message",
                                        "data": {
                                            "message": {
                                                "content": [{"type": "text", "text": "已经看见公司软件包。"}]
                                            }
                                        },
                                    }
                                },
                                {"event": {"type": "turn/end", "data": {}}},
                            ],
                            "hasMore": False,
                        },
                    }
                }
            raise AssertionError(method)

        out = turn(message="看看我们接了哪些软件", client=DshSessionClient(transport=transport))
        assert "软件包" in out["reply"]
        assert "qagent_list_engines" in out["used_tools"]
        assert out.get("via") == "dsh-session"
        code, proxied = dispatch("POST", "/api/chat", {"message": "看看我们接了哪些软件"})
        assert code == 200
        assert proxied.get("ready") is True
        assert proxied.get("via") == "dsh-session"
        assert "自研循环" in proxied["reply"] or "运行时" in proxied["reply"]
        assert "qagent_list_engines" not in proxied.get("used_tools", [])
        code, forbidden = dispatch("POST", "/api/chat", {"message": "批准"}, {})
        assert code == 403
        code, st = dispatch("GET", "/api/chat/status")
        assert code == 200
        assert st.get("via") == "dsh-session"
    finally:
        reset_chat()
        reset_agent()
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        for name in ("workplace.json", "secrets.json", "thread.json", "dsh.env", "dsh-session.json"):
            try:
                (folder / name).unlink()
            except OSError:
                pass


def test_dsh_session() -> None:
    from qagent.adapters.dsh_session import DshSessionClient, DshSessionError

    def transport(method: str, payload: dict) -> dict:
        if method == "session.create":
            assert payload.get("cwd")
            assert payload.get("agentPreset") == "qagent"
            return {"result": {"ok": True, "value": {"sessionId": "sess_test"}}}
        if method == "session.prompt":
            assert payload["sessionId"] == "sess_test"
            assert payload["mode"] == "queue"
            assert payload["content"][0]["text"] == "扫氢分子"
            return {"result": {"ok": True, "value": {"accepted": True}}}
        if method == "session.history":
            return {
                "result": {
                    "ok": True,
                    "value": {
                        "events": [
                            {
                                "event": {
                                    "type": "assistant/message",
                                    "data": {"message": {"content": [{"type": "text", "text": "已进 session"}]}},
                                }
                            }
                        ],
                        "hasMore": False,
                    },
                }
            }
        raise AssertionError(method)

    client = DshSessionClient(transport=transport)
    session_id = client.create()
    assert session_id == "sess_test"
    client.prompt(session_id, "扫氢分子")
    assert client.recent_assistant_text(session_id) == "已进 session"
    snap = client.wait_for_turn(session_id, timeout=0)
    assert snap["reply"] == "已进 session"
    assert snap["running"] is False

    def boom(_method: str, _payload: dict) -> dict:
        return {"result": {"ok": False, "error": {"code": "agent-preset-invalid", "message": "persona"}}}

    try:
        DshSessionClient(transport=boom).create()
    except DshSessionError as exc:
        assert exc.code == "agent-preset-invalid"
        assert "自研循环" in str(exc)
    else:
        raise AssertionError("expected DshSessionError")


def test_product_eval() -> None:
    cases = load_product_eval_cases()
    ids = [row.id for row in cases]
    assert [row.id for row in cases if row.id.startswith("Q-h")] == [f"Q-h{i:02d}" for i in range(1, 11)]
    assert [row.id for row in cases if row.id.startswith("Q-a")] == [f"Q-a{i:02d}" for i in range(1, 11)]
    assert [row.id for row in cases if row.id.startswith("Q-f")] == [f"Q-f{i:02d}" for i in range(1, 6)]
    assert [row.id for row in cases if row.id.startswith("Q-c")] == [f"Q-c{i:02d}" for i in range(1, 6)]
    assert len(ids) == 30
    by_id = {row.id: row for row in cases}
    assert by_id["Q-h01"].prompt == "改一下 CAL"
    assert "twin_id" in by_id["Q-h01"].qagent_must_not
    assert by_id["Q-h08"].preset == "algo"
    from qagent.services.product_eval import run_product_evals

    decided = run_product_evals("Q-h01", "Q-h02", "Q-h04", "Q-h05", "Q-h08", "Q-c05")
    assert decided and all(row.ok for row in decided), decided
    for row in cases:
        assert row.prompt
        assert row.kind
        assert row.assertions
        assert row.qagent_must
        assert row.qagent_must_not


def test_docs_empty() -> None:
    from qagent.adapters.docs import WiredDocs

    folder = ROOT / ".qagent" / "test-empty-knowledge"
    folder.mkdir(parents=True, exist_ok=True)
    previous = os.environ.get("QAGENT_KNOWLEDGE_PATH")
    os.environ["QAGENT_KNOWLEDGE_PATH"] = str(folder)
    try:
        hits = WiredDocs().search({"query": "TwinRun circuit.body mode shots"})
        assert hits["hits"]
        assert any("mode" in item["text"] for item in hits["hits"])
        empty = WiredDocs().search({"query": "this-query-should-miss-zzzz"})
        assert empty["empty"] is True
        assert empty["hits"] == []
    finally:
        if previous is None:
            os.environ.pop("QAGENT_KNOWLEDGE_PATH", None)
        else:
            os.environ["QAGENT_KNOWLEDGE_PATH"] = previous


def test_q01() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_q01 import (
        test_decision_subset_still_green,
        test_h06_skips_without_live_twin,
        test_no_fake_twin_or_cal,
        test_q02_table_has_thirty_rows,
        test_wired_invoke_receipt,
    )

    test_decision_subset_still_green()
    test_wired_invoke_receipt()
    test_h06_skips_without_live_twin()
    test_no_fake_twin_or_cal()
    test_q02_table_has_thirty_rows()


def test_qh06() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_qh06 import (
        test_qh06_note,
        test_qh06_pin_ask_swap_refused,
        test_qh06_product_case_ok,
    )

    test_qh06_product_case_ok()
    test_qh06_pin_ask_swap_refused()
    test_qh06_note()


def test_h01d() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_h01d import (
        test_approve_no_pending,
        test_approve_same_session,
        test_chat_run_still_prompts,
        test_create_prompt_history_still_work,
        test_fold_asked,
        test_fold_requested,
        test_fold_resolved_clears,
        test_fold_tool_result_clears,
        test_parse_mux_sse_no_live,
        test_reject_same_session,
    )

    test_fold_asked()
    test_fold_requested()
    test_fold_resolved_clears()
    test_fold_tool_result_clears()
    test_approve_same_session()
    test_reject_same_session()
    test_approve_no_pending()
    test_create_prompt_history_still_work()
    test_chat_run_still_prompts()
    test_parse_mux_sse_no_live()


def test_h01d_live() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_h01d_live import _live_mux_forced, probe_live, test_note_records_evidence

    test_note_records_evidence()
    if _live_mux_forced():
        probe_live()


def test_h01d_ws() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_h01d_ws import (
        test_get_426_not_success,
        test_mux_disabled_returns_none,
        test_no_twin_id_minted,
        test_note_cites_websocket_downlink,
        test_optional_live_3081,
        test_parse_json_server_request,
        test_ws_peek_rpc_id,
    )

    test_parse_json_server_request()
    test_get_426_not_success()
    test_mux_disabled_returns_none()
    test_ws_peek_rpc_id()
    test_no_twin_id_minted()
    test_note_cites_websocket_downlink()
    if (os.environ.get("QAGENT_LIVE_MUX") or "").strip() == "1":
        test_optional_live_3081()


def test_h01d_orphan() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_h01d_orphan import (
        test_empty_mux_leaves_pending_none,
        test_injected_transport_no_network,
        test_mux_off_no_network_no_invented,
        test_no_twin_id_minted,
        test_note_exists_no_live_accepted,
        test_orphan_history_has_no_pending,
        test_orphan_snapshot_takes_rpc_from_peek,
    )

    test_orphan_history_has_no_pending()
    test_orphan_snapshot_takes_rpc_from_peek()
    test_empty_mux_leaves_pending_none()
    test_mux_off_no_network_no_invented()
    test_injected_transport_no_network()
    test_no_twin_id_minted()
    test_note_exists_no_live_accepted()


def test_h01d_approve_live() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_h01d_approve_live import (
        test_live_probe_optional,
        test_no_minted_rpc,
        test_note_exists,
        test_probe_exists_gated,
        test_refuses_fake_accepted,
    )

    test_note_exists()
    test_refuses_fake_accepted()
    test_no_minted_rpc()
    test_probe_exists_gated()
    if (os.environ.get("QAGENT_LIVE_MUX") or "").strip() == "1":
        test_live_probe_optional()


def test_h01e_settings() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_h01e_settings import (
        test_chat_source_no_twin_mint,
        test_classify_empty_still_works,
        test_not_ready_opens_settings,
        test_pending_approval_from_snapshot_only,
        test_ready_does_not_open_settings,
    )

    test_not_ready_opens_settings()
    test_ready_does_not_open_settings()
    test_classify_empty_still_works()
    test_pending_approval_from_snapshot_only()
    test_chat_source_no_twin_mint()


def test_h01g() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_h01g import (
        test_note,
        test_profile_tools_same_realpath,
        test_scripts_align_dsh_tools,
    )

    test_note()
    test_scripts_align_dsh_tools()
    test_profile_tools_same_realpath()


def test_h01h() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_h01h import (
        test_explicit_algo_still_writes,
        test_heal_stale_sign_to_lab,
        test_lab_allows_g0_tools_sign_algo_block,
        test_no_fourth_handle_or_extra_pipeline,
        test_note,
        test_start_runtime_defaults_lab,
    )

    test_note()
    test_start_runtime_defaults_lab()
    test_heal_stale_sign_to_lab()
    test_explicit_algo_still_writes()
    test_lab_allows_g0_tools_sign_algo_block()
    test_no_fourth_handle_or_extra_pipeline()


def test_h01i() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_h01i import (
        test_e11_invoke_still_blocks_southbound,
        test_no_fourth_handle_or_extra_pipeline,
        test_note,
        test_qdata_plugin_does_not_register_sandbox,
    )

    test_note()
    test_qdata_plugin_does_not_register_sandbox()
    test_e11_invoke_still_blocks_southbound()
    test_no_fourth_handle_or_extra_pipeline()


def test_h01j() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_h01j import (
        test_bubble_still_send_approve,
        test_no_fourth_handle_or_extra_pipeline,
        test_note,
    )

    test_note()
    test_bubble_still_send_approve()
    test_no_fourth_handle_or_extra_pipeline()


def test_h01k() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_h01k import (
        test_circuit_id_approved_does_not_mint,
        test_circuit_id_unapproved_asks,
        test_dsh_requires_pipeline_fields,
        test_empty_still_errors,
        test_no_fourth_handle_or_extra_pipeline,
        test_note,
    )

    test_note()
    test_dsh_requires_pipeline_fields()
    test_empty_still_errors()
    test_circuit_id_unapproved_asks()
    test_circuit_id_approved_does_not_mint()
    test_no_fourth_handle_or_extra_pipeline()


def test_h01l() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_h01l import (
        test_circuit_http_face,
        test_face_draws_circuit_and_keeps_approve_literal,
        test_fold_history_exposes_circuit_for_face,
        test_lab_is_told_uccsd_not_recipe_as_circuit,
        test_live_wrap_when_qchem_home,
        test_no_fourth_handle_or_src_qchem_import,
        test_note,
        test_uccsd_pauli_pins_four_qubits,
        test_unknown_circuit_id_does_not_fallback,
    )

    test_note()
    test_face_draws_circuit_and_keeps_approve_literal()
    test_lab_is_told_uccsd_not_recipe_as_circuit()
    test_uccsd_pauli_pins_four_qubits()
    test_circuit_http_face()
    test_unknown_circuit_id_does_not_fallback()
    test_fold_history_exposes_circuit_for_face()
    test_live_wrap_when_qchem_home()
    test_no_fourth_handle_or_src_qchem_import()


def test_h01m() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_h01m import (
        test_chat_waits_for_new_turn,
        test_face_still_can_draw_and_ask,
        test_fold_history_keeps_this_turn_only,
        test_no_fourth_handle_or_src_qchem_import,
        test_note,
        test_prompts_are_not_frozen_to_uccsd,
    )

    test_note()
    test_prompts_are_not_frozen_to_uccsd()
    test_fold_history_keeps_this_turn_only()
    test_chat_waits_for_new_turn()
    test_face_still_can_draw_and_ask()
    test_no_fourth_handle_or_src_qchem_import()


def test_l103() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_l103 import (
        test_e22_handles_only,
        test_no_cirq_import_in_src,
        test_no_third_handle,
        test_note_exists,
        test_pack_exists_reserved,
        test_package_execute_is_invoke,
        test_reserved_fill_and_invoke_deny,
    )

    test_pack_exists_reserved()
    test_no_cirq_import_in_src()
    test_no_third_handle()
    test_reserved_fill_and_invoke_deny()
    test_package_execute_is_invoke()
    test_e22_handles_only()
    test_note_exists()


def test_l103_plan() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_l103_plan import (
        test_cirq_stays_reserved_until_relaxed,
        test_l103_still_green,
        test_lists_those_test_file_names,
        test_plan_exists,
        test_refuses_wired_as_current_state,
    )

    test_plan_exists()
    test_lists_those_test_file_names()
    test_cirq_stays_reserved_until_relaxed()
    test_refuses_wired_as_current_state()
    test_l103_still_green()


def test_l103_relax() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_l103_relax import (
        test_does_not_claim_cirq_listed,
        test_note_exists,
        test_refuses_wired_as_current_state,
        test_relax_only_not_wired,
    )

    test_note_exists()
    test_relax_only_not_wired()
    test_refuses_wired_as_current_state()
    test_does_not_claim_cirq_listed()


def test_l103_relax2() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_l103_relax2 import (
        test_does_not_claim_cirq_listed,
        test_note_exists,
        test_refuses_wired_as_current_state,
        test_relax_only_not_wired,
    )

    test_note_exists()
    test_relax_only_not_wired()
    test_refuses_wired_as_current_state()
    test_does_not_claim_cirq_listed()


def test_l103_wire() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_l103_wire import (
        test_claim_twin_id_denied,
        test_list_engines_has_wired_cirq,
        test_no_cirq_import,
        test_simulator_run_has_no_twin_id,
        test_wire_note_exists,
    )

    test_list_engines_has_wired_cirq()
    test_simulator_run_has_no_twin_id()
    test_claim_twin_id_denied()
    test_no_cirq_import()
    test_wire_note_exists()


def test_l103_how() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_l103_how import (
        test_how_cirq_already_wired_example,
        test_how_next_pack_reserved_first,
        test_no_fourth_handle,
        test_no_stale_claims,
        test_note_exists,
    )

    test_how_cirq_already_wired_example()
    test_how_next_pack_reserved_first()
    test_note_exists()
    test_no_stale_claims()
    test_no_fourth_handle()


def test_l103_pl() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_l103_pl import (
        test_no_e23,
        test_no_pennylane_import_in_src,
        test_no_third_handle,
        test_note_exists,
        test_pack_reserved_not_listed,
        test_package_execute_is_invoke,
        test_reserved_fill_and_invoke_deny,
        test_southbound_still_forbidden,
    )

    test_pack_reserved_not_listed()
    test_no_pennylane_import_in_src()
    test_no_third_handle()
    test_reserved_fill_and_invoke_deny()
    test_southbound_still_forbidden()
    test_package_execute_is_invoke()
    test_no_e23()
    test_note_exists()


def test_iface_pl() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_iface_pl import (
        test_invoke_ids_omit_pennylane,
        test_list_engines_row_reserved_not_ids,
        test_no_fourth_handle,
        test_no_stale_claims,
        test_note_exists,
        test_pennylane_only_on_list_engines_row,
    )

    test_list_engines_row_reserved_not_ids()
    test_pennylane_only_on_list_engines_row()
    test_invoke_ids_omit_pennylane()
    test_note_exists()
    test_no_stale_claims()
    test_no_fourth_handle()


def test_l104() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_l104 import (
        test_cirq_not_required,
        test_current_tree_has_fixture_and_tests,
        test_fixture_parses_and_covers_wired,
        test_frozen_honest_keys,
        test_no_required_twin_id,
        test_no_science_imports_in_gate,
        test_note_exists,
        test_temp_dir_extra_pack_missing,
    )

    test_fixture_parses_and_covers_wired()
    test_cirq_not_required()
    test_no_required_twin_id()
    test_frozen_honest_keys()
    test_current_tree_has_fixture_and_tests()
    test_temp_dir_extra_pack_missing()
    test_no_science_imports_in_gate()
    test_note_exists()


def test_l104c() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_l104c import (
        test_helper_green_on_current_tree,
        test_new_step_mentions_gate,
        test_no_g3_passed,
        test_no_secrets_or_official,
        test_note_exists,
        test_q02b_commands_remain,
    )

    test_q02b_commands_remain()
    test_new_step_mentions_gate()
    test_no_secrets_or_official()
    test_note_exists()
    test_no_g3_passed()
    test_helper_green_on_current_tree()


def test_l104c_align() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_l104c_align import (
        test_helper_source_has_no_cirq,
        test_missing_follows_wired_catalog,
        test_no_g3_passed,
        test_note_follows_list_engines,
        test_note_keeps_l104c_anchors,
        test_stale_reserved_gone,
    )

    test_note_keeps_l104c_anchors()
    test_note_follows_list_engines()
    test_stale_reserved_gone()
    test_no_g3_passed()
    test_helper_source_has_no_cirq()
    test_missing_follows_wired_catalog()


def test_i03() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_i03 import (
        test_append_five_kinds,
        test_claim_blocked_jsonl_stays_flat,
        test_forbidden_keys_stripped,
        test_fork_drops_twin_and_records_parent,
        test_no_secret_values,
        test_replay_same_field_set,
        test_short_payload_strips_nested,
    )

    test_short_payload_strips_nested()
    test_append_five_kinds()
    test_forbidden_keys_stripped()
    test_replay_same_field_set()
    test_no_secret_values()
    test_fork_drops_twin_and_records_parent()
    test_claim_blocked_jsonl_stays_flat()


def test_i03d() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_i03d import (
        test_assignment_id_filter,
        test_dispatch_has_no_status_local,
        test_fork_still_drops_twin_id,
        test_get_empty_list,
        test_get_sees_pin_and_estimate,
        test_get_strips_secrets_and_body,
        test_note_exists,
        test_post_does_not_append,
    )

    test_get_empty_list()
    test_get_sees_pin_and_estimate()
    test_assignment_id_filter()
    test_get_strips_secrets_and_body()
    test_post_does_not_append()
    test_fork_still_drops_twin_id()
    test_dispatch_has_no_status_local()
    test_note_exists()


def test_i03e() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_i03e import (
        test_eln_face_ids,
        test_get_eln_no_post,
        test_keeps_c01e,
        test_no_rooms_or_finder,
        test_note_exists,
        test_paint_type_and_assignment_only,
        test_refuses_to_claim_g0_g2_pass,
    )

    test_eln_face_ids()
    test_get_eln_no_post()
    test_paint_type_and_assignment_only()
    test_refuses_to_claim_g0_g2_pass()
    test_keeps_c01e()
    test_note_exists()
    test_no_rooms_or_finder()


def test_i03f() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_i03f import (
        test_dispatch_has_no_status_local,
        test_empty_tenant_sees_pin_and_estimate,
        test_foreign_assignment_query_is_empty,
        test_no_secrets_circuit_or_minted_twin,
        test_note_exists,
        test_post_does_not_append,
        test_tenant_a_does_not_see_b,
        test_unscoped_hidden_from_set_tenant,
    )

    test_empty_tenant_sees_pin_and_estimate()
    test_tenant_a_does_not_see_b()
    test_unscoped_hidden_from_set_tenant()
    test_foreign_assignment_query_is_empty()
    test_post_does_not_append()
    test_no_secrets_circuit_or_minted_twin()
    test_dispatch_has_no_status_local()
    test_note_exists()


def test_i03g() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_i03g import (
        test_get_eln_no_post,
        test_keeps_c01g,
        test_keeps_i03e,
        test_no_rooms_or_finder,
        test_note_exists,
        test_paint_short_reason,
        test_refuses_to_claim_g0_g2_pass,
    )

    test_paint_short_reason()
    test_get_eln_no_post()
    test_keeps_i03e()
    test_keeps_c01g()
    test_refuses_to_claim_g0_g2_pass()
    test_note_exists()
    test_no_rooms_or_finder()


def test_i03h() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_i03h import (
        test_dispatch_has_no_status_local,
        test_get_claim_blocked_has_reason,
        test_get_keeps_payload_reason,
        test_get_strips_secrets_and_keeps_reason,
        test_note_exists,
        test_post_does_not_append,
    )

    test_get_claim_blocked_has_reason()
    test_get_keeps_payload_reason()
    test_get_strips_secrets_and_keeps_reason()
    test_post_does_not_append()
    test_dispatch_has_no_status_local()
    test_note_exists()


def test_i03i() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_i03i import (
        test_fork_still_drops_twin_id,
        test_kinds_include_claim_blocked_after_five,
        test_note_exists,
        test_replay_types_equal_kinds,
    )

    test_kinds_include_claim_blocked_after_five()
    test_replay_types_equal_kinds()
    test_fork_still_drops_twin_id()
    test_note_exists()


def test_i03j() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_i03j import (
        test_cards_source_has_no_fourth_handle,
        test_cards_wash_append_and_http,
        test_note_exists,
    )

    test_cards_wash_append_and_http()
    test_cards_source_has_no_fourth_handle()
    test_note_exists()


def test_i03k() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_i03k import (
        test_eln_get_drops_twin_keeps_face,
        test_eln_http_source_has_no_fourth_handle,
        test_note_exists,
    )

    test_eln_get_drops_twin_keeps_face()
    test_eln_http_source_has_no_fourth_handle()
    test_note_exists()


def test_i03l() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_i03l import (
        test_http_keeps_newest_cap,
        test_live_http_is_capped,
        test_note_copies_hit,
        test_this_file_does_not_skip,
    )

    test_http_keeps_newest_cap()
    test_live_http_is_capped()
    test_note_copies_hit()
    test_this_file_does_not_skip()


def test_i03m() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_i03m import (
        test_assignment_fork_copies_eln_without_twin,
        test_note_copies_hit,
        test_this_file_does_not_skip,
    )

    test_assignment_fork_copies_eln_without_twin()
    test_note_copies_hit()
    test_this_file_does_not_skip()


def test_i03n() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_i03n import (
        test_approved_run_tags_signoff_and_b3,
        test_invoke_without_assignment_stays_untagged,
        test_note_copies_hit,
        test_this_file_does_not_skip,
        test_unapproved_run_tags_estimate,
    )

    test_unapproved_run_tags_estimate()
    test_approved_run_tags_signoff_and_b3()
    test_invoke_without_assignment_stays_untagged()
    test_note_copies_hit()
    test_this_file_does_not_skip()


def test_i03o() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_i03o import (
        test_eln_paints_estimate_and_b3_not_twin,
        test_live_http_eln_has_estimate_and_b3,
        test_note_copies_hit,
        test_this_file_does_not_skip,
    )

    test_eln_paints_estimate_and_b3_not_twin()
    test_live_http_eln_has_estimate_and_b3()
    test_note_copies_hit()
    test_this_file_does_not_skip()


def test_i03p() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_i03p import (
        test_eln_paints_shots_not_twin,
        test_live_http_eln_has_shots,
        test_note_copies_hit,
        test_this_file_does_not_skip,
    )

    test_eln_paints_shots_not_twin()
    test_live_http_eln_has_shots()
    test_note_copies_hit()
    test_this_file_does_not_skip()


def test_i03q() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_i03q import (
        test_collapse_keeps_newest_assignment,
        test_http_unfiltered_collapses_assignment,
        test_note_copies_hit,
        test_this_file_does_not_skip,
    )

    test_collapse_keeps_newest_assignment()
    test_http_unfiltered_collapses_assignment()
    test_note_copies_hit()
    test_this_file_does_not_skip()


def test_i03r() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_i03r import (
        test_eln_face_paints_handles_not_twin,
        test_note_copies_hit,
        test_run_writes_handles_without_twin,
        test_this_file_does_not_skip,
    )

    test_run_writes_handles_without_twin()
    test_eln_face_paints_handles_not_twin()
    test_note_copies_hit()
    test_this_file_does_not_skip()


def test_r03c() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_r03c import (
        test_c01_i01c_copy_kept,
        test_no_fake_twin_id_in_markup,
        test_signed_label_not_default_empty_or_ask,
        test_signed_vs_unsigned_classes,
    )

    test_signed_vs_unsigned_classes()
    test_signed_label_not_default_empty_or_ask()
    test_c01_i01c_copy_kept()
    test_no_fake_twin_id_in_markup()


def test_i02() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_i02 import (
        test_apply_env_keeps_job_secrets_out_of_env,
        test_chat_prompt_hides_planted_secrets,
        test_public_file_secret_keys_are_dropped,
        test_source_does_not_format_secrets_for_dsh,
        test_status_json_hides_planted_secrets,
    )

    test_status_json_hides_planted_secrets()
    test_chat_prompt_hides_planted_secrets()
    test_apply_env_keeps_job_secrets_out_of_env()
    test_source_does_not_format_secrets_for_dsh()
    test_public_file_secret_keys_are_dropped()


def test_i02d() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_i02d import (
        test_live_loopback_twin_still_works,
        test_live_qdata_loopback_still_works,
        test_loopback_skips_bearer,
        test_note_copies_hit,
        test_this_file_does_not_skip,
    )

    test_loopback_skips_bearer()
    test_live_loopback_twin_still_works()
    test_live_qdata_loopback_still_works()
    test_note_copies_hit()
    test_this_file_does_not_skip()


def test_a05() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_a05 import (
        _STORE,
        test_engines_reserved_stay_reserved,
        test_invoke_list_assets_and_engines,
        test_list_length_bounded,
        test_no_forbidden_keys,
        test_no_twin_id,
    )

    if _STORE.exists():
        shutil.rmtree(_STORE)
    test_invoke_list_assets_and_engines()
    test_no_forbidden_keys()
    test_list_length_bounded()
    test_no_twin_id()
    test_engines_reserved_stay_reserved()
    if _STORE.exists():
        shutil.rmtree(_STORE)


def test_a05_live() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_a05_live import (
        test_live_probe_optional,
        test_no_pauli,
        test_no_twin,
        test_note_exists,
        test_probe_exists_gated,
        test_refuses_live_pass,
    )

    test_note_exists()
    test_refuses_live_pass()
    test_no_pauli()
    test_no_twin()
    test_probe_exists_gated()
    if (os.environ.get("QAGENT_LIVE_QDATA") or "").strip() == "1":
        test_live_probe_optional()


def test_a05b() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_a05b import (
        test_invoke_reserved_pennylane,
        test_no_fourth_handle,
        test_no_pennylane_import_or_twin_assign,
        test_note_exists,
        test_schema_allows_reserved_engines,
        test_workplace_reserved_pennylane,
    )

    test_invoke_reserved_pennylane()
    test_workplace_reserved_pennylane()
    test_schema_allows_reserved_engines()
    test_no_fourth_handle()
    test_note_exists()
    test_no_pennylane_import_or_twin_assign()


def test_a05c() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_a05c import (
        test_company_payload_reserved_pennylane,
        test_http_company_reserved_pennylane,
        test_no_fourth_handle,
        test_no_pennylane_import_or_twin_assign,
        test_note_exists,
    )

    test_company_payload_reserved_pennylane()
    test_http_company_reserved_pennylane()
    test_no_fourth_handle()
    test_note_exists()
    test_no_pennylane_import_or_twin_assign()


def test_a05g() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_a05g import (
        test_a05_live_contract_untouched,
        test_live_run_then_list_has_card,
        test_note_copies_hit,
        test_this_file_does_not_skip,
    )

    test_live_run_then_list_has_card()
    test_note_copies_hit()
    test_a05_live_contract_untouched()
    test_this_file_does_not_skip()


def test_a05h() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_a05h import (
        test_adapter_keeps_tail,
        test_newest_card_survives_over_budget,
        test_note_copies_hit,
        test_this_file_does_not_skip,
    )

    test_newest_card_survives_over_budget()
    test_note_copies_hit()
    test_this_file_does_not_skip()
    test_adapter_keeps_tail()


def test_a05i() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_a05i import (
        test_adapter_hits_http_list,
        test_dead_url_is_honest,
        test_fixture_strips_fat_http_row,
        test_live_http_assets_appear,
        test_note_copies_hit,
        test_this_file_does_not_skip,
    )

    test_live_http_assets_appear()
    test_fixture_strips_fat_http_row()
    test_dead_url_is_honest()
    test_note_copies_hit()
    test_adapter_hits_http_list()
    test_this_file_does_not_skip()


def test_c01() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_c01 import (
        test_hpc_secret_password_not_painted,
        test_inbox_and_approve_kept,
        test_no_finder_workspace_or_rooms,
        test_no_recipe_name_wall,
    )

    test_no_recipe_name_wall()
    test_inbox_and_approve_kept()
    test_no_finder_workspace_or_rooms()
    test_hpc_secret_password_not_painted()


def test_c02() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_c02 import (
        test_create_body_or_header_stamps_tenant,
        test_empty_tenant_sees_unscoped,
        test_receipt_has_no_body_or_secrets,
        test_tenant_a_cannot_get_b,
        test_tenant_a_list_excludes_b,
        test_verify_receipt_script_still_works,
    )

    test_tenant_a_cannot_get_b()
    test_tenant_a_list_excludes_b()
    test_empty_tenant_sees_unscoped()
    test_receipt_has_no_body_or_secrets()
    test_verify_receipt_script_still_works()
    test_create_body_or_header_stamps_tenant()


def test_c02d() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_c02d import (
        test_empty_tenant_skips_header,
        test_keeps_c01e,
        test_keeps_eln_get_only,
        test_no_rooms_or_finder,
        test_note_exists,
        test_refuses_to_claim_g0_g2_pass,
        test_tenant_query_header_and_storage,
    )

    test_tenant_query_header_and_storage()
    test_empty_tenant_skips_header()
    test_keeps_eln_get_only()
    test_keeps_c01e()
    test_refuses_to_claim_g0_g2_pass()
    test_note_exists()
    test_no_rooms_or_finder()


def test_c03() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_c03 import (
        test_dead_cloud_url_is_honest,
        test_empty_workplace_unsets_cloud_env,
        test_five_pack_unchanged,
        test_ibm_run_deny_cloud_off_and_on,
        test_note_exists,
        test_qc05_still_ok,
        test_save_cloud_url_sets_env_and_status,
    )

    test_empty_workplace_unsets_cloud_env()
    test_save_cloud_url_sets_env_and_status()
    test_ibm_run_deny_cloud_off_and_on()
    test_dead_cloud_url_is_honest()
    test_qc05_still_ok()
    test_note_exists()
    test_five_pack_unchanged()


def test_c01c() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_c01c import (
        test_no_fourth_handle,
        test_refuses_to_claim_pass,
        test_required_words,
        test_script_exists,
    )

    test_script_exists()
    test_required_words()
    test_refuses_to_claim_pass()
    test_no_fourth_handle()


def test_c01d() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_c01d import (
        test_customer_role_path,
        test_no_rooms_or_finder,
        test_note_exists,
        test_refuses_to_claim_g2_pass,
        test_secret_ids_kept,
        test_secret_values_never_from_api,
    )

    test_customer_role_path()
    test_secret_values_never_from_api()
    test_secret_ids_kept()
    test_no_rooms_or_finder()
    test_note_exists()
    test_refuses_to_claim_g2_pass()


def test_c01e() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_c01e import (
        test_boot_opens_settings_when_not_ready,
        test_health_uses_public_model_not_secrets,
        test_no_rooms_or_finder,
        test_note_exists,
        test_receipt_download_and_verify_paths,
        test_refuses_to_claim_g0_g2_pass,
        test_sibling_ids_kept,
    )

    test_boot_opens_settings_when_not_ready()
    test_receipt_download_and_verify_paths()
    test_health_uses_public_model_not_secrets()
    test_refuses_to_claim_g0_g2_pass()
    test_sibling_ids_kept()
    test_note_exists()
    test_no_rooms_or_finder()


def test_c01f() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_c01f import (
        test_g0_auto_settings_and_human_model,
        test_g2_download_and_verify_on_face,
        test_no_fourth_handle,
        test_note_exists,
        test_refuses_to_claim_pass,
    )

    test_g0_auto_settings_and_human_model()
    test_g2_download_and_verify_on_face()
    test_refuses_to_claim_pass()
    test_no_fourth_handle()
    test_note_exists()


def test_c01g() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_c01g import (
        test_keeps_c01e,
        test_keeps_eln_get_only,
        test_keeps_tenant_header,
        test_no_rooms_or_finder,
        test_note_exists,
        test_refuses_to_claim_g0_g2_pass,
        test_welcome_packs_paint_kind,
    )

    test_welcome_packs_paint_kind()
    test_keeps_c01e()
    test_keeps_eln_get_only()
    test_keeps_tenant_header()
    test_refuses_to_claim_g0_g2_pass()
    test_note_exists()
    test_no_rooms_or_finder()


def test_c01h() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_c01h import (
        test_engine_list_still_only_engines,
        test_fill_settings_paints_reserved_engines,
        test_html_has_reserved_list,
        test_keeps_c01g_line_and_c01e,
        test_keeps_eln_get_only,
        test_keeps_tenant_header,
        test_no_rooms_or_finder_or_fourth_handle,
        test_note_exists,
        test_refuses_to_claim_wired_or_g2,
        test_welcome_stays_engines_only,
    )

    test_html_has_reserved_list()
    test_fill_settings_paints_reserved_engines()
    test_welcome_stays_engines_only()
    test_engine_list_still_only_engines()
    test_keeps_c01g_line_and_c01e()
    test_keeps_eln_get_only()
    test_keeps_tenant_header()
    test_refuses_to_claim_wired_or_g2()
    test_note_exists()
    test_no_rooms_or_finder_or_fourth_handle()


def test_c01i() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_c01i import (
        test_js_never_reads_identity,
        test_keeps_approve_and_assignments,
        test_keeps_c01g_eln_tenant_secret,
        test_keeps_reserved_list_and_welcome_only_engines,
        test_no_rooms_or_finder_or_fourth_handle,
        test_note_exists,
        test_paint_preflight_draws_three_checks,
        test_refuses_to_claim_wired_or_g2,
    )

    test_paint_preflight_draws_three_checks()
    test_js_never_reads_identity()
    test_keeps_reserved_list_and_welcome_only_engines()
    test_keeps_approve_and_assignments()
    test_keeps_c01g_eln_tenant_secret()
    test_refuses_to_claim_wired_or_g2()
    test_note_exists()
    test_no_rooms_or_finder_or_fourth_handle()


def test_c01j() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_c01j import (
        test_face_still_reads_ask_tool_and_handles,
        test_inbox_face_slices_do_not_read_columns,
        test_keeps_approve_eln_tenant_secret,
        test_keeps_c01i_preflight_checks,
        test_keeps_reserved_list_and_welcome_only_engines,
        test_no_rooms_or_finder_or_fourth_handle,
        test_note_exists,
        test_refuses_to_claim_wired_or_g2,
    )

    test_inbox_face_slices_do_not_read_columns()
    test_face_still_reads_ask_tool_and_handles()
    test_keeps_c01i_preflight_checks()
    test_keeps_reserved_list_and_welcome_only_engines()
    test_keeps_approve_eln_tenant_secret()
    test_refuses_to_claim_wired_or_g2()
    test_note_exists()
    test_no_rooms_or_finder_or_fourth_handle()


def test_c01k() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_c01k import (
        test_face_label_eats_reason,
        test_inbox_uses_face_label_not_raw_status,
        test_keeps_needs_ask_query_and_no_columns,
        test_no_rooms_or_finder_or_fourth_handle,
        test_note_exists,
        test_receipt_face_eats_reason,
        test_refuses_to_claim_wired_or_g2,
    )

    test_face_label_eats_reason()
    test_inbox_uses_face_label_not_raw_status()
    test_receipt_face_eats_reason()
    test_keeps_needs_ask_query_and_no_columns()
    test_refuses_to_claim_wired_or_g2()
    test_note_exists()
    test_no_rooms_or_finder_or_fourth_handle()


def test_c01l() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_c01l import (
        test_keeps_get_eln_and_no_columns,
        test_kind_label_has_chinese,
        test_kind_map_keeps_english_keys,
        test_no_rooms_or_finder_or_fourth_handle,
        test_note_exists,
        test_paint_eln_uses_label_not_raw_kind,
        test_refuses_to_claim_wired_or_g2,
    )

    test_kind_label_has_chinese()
    test_paint_eln_uses_label_not_raw_kind()
    test_kind_map_keeps_english_keys()
    test_keeps_get_eln_and_no_columns()
    test_refuses_to_claim_wired_or_g2()
    test_note_exists()
    test_no_rooms_or_finder_or_fourth_handle()


def test_c01m() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_c01m import (
        test_chat_bubble_still_sends_approve,
        test_inbox_uses_assignment_action,
        test_note_copies_hit,
        test_this_file_does_not_skip,
    )

    test_inbox_uses_assignment_action()
    test_chat_bubble_still_sends_approve()
    test_note_copies_hit()
    test_this_file_does_not_skip()


def test_c01n() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_c01n import (
        test_chat_bubble_still_sends_approve,
        test_inbox_paints_estimate_not_columns,
        test_note_copies_hit,
        test_this_file_does_not_skip,
    )

    test_inbox_paints_estimate_not_columns()
    test_chat_bubble_still_sends_approve()
    test_note_copies_hit()
    test_this_file_does_not_skip()


def test_c01o() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_c01o import (
        test_chat_bubble_still_sends_approve,
        test_note_copies_hit,
        test_receipt_paints_b3_not_columns,
        test_this_file_does_not_skip,
    )

    test_receipt_paints_b3_not_columns()
    test_chat_bubble_still_sends_approve()
    test_note_copies_hit()
    test_this_file_does_not_skip()


def test_c01p() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_c01p import (
        test_chat_bubble_still_sends_approve,
        test_note_copies_hit,
        test_receipt_paints_aer_not_columns,
        test_this_file_does_not_skip,
    )

    test_receipt_paints_aer_not_columns()
    test_chat_bubble_still_sends_approve()
    test_note_copies_hit()
    test_this_file_does_not_skip()


def test_c01q() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_c01q import (
        test_chat_bubble_still_sends_approve,
        test_face_paints_circuit_and_asset_from_handles,
        test_live_http_face_already_has_handles,
        test_note_copies_hit,
        test_this_file_does_not_skip,
    )

    test_face_paints_circuit_and_asset_from_handles()
    test_live_http_face_already_has_handles()
    test_chat_bubble_still_sends_approve()
    test_note_copies_hit()
    test_this_file_does_not_skip()


def test_c01r() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_c01r import (
        test_chat_bubble_still_sends_approve,
        test_note_copies_hit,
        test_signed_receipt_has_fork_action,
        test_this_file_does_not_skip,
    )

    test_signed_receipt_has_fork_action()
    test_chat_bubble_still_sends_approve()
    test_note_copies_hit()
    test_this_file_does_not_skip()


def test_c01u() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_c01u import (
        test_chat_bubble_still_sends_approve,
        test_note_copies_hit,
        test_put_workplace_without_token_is_403,
        test_save_is_honest_on_forbidden_and_url,
        test_this_file_does_not_skip,
    )

    test_save_is_honest_on_forbidden_and_url()
    test_put_workplace_without_token_is_403()
    test_chat_bubble_still_sends_approve()
    test_note_copies_hit()
    test_this_file_does_not_skip()


def test_c01v() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_c01v import (
        test_chat_bubble_still_sends_approve,
        test_not_ready_opens_staff_pack,
        test_note_copies_hit,
        test_this_file_does_not_skip,
    )

    test_not_ready_opens_staff_pack()
    test_chat_bubble_still_sends_approve()
    test_note_copies_hit()
    test_this_file_does_not_skip()


def test_c01w() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_c01w import (
        test_chat_keeps_qasm_out_of_turn_body,
        test_face_hides_handles_and_keeps_approve,
        test_note_copies_hit,
        test_program_http_is_not_the_face,
        test_qasm_roundtrip_has_no_science_import,
        test_this_file_does_not_skip,
        test_upload_pins_without_qasm_on_face,
        test_wait_timeout_does_not_reuse_old_turn,
    )

    test_qasm_roundtrip_has_no_science_import()
    test_program_http_is_not_the_face()
    test_upload_pins_without_qasm_on_face()
    test_wait_timeout_does_not_reuse_old_turn()
    test_face_hides_handles_and_keeps_approve()
    test_chat_keeps_qasm_out_of_turn_body()
    test_note_copies_hit()
    test_this_file_does_not_skip()


def test_c01x() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_c01x import (
        test_drawn_circuit_is_not_replaced,
        test_fold_keeps_richer_circuit,
        test_note_copies_hit,
        test_rail_shows_current_task_only,
        test_skill_still_forbids_export_for_diagram,
        test_this_file_does_not_skip,
        test_voice_redacts_handles_and_internal_names,
    )

    test_voice_redacts_handles_and_internal_names()
    test_rail_shows_current_task_only()
    test_drawn_circuit_is_not_replaced()
    test_fold_keeps_richer_circuit()
    test_skill_still_forbids_export_for_diagram()
    test_note_copies_hit()
    test_this_file_does_not_skip()


def test_c01y() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_c01y import (
        test_approve_and_hard_rails,
        test_layout_and_tokens,
        test_note_copies_hit,
        test_starters_are_not_uccsd,
        test_this_file_does_not_skip,
    )

    test_layout_and_tokens()
    test_starters_are_not_uccsd()
    test_approve_and_hard_rails()
    test_note_copies_hit()
    test_this_file_does_not_skip()


def test_c01z() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_c01z import (
        test_approve_and_hard_rails,
        test_fill_does_not_dump_reply_html,
        test_note_copies_hit,
        test_static_path_stays_inside_shell,
        test_this_file_does_not_skip,
        test_vendor_and_html_wire,
        test_voice_tells_model_the_face_renders,
    )

    test_vendor_and_html_wire()
    test_static_path_stays_inside_shell()
    test_fill_does_not_dump_reply_html()
    test_approve_and_hard_rails()
    test_voice_tells_model_the_face_renders()
    test_note_copies_hit()
    test_this_file_does_not_skip()


def test_c01aa() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_c01aa import (
        test_approve_and_hard_rails,
        test_chat_recovers_instead_of_giving_up,
        test_console_tokens_and_locks,
        test_note_copies_hit,
        test_running_placeholder_is_human,
        test_this_file_does_not_skip,
    )

    test_chat_recovers_instead_of_giving_up()
    test_console_tokens_and_locks()
    test_approve_and_hard_rails()
    test_running_placeholder_is_human()
    test_note_copies_hit()
    test_this_file_does_not_skip()


def test_c01ab() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_c01ab import (
        test_booktabs_table_not_grid,
        test_circuit_figure_sits_on_paper,
        test_math_and_code_read_as_print,
        test_note_copies_hit,
        test_paper_measure_and_rhythm,
        test_structure_and_hard_rails_untouched,
        test_this_file_does_not_skip,
    )

    test_paper_measure_and_rhythm()
    test_booktabs_table_not_grid()
    test_math_and_code_read_as_print()
    test_circuit_figure_sits_on_paper()
    test_structure_and_hard_rails_untouched()
    test_note_copies_hit()
    test_this_file_does_not_skip()


def test_c01ac() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_c01ac import (
        test_approve_is_a_permit_card,
        test_gold_only_on_permit_and_inbox_approve,
        test_hard_rails_and_layout_locks,
        test_note_copies_hit,
        test_permit_estimate_is_conditional_not_invented,
        test_seal_meaning_is_text_not_color,
        test_this_file_does_not_skip,
    )

    test_approve_is_a_permit_card()
    test_permit_estimate_is_conditional_not_invented()
    test_gold_only_on_permit_and_inbox_approve()
    test_seal_meaning_is_text_not_color()
    test_hard_rails_and_layout_locks()
    test_note_copies_hit()
    test_this_file_does_not_skip()


def test_c01ad() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_c01ad import (
        test_busy_pulse_stops_under_reduced_motion,
        test_fault_strip_is_labelled_not_model_speech,
        test_hard_rails_and_locks,
        test_note_copies_hit,
        test_this_file_does_not_skip,
        test_user_turn_stays_a_conversation_turn,
    )

    test_user_turn_stays_a_conversation_turn()
    test_fault_strip_is_labelled_not_model_speech()
    test_busy_pulse_stops_under_reduced_motion()
    test_hard_rails_and_locks()
    test_note_copies_hit()
    test_this_file_does_not_skip()


def test_c01af() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_c01af import (
        test_empty_state_stays_two_doors,
        test_hard_rails_and_locks,
        test_note_copies_hit,
        test_one_focus_indicator,
        test_print_stylesheet_hides_chrome_and_lightens,
        test_this_file_does_not_skip,
    )

    test_one_focus_indicator()
    test_print_stylesheet_hides_chrome_and_lightens()
    test_empty_state_stays_two_doors()
    test_hard_rails_and_locks()
    test_note_copies_hit()
    test_this_file_does_not_skip()


def test_c01ae() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_c01ae import (
        test_face_paints_record_not_rooms,
        test_hard_rails_and_locks,
        test_http_sessions_read_only_face,
        test_journal_tenant_isolation,
        test_note_copies_hit,
        test_store_journal_roundtrip,
        test_this_file_does_not_skip,
        test_turn_journals_and_list_sessions,
    )

    test_store_journal_roundtrip()
    test_journal_tenant_isolation()
    test_turn_journals_and_list_sessions()
    test_http_sessions_read_only_face()
    test_face_paints_record_not_rooms()
    test_hard_rails_and_locks()
    test_note_copies_hit()
    test_this_file_does_not_skip()


def test_c02h() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_c02h import (
        test_empty_role_query_clears_customer,
        test_empty_tenant_query_clears_storage,
        test_keeps_inbox_http_and_chat_mux,
        test_no_rooms_or_finder,
        test_note_copies_hit,
        test_refuses_to_claim_g0_g2_pass,
        test_this_file_does_not_skip,
    )

    test_empty_tenant_query_clears_storage()
    test_empty_role_query_clears_customer()
    test_keeps_inbox_http_and_chat_mux()
    test_no_rooms_or_finder()
    test_refuses_to_claim_g0_g2_pass()
    test_note_copies_hit()
    test_this_file_does_not_skip()


def test_c02e() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_c02e import (
        test_c01f_download_and_verify_kept,
        test_g2_two_customers_query_tenant,
        test_no_fourth_handle,
        test_note_exists,
        test_refuses_to_claim_pass,
    )

    test_g2_two_customers_query_tenant()
    test_c01f_download_and_verify_kept()
    test_refuses_to_claim_pass()
    test_no_fourth_handle()
    test_note_exists()


def test_c02f() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_c02f import (
        test_approve_stays_on_caller_session,
        test_empty_tenant_existing_api,
        test_http_headers_split_sessions,
        test_no_twin_or_science_import,
        test_note_and_interfaces,
        test_reset_empty_unlinks_staff,
        test_reset_one_tenant_only,
        test_tenant_key_is_not_a_path,
        test_tenants_keep_separate_keys,
        test_turn_status_a_cannot_see_b,
    )

    test_empty_tenant_existing_api()
    test_tenants_keep_separate_keys()
    test_turn_status_a_cannot_see_b()
    test_http_headers_split_sessions()
    test_reset_empty_unlinks_staff()
    test_reset_one_tenant_only()
    test_approve_stays_on_caller_session()
    test_tenant_key_is_not_a_path()
    test_no_twin_or_science_import()
    test_note_and_interfaces()


def test_c02g() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_c02g import (
        test_c02e_and_c01f_kept,
        test_g2_two_customers_chat_split,
        test_no_fourth_handle,
        test_note_exists,
        test_refuses_to_claim_pass,
    )

    test_g2_two_customers_chat_split()
    test_c02e_and_c01f_kept()
    test_refuses_to_claim_pass()
    test_no_fourth_handle()
    test_note_exists()


def test_o01a() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_o01a import (
        test_bootstrap_dsh_ver_frozen,
        test_note_freeze_not_bump,
        test_package_json_frozen,
        test_pins_json_frozen,
        test_readme_mentions_both_pins,
        test_sources_agree,
    )

    test_pins_json_frozen()
    test_package_json_frozen()
    test_bootstrap_dsh_ver_frozen()
    test_readme_mentions_both_pins()
    test_sources_agree()
    test_note_freeze_not_bump()


def test_o01b() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_o01b import (
        test_approved_needs_matching_header,
        test_bind_all_interfaces_needs_token,
        test_bind_loopback,
        test_note_exists,
        test_public_keys_hide_secrets,
        test_start_ui_loopback,
    )

    test_bind_loopback()
    test_bind_all_interfaces_needs_token()
    test_approved_needs_matching_header()
    test_start_ui_loopback()
    test_public_keys_hide_secrets()
    test_note_exists()


def test_o01c() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_o01c import (
        test_both_handbooks_exist,
        test_customer_rails,
        test_internal_rails,
        test_no_fourth_handle,
        test_note_exists,
    )

    test_both_handbooks_exist()
    test_internal_rails()
    test_customer_rails()
    test_no_fourth_handle()
    test_note_exists()


def test_o01d() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_o01d import (
        test_customer_mentions_role_and_3080,
        test_no_fourth_handle,
        test_no_g2_pass_claim,
        test_note_exists,
    )

    test_customer_mentions_role_and_3080()
    test_no_g2_pass_claim()
    test_no_fourth_handle()
    test_note_exists()


def test_o01e() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_o01e import (
        test_no_fourth_handle,
        test_no_g2_pass_claim,
        test_note_exists,
        test_start_ui_loopback_and_customer,
    )

    test_start_ui_loopback_and_customer()
    test_no_g2_pass_claim()
    test_no_fourth_handle()
    test_note_exists()


def test_o01f() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_o01f import (
        test_customer_no_eln_append,
        test_internal_eln_readonly_and_settings,
        test_no_fourth_handle,
        test_no_g_pass_claim,
        test_note_exists,
    )

    test_internal_eln_readonly_and_settings()
    test_customer_no_eln_append()
    test_no_g_pass_claim()
    test_no_fourth_handle()
    test_note_exists()


def test_o01g() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_o01g import (
        test_customer_two_tenants,
        test_internal_empty_tenant_and_customer_face,
        test_no_fourth_handle,
        test_no_g_pass_claim,
        test_note_exists,
    )

    test_internal_empty_tenant_and_customer_face()
    test_customer_two_tenants()
    test_no_g_pass_claim()
    test_no_fourth_handle()
    test_note_exists()


def test_o01h() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_o01h import (
        test_no_fourth_handle,
        test_no_g2_pass_claim,
        test_note_exists,
        test_start_ui_tenant_after_customer,
    )

    test_start_ui_tenant_after_customer()
    test_no_g2_pass_claim()
    test_no_fourth_handle()
    test_note_exists()


def test_o01i() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_o01i import (
        test_customer_cannot_see_other_talking,
        test_internal_configured_tenant_own_chat,
        test_no_fourth_handle,
        test_no_g_pass_claim,
        test_note_exists,
    )

    test_internal_configured_tenant_own_chat()
    test_customer_cannot_see_other_talking()
    test_no_g_pass_claim()
    test_no_fourth_handle()
    test_note_exists()


def test_o01k() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_o01k import (
        test_customer_simulator_not_our_receipt,
        test_internal_cirq_in_catalog_not_machine,
        test_no_fourth_handle,
        test_no_g_pass_claim,
        test_note_exists,
    )

    test_internal_cirq_in_catalog_not_machine()
    test_customer_simulator_not_our_receipt()
    test_no_g_pass_claim()
    test_no_fourth_handle()
    test_note_exists()


def test_o01p() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_o01p import (
        test_customer_eln_is_internal,
        test_internal_claim_blocked_short_reason,
        test_no_fourth_handle,
        test_no_g_pass_claim,
        test_note_exists,
    )

    test_internal_claim_blocked_short_reason()
    test_customer_eln_is_internal()
    test_no_g_pass_claim()
    test_no_fourth_handle()
    test_note_exists()


def test_o01q() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_o01q import (
        test_customer_no_pennylane_keep_simulator_line,
        test_internal_pennylane_reserved_not_in_catalog,
        test_no_fourth_handle,
        test_no_g_pass_claim,
        test_note_exists,
    )

    test_internal_pennylane_reserved_not_in_catalog()
    test_customer_no_pennylane_keep_simulator_line()
    test_no_g_pass_claim()
    test_no_fourth_handle()
    test_note_exists()


def test_g0_script() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_g0_script import (
        test_forbids_fake_twin_id,
        test_human_fills_model,
        test_ports_3080_3081,
        test_refuses_to_claim_pass,
        test_scan_hydrogen_line,
        test_script_exists,
    )

    test_script_exists()
    test_scan_hydrogen_line()
    test_ports_3080_3081()
    test_refuses_to_claim_pass()
    test_forbids_fake_twin_id()
    test_human_fills_model()


def test_g1_script() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_g1_script import (
        test_aer_provenance,
        test_no_fourth_handle,
        test_ports_and_engines,
        test_refuses_to_claim_pass,
        test_script_exists,
    )

    test_script_exists()
    test_ports_and_engines()
    test_aer_provenance()
    test_refuses_to_claim_pass()
    test_no_fourth_handle()


def test_g1e() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_g1e import (
        test_no_fourth_handle,
        test_note_exists,
        test_refuses_to_claim_pass,
        test_script_aligned,
    )

    test_script_aligned()
    test_note_exists()
    test_refuses_to_claim_pass()
    test_no_fourth_handle()


def test_g1f() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_g1f import (
        test_no_fourth_handle,
        test_note_exists,
        test_refuses_to_claim_pass,
        test_script_keeps_g1e,
        test_script_pennylane_unlisted,
    )

    test_script_keeps_g1e()
    test_script_pennylane_unlisted()
    test_note_exists()
    test_refuses_to_claim_pass()
    test_no_fourth_handle()


def test_g2e() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_g2e import (
        test_no_fourth_handle,
        test_note_exists,
        test_refuses_to_claim_pass,
        test_script_aligned,
    )

    test_script_aligned()
    test_note_exists()
    test_refuses_to_claim_pass()
    test_no_fourth_handle()


def test_g3_script() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_g3_script import (
        test_mentions_required,
        test_no_fourth_handle,
        test_no_official_codex_invoked,
        test_refuses_g3_pass_phrases,
        test_script_exists,
    )

    test_script_exists()
    test_mentions_required()
    test_refuses_g3_pass_phrases()
    test_no_official_codex_invoked()
    test_no_fourth_handle()


def test_g3e() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_g3e import (
        test_no_fourth_handle,
        test_no_official_codex_invoked,
        test_note_exists,
        test_refuses_to_claim_pass,
        test_script_aligned,
    )

    test_script_aligned()
    test_note_exists()
    test_refuses_to_claim_pass()
    test_no_official_codex_invoked()
    test_no_fourth_handle()


def test_q02b() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_q02b import test_workflow_commands_and_cwd, test_workflow_exists

    test_workflow_exists()
    test_workflow_commands_and_cwd()


def test_q02c() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_q02c import (
        test_cal_fail_closed,
        test_forged_twin_fail_closed,
        test_no_twin_id_minted,
        test_note_exists,
        test_skip_ask_fail_closed,
    )

    test_forged_twin_fail_closed()
    test_skip_ask_fail_closed()
    test_cal_fail_closed()
    test_no_twin_id_minted()
    test_note_exists()


def test_q02_report() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_q02_report import (
        test_no_g3_passed,
        test_no_official_codex_invoked,
        test_report_exists,
        test_report_mentions_required,
    )

    test_report_exists()
    test_report_mentions_required()
    test_no_official_codex_invoked()
    test_no_g3_passed()


def test_r01b() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_r01b import (
        test_no_twin_run_auto_approve_in_frontmatter,
        test_profile_preset_stays_empty,
        test_skills_sync_hides_twin_from_algo,
        test_start_runtime_mentions_skills_sync,
        test_visibility_hides_twin_from_algo,
    )

    test_profile_preset_stays_empty()
    test_visibility_hides_twin_from_algo()
    test_start_runtime_mentions_skills_sync()
    test_no_twin_run_auto_approve_in_frontmatter()
    test_skills_sync_hides_twin_from_algo()


def test_r01d() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_r01d import (
        test_decide_twin_run_lab_ask_algo_deny,
        test_every_skill_is_default_suggestion,
        test_invoke_twin_run_lab_unapproved_needs_ask,
        test_no_skill_auto_approves_twin_run,
        test_note_exists,
        test_profile_skills_stay_in_sync,
        test_twin_run_skill_cannot_bypass_ask,
    )

    test_every_skill_is_default_suggestion()
    test_twin_run_skill_cannot_bypass_ask()
    test_decide_twin_run_lab_ask_algo_deny()
    test_invoke_twin_run_lab_unapproved_needs_ask()
    test_no_skill_auto_approves_twin_run()
    test_profile_skills_stay_in_sync()
    test_note_exists()


def test_r01e() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_r01e import (
        test_copies_agree,
        test_hard_rails,
        test_no_all_reserved_lie,
        test_no_fourth_handle,
        test_note_exists,
        test_r01d_locks,
        test_wired_cirq_reserved_pennylane,
    )

    test_no_all_reserved_lie()
    test_wired_cirq_reserved_pennylane()
    test_r01d_locks()
    test_hard_rails()
    test_copies_agree()
    test_no_fourth_handle()
    test_note_exists()


def test_r02() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_r02 import (
        test_estimate_ok_no_signoff_no_twin,
        test_note_exists,
        test_rails_assets_first_no_invented_twin,
        test_twin_run_unapproved_needs_ask,
        test_unknown_tool_and_no_rule_deny,
    )

    test_unknown_tool_and_no_rule_deny()
    test_estimate_ok_no_signoff_no_twin()
    test_twin_run_unapproved_needs_ask()
    test_rails_assets_first_no_invented_twin()
    test_note_exists()


def test_l102() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_l102 import (
        test_attended_approved_no_parent_context,
        test_attended_not_approved_no_diff_no_files,
        test_diff_has_no_forbidden_symbols,
        test_e13_e17_eval_shape,
        test_oneshot_does_not_write_spi_scratch,
    )

    test_oneshot_does_not_write_spi_scratch()
    test_attended_not_approved_no_diff_no_files()
    test_attended_approved_no_parent_context()
    test_diff_has_no_forbidden_symbols()
    test_e13_e17_eval_shape()


def test_l102d() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_l102d import (
        test_e13_contract_text,
        test_e13_eval_ok,
        test_e17_eval_still_ok,
        test_note_exists,
        test_oneshot_honest_not_green,
    )

    test_oneshot_honest_not_green()
    test_e13_eval_ok()
    test_e17_eval_still_ok()
    test_e13_contract_text()
    test_note_exists()


def test_l102_live() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_l102_live import (
        test_l102_and_l102d_still_green,
        test_no_codex_invoked_claim,
        test_note_exists_unproven,
        test_oneshot_stays_unwired,
        test_refuses_tests_green_as_done,
    )

    test_note_exists_unproven()
    test_refuses_tests_green_as_done()
    test_no_codex_invoked_claim()
    test_oneshot_stays_unwired()
    test_l102_and_l102d_still_green()


def test_a03c() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_a03c import (
        test_approved_dead_url_errors_without_twin_id,
        test_swap_circuit_under_same_id_refused,
        test_unapproved_twin_run_needs_ask,
    )

    test_unapproved_twin_run_needs_ask()
    test_approved_dead_url_errors_without_twin_id()
    test_swap_circuit_under_same_id_refused()


def test_a03_live() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_a03_live import (
        test_live_probe_optional,
        test_no_minted_id,
        test_note_exists,
        test_probe_exists_gated,
        test_refuses_fake_twin,
    )

    test_note_exists()
    test_refuses_fake_twin()
    test_no_minted_id()
    test_probe_exists_gated()
    if (os.environ.get("QAGENT_LIVE_TWIN") or "").strip() == "1":
        test_live_probe_optional()


def test_a03f() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_a03f import (
        test_cloud_and_secrets_stay_out,
        test_empty_env_reads_ionstack_home,
        test_existing_env_not_overwritten,
        test_missing_or_bad_json_is_quiet,
        test_no_fourth_handle,
        test_note_homes_not_wiring,
        test_script_source_mentions_homes,
    )

    test_script_source_mentions_homes()
    test_empty_env_reads_ionstack_home()
    test_existing_env_not_overwritten()
    test_cloud_and_secrets_stay_out()
    test_missing_or_bad_json_is_quiet()
    test_note_homes_not_wiring()
    test_no_fourth_handle()


def test_a03g() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_a03g import (
        test_a03_live_contract_untouched,
        test_live_invoke_identity_no_twin_id,
        test_live_invoke_pipeline_twin_run,
        test_note_copies_hit,
    )

    test_live_invoke_identity_no_twin_id()
    test_live_invoke_pipeline_twin_run()
    test_note_copies_hit()
    test_a03_live_contract_untouched()


def test_e05g() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_e05g import (
        test_dead_url_honest_error,
        test_live_run_eval_e05,
        test_note_copies_hit,
        test_twin_args_default_is_pipeline,
    )

    test_twin_args_default_is_pipeline()
    test_live_run_eval_e05()
    test_dead_url_honest_error()
    test_note_copies_hit()


def test_a03i() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_a03i import (
        test_dead_url_honest_error,
        test_live_approved_vibe_path,
        test_note_copies_hit,
        test_this_file_does_not_skip,
        test_unapproved_still_needs_ask,
        test_vibe_path_default_is_pipeline,
    )

    test_vibe_path_default_is_pipeline()
    test_unapproved_still_needs_ask()
    test_live_approved_vibe_path()
    test_dead_url_honest_error()
    test_note_copies_hit()
    test_this_file_does_not_skip()


def test_i01c() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_i01c import test_assignments_and_approve_path, test_inbox_markup

    test_inbox_markup()
    test_assignments_and_approve_path()


def test_i01d() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_i01d import (
        test_no_document_keydown_sends_chat,
        test_no_third_loop_or_rooms,
        test_note_exists,
        test_prompt_ime_composing,
        test_setbusy_aria_busy_stage,
        test_settings_dialog_exists,
    )

    test_setbusy_aria_busy_stage()
    test_prompt_ime_composing()
    test_no_document_keydown_sends_chat()
    test_settings_dialog_exists()
    test_note_exists()
    test_no_third_loop_or_rooms()


def test_i01e() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_i01e import (
        test_no_fourth_handle_in_payload,
        test_note_exists,
        test_preflight_and_http_omit_identity,
    )

    test_preflight_and_http_omit_identity()
    test_note_exists()
    test_no_fourth_handle_in_payload()


def test_i01f() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_i01f import (
        test_get_list_and_id_are_face_only,
        test_note_exists,
        test_preflight_still_omits_identity,
        test_tenant_lists_isolated,
    )

    test_get_list_and_id_are_face_only()
    test_tenant_lists_isolated()
    test_preflight_still_omits_identity()
    test_note_exists()


def test_i01g() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_i01g import (
        test_get_list_still_thin,
        test_note_exists,
        test_post_create_cancel_reject_are_face,
        test_post_run_approved_without_token_is_403,
    )

    test_post_create_cancel_reject_are_face()
    test_post_run_approved_without_token_is_403()
    test_get_list_still_thin()
    test_note_exists()


def test_i01h() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_i01h import (
        test_assignments_still_face_and_vibe_path_still_full,
        test_invoke_list_engines_is_thin,
        test_invoke_needs_ask_omits_args,
        test_invoke_twin_run_approved_without_token_is_403,
        test_note_exists,
        test_vibe_approved_without_token_is_403,
        test_vibe_unapproved_is_thin,
    )

    test_invoke_list_engines_is_thin()
    test_invoke_twin_run_approved_without_token_is_403()
    test_invoke_needs_ask_omits_args()
    test_vibe_unapproved_is_thin()
    test_vibe_approved_without_token_is_403()
    test_assignments_still_face_and_vibe_path_still_full()
    test_note_exists()


def test_i01i() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_i01i import (
        test_failed_reason_via_service,
        test_get_cancel_has_cancelled_reason,
        test_get_reject_has_rejected_reason,
        test_model_face_does_not_copy_error,
        test_note_exists,
    )

    test_get_cancel_has_cancelled_reason()
    test_get_reject_has_rejected_reason()
    test_failed_reason_via_service()
    test_model_face_does_not_copy_error()
    test_note_exists()


def test_i01j() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_i01j import (
        test_approve_without_token_is_403,
        test_http_chat_omits_session_id,
        test_http_pending_stays_slim,
        test_note_exists,
        test_turn_still_has_session_id,
    )

    test_http_chat_omits_session_id()
    test_http_pending_stays_slim()
    test_approve_without_token_is_403()
    test_turn_still_has_session_id()
    test_note_exists()


def test_i01k() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_i01k import (
        test_eval_token_mismatch_is_403,
        test_eval_with_matching_token_is_thin,
        test_eval_without_token_is_403,
        test_http_chat_omits_used_tools_and_session_id,
        test_note_exists,
        test_turn_still_has_used_tools,
    )

    test_eval_without_token_is_403()
    test_eval_token_mismatch_is_403()
    test_eval_with_matching_token_is_thin()
    test_http_chat_omits_used_tools_and_session_id()
    test_turn_still_has_used_tools()
    test_note_exists()


def test_i01l() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_i01l import (
        test_note_exists,
        test_reset_chat_service_needs_no_token,
        test_reset_token_mismatch_is_403,
        test_reset_with_matching_token_clears_staff,
        test_reset_without_token_is_403,
    )

    test_reset_without_token_is_403()
    test_reset_token_mismatch_is_403()
    test_reset_with_matching_token_clears_staff()
    test_reset_chat_service_needs_no_token()
    test_note_exists()


def test_i01m() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_i01m import (
        test_get_workplace_stays_open,
        test_note_exists,
        test_put_token_mismatch_is_403,
        test_put_with_matching_token_then_get_hides_secret,
        test_put_without_token_is_403,
        test_save_workplace_service_needs_no_token,
    )

    test_put_without_token_is_403()
    test_put_token_mismatch_is_403()
    test_put_with_matching_token_then_get_hides_secret()
    test_get_workplace_stays_open()
    test_save_workplace_service_needs_no_token()
    test_note_exists()


def test_i01n() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_i01n import (
        test_face_makespan_helper,
        test_live_http_face_has_estimate,
        test_model_face_copies_makespan_not_columns,
        test_note_copies_hit,
        test_service_run_face_has_estimate,
        test_this_file_does_not_skip,
    )

    test_face_makespan_helper()
    test_model_face_copies_makespan_not_columns()
    test_service_run_face_has_estimate()
    test_live_http_face_has_estimate()
    test_note_copies_hit()
    test_this_file_does_not_skip()


def test_i01o() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_i01o import (
        test_face_b3_helper,
        test_live_http_signed_has_verdict,
        test_model_face_copies_verdict_not_columns,
        test_note_copies_hit,
        test_this_file_does_not_skip,
    )

    test_face_b3_helper()
    test_model_face_copies_verdict_not_columns()
    test_live_http_signed_has_verdict()
    test_note_copies_hit()
    test_this_file_does_not_skip()


def test_i01p() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_i01p import (
        test_face_aer_helper,
        test_live_http_signed_has_aer,
        test_model_face_copies_aer_not_twin_source,
        test_note_copies_hit,
        test_this_file_does_not_skip,
    )

    test_face_aer_helper()
    test_model_face_copies_aer_not_twin_source()
    test_live_http_signed_has_aer()
    test_note_copies_hit()
    test_this_file_does_not_skip()


def test_i01q() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_i01q import (
        test_chat_bubble_still_sends_approve,
        test_face_shots_helper,
        test_live_approve_face_has_shots,
        test_live_http_signed_has_shots,
        test_model_face_copies_shots_not_columns,
        test_note_copies_hit,
        test_receipt_paints_shots_not_columns,
        test_this_file_does_not_skip,
    )

    test_face_shots_helper()
    test_model_face_copies_shots_not_columns()
    test_live_approve_face_has_shots()
    test_live_http_signed_has_shots()
    test_receipt_paints_shots_not_columns()
    test_chat_bubble_still_sends_approve()
    test_note_copies_hit()
    test_this_file_does_not_skip()


def test_h02e() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_h02e import (
        test_http_source_has_no_agent,
        test_note_exists,
        test_reset_with_token_clears_staff,
    )

    test_http_source_has_no_agent()
    test_reset_with_token_clears_staff()
    test_note_exists()


def test_h02f() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_h02f import (
        test_http_source_has_no_agent,
        test_loop_still_in_source,
        test_note_exists,
        test_reset_agent_ok,
        test_turn_raises,
    )

    test_turn_raises()
    test_reset_agent_ok()
    test_loop_still_in_source()
    test_http_source_has_no_agent()
    test_note_exists()


def test_a02() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_a02 import (
        test_adapter_does_not_import_qchem,
        test_export_parity_requires_asset_id,
        test_failing_bin_not_qchem_cli,
        test_home_missing_bin_not_qchem_cli,
        test_live_cli_asset_id_no_circuit_handle,
        test_missing_bin_not_qchem_cli,
        test_no_bin_local_card,
        test_payload_has_asset_id_no_twin,
    )

    test_no_bin_local_card()
    test_missing_bin_not_qchem_cli()
    test_home_missing_bin_not_qchem_cli()
    test_failing_bin_not_qchem_cli()
    test_payload_has_asset_id_no_twin()
    test_live_cli_asset_id_no_circuit_handle()
    test_export_parity_requires_asset_id()
    test_adapter_does_not_import_qchem()


def test_a02_live() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_a02_live import (
        test_live_probe_optional,
        test_no_twin_id,
        test_note_exists,
        test_probe_exists_gated,
        test_refuses_fake_cli,
    )

    test_note_exists()
    test_refuses_fake_cli()
    test_no_twin_id()
    test_probe_exists_gated()
    if (os.environ.get("QAGENT_LIVE_QCHEM") or "").strip() == "1":
        test_live_probe_optional()


def test_a02g() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_a02g import (
        test_extracts_last_json_from_logs,
        test_live_invoke_qchem_run,
        test_note_copies_live_payload,
    )

    test_extracts_last_json_from_logs()
    test_live_invoke_qchem_run()
    test_note_copies_live_payload()


def test_a02h() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_a02h import (
        test_live_run_then_list_has_card,
        test_note_copies_hit,
        test_offline_no_home_local_wrap,
        test_this_file_does_not_skip,
    )

    test_offline_no_home_local_wrap()
    test_live_run_then_list_has_card()
    test_note_copies_hit()
    test_this_file_does_not_skip()


def test_a02i() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_a02i import (
        test_live_qchem_then_dequant,
        test_note_copies_hit,
        test_this_file_does_not_skip,
    )

    test_live_qchem_then_dequant()
    test_note_copies_hit()
    test_this_file_does_not_skip()


def test_a04() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_a04 import (
        test_adapter_does_not_import_science,
        test_alt_estimate_contract,
        test_e12_e14,
        test_invoke_backend_switch_keeps_tool_name,
        test_mapqccd_estimate_contract,
        test_wired_route_follows_env,
    )

    test_mapqccd_estimate_contract()
    test_alt_estimate_contract()
    test_invoke_backend_switch_keeps_tool_name()
    test_wired_route_follows_env()
    test_e12_e14()
    test_adapter_does_not_import_science()


def test_a04g() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_a04g import (
        test_live_invoke_estimate_not_formula,
        test_note_copies_hit,
        test_this_file_does_not_skip,
    )

    test_live_invoke_estimate_not_formula()
    test_note_copies_hit()
    test_this_file_does_not_skip()


def test_a06g() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_a06g import (
        test_live_invoke_aer_matches_interop,
        test_note_copies_hit,
        test_this_file_does_not_skip,
    )

    test_live_invoke_aer_matches_interop()
    test_note_copies_hit()
    test_this_file_does_not_skip()


def test_a06h() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_a06h import (
        test_live_invoke_export_matches_interop,
        test_note_copies_hit,
        test_this_file_does_not_skip,
    )

    test_live_invoke_export_matches_interop()
    test_note_copies_hit()
    test_this_file_does_not_skip()


def test_a06i() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_a06i import (
        test_live_invoke_import_matches_interop,
        test_note_copies_hit,
        test_this_file_does_not_skip,
    )

    test_live_invoke_import_matches_interop()
    test_note_copies_hit()
    test_this_file_does_not_skip()


def test_a01() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_a01 import (
        test_adapter_does_not_import_qdata_or_mint_twin,
        test_cli_failure_raises,
        test_dead_url_get_job_fails,
        test_dead_url_submit_fails,
        test_forbidden_out_kept,
        test_get_job_payload_keys,
        test_job_from_live_strips_forbidden,
        test_run_recipe_local_card_without_cli,
    )

    test_forbidden_out_kept()
    test_dead_url_submit_fails()
    test_dead_url_get_job_fails()
    test_get_job_payload_keys()
    test_job_from_live_strips_forbidden()
    test_run_recipe_local_card_without_cli()
    test_cli_failure_raises()
    test_adapter_does_not_import_qdata_or_mint_twin()


def test_a01_live() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_a01_live import (
        test_live_probe_optional,
        test_no_twin_id,
        test_note_exists,
        test_probe_exists_gated,
        test_refuses_fake_done,
    )

    test_note_exists()
    test_refuses_fake_done()
    test_no_twin_id()
    test_probe_exists_gated()
    if (os.environ.get("QAGENT_LIVE_QDATA") or "").strip() == "1":
        test_live_probe_optional()


def test_a01e() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_a01e import (
        test_cloud_and_secrets_stay_out,
        test_empty_env_reads_qdata_home,
        test_existing_env_not_overwritten,
        test_missing_or_bad_json_is_quiet,
        test_no_fourth_handle,
        test_no_home_keeps_honest_fail,
        test_note_homes_not_wiring,
        test_script_source_mentions_homes,
    )

    test_script_source_mentions_homes()
    test_empty_env_reads_qdata_home()
    test_existing_env_not_overwritten()
    test_no_home_keeps_honest_fail()
    test_cloud_and_secrets_stay_out()
    test_missing_or_bad_json_is_quiet()
    test_note_homes_not_wiring()
    test_no_fourth_handle()


def test_a01g() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_a01g import (
        test_a01_live_contract_untouched,
        test_live_invoke_qdata_cli,
        test_note_copies_hit,
    )

    test_live_invoke_qdata_cli()
    test_note_copies_hit()
    test_a01_live_contract_untouched()


def test_a01h() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_a01h import (
        test_a01_live_contract_untouched,
        test_healthz_live,
        test_live_invoke_submit_job,
        test_note_copies_hit,
        test_this_file_does_not_skip,
    )

    test_healthz_live()
    test_live_invoke_submit_job()
    test_note_copies_hit()
    test_a01_live_contract_untouched()
    test_this_file_does_not_skip()


def test_a01i() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_a01i import (
        test_a01_live_contract_untouched,
        test_healthz_live,
        test_live_invoke_get_job,
        test_note_copies_hit,
        test_this_file_does_not_skip,
    )

    test_healthz_live()
    test_live_invoke_get_job()
    test_note_copies_hit()
    test_a01_live_contract_untouched()
    test_this_file_does_not_skip()


def test_a01j() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_a01j import (
        test_a01_live_contract_untouched,
        test_live_run_then_get_run_record,
        test_note_copies_hit,
        test_this_file_does_not_skip,
    )

    test_live_run_then_get_run_record()
    test_note_copies_hit()
    test_a01_live_contract_untouched()
    test_this_file_does_not_skip()


def test_a01k() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_a01k import (
        test_a01_live_contract_untouched,
        test_live_run_then_dequant,
        test_note_copies_hit,
        test_this_file_does_not_skip,
    )

    test_live_run_then_dequant()
    test_note_copies_hit()
    test_a01_live_contract_untouched()
    test_this_file_does_not_skip()


def test_r03() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_r03 import (
        test_can_sign_needs_both_handle_and_source,
        test_cancel_signed_raises,
        test_receipt_kind_and_no_secrets,
        test_seal_mutate_shots_verify_fails,
        test_validate_status_signed_without_twin_raises,
        test_verify_receipt_script_rejects_tamper,
    )

    test_can_sign_needs_both_handle_and_source()
    test_validate_status_signed_without_twin_raises()
    test_cancel_signed_raises()
    test_seal_mutate_shots_verify_fails()
    test_receipt_kind_and_no_secrets()
    test_verify_receipt_script_rejects_tamper()


def test_r03g() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_r03g import (
        test_assignment_twin_args_are_pipeline,
        test_dead_url_approve_unsigned,
        test_live_approve_signs_receipt,
        test_note_copies_hit,
        test_this_file_does_not_skip,
        test_unapproved_ask_is_pipeline,
    )

    test_assignment_twin_args_are_pipeline()
    test_unapproved_ask_is_pipeline()
    test_live_approve_signs_receipt()
    test_dead_url_approve_unsigned()
    test_note_copies_hit()
    test_this_file_does_not_skip()


def test_r03h() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_r03h import (
        test_approve_without_token_is_403,
        test_live_http_approve_signs_receipt,
        test_note_copies_hit,
        test_this_file_does_not_skip,
    )

    test_approve_without_token_is_403()
    test_live_http_approve_signs_receipt()
    test_note_copies_hit()
    test_this_file_does_not_skip()


def test_h03() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_h03 import (
        test_apply_env_sets_model,
        test_empty_address_not_ready,
        test_parse_llm_pool,
        test_save_writes_dsh_model,
        test_status_json_hides_secrets,
        test_switch_model_updates_dsh_env,
    )

    test_parse_llm_pool()
    test_save_writes_dsh_model()
    test_apply_env_sets_model()
    test_switch_model_updates_dsh_env()
    test_status_json_hides_secrets()
    test_empty_address_not_ready()


def test_h03d_live() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_h03d_live import (
        _live_forced,
        test_get_never_secrets,
        test_live_probe_optional,
        test_note_exists,
        test_probe_exists_gated,
        test_refuses_fake_switch,
    )

    test_note_exists()
    test_refuses_fake_switch()
    test_get_never_secrets()
    test_probe_exists_gated()
    if _live_forced():
        test_live_probe_optional()


def test_h03e() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_h03e import (
        test_next_model_empty_when_not_ready,
        test_next_model_matches_llm_model_when_set,
        test_note_exists,
        test_secret_keys_absent,
    )

    test_next_model_matches_llm_model_when_set()
    test_next_model_empty_when_not_ready()
    test_secret_keys_absent()
    test_note_exists()


def test_h03f() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_h03f import (
        test_clear_home_drops_line,
        test_cloud_and_hpc_secret_stay_out,
        test_no_fourth_handle,
        test_note_homes_not_wiring,
        test_save_writes_four_homes,
    )

    test_save_writes_four_homes()
    test_clear_home_drops_line()
    test_cloud_and_hpc_secret_stay_out()
    test_note_homes_not_wiring()
    test_no_fourth_handle()


def test_h03g() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_h03g import (
        test_cloud_and_secrets_stay_out,
        test_empty_env_reads_qdata_home,
        test_existing_env_not_overwritten,
        test_missing_or_bad_json_is_quiet,
        test_no_fourth_handle,
        test_note_homes_not_wiring,
        test_script_source_mentions_homes,
    )

    test_script_source_mentions_homes()
    test_empty_env_reads_qdata_home()
    test_existing_env_not_overwritten()
    test_cloud_and_secrets_stay_out()
    test_missing_or_bad_json_is_quiet()
    test_note_homes_not_wiring()
    test_no_fourth_handle()


def test_h03h() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_h03h import (
        test_cloud_and_secrets_stay_out,
        test_dsh_env_then_workplace,
        test_empty_env_reads_qdata_home,
        test_existing_env_not_overwritten,
        test_missing_or_bad_json_is_quiet,
        test_no_fourth_handle,
        test_note_homes_not_wiring,
        test_script_copy_keeps_existing_env,
        test_script_source_mentions_homes,
    )

    test_script_source_mentions_homes()
    test_empty_env_reads_qdata_home()
    test_existing_env_not_overwritten()
    test_dsh_env_then_workplace()
    test_script_copy_keeps_existing_env()
    test_cloud_and_secrets_stay_out()
    test_missing_or_bad_json_is_quiet()
    test_note_homes_not_wiring()
    test_no_fourth_handle()


def test_h03i() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_h03i import (
        test_live_health_homes,
        test_live_workplace_not_ready,
        test_no_fourth_handle,
        test_note_copies_health,
        test_this_file_does_not_skip,
    )

    test_live_health_homes()
    test_live_workplace_not_ready()
    test_note_copies_health()
    test_this_file_does_not_skip()
    test_no_fourth_handle()


def test_h03j() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_h03j import (
        test_cloud_and_hpc_still_out,
        test_empty_llm_save_keeps_existing_deepseek,
        test_nonempty_llm_still_overwrites,
        test_note_copies_hit,
        test_this_file_does_not_skip,
    )

    test_empty_llm_save_keeps_existing_deepseek()
    test_nonempty_llm_still_overwrites()
    test_cloud_and_hpc_still_out()
    test_note_copies_hit()
    test_this_file_does_not_skip()


def test_h04() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_h04 import (
        test_excerpt_length,
        test_max_hits,
        test_miss_is_empty,
        test_no_network_imports,
        test_twinrun_handbook_keywords,
    )

    test_excerpt_length()
    test_miss_is_empty()
    test_no_network_imports()
    test_twinrun_handbook_keywords()
    test_max_hits()


def test_h04d() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_h04d import (
        test_empty_lib_honest,
        test_knowledge_twinrun_hits,
        test_layout_three_roots,
        test_no_network,
        test_no_twin_id_in_excerpts,
        test_note_exists,
    )

    test_knowledge_twinrun_hits()
    test_empty_lib_honest()
    test_no_network()
    test_no_twin_id_in_excerpts()
    test_note_exists()
    test_layout_three_roots()


def test_h04e() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_h04e import (
        test_empty_lib_honest,
        test_estimate_hits,
        test_list_engines_hits,
        test_manuals_on_disk,
        test_no_minted_twin_id,
        test_no_network_in_manuals,
        test_note_exists,
        test_receipt_hits,
    )

    test_list_engines_hits()
    test_estimate_hits()
    test_receipt_hits()
    test_empty_lib_honest()
    test_no_network_in_manuals()
    test_no_minted_twin_id()
    test_note_exists()
    test_manuals_on_disk()


def test_h04f() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_h04f import (
        test_eln_hits,
        test_empty_lib_honest,
        test_manual_on_disk,
        test_no_minted_twin_id,
        test_no_network_in_manual,
        test_note_exists,
    )

    test_eln_hits()
    test_empty_lib_honest()
    test_no_network_in_manual()
    test_no_minted_twin_id()
    test_note_exists()
    test_manual_on_disk()


def test_h04g() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_h04g import (
        test_empty_lib_honest,
        test_manual_on_disk,
        test_no_minted_twin_id,
        test_no_network_in_manual,
        test_note_exists,
        test_tenant_hits,
    )

    test_tenant_hits()
    test_empty_lib_honest()
    test_no_network_in_manual()
    test_no_minted_twin_id()
    test_note_exists()
    test_manual_on_disk()


def test_h04h() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_h04h import (
        test_cirq_hits,
        test_empty_lib_honest,
        test_manual_on_disk,
        test_no_minted_twin_id,
        test_no_network_in_manual,
        test_note_exists,
    )

    test_cirq_hits()
    test_empty_lib_honest()
    test_no_network_in_manual()
    test_no_minted_twin_id()
    test_note_exists()
    test_manual_on_disk()


def test_h04i() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_h04i import (
        test_claim_hits,
        test_empty_lib_honest,
        test_manual_on_disk,
        test_no_minted_twin_id,
        test_no_network_in_manual,
        test_note_exists,
    )

    test_claim_hits()
    test_empty_lib_honest()
    test_no_network_in_manual()
    test_no_minted_twin_id()
    test_note_exists()
    test_manual_on_disk()


def test_h04j() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_h04j import (
        test_empty_lib_honest,
        test_manual_on_disk,
        test_no_minted_twin_id,
        test_no_network_in_manual,
        test_note_exists,
        test_pennylane_hits,
    )

    test_pennylane_hits()
    test_empty_lib_honest()
    test_no_network_in_manual()
    test_no_minted_twin_id()
    test_note_exists()
    test_manual_on_disk()


def test_h04k() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_h04k import (
        test_list_engines_hits,
        test_manual_on_disk,
        test_no_minted_twin_id,
        test_note_exists,
    )

    test_list_engines_hits()
    test_manual_on_disk()
    test_no_minted_twin_id()
    test_note_exists()


def test_l101d() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_l101d import test_spi_shape

    test_spi_shape()


def test_gov() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_gov import (
        test_boot_rails,
        test_eval_gov_pool,
        test_gov_http_face,
        test_handoff_schema,
        test_invoke_records_ask,
        test_knowledge_hits_orange_book,
        test_safe_mode_is_boot,
        test_witness_gates,
    )

    test_boot_rails()
    test_witness_gates()
    test_handoff_schema()
    test_safe_mode_is_boot()
    test_eval_gov_pool()
    test_gov_http_face()
    test_knowledge_hits_orange_book()
    test_invoke_records_ask()


def test_ux() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_ux import (
        test_catalog_explains_estimate_slot,
        test_docs_hit_error_codes,
        test_export_needs_context,
        test_gov_face_has_lamps,
        test_life_hides_tool_names,
        test_list_engines_announces_switch,
        test_note_exists,
        test_pin_qiskit_needs_body,
        test_preset_http_read_vs_write,
        test_shell_keeps_rails,
    )

    test_catalog_explains_estimate_slot()
    test_list_engines_announces_switch()
    test_preset_http_read_vs_write()
    test_gov_face_has_lamps()
    test_pin_qiskit_needs_body()
    test_export_needs_context()
    test_docs_hit_error_codes()
    test_life_hides_tool_names()
    test_shell_keeps_rails()
    test_note_exists()


def test_u09() -> None:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from test_u09 import (
        test_asks_lamp_does_not_print_jsonl_count,
        test_console_skeleton,
        test_gold_stays_on_permit_only,
        test_hard_rails,
        test_note_copies_hit,
        test_this_file_does_not_skip,
    )

    test_console_skeleton()
    test_asks_lamp_does_not_print_jsonl_count()
    test_gold_stays_on_permit_only()
    test_hard_rails()
    test_note_copies_hit()
    test_this_file_does_not_skip()


def test_slots() -> None:
    try:
        fill("S-QDATA-04", "qdata_run_recipe.execute")
    except FillSlotError as exc:
        assert exc.slot_id == "S-QDATA-04"
    else:
        raise AssertionError("expected FillSlotError")
    assert empty_slots() == []
    for slot in load_slots():
        assert slot.fill
        if slot.fill.endswith((".ts", ".yml", ".md", ".py")):
            assert (QROOT / slot.fill).exists(), slot.fill
        elif slot.fill == "pins.json":
            assert (QROOT / "pins.json").exists()


def main() -> int:
    failed = 0
    for name, fn in [
        ("policy", test_policy),
        ("gov", test_gov),
        ("ux", test_ux),
        ("u09", test_u09),
        ("contracts", test_contracts),
        ("engines", test_engines),
        ("ports", test_ports),
        ("company_shell", test_company_shell),
        ("workbench", test_workbench),
        ("chat", test_chat),
        ("dsh_session", test_dsh_session),
        ("product_eval", test_product_eval),
        ("q01", test_q01),
        ("qh06", test_qh06),
        ("docs_empty", test_docs_empty),
        ("h01d", test_h01d),
        ("h01d_live", test_h01d_live),
        ("h01d_ws", test_h01d_ws),
        ("h01d_orphan", test_h01d_orphan),
        ("h01d_approve_live", test_h01d_approve_live),
        ("h01e_settings", test_h01e_settings),
        ("h01g", test_h01g),
        ("h01h", test_h01h),
        ("h01i", test_h01i),
        ("h01j", test_h01j),
        ("h01k", test_h01k),
        ("h01l", test_h01l),
        ("h01m", test_h01m),
        ("l103", test_l103),
        ("l103_plan", test_l103_plan),
        ("l103_relax", test_l103_relax),
        ("l103_relax2", test_l103_relax2),
        ("l103_wire", test_l103_wire),
        ("l103_how", test_l103_how),
        ("l103_pl", test_l103_pl),
        ("iface_pl", test_iface_pl),
        ("l104", test_l104),
        ("l104c", test_l104c),
        ("l104c_align", test_l104c_align),
        ("i03", test_i03),
        ("i03d", test_i03d),
        ("i03e", test_i03e),
        ("i03f", test_i03f),
        ("i03g", test_i03g),
        ("i03h", test_i03h),
        ("i03i", test_i03i),
        ("i03j", test_i03j),
        ("i03k", test_i03k),
        ("i03l", test_i03l),
        ("i03m", test_i03m),
        ("i03n", test_i03n),
        ("i03o", test_i03o),
        ("i03p", test_i03p),
        ("i03q", test_i03q),
        ("i03r", test_i03r),
        ("r03c", test_r03c),
        ("i02", test_i02),
        ("i02d", test_i02d),
        ("a05", test_a05),
        ("a05_live", test_a05_live),
        ("a05b", test_a05b),
        ("a05c", test_a05c),
        ("a05g", test_a05g),
        ("a05h", test_a05h),
        ("a05i", test_a05i),
        ("c01", test_c01),
        ("c02", test_c02),
        ("c02d", test_c02d),
        ("c03", test_c03),
        ("c01c", test_c01c),
        ("c01d", test_c01d),
        ("c01e", test_c01e),
        ("c01f", test_c01f),
        ("c01g", test_c01g),
        ("c01h", test_c01h),
        ("c01i", test_c01i),
        ("c01j", test_c01j),
        ("c01k", test_c01k),
        ("c01l", test_c01l),
        ("c01m", test_c01m),
        ("c01n", test_c01n),
        ("c01o", test_c01o),
        ("c01p", test_c01p),
        ("c01q", test_c01q),
        ("c01r", test_c01r),
        ("c01u", test_c01u),
        ("c01v", test_c01v),
        ("c01w", test_c01w),
        ("c01x", test_c01x),
        ("c01y", test_c01y),
        ("c01z", test_c01z),
        ("c01aa", test_c01aa),
        ("c01ab", test_c01ab),
        ("c01ac", test_c01ac),
        ("c01ad", test_c01ad),
        ("c01af", test_c01af),
        ("c01ae", test_c01ae),
        ("c02e", test_c02e),
        ("c02f", test_c02f),
        ("c02g", test_c02g),
        ("c02h", test_c02h),
        ("o01a", test_o01a),
        ("o01b", test_o01b),
        ("o01c", test_o01c),
        ("o01d", test_o01d),
        ("o01e", test_o01e),
        ("o01f", test_o01f),
        ("o01g", test_o01g),
        ("o01h", test_o01h),
        ("o01i", test_o01i),
        ("o01k", test_o01k),
        ("o01p", test_o01p),
        ("o01q", test_o01q),
        ("g0_script", test_g0_script),
        ("g1_script", test_g1_script),
        ("g1e", test_g1e),
        ("g1f", test_g1f),
        ("g2e", test_g2e),
        ("g3_script", test_g3_script),
        ("g3e", test_g3e),
        ("q02b", test_q02b),
        ("q02c", test_q02c),
        ("q02_report", test_q02_report),
        ("r01b", test_r01b),
        ("r01d", test_r01d),
        ("r01e", test_r01e),
        ("r02", test_r02),
        ("l102", test_l102),
        ("l102d", test_l102d),
        ("l102_live", test_l102_live),
        ("a03c", test_a03c),
        ("a03_live", test_a03_live),
        ("a03f", test_a03f),
        ("a03g", test_a03g),
        ("e05g", test_e05g),
        ("a03i", test_a03i),
        ("i01c", test_i01c),
        ("i01e", test_i01e),
        ("i01f", test_i01f),
        ("i01g", test_i01g),
        ("i01h", test_i01h),
        ("i01i", test_i01i),
        ("i01j", test_i01j),
        ("i01k", test_i01k),
        ("i01l", test_i01l),
        ("i01m", test_i01m),
        ("i01n", test_i01n),
        ("i01o", test_i01o),
        ("i01p", test_i01p),
        ("i01q", test_i01q),
        ("h02e", test_h02e),
        ("h02f", test_h02f),
        ("i01d", test_i01d),
        ("a02", test_a02),
        ("a02_live", test_a02_live),
        ("a02g", test_a02g),
        ("a02h", test_a02h),
        ("a02i", test_a02i),
        ("a04", test_a04),
        ("a04g", test_a04g),
        ("a06g", test_a06g),
        ("a06h", test_a06h),
        ("a06i", test_a06i),
        ("a01", test_a01),
        ("a01_live", test_a01_live),
        ("a01e", test_a01e),
        ("a01g", test_a01g),
        ("a01h", test_a01h),
        ("a01i", test_a01i),
        ("a01j", test_a01j),
        ("a01k", test_a01k),
        ("r03", test_r03),
        ("r03g", test_r03g),
        ("r03h", test_r03h),
        ("h03", test_h03),
        ("h03d_live", test_h03d_live),
        ("h03e", test_h03e),
        ("h03f", test_h03f),
        ("h03g", test_h03g),
        ("h03h", test_h03h),
        ("h03i", test_h03i),
        ("h03j", test_h03j),
        ("h04", test_h04),
        ("h04d", test_h04d),
        ("h04e", test_h04e),
        ("h04f", test_h04f),
        ("h04g", test_h04g),
        ("h04h", test_h04h),
        ("h04i", test_h04i),
        ("h04j", test_h04j),
        ("h04k", test_h04k),
        ("l101d", test_l101d),
        ("slots", test_slots),
    ]:
        try:
            check(name, fn)
        except Exception:
            failed += 1
            print(f"FAIL {name}")
            traceback.print_exc()
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
