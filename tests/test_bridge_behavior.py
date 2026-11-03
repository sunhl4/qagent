from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = (ROOT / "packages/company-agent-core/src/runtime.js").as_uri()
NODE = Path(os.environ.get("COMPANY_AGENT_RUNTIME_DIR",
            Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
            / "unitqc-company-agent/dsh-runtime")) / "node_modules/node/bin/node"
PYTHON = Path(sys.executable)


def run(program, *, env=None, timeout=45):
    environment = {
        "PATH": "/usr/bin:/bin", "COMPANY_AGENT_PYTHON": str(PYTHON),
        "COMPANY_AGENT_PYTHONPATH": str(ROOT / "src"),
        "COMPANY_AGENT_PROFILE": "company-agent", "COMPANY_AGENT_PRESET": "lab",
        # Hermetic ledger: every bridge probe gets a fresh turn identity and
        # receipt root, so termination budgets never accumulate across runs.
        "COMPANY_AGENT_TURN_ID": f"fixture-{uuid.uuid4().hex[:16]}",
        "COMPANY_AGENT_RECEIPT_DIR": tempfile.mkdtemp(prefix="company-agent-fixture-"),
    }
    environment.update(env or {})
    # Windows node aborts at process init (ncrypto::CSPRNG) without SystemRoot,
    # and subprocessEnvironment() requires absolute PATH entries, so the POSIX
    # "/usr/bin:/bin" hermetic PATH only applies off-Windows.
    if os.name == "nt":
        environment["SystemRoot"] = os.environ.get("SystemRoot", "")
        environment["windir"] = os.environ.get("windir", "")
        environment["PATH"] = os.environ.get("PATH", "")
    assert NODE.is_file(), "pinned DSH Node missing; run scripts/bootstrap_dsh.sh"
    assert PYTHON.is_file(), "managed test Python missing"
    return subprocess.run([str(NODE), "--input-type=module", "-e", program], cwd=ROOT,
                          env=environment, capture_output=True, text=True, timeout=timeout)


def fake_python(tmp_path, body):
    path = tmp_path / "fake-python"
    path.write_text(f"#!{PYTHON}\n" + body)
    path.chmod(0o700)
    return str(path)


@pytest.mark.parametrize("value", [
    "Number.MAX_SAFE_INTEGER + 1",
    "-(Number.MAX_SAFE_INTEGER + 1)",
])
def test_bridge_rejects_nested_unsafe_integer_before_spawn(tmp_path, value):
    marker = tmp_path / "spawned"
    executable = fake_python(tmp_path, f"from pathlib import Path\nPath({str(marker)!r}).touch()\n")
    program = f"""import {{ validate }} from {json.dumps(RUNTIME)};
try {{
  await validate('company_capabilities', {{nested: [{{value: {value}}}]}});
}} catch (error) {{
  console.log(error.message);
}}
"""
    result = run(program, env={"COMPANY_AGENT_PYTHON": executable})
    assert result.returncode == 0, result.stderr
    assert "arguments must be JSON serializable" in result.stdout
    assert not marker.exists()


def test_bridge_scrubs_environment_and_uses_stdin(tmp_path):
    executable = fake_python(tmp_path, """import json,os,sys
bad = ['PYTHONHOME','PYTHONSTARTUP','NODE_OPTIONS','LD_LIBRARY_PATH','COMPANY_AGENT_APPROVAL_CONTEXT']
assert not any(key in os.environ for key in bad)
assert os.environ['PYTHONPATH'] == os.environ['COMPANY_AGENT_PYTHONPATH']
assert sys.argv[-1] == '-'
assert 'private-input-marker' not in ' '.join(sys.argv)
assert json.load(sys.stdin) == {'query':'private-input-marker'}
print(json.dumps({'valid':True,'error':None}))
""")
    program = f"""import {{ validate }} from {json.dumps(RUNTIME)};
// Set unsafe variables after Node starts, to test only the child environment.
for (const key of ['PYTHONHOME','PYTHONSTARTUP','NODE_OPTIONS','LD_LIBRARY_PATH',
  'COMPANY_AGENT_APPROVAL_CONTEXT']) process.env[key]='unsafe';
console.log(JSON.stringify(await validate('company_knowledge_search', {{query:'private-input-marker'}})));
"""
    result = run(program, env={"COMPANY_AGENT_PYTHON": executable})
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"valid": True, "error": None}


