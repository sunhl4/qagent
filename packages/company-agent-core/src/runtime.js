import { delimiter, isAbsolute } from "node:path";
import { spawn, spawnSync } from "node:child_process";

const PROFILE_PRESETS = Object.freeze({
  "company-agent": new Set(["boot", "lab", "algo", "sign"]),
  "company-agent-minimal": new Set(["boot", "algo"]),
});
const COMPANY_TOOL_PREFIXES = ["company_", "quantum_", "hpc_"];
const CLI_TIMEOUT_MS = 35_000;
const CLI_MAX_BUFFER_BYTES = 1_100_000;
// Tail of the raw stderr stream kept for error reporting, independent of the
// diagnostic line parser which consumes (and discards) complete lines.
const STDERR_TAIL_KEEP_BYTES = 4_000;
const CLI_PIPE_CLOSE_GRACE_MS = 250;
const MAX_TOOL_RESULT_BYTES = 64_000;
const DSH_SCHEMA_KEYS = new Set([
  "type",
  "oneOf",
  "properties",
  "required",
  "additionalProperties",
  "items",
  "enum",
  "const",
  "title",
  "description",
  "default",
  "deprecated",
  "readOnly",
  "writeOnly",
]);
const PYTHON_SCHEMA_KEYS = new Set([
  ...DSH_SCHEMA_KEYS,
  "minLength", "maxLength", "pattern", "minimum", "maximum",
  "minItems", "maxItems", "uniqueItems", "minProperties", "maxProperties",
]);
PYTHON_SCHEMA_KEYS.delete("oneOf");
const MAX_DSH_SCHEMA_DEPTH = 32;
let cachedTools;
let cachedCompleteTools;

export function dshSchema(schema, depth = 0) {
  if (!Number.isInteger(depth) || depth < 0) {
    throw new Error("company-agent contract schema depth is invalid");
  }
  if (depth > MAX_DSH_SCHEMA_DEPTH) {
    throw new Error("company-agent contract schema exceeds maximum nesting depth");
  }
  if (!schema || typeof schema !== "object" || Array.isArray(schema)) {
    throw new Error("company-agent contract schema must be an object");
  }
  if (Object.keys(schema).some((key) => !PYTHON_SCHEMA_KEYS.has(key))) {
    throw new Error("company-agent contract schema has unsupported keywords");
  }
  if (schema.type === undefined) {
    throw new Error("company-agent contract schema must declare a type");
  }
  const knownType = new Set(["object", "array", "string", "boolean", "integer", "number", "null"]);
  if (!knownType.has(schema.type)) {
    throw new Error(`company-agent contract schema has unsupported type ${String(schema.type)}`);
  }
  if (schema.type === "object" && schema.properties === undefined) {
    throw new Error("company-agent object schema properties must be explicit");
  }
  if (
    schema.type === "object"
    && (!schema.properties || typeof schema.properties !== "object" || Array.isArray(schema.properties))
  ) {
    throw new Error("company-agent object schema properties must be an object");
  }
  if (schema.type === "object" && schema.additionalProperties === undefined) {
    throw new Error("company-agent object schema must declare additionalProperties");
  }
  if (
    schema.type === "object"
    && typeof schema.additionalProperties !== "boolean"
    && (typeof schema.additionalProperties !== "object" || Array.isArray(schema.additionalProperties))
  ) {
    throw new Error("company-agent object schema has invalid additionalProperties");
  }
  if (schema.type === "array" && schema.items === undefined) {
    throw new Error("company-agent array schema must declare items");
  }
  if (
    schema.type === "array"
    && (!schema.items || typeof schema.items !== "object" || Array.isArray(schema.items))
  ) {
    throw new Error("company-agent array schema items must be an object");
  }
  if (schema.required !== undefined) {
    if (!Array.isArray(schema.required) || schema.required.some((name) => typeof name !== "string")) {
      throw new Error("company-agent schema required must be an array of strings");
    }
    if (new Set(schema.required).size !== schema.required.length) {
      throw new Error("company-agent schema required contains duplicates");
    }
  }
  if (schema.required !== undefined && schema.type !== "object") {
    throw new Error("company-agent schema required is only valid for objects");
  }
  if (
    schema.required !== undefined
    && (
      schema.properties === undefined
      || schema.required.some((name) => !(name in schema.properties))
    )
  ) {
    throw new Error("company-agent schema required references an unknown property");
  }
  if (schema.enum !== undefined) {
    if (!Array.isArray(schema.enum) || schema.enum.length === 0 || schema.enum.length !== new Set(schema.enum.map(JSON.stringify)).size) {
      throw new Error("company-agent schema enum must contain unique JSON values");
    }
  }
  const projected = {};
  for (const [key, value] of Object.entries(schema)) {
    if (!DSH_SCHEMA_KEYS.has(key)) continue;
    if (key === "properties") {
      if (!value || typeof value !== "object" || Array.isArray(value)) {
        throw new Error("company-agent schema properties must be an object");
      }
      if (schema.required?.some((name) => !(name in value))) {
        throw new Error("company-agent schema required references an unknown property");
      }
      projected.properties = Object.fromEntries(
        Object.entries(value).map(([name, child]) => [name, dshSchema(child, depth + 1)]),
      );
    } else if (key === "items" || (key === "additionalProperties" && typeof value === "object")) {
      projected[key] = dshSchema(value, depth + 1);
    } else {
      if (typeof value === "number" && !Number.isFinite(value)) {
        throw new Error("company-agent schema number must be finite");
      }
      projected[key] = value;
    }
  }
  return projected;
}

