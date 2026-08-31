import { existsSync, readFileSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const QAGENT_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");

export type Decision = "allow" | "deny" | "ask";

export type InvokePayload = {
  tool: string;
  decision: Decision;
  status: "denied" | "needs_ask" | "not_wired" | "ok" | "error";
  slot_id?: string | null;
  payload?: Record<string, unknown> | null;
};

function runPython(
  action: "decide" | "invoke",
  tool: string,
  args: unknown,
  preset: string,
  approved = false,
): string {
  const env = {
    ...process.env,
    PYTHONPATH: `${QAGENT_ROOT}/src`,
    QAGENT_ROOT,
    QAGENT_PRESET: preset,
  };
  const argv = [
    "-m",
    "qagent.entrypoints.invoke_cli",
    action,
    "--tool",
    tool,
    "--preset",
    preset,
    "--args",
    JSON.stringify(args ?? {}),
  ];
  if (approved) {
    argv.push("--approved");
  }
  const result = spawnSync(
    process.env.QAGENT_PYTHON || "python3",
    argv,
    { env, encoding: "utf8" },
  );
  if (result.status !== 0) {
    throw new Error(result.stderr || result.stdout || `qagent ${action} failed`);
  }
  return result.stdout.trim();
}

const PRESETS = new Set(["lab", "algo", "sign"]);

function readStoredPreset(): string | undefined {
  const file = process.env.QAGENT_PRESET_FILE || resolve(QAGENT_ROOT, ".qagent/active_preset");
  if (!existsSync(file)) {
    return undefined;
  }
  const text = readFileSync(file, "utf8").trim();
  return PRESETS.has(text) ? text : undefined;
}

export function currentPreset(): string {
  const stored = readStoredPreset();
  if (stored) {
    return stored;
  }
  const env = process.env.QAGENT_PRESET || "";
  return PRESETS.has(env) ? env : "lab";
}

export function qagentDecide(tool: string, args: unknown, preset = currentPreset()): Decision {
  const parsed = JSON.parse(runPython("decide", tool, args, preset)) as { decision?: string };
  const decision = parsed.decision;
  if (decision === "allow" || decision === "deny" || decision === "ask") {
    return decision;
  }
  return "deny";
}

export function qagentInvoke(
  tool: string,
  args: unknown,
  preset = currentPreset(),
  approved = false,
): InvokePayload {
  return JSON.parse(runPython("invoke", tool, args, preset, approved)) as InvokePayload;
}
