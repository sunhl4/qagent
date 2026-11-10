// Real DSH agent loop for one literature seat turn. The model is a fixed local
// adapter, so no remote model is called and no HPC job is submitted.
import { pathToFileURL } from "node:url";
import { resolve } from "node:path";

const root = process.env.COMPANY_AGENT_TEST_ROOT;
const modules = process.env.COMPANY_AGENT_TEST_MODULES;
const workspace = process.env.PROBE_WORKSPACE;
const compileArgs = JSON.parse(process.env.PROBE_COMPILE);
const runArgs = JSON.parse(process.env.PROBE_RUN);
const steps = [
  ["company_literature_search", { query: "synthetic source", fixture: "search.json" }],
  ["company_literature_fetch", { paper_id: "demo1", fixture: "paper" }],
  ["company_literature_index", { paper_id: "demo1" }],
  ["company_research_compile", compileArgs],
  ["company_research_run", runArgs],
];
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
const events = [];
let asks = 0;
const approvalTools = [];
let generation = 0;
class FixedAdapter extends llm.LlmAdapter {
  async *stream() {
    if (generation < steps.length) {
      const [name, args] = steps[generation];
      generation += 1;
      const id = `call-literature-${generation}`;
      const encoded = JSON.stringify(args);
      yield { type: "block-start", index: 0, blockType: "tool-call" };
      yield { type: "tool-call-delta", index: 0, id, name, argumentsDelta: encoded };
      yield { type: "block-end", index: 0,
        block: { type: "tool-call", id, name, arguments: encoded } };
      yield { type: "finish", reason: { kind: "tool-calls" } };
    } else {
      generation += 1;
      yield { type: "block-start", index: 0, blockType: "text" };
      yield { type: "text-delta", index: 0, text: "seat turn completed" };
      yield { type: "block-end", index: 0, block: { type: "text", text: "seat turn completed" } };
      yield { type: "finish", reason: { kind: "stop" } };
    }
  }
}
ctx.llm.registerAdapter(["fixture"], new FixedAdapter());
ctx.on("session/event", (_session, event) => events.push(event), { global: true });
ctx.on("approval/request", async (request) => {
  asks += 1;
  approvalTools.push(request.toolName);
  return "allowed-once";
});
const { createRequire } = await import("node:module");
const require = createRequire(resolve(root, "profiles/company-agent/package.json"));
const bridge = await import(pathToFileURL(require.resolve("@unitqc/company-agent-core/runtime")));
const policy = await import(pathToFileURL(require.resolve("@unitqc/company-agent-policy")));
policy.apply(ctx);
bridge.registerCapabilityTools(ctx, ["company.literature", "company.research"]);
const handle = await ctx.agents.create({
  sessionId: "session-literature",
  meta: { cwd: workspace },
  agentOptions: { provider: "fixture", model: "fixed" },
});
handle.agent.followup(llm.createUserMessage({
  content: [{ type: "text", text: "Index the local paper fixture, then compile the prepared scale card." }],
  source: { kind: "user" },
}));
await handle.agent.whenIdle();
await new Promise(resolve => setTimeout(resolve, 80));

function payloadOf(event) {
  const blocks = event?.data?.message?.content;
  const block = Array.isArray(blocks) ? blocks.find((row) => row?.type === "tool-result") : undefined;
  const textItem = Array.isArray(block?.content)
    ? block.content.find((row) => row?.type === "text")
    : undefined;
  const text = typeof textItem?.text === "string" ? textItem.text : "";
  let payload = null;
  try {
    payload = JSON.parse(text);
  } catch {
    payload = null;
  }
  return {
    callId: typeof block?.toolCallId === "string" ? block.toolCallId : "",
    errored: block?.isError === true,
    text: text.slice(0, 400),
    payload,
  };
}

const calls = events.filter((event) => event.type === "tool/call").map((event) => {
  const blocks = event?.data?.message?.content;
  const block = Array.isArray(blocks) ? blocks.find((row) => row?.type === "tool-call") : undefined;
  return {
    callId: block?.id || event?.data?.id || "",
    name: block?.name || event?.data?.name || "",
  };
});
const results = events.filter((event) => event.type === "tool/result").map(payloadOf);
console.log(JSON.stringify({ asks, approvalTools, generation, calls, results }));
await handle.dispose();
for (const fiber of fibers) {
  if (fiber && typeof fiber.dispose === "function") await fiber.dispose();
}
process.exit(0);