@pytest.mark.parametrize("mode", ["cancel", "timeout", "stdout", "stderr"])
def test_bridge_waits_for_child_exit_on_failure(tmp_path, mode):
    marker = tmp_path / "pid"
    body = f"""import os,time,sys
from pathlib import Path
Path({str(marker)!r}).write_text(str(os.getpid()))
"""
    if mode in {"stdout", "stderr"}:
        body += f"print('x'*1_100_001,file=sys.{mode},flush=True)\n"
    body += "time.sleep(60)\n"
    executable = fake_python(tmp_path, body)
    timer_override = (
        "globalThis.setTimeout=(fn,ms,...args)=>realTimeout(fn,ms===35000?200:ms,...args);"
        if mode == "timeout" else ""
    )
    program = f"""import {{ readFileSync, existsSync }} from 'node:fs';
const realTimeout = globalThis.setTimeout;
{timer_override}
const {{ validate }} = await import({json.dumps(RUNTIME)});
const control = new AbortController();
const task = validate('company_capabilities', {{}}, control.signal);
if ({json.dumps(mode)} === 'cancel') {{
  for (let i=0; i<100 && !existsSync({json.dumps(str(marker))}); i++)
    await new Promise(resolve => realTimeout(resolve,10));
  control.abort();
}}
let error;
try {{ await task; }} catch (caught) {{ error=caught.message; }}
const pid=Number(readFileSync({json.dumps(str(marker))},'utf8'));
let alive=true;
try {{ process.kill(pid,0); }} catch {{ alive=false; }}
console.log(JSON.stringify({{error,alive}}));
"""
    result = run(program, env={"COMPANY_AGENT_PYTHON": executable})
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["alive"] is False
    expected = {"cancel": "cancelled", "timeout": "timed out", "stdout": "output exceeded",
                "stderr": "diagnostics exceeded"}[mode]
    assert expected in payload["error"]


def test_diagnostic_parser_rejects_extra_duplicate_and_wrong_typed_metadata():
    event = {"version": "1.0", "event": "provider", "tool": "quantum_device_run",
             "operation": "device.run", "request_id": "req_" + "a" * 32,
             "contract_digest": "sha256:" + "b" * 64, "elapsed_ms": 0, "status": "started",
             "error_category": "none", "execution_state": "dispatched"}
    good = "company-agent-diagnostic:" + json.dumps(event, separators=(",", ":"))
    bad = [good.replace('"elapsed_ms":0', '"elapsed_ms":true'),
           good.replace('"version":"1.0"', '"version":"0","version":"1.0"'),
           good[:-1] + ',"extra":"private"}', "arbitrary stderr", good.replace('"device.run"', '[]')]
    result = run(f"import {{ parseDiagnostic }} from {json.dumps(RUNTIME)}; "
                 f"console.log(JSON.stringify({json.dumps([good, *bad])}.map(parseDiagnostic)));")
    assert result.returncode == 0, result.stderr
    rows = json.loads(result.stdout)
    assert rows == [event, *[None for _ in bad]]


def test_unknown_tool_diagnostic_uses_only_fixed_redacted_labels():
    event = {"version": "1.0", "event": "invocation", "tool": "unknown", "operation": "unknown",
             "request_id": "", "contract_digest": "sha256:" + "b" * 64, "elapsed_ms": 0,
             "status": "denied", "error_category": "validation", "execution_state": "not_dispatched"}
    variants = [event, {**event, "event": "provider"}, {**event, "tool": "user_supplied_name"},
                {**event, "status": "ok"}]
    lines = ["company-agent-diagnostic:" + json.dumps(row, separators=(",", ":")) for row in variants]
    result = run(f"import {{ parseDiagnostic }} from {json.dumps(RUNTIME)}; "
                 f"console.log(JSON.stringify({json.dumps(lines)}.map(parseDiagnostic)));")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == [event, None, None, None]


def test_spawn_failure_is_short_and_settles_after_close():
    result = run(f"import {{ validate }} from {json.dumps(RUNTIME)}; "
                 "try { await validate('company_capabilities',{}); } "
                 "catch(e) { console.log(e.message); }",
                 env={"COMPANY_AGENT_PYTHON": "/not-present/fixture-python"})
    assert result.returncode == 0
    assert "process failed" in result.stdout
    assert "/not-present" not in result.stdout


@pytest.mark.parametrize("early_exit", [False, True])
def test_bridge_kills_descendant_holding_inherited_pipes_and_settles_bounded(tmp_path, early_exit):
    child_pid = tmp_path / "child-pid"
    descendant_pid = tmp_path / "descendant-pid"
    ending = 'print(\'{"valid":true,"error":null}\',flush=True)' if early_exit else 'time.sleep(60)'
    body = f"""import os,subprocess,sys,time
from pathlib import Path
Path({str(child_pid)!r}).write_text(str(os.getpid()))
code = ("import os,time; from pathlib import Path; "
        "Path({str(descendant_pid)!r}).write_text(str(os.getpid())); time.sleep(60)")
subprocess.Popen([sys.executable, '-c', code])
{ending}
"""
    executable = fake_python(tmp_path, body)
    program = f"""import {{ existsSync, readFileSync }} from 'node:fs';
import {{ performance }} from 'node:perf_hooks';
const {{ validate }} = await import({json.dumps(RUNTIME)});
const control = new AbortController();
const task = validate('company_capabilities', {{}}, control.signal);
const paths = [{json.dumps(str(child_pid))}, {json.dumps(str(descendant_pid))}];
for (let i=0; i<200 && paths.some(path => !existsSync(path)); i++)
  await new Promise(resolve => setTimeout(resolve,10));
const started = performance.now();
if (!{json.dumps(early_exit)}) control.abort();
let error;
try {{ await task; }} catch (caught) {{ error = caught.message; }}
const elapsed = performance.now() - started;
const pids = paths.map(path => Number(readFileSync(path,'utf8')));
let alive = pids.map(pid => {{ try {{ process.kill(pid,0); return true; }} catch {{ return false; }} }});
for (let i=0; i<100 && alive.some(Boolean); i++) {{
  await new Promise(resolve => setTimeout(resolve,10));
  alive = pids.map(pid => {{ try {{ process.kill(pid,0); return true; }} catch {{ return false; }} }});
}}
console.log(JSON.stringify({{error,elapsed,alive}}));
"""
    result = run(program, env={"COMPANY_AGENT_PYTHON": executable}, timeout=10)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert ("inherited pipes" if early_exit else "cancelled") in payload["error"]
    assert payload["elapsed"] < 2_000
    assert payload["alive"] == [False, False]