function configuredPythonPath() {
  const configured = String(process.env.COMPANY_AGENT_PYTHONPATH || "").trim();
  if (!configured) throw new Error("COMPANY_AGENT_PYTHONPATH is required");
  const entries = configured.split(delimiter);
  if (entries.length !== 1 || !isAbsolute(configured)) {
    throw new Error("COMPANY_AGENT_PYTHONPATH must be an absolute path");
  }
  if (/[\0]/.test(configured)) {
    throw new Error("COMPANY_AGENT_PYTHONPATH contains invalid characters");
  }
  return configured;
}

function subprocessEnvironment({ approved = false, workspace, turn, session } = {}) {
  const env = { ...process.env };
  delete env.COMPANY_AGENT_TOOL_WORKSPACE;
  // The kernel termination budget keys its durable ledger by this value; the
  // session id scopes the ledger to one session instead of one DSH process,
  // so a fresh session starts with fresh counters (turn_env in budgets.json).
  delete env.COMPANY_AGENT_TURN_ID;
  // Only the live DSH agent id may bind a ticket. Drop any parent-supplied value.
  delete env.COMPANY_AGENT_SESSION_ID;
  if (session !== undefined) {
    if (typeof session !== "string" || session.length > 80 || !/^dsh:[\x21-\x7e]+$/.test(session)) {
      throw new Error("company-agent session reference is invalid");
    }
    env.COMPANY_AGENT_SESSION_ID = session;
  }
  if (turn !== undefined) {
    if (typeof turn !== "string" || turn.length > 512 || !/^[\x21-\x7e]+$/.test(turn)) {
      throw new Error("company-agent turn identifier is invalid");
    }
    env.COMPANY_AGENT_TURN_ID = turn;
  }
  if (workspace !== undefined) {
    if (typeof workspace !== "string" || !isAbsolute(workspace) || /[\r\n\0]/.test(workspace)) {
      throw new Error("company-agent tool workspace is invalid");
    }
    env.COMPANY_AGENT_TOOL_WORKSPACE = workspace;
  }
  for (const key of Object.keys(env)) {
    if (
      key === "PYTHONPATH"
      || key.startsWith("PYTHON")
      || key === "LD_PRELOAD"
      || key === "LD_LIBRARY_PATH"
      || key === "NODE_OPTIONS"
    ) delete env[key];
  }
  if (approved) {
    if (process.env.COMPANY_AGENT_PROFILE !== "company-agent") {
      throw new Error("approved tool execution requires the full company-agent profile");
    }
    env.COMPANY_AGENT_APPROVAL_CONTEXT = "dsh";
    env.COMPANY_AGENT_PROFILE = "company-agent";
  } else {
    delete env.COMPANY_AGENT_APPROVAL_CONTEXT;
  }
  const configured = configuredPythonPath();
  const basePath = String(process.env.PATH || "").trim();
  if (!basePath) throw new Error("PATH is required for company-agent subprocesses");
  if (basePath.split(delimiter).some((entry) => entry === "" || entry === "." || !isAbsolute(entry))) {
    throw new Error("PATH must contain only absolute non-empty entries");
  }
  env.PATH = basePath;
  env.PYTHONPATH = configured;
  env.PYTHONNOUSERSITE = "1";
  env.PYTHONDONTWRITEBYTECODE = "1";
  // The result envelope leaves the kernel as UTF-8 bytes; on hosts whose
  // console code page is not UTF-8 (e.g. Windows GBK), Python would otherwise
  // re-encode the payload and Chinese facts arrive mojibake.
  env.PYTHONUTF8 = "1";
  return env;
}

