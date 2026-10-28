// Test-only fixed model fixture. All turns and tool scheduling belong to the real DSH loop.
import { pathToFileURL } from "node:url";
import { resolve } from "node:path";
import { createServer } from "node:http";
import { once } from "node:events";

const root = process.env.COMPANY_AGENT_TEST_ROOT;
const modules = process.env.COMPANY_AGENT_TEST_MODULES;
const scenario = process.argv[2] || "allow";
const upstream = name => import(pathToFileURL(resolve(modules, "@deepseek-ai", name, "lib/index.js")));
const { Context } = await upstream("cordis");
const llm = await upstream("dsh-llm");
const ctx = new Context();
const fibers = [];
for (const name of ["dsh-system-prompt", "dsh-session", "dsh-session-projection", "dsh-agent",
  "dsh-llm", "dsh-tools", "dsh-user-approval", "dsh-agent-loop"]) {
  const module = await upstream(name);
  fibers.push(await ctx.plugin(module.default, name === "dsh-agent-loop" ? { agents: [] } : {}));
}
// The same real DSH approval lifecycle also covers cloud/HPC submissions.
const fixtureCapability = process.env.COMPANY_AGENT_FIXTURE_CAPABILITY || "device";
const fixtureTool = fixtureCapability === "cloud" ? "quantum_cloud_submit"
  : fixtureCapability === "hpc" ? "hpc_submit" : "quantum_device_run";
const fixtureArgs = fixtureCapability === "cloud"
  ? { program_path: "fixture.qasm", target: "fixture-sim", shots: 100 }
  : fixtureCapability === "hpc" ? { job_name: "fixture", script: "/home/fixture/test.sh" }
    : { circuit_id: "circ_fixture", shots: 1 };