@pytest.mark.parametrize("payload", [
    [], {},
    {"tool": "quantum_device_run", "decision": "ask", "status": "ok", "payload": None, "error": None},
    {"tool": "quantum_device_run", "decision": "deny", "status": "ok", "payload": {}, "error": None},
])
def test_bad_device_envelope_after_dispatch_retains_unknown_state(tmp_path, payload):
    event = {"version": "1.0", "event": "provider", "tool": "quantum_device_run",
             "operation": "device.run", "request_id": "req_" + "a" * 32,
             "contract_digest": "sha256:" + "b" * 64, "elapsed_ms": 0, "status": "started",
             "error_category": "none", "execution_state": "dispatched"}
    diagnostic = "company-agent-diagnostic:" + json.dumps(event, separators=(",", ":"))
    executable = fake_python(tmp_path, "import sys\n"
                             f"print({diagnostic!r}, file=sys.stderr, flush=True)\n"
                             f"print({json.dumps(payload)!r})\n")
    result = run(f"import {{ invoke }} from {json.dumps(RUNTIME)}; "
                 "try { await invoke('quantum_device_run',{circuit_id:'circ_fixture',shots:1},true); } "
                 "catch(e) { console.log(e.message); }",
                 env={"COMPANY_AGENT_PYTHON": executable})
    assert result.returncode == 0, result.stderr
    assert "outcome unknown; do not retry automatically; request_id=" + event["request_id"] in result.stdout
    diagnostics = [json.loads(line.removeprefix("company-agent-diagnostic:"))
                   for line in result.stderr.splitlines()]
    assert diagnostics[-1]["execution_state"] == "unknown"
    assert diagnostics[-1]["request_id"] == event["request_id"]


def test_invocation_final_diagnostic_does_not_erase_device_dispatch(tmp_path):
    provider = {"version": "1.0", "event": "provider", "tool": "quantum_device_run",
                "operation": "device.run", "request_id": "req_" + "a" * 32,
                "contract_digest": "sha256:" + "b" * 64, "elapsed_ms": 0,
                "status": "started", "error_category": "none",
                "execution_state": "dispatched"}
    invocation = {**provider, "event": "invocation", "request_id": "", "status": "error",
                  "error_category": "validation", "execution_state": "not_dispatched"}
    lines = ["company-agent-diagnostic:" + json.dumps(row, separators=(",", ":"))
             for row in (provider, invocation)]
    executable = fake_python(
        tmp_path,
        "import json,sys\n"
        + "\n".join(f"print({line!r}, file=sys.stderr, flush=True)" for line in lines)
        + "\nprint(json.dumps([]))\n",
    )
    result = run(
        f"import {{ invoke }} from {json.dumps(RUNTIME)}; "
        "try { await invoke('quantum_device_run',{circuit_id:'circ_fixture',shots:1},true); } "
        "catch(e) { console.log(e.message); }",
        env={"COMPANY_AGENT_PYTHON": executable},
    )
    assert result.returncode == 0, result.stderr
    expected = "outcome unknown; do not retry automatically; request_id=" + provider["request_id"]
    assert expected in result.stdout
    diagnostics = [json.loads(line.removeprefix("company-agent-diagnostic:"))
                   for line in result.stderr.splitlines()]
    assert [row["event"] for row in diagnostics] == ["provider", "invocation", "provider"]
    assert diagnostics[-1]["execution_state"] == "unknown"
    assert diagnostics[-1]["request_id"] == provider["request_id"]


def test_real_entry_never_inherits_device_approval():
    # An unapproved bridge call is a policy question, never an execution.
    result = run(f"import {{ invoke }} from {json.dumps(RUNTIME)}; "
                 "console.log(JSON.stringify(await invoke('quantum_device_run',"
                 "{circuit_id:'circ_fixture',shots:1})));",
                 env={"COMPANY_AGENT_APPROVAL_CONTEXT": "dsh"})
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["status"] == "needs_ask"