function pythonCommand(argv) {
  if (!Array.isArray(argv) || argv.some((item) => typeof item !== "string")) {
    throw new Error("company-agent CLI arguments must be a string array");
  }
  if (argv.length > 32 || argv.some((item) => Buffer.byteLength(item, "utf8") > 4096)) {
    throw new Error("company-agent CLI arguments are too large");
  }
  const executable = process.env.COMPANY_AGENT_PYTHON;
  if (!executable) throw new Error("COMPANY_AGENT_PYTHON is required");
  if (!isAbsolute(executable)) {
    throw new Error("COMPANY_AGENT_PYTHON must be an absolute path");
  }
  return {
    executable,
    // -s disables user site (PYTHONNOUSERSITE is also forced in the child env)
    // and -P keeps the launch directory off sys.path; PYTHONPATH stays honored
    // because -I would also ignore the managed path set in subprocessEnvironment().
    args: ["-s", "-P", "-m", "company_agent.cli", ...argv],
  };
}

function parseCliOutput(stdout, status, diagnostics = "") {
  const output = String(stdout || "").trim();
  if (!output) {
    const detail = diagnostics.replace(/\s+/g, " ").trim().slice(-200);
    throw new Error((detail
      ? `company-agent CLI returned no JSON: ${detail}`
      : "company-agent CLI returned no JSON")
      + ` (exit=${String(status)})`);
  }
  if (status === null || status === undefined) {
    throw new Error("company-agent CLI exited without a status");
  }
  if (Buffer.byteLength(output, "utf8") > CLI_MAX_BUFFER_BYTES) {
    throw new Error("company-agent CLI output exceeded maximum size");
  }
  let payload;
  try {
    payload = JSON.parse(output);
  } catch {
    const detail = diagnostics.replace(/\s+/g, " ").trim().slice(-200);
    throw new Error(detail
      ? `company-agent CLI returned invalid JSON: ${output.slice(0, 200)} | diagnostic: ${detail}`
      : "company-agent CLI returned invalid JSON");
  }
  if (status !== 0 && status !== 1) {
    throw new Error(`company-agent CLI exited with status ${status}`);
  }
  return payload;
}

function runCliSync(argv) {
  const command = pythonCommand(argv);
  const result = spawnSync(command.executable, command.args, {
    env: subprocessEnvironment(),
    input: "",
    encoding: "utf8",
    timeout: CLI_TIMEOUT_MS,
    maxBuffer: CLI_MAX_BUFFER_BYTES,
    windowsHide: true,
  });
  if (result.error) {
    if (result.error.code === "ETIMEDOUT") throw new Error("company-agent CLI timed out");
    throw new Error(`company-agent CLI failed: ${result.error.message}`);
  }
  if (result.signal) throw new Error(`company-agent CLI terminated by ${result.signal}`);
  return parseCliOutput(result.stdout, result.status);
}

export function parseDiagnostic(line) {
  const prefix = "company-agent-diagnostic:";
  if (typeof line !== "string" || !line.startsWith(prefix)
    || Buffer.byteLength(line.slice(prefix.length)) > 2000) return null;
  try {
    const raw = line.slice(prefix.length);
    const value = JSON.parse(raw);
    // Python emits canonical compact ASCII metadata; this also rejects duplicate fields.
    if (JSON.stringify(value) !== raw) return null;
    const fields = ["version", "event", "tool", "operation", "request_id", "contract_digest",
      "elapsed_ms", "status", "error_category", "execution_state"];
    const unknownInvocation = value?.event === "invocation"
      && value?.tool === "unknown" && value?.operation === "unknown"
      && value?.request_id === "" && value?.execution_state === "not_dispatched"
      && ["denied", "error"].includes(value?.status);
    if (!value || typeof value !== "object" || Array.isArray(value)
      || Object.keys(value).length !== fields.length || fields.some(key => !(key in value))
      || fields.filter(key => key !== "elapsed_ms").some(key => typeof value[key] !== "string")
      || value.version !== "1.0" || !["provider", "invocation"].includes(value.event)
      || value.tool.length > 128 || value.operation.length > 128
      || (!unknownInvocation && !/^(company|quantum|hpc)_[a-z_]+$/.test(value.tool))
      || (!unknownInvocation && !/^[a-z]+(\.[a-z-]+)+$/.test(value.operation))
      || !/^(req_[0-9a-f]{32})?$/.test(value.request_id)
      || !/^sha256:[0-9a-f]{64}$/.test(value.contract_digest)
      || !Number.isSafeInteger(value.elapsed_ms) || value.elapsed_ms < 0
      || !["started", "ok", "error", "denied", "needs_ask"].includes(value.status)
      || !["not_dispatched", "dispatched", "completed", "unknown"].includes(value.execution_state)
      || (["dispatched", "unknown"].includes(value.execution_state) && !value.request_id)
      || (!unknownInvocation && cachedCompleteTools && !cachedCompleteTools.some(
        row => row.name === value.tool && row.operation === value.operation,
      ))
      || !["none", "validation", "transport", "authentication", "remote", "invalid_result",
        "cancelled", "timeout", "internal"].includes(value.error_category)) return null;
    return value;
  } catch { return null; }
}