let calls = 0;
let asks = 0;
const events = [];
let handle;
const realTimeout = globalThis.setTimeout;
const realClearTimeout = globalThis.clearTimeout;
const bridgeTimers = new Map();
if (scenario === "timeout_after") {
  globalThis.setTimeout = (fn, ms, ...args) => {
    const timer = realTimeout(fn, ms, ...args);
    if (ms === 35000) bridgeTimers.set(timer, { fn, args });
    return timer;
  };
  globalThis.clearTimeout = timer => {
    bridgeTimers.delete(timer);
    return realClearTimeout(timer);
  };
}
const server = createServer(async (req, res) => {
  let body = "";
  for await (const chunk of req) body += chunk;
  const request = JSON.parse(body);
  calls++;
  if (scenario === "cancel_after") { handle.agent.cancel({kind: "user"}); return; }
  if (scenario === "timeout_after") {
    // Trigger the real bridge timeout callback only after the server received the request.
    // A fixed startup delay races WSL file access and can time out authorization instead.
    const current = [...bridgeTimers.entries()].at(-1);
    if (!current) throw new Error("device bridge timeout was not armed");
    const [timer, { fn, args }] = current;
    globalThis.clearTimeout(timer);
    realTimeout(() => fn(...args), 25);
    return;
  }
  const result = fixtureCapability === "cloud"
    ? { provider: "uqc-cloud", cloud_task: "fixture-task", target: "fixture-sim", state: "submitted", shots: 100 }
    : fixtureCapability === "hpc"
      ? { provider: "hpc-slurm-ssh", slurm_number: "101", job_name: "fixture", state: "pending" }
      : { twin_id: "twin_fixture", provenance: "qccd-twin", shots_actual: 1,
        summary: { status: "completed", duration_ms: 1 } };
  res.writeHead(200, {"Content-Type": "application/json"});
  res.end(JSON.stringify({ protocol: "company-agent-provider/1.0", provider: fixtureCapability === "cloud"
    ? "uqc-cloud" : fixtureCapability === "hpc" ? "hpc-slurm-ssh" : "ionstack-twinrun",
    ok: true, request_id: request.request_id, result }));
});
server.listen(0, "127.0.0.1");
await once(server, "listening");
process.env.COMPANY_AGENT_DEVICE_INVOKE_URL = `http://127.0.0.1:${server.address().port}/invoke`;
process.env.COMPANY_AGENT_DEVICE_TOKEN = "local-fixture";
for (const kind of ["HPC", "CLOUD"]) {
  process.env[`COMPANY_AGENT_${kind}_INVOKE_URL`] = process.env.COMPANY_AGENT_DEVICE_INVOKE_URL;
  process.env[`COMPANY_AGENT_${kind}_TOKEN`] = "local-fixture";
}
let generation = 0;
class FixedAdapter extends llm.LlmAdapter {
  async *stream() {
    const toolTurns = scenario === "twice" ? 2 : 1;
    if (generation++ < toolTurns) {
      const id = `call-fixture-${generation}`;
      const args = JSON.stringify(fixtureArgs);
      yield { type: "block-start", index: 0, blockType: "tool-call" };
      yield { type: "tool-call-delta", index: 0, id, name: fixtureTool, argumentsDelta: args };
      yield { type: "block-end", index: 0,
        block: { type: "tool-call", id, name: fixtureTool, arguments: args } };
      yield { type: "finish", reason: { kind: "tool-calls" } };
    } else {
      yield { type: "block-start", index: 0, blockType: "text" };
      yield { type: "text-delta", index: 0, text: "fixture completed" };
      yield { type: "block-end", index: 0, block: { type: "text", text: "fixture completed" } };
      yield { type: "finish", reason: { kind: "stop" } };
    }
  }
}
ctx.llm.registerAdapter(["fixture"], new FixedAdapter());
ctx.on("session/event", (_session, event) => events.push(event), {global: true});
const approvalRequests = [];
if (scenario !== "missing") ctx.on("approval/request", async (request) => {
  asks++;
  approvalRequests.push({toolName: request.toolName, reason: request.reason});
  if (scenario === "cancel_before" || scenario === "late") {
    handle.agent.cancel({kind: "user"});
    await new Promise(resolve => setTimeout(resolve, 50));
    return scenario === "late" ? "allowed-once" : "cancelled";
  }
  return scenario === "reject" ? "rejected" : "allowed-once";
});
const { createRequire } = await import("node:module");
const require = createRequire(resolve(root, "profiles/company-agent/package.json"));
const bridge = await import(pathToFileURL(require.resolve("@unitqc/company-agent-core/runtime")));
const policy = await import(pathToFileURL(require.resolve("@unitqc/company-agent-policy")));
policy.apply(ctx);
bridge.registerCapabilityTools(ctx, [fixtureCapability === "cloud" ? "compute.cloud"
  : fixtureCapability === "hpc" ? "compute.hpc" : "quantum.device"]);
if (scenario === "deny_boot") process.env.COMPANY_AGENT_PRESET = "boot";
if (scenario === "deny_algo") process.env.COMPANY_AGENT_PRESET = "algo";
handle = await ctx.agents.create({sessionId: "session-fixture", meta: {cwd: root},
  agentOptions: {provider: "fixture", model: "fixed"}});
handle.agent.followup(llm.createUserMessage({content: [{type: "text", text: "Run the fixed local fixture."}],
  source: {kind: "user"}}));
await handle.agent.whenIdle();
await new Promise(resolve => setTimeout(resolve, 80));
const audit = events.filter(event => event.type.startsWith("approval/"));
console.log(JSON.stringify({scenario, calls, asks, generation, audit, approvalRequests,
  eventTypes: events.map(event => event.type),
  results: events.filter(event => event.type.includes("tool") || event.type === "assistant/attempt"
    || event.type === "step/end" || event.type === "turn/end")}));
await handle.dispose();
server.closeAllConnections();
await new Promise(resolve => server.close(resolve));
// This isolated fixture process exits only after DSH agent and HTTP handles have settled.
process.exit(0);
