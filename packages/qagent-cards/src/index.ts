import { spawnSync } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import type { Context } from "../../../seams/dsh.d.ts";

const QAGENT_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "../../..");

function card(kind: "pes" | "signoff"): Record<string, unknown> {
  const result = spawnSync(
    process.env.QAGENT_PYTHON || "python3",
    ["-m", "qagent.entrypoints.cards_cli", kind],
    { env: { ...process.env, PYTHONPATH: `${QAGENT_ROOT}/src` }, encoding: "utf8" },
  );
  if (result.status !== 0) {
    throw new Error(result.stderr || result.stdout || `qagent-cards ${kind} failed`);
  }
  return JSON.parse(result.stdout.trim()) as Record<string, unknown>;
}

export const name = "qagent-cards";

export function pesConversationNode(): Record<string, unknown> {
  return card("pes");
}

export function signoffCard(): Record<string, unknown> {
  return card("signoff");
}

export function apply(_ctx: Context) {
  // Conversation nodes, not new science tool names.
}