function runCli(argv, signal, stdin = "", options = {}) {
  if (!Number.isInteger(CLI_TIMEOUT_MS) || CLI_TIMEOUT_MS <= 0) {
    throw new Error("company-agent CLI timeout is invalid");
  }
  const command = pythonCommand(argv);
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(new Error("company-agent CLI call was cancelled"));
      return;
    }
    let env;
    try {
      env = subprocessEnvironment(options);
    } catch (error) {
      reject(error);
      return;
    }
    const child = spawn(command.executable, command.args, {
      env,
      stdio: ["pipe", "pipe", "pipe"],
      windowsHide: true,
      shell: false,
      // Detached process groups (POSIX) give the cleanup path its whole-group
      // kill; Windows needs no detachment because taskkill /T sweeps the tree.
      detached: process.platform !== "win32",
    });
    let stdout = "";
    let stdoutBytes = 0;
    let stderrBytes = 0;
    // Raw stderr tail: Buffer chunks are kept (not decoded strings) so a UTF-8
    // character split across chunk boundaries is still decoded correctly once.
    let stderrTailChunks = [];
    let stderrTailBytes = 0;
    let settled = false;
    let failure;
    let diagnosticBuffer = "";
    let providerRequest;
    let providerDiagnostic;
    let providerOperation;
    let childExited = false;
    let childSpawned = false;
    let failureCleanupTimer;
    let pipeCloseTimer;
    let closeStatus;
    let closeSignal;
    const startedAt = Date.now();
    const onAbort = () => fail("company-agent CLI call was cancelled");
    const closePipes = () => {
      child.stdin.destroy();
      child.stdout.destroy();
      child.stderr.destroy();
    };
    const killGroup = () => {
      if (!Number.isSafeInteger(child.pid) || child.pid <= 0 || !childSpawned) return;
      if (process.platform !== "win32") {
        try { process.kill(-child.pid, "SIGKILL"); } catch (error) {
          if (error?.code !== "ESRCH") failure ??= "company-agent CLI process cleanup failed";
        }
        return;
      }
      // Windows has no process groups here: sweep the whole child tree so the
      // timeout/cancel contract still removes inherited descendants.
      try {
        spawn("taskkill", ["/pid", String(child.pid), "/T", "/F"],
          { windowsHide: true, shell: false, stdio: "ignore" });
      } catch (error) {
        failure ??= "company-agent CLI process cleanup failed";
      }
    };
    const finish = (callback) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      clearTimeout(failureCleanupTimer);
      clearTimeout(pipeCloseTimer);
      signal?.removeEventListener("abort", onAbort);
      closePipes();
      callback();
    };
    const fail = (message) => {
      if (settled || failure) return;
      failure = message;
      killGroup();
      // Wait briefly for the direct child to reap, then bound any inherited
      // stdout/stderr descriptors held by descendants.
      failureCleanupTimer = setTimeout(() => {
        killGroup();
        closePipes();
        if (childExited) settleFromExit();
      }, CLI_PIPE_CLOSE_GRACE_MS);
    };
    child.stdin.on("error", (error) => fail(`company-agent CLI input failed: ${error.message}`));
    const timer = setTimeout(() => fail("company-agent CLI timed out"), CLI_TIMEOUT_MS);
    signal?.addEventListener("abort", onAbort, { once: true });
    child.stdin.end(stdin);
    child.stdout.setEncoding("utf8");
    child.stdout.on("data", (chunk) => {
      stdoutBytes += Buffer.byteLength(chunk, "utf8");
      if (stdoutBytes > CLI_MAX_BUFFER_BYTES) {
        fail("company-agent CLI output exceeded maximum size");
        return;
      }
      stdout += chunk;
    });
    child.stderr.on("data", (chunk) => {
      const raw = Buffer.isBuffer(chunk) ? chunk : Buffer.from(String(chunk), "utf8");
      stderrBytes += raw.length;
      if (stderrBytes > CLI_MAX_BUFFER_BYTES) {
        fail("company-agent CLI diagnostics exceeded maximum size");
        return;
      }
      // Keep the raw tail for diagnostics in parseCliOutput even though the
      // line loop below consumes complete lines out of diagnosticBuffer;
      // otherwise only the trailing partial line would ever reach it.
      stderrTailChunks.push(raw);
      stderrTailBytes += raw.length;
      while (stderrTailBytes > STDERR_TAIL_KEEP_BYTES && stderrTailChunks.length > 1) {
        stderrTailBytes -= stderrTailChunks[0].length;
        stderrTailChunks = stderrTailChunks.slice(1);
      }
      diagnosticBuffer += raw.toString();
      let end;
      while ((end = diagnosticBuffer.indexOf("\n")) >= 0) {
        const line = diagnosticBuffer.slice(0, end);
        diagnosticBuffer = diagnosticBuffer.slice(end + 1);
        const event = parseDiagnostic(line);
        if (event) {
          if (["device.run", "hpc.submit", "cloud.submit"].includes(event.operation) && event.execution_state === "dispatched") {
            providerRequest = event.request_id;
            providerDiagnostic = event;
            providerOperation = event.operation;
          }
          // Invocation-final diagnostics are independent of provider dispatch.
          // A later not_dispatched final event must not erase an observed
          // request whose device outcome can no longer be inferred safely.
          process.stderr.write(`company-agent-diagnostic:${JSON.stringify(event)}\n`);
        }
      }
      if (Buffer.byteLength(diagnosticBuffer, "utf8") > 4000) diagnosticBuffer = "";
    });
    child.once("spawn", () => { childSpawned = true; });
    child.on("error", () => {
      // Spawn failures have no process group or exit event. Keep the error
      // generic and settle after Node closes the attempted child handles.
      failure = "company-agent CLI process failed";
    });
    const settleFromExit = () => {
      finish(() => {
        const executionLabel = providerOperation === "device.run" ? "device execution" : providerOperation;
        const suffix = providerRequest
          ? `; ${executionLabel} outcome unknown; do not retry automatically; request_id=${providerRequest}`
          : "";
        const unknown = (message) => {
          if (providerDiagnostic) {
            const event = { ...providerDiagnostic, elapsed_ms: Date.now() - startedAt,
              status: "error", execution_state: "unknown",
              error_category: message.includes("cancelled") ? "cancelled"
                : message.includes("timed out") ? "timeout" : "internal" };
            process.stderr.write(`company-agent-diagnostic:${JSON.stringify(event)}\n`);
          }
          return new Error(message + suffix);
        };
        if (failure) return reject(unknown(failure));
        if (closeSignal) return reject(unknown(`company-agent CLI terminated by ${closeSignal}`));
        try {
          const stderrTail = Buffer.concat(stderrTailChunks).toString("utf8");
          const payload = parseCliOutput(stdout, closeStatus, stderrTail);
          resolve(options.validateResult ? options.validateResult(payload) : payload);
        } catch (error) {
          reject(unknown(error.message));
        }
      });
    };
    child.on("exit", (status, signal) => {
      childExited = true;
      closeStatus = status;
      closeSignal = signal;
      if (failure) {
        killGroup();
        if (failureCleanupTimer) return;
      }
      // Inherited open pipes after the direct child exits indicate an
      // unexpected descendant. Kill the remaining group and fail closed.
      pipeCloseTimer = setTimeout(() => {
        failure ??= "company-agent CLI left inherited pipes open";
        killGroup();
        closePipes();
        settleFromExit();
      }, CLI_PIPE_CLOSE_GRACE_MS);
    });
    child.on("close", (status, signal) => {
      if (!childExited) {
        childExited = true;
        closeStatus = status;
        closeSignal = signal;
      }
      if (failure && childSpawned) killGroup();
      settleFromExit();
    });
  });
}

function configuredPreset() {
  const preset = process.env.COMPANY_AGENT_PRESET;
  if (!preset) throw new Error("COMPANY_AGENT_PRESET is required");
  if (preset !== preset.trim()) throw new Error("COMPANY_AGENT_PRESET must not contain whitespace");
  const profile = process.env.COMPANY_AGENT_PROFILE;
  const presets = PROFILE_PRESETS[profile];
  if (!presets) {
    throw new Error("COMPANY_AGENT_PROFILE is required and must be valid");
  }
  if (!presets.has(preset)) {
    throw new Error(`preset ${preset} is not allowed for profile ${profile}`);
  }
  return preset;
}

function callArguments(action, tool, approved = false) {
  const argv = [action, "--tool", tool, "--preset", configuredPreset(), "--args", "-"];
  if (approved) argv.push("--approved");
  return argv;
}

function encodeArguments(args) {
  let payload;
  try {
    payload = JSON.stringify(args ?? {}, (_key, value) => {
      if (
        value === undefined || typeof value === "function" || typeof value === "symbol"
        || typeof value === "bigint"
        || (typeof value === "number" && (
          !Number.isFinite(value) || Object.is(value, -0)
          || (Number.isInteger(value) && !Number.isSafeInteger(value))
        ))
      ) {
        throw new Error("non-JSON argument");
      }
      return value;
    });
  } catch {
    throw new Error("company-agent arguments must be JSON serializable");
  }
  if (payload === undefined) throw new Error("company-agent arguments must be JSON serializable");
  if (Buffer.byteLength(payload, "utf8") > 256_000) {
    throw new Error("company-agent arguments exceeded maximum size");
  }
  let parsed;
  try {
    parsed = JSON.parse(payload);
  } catch {
    throw new Error("company-agent arguments must be valid JSON");
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("company-agent arguments must be a JSON object");
  }
  return payload;
}

export async function authorize(tool, args, signal) {
  if (typeof tool !== "string" || tool.length > 128 || !COMPANY_TOOL_PREFIXES.some((prefix) => tool.startsWith(prefix))) {
    return { decision: "deny", error: "invalid tool name" };
  }
  const payload = await runCli(callArguments("authorize", tool), signal, encodeArguments(args));
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    return { decision: "deny", error: "invalid authorization result" };
  }
  if (Object.keys(payload).some((key) => key !== "decision" && key !== "error")) {
    return { decision: "deny", error: "invalid authorization result" };
  }
  const value = payload.decision;
  if (!new Set(["allow", "ask", "deny"]).has(value) || !("error" in payload)
    || (payload.error !== null && typeof payload.error !== "string")
    || (value !== "deny" && payload.error !== null)) {
    return { decision: "deny", error: "invalid authorization result" };
  }
  return { decision: value, error: payload.error };
}

export async function validate(tool, args, signal) {
  if (typeof tool !== "string" || tool.length > 128 || !COMPANY_TOOL_PREFIXES.some((prefix) => tool.startsWith(prefix))) {
    return { valid: false, error: "invalid tool name" };
  }
  const payload = await runCli(callArguments("validate", tool), signal, encodeArguments(args));
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    return { valid: false, error: "invalid validation result" };
  }
  if (Object.keys(payload).some((key) => key !== "valid" && key !== "error")) {
    return { valid: false, error: "invalid validation result" };
  }
  return {
    valid: payload.valid === true,
    error: typeof payload.error === "string" && payload.error ? payload.error : null,
  };
}

export async function decide(tool, args, signal) {
  if (typeof tool !== "string" || tool.length > 128 || !COMPANY_TOOL_PREFIXES.some((prefix) => tool.startsWith(prefix))) {
    return "deny";
  }
  const payload = await runCli(callArguments("decide", tool), signal, encodeArguments(args));
  if (
    !payload
    || typeof payload !== "object"
    || Array.isArray(payload)
    || Object.keys(payload).length !== 1
    || !("decision" in payload)
  ) {
    return "deny";
  }
  const value = String(payload.decision || "deny");
  return value === "allow" || value === "ask" ? value : "deny";
}

export async function invoke(tool, args, approved = false, signal, workspace, turn, session) {
  if (typeof tool !== "string" || tool.length > 128 || !COMPANY_TOOL_PREFIXES.some((prefix) => tool.startsWith(prefix))) {
    throw new Error("company-agent invoke received an invalid tool name");
  }
  if (typeof approved !== "boolean") throw new Error("approved must be a boolean");
  return runCli(
    callArguments("invoke", tool, approved),
    signal,
    encodeArguments(args),
    { approved, workspace, turn, session, validateResult: result => validateInvocationResult(result, tool, approved) },
  );
}

function validateInvocationResult(result, tool, approved) {
  if (!result || typeof result !== "object" || Array.isArray(result)) {
    throw new Error("company-agent invoke returned an invalid result");
  }
  const allowed = new Set(["tool", "decision", "status", "payload", "error"]);
  if (Object.keys(result).length !== allowed.size || Object.keys(result).some((key) => !allowed.has(key))) {
    throw new Error("company-agent invoke returned unknown fields");
  }
  if (result.tool !== tool) throw new Error("company-agent invoke correlation mismatch");
  if (!new Set(["allow", "ask", "deny"]).has(result.decision)) {
    throw new Error("company-agent invoke returned an invalid decision");
  }
  if (!new Set(["ok", "error", "needs_ask", "denied"]).has(result.status)) {
    throw new Error("company-agent invoke returned an invalid status");
  }
  if (result.status === "needs_ask" && result.decision !== "ask") {
    throw new Error("company-agent invoke returned inconsistent approval status");
  }
  if (result.status === "denied" && result.decision !== "deny") {
    throw new Error("company-agent invoke returned inconsistent denial status");
  }
  if (result.status === "needs_ask" && result.error != null) {
    throw new Error("company-agent invoke returned an error before approval");
  }
  if (result.status === "ok" && result.error != null) {
    throw new Error("company-agent invoke returned an error for successful status");
  }
  if (result.status === "error" && result.decision === "deny" && typeof result.error !== "string") {
    throw new Error("company-agent invoke returned inconsistent validation error");
  }
  if (result.status !== "ok" && result.status !== "needs_ask" && typeof result.error !== "string") {
    throw new Error("company-agent invoke returned no error for failed status");
  }
  if (result.status === "ok" && result.payload == null) {
    throw new Error("company-agent invoke returned no successful payload");
  }
  if (result.status === "ok" && (
    result.decision === "deny" || (result.decision === "ask" && !approved)
    || !result.payload || typeof result.payload !== "object" || Array.isArray(result.payload)
    || Buffer.byteLength(JSON.stringify(result.payload), "utf8") > MAX_TOOL_RESULT_BYTES
  )) {
    throw new Error("company-agent invoke returned an inconsistent successful payload");
  }
  if (result.status !== "ok" && result.payload != null) {
    throw new Error("company-agent invoke returned payload for a failed status");
  }
  return result;
}

function validateToolRows(payload) {
  if (!Array.isArray(payload)) throw new Error("company-agent tools must return an array");
  const names = payload.map((row) => String(row?.name || ""));
  if (
    names.some((name) => !name || !COMPANY_TOOL_PREFIXES.some((prefix) => name.startsWith(prefix)))
    || names.length !== new Set(names).size
  ) {
    throw new Error("company-agent tools returned an invalid or duplicate tool name");
  }
  return payload;
}

function completeToolCatalog() {
  if (cachedCompleteTools === undefined) {
    cachedCompleteTools = validateToolRows(runCliSync(["tools"]));
  }
  return cachedCompleteTools;
}

export function toolCatalog() {
  if (cachedTools === undefined) {
    cachedTools = validateToolRows(runCliSync(["tools", "--preset", configuredPreset()]));
  }
  return cachedTools;
}

export function registerTool(ctx, contract) {
  if (!ctx?.tools || typeof ctx.tools.register !== "function") {
    throw new Error("company-agent tool registry is unavailable");
  }
  if (!contract || typeof contract !== "object" || Array.isArray(contract)) {
    throw new Error("company-agent tool contract must be an object");
  }
  const expectedFields = new Set([
    "name",
    "capability",
    "operation",
    "input_handles",
    "output_handles",
    "description",
    "parameters",
    "output",
  ]);
  if (Object.keys(contract).length !== expectedFields.size || Object.keys(contract).some((key) => !expectedFields.has(key))) {
    throw new Error("company-agent tool contract has unknown fields");
  }
  const { name, description, parameters } = contract;
  if (typeof name !== "string" || name.length > 128 || !COMPANY_TOOL_PREFIXES.some((prefix) => name.startsWith(prefix))) {
    throw new Error("company-agent tool has an invalid name");
  }
  if (typeof contract.capability !== "string" || !contract.capability.includes(".")) {
    throw new Error(`company-agent tool ${name} has an invalid capability`);
  }
  if (typeof contract.operation !== "string" || !contract.operation.includes(".")) {
    throw new Error(`company-agent tool ${name} has an invalid operation`);
  }
  if (typeof description !== "string" || !description.trim() || Buffer.byteLength(description, "utf8") > 2000) {
    throw new Error(`company-agent tool ${name} has no description`);
  }
  for (const key of ["input_handles", "output_handles"]) {
    if (!Array.isArray(contract[key]) || contract[key].some((handle) => !["asset_id", "circuit_id", "twin_id"].includes(handle))) {
      throw new Error(`company-agent tool ${name} has invalid handle metadata`);
    }
    if (new Set(contract[key]).size !== contract[key].length) {
      throw new Error(`company-agent tool ${name} repeats handle metadata`);
    }
  }
  if (contract.input_handles.some((handle) => contract.output_handles.includes(handle))) {
    throw new Error(`company-agent tool ${name} reuses input handles as outputs`);
  }
  const outputSchema = contract.output;
  if (!parameters || parameters.type !== "object") {
    throw new Error(`company-agent tool ${name} has no object input contract`);
  }
  if (!outputSchema || outputSchema.type !== "object") {
    throw new Error(`company-agent tool ${name} has no object output contract`);
  }
  const expectedProfile = String(process.env.COMPANY_AGENT_PROFILE || "");
  if (!PROFILE_PRESETS[expectedProfile]) {
    throw new Error("company-agent profile is invalid during tool registration");
  }
  if (expectedProfile === "company-agent-minimal" && contract.capability === "quantum.device") {
    throw new Error("company-agent-minimal cannot register device tools");
  }
  if (expectedProfile === "company-agent" && contract.capability === "quantum.device") {
    const preset = configuredPreset();
    if (preset !== "lab" && preset !== "sign") {
      throw new Error("device tools may only register in lab or sign presets");
    }
  }
  ctx.tools.register({
    name,
    description,
    parameters: dshSchema(parameters),
    output: {
      schema: dshSchema(outputSchema),
      render: (_args, value) => {
        if (!value || typeof value !== "object" || Array.isArray(value)) {
          throw new Error(`${name}: rendered result must be an object`);
        }
        let text;
        try {
          text = JSON.stringify(value);
        } catch {
          throw new Error(`${name}: rendered result was not JSON serializable`);
        }
        if (typeof text !== "string") {
          throw new Error(`${name}: rendered result was not a JSON value`);
        }
        if (Buffer.byteLength(text, "utf8") > MAX_TOOL_RESULT_BYTES) {
          throw new Error(`${name}: rendered result exceeded maximum size`);
        }
        return [{ type: "text", text }];
      },
    },
    execute: async (args, exec) => {
      // DSH invokes this handler only after pre-execute policy and user approval.
      // Only an ask decision needs the reserved approval marker; allow calls must
      // also work in minimal profiles, which cannot carry device approval.
      const { decision } = await authorize(name, args, exec?.signal);
      // Termination-budget turn key: scope the durable ledger to this session
      // (exec.agent.id is the session id per dsh-agent's public Agent face) so
      // counters restart with every session instead of one process lifetime.
      const turn = String(exec?.agent?.id ?? exec?.agent?.session?.header?.id ?? "");
      const hostSession = name === "company_work_item" && turn ? `dsh:${turn}` : undefined;
      const needsWorkspaceHeader = name === "quantum_cloud_submit" || name === "hpc_stage_file"
        || name === "hpc_file_fetch" || name.startsWith("company_latex_");
      const result = needsWorkspaceHeader
        ? await invoke(name, args, decision === "ask", exec?.signal, exec?.agent?.session?.header?.cwd, turn || undefined, hostSession)
        : await invoke(name, args, decision === "ask", exec?.signal, undefined, turn || undefined, hostSession);
      if (result.status === "ok") {
        if (result.decision !== "allow" && result.decision !== "ask") {
          throw new Error(`${name}: invalid successful decision`);
        }
        if (!result.payload || typeof result.payload !== "object" || Array.isArray(result.payload)) {
          throw new Error(`${name}: invalid successful payload`);
        }
        return result.payload;
      }
      const message = String(result.error || result.status || "failed");
      const folded = message.toLowerCase();
      if (
        Buffer.byteLength(message, "utf8") > 500
        || ["token", "secret", "password", "authorization", "http://", "https://"].some((term) => folded.includes(term))
      ) {
        throw new Error(`${name}: tool execution failed`);
      }
      throw new Error(`${name}: ${message}`);
    },
  });
}

export function registerCapabilityTools(ctx, capabilities) {
  if (!Array.isArray(capabilities) || capabilities.some((item) => typeof item !== "string")) {
    throw new Error("company-agent capability selection must be a string array");
  }
  const allowed = new Set(capabilities);
  if (allowed.size !== capabilities.length) {
    throw new Error("company-agent capability selection contains duplicates");
  }
  const available = new Set(
    completeToolCatalog()
      .filter((contract) => allowed.has(contract.capability))
      .map((contract) => contract.capability),
  );
  const unknown = [...allowed].filter((capability) => !available.has(capability));
  if (unknown.length) {
    throw new Error(`company-agent catalog has unknown capabilities: ${unknown.sort().join(", ")}`);
  }
  for (const contract of toolCatalog()) {
    if (allowed.has(contract.capability)) {
      registerTool(ctx, contract);
    }
  }
}
