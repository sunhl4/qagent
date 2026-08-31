import type { Context } from "../../../seams/dsh.d.ts";
import { registerInvokeTool } from "../../../seams/qagent_tool.ts";

export const name = "qagent-codex-attended";
export const inject = ["tools"];

export function apply(ctx: Context) {
  registerInvokeTool(ctx, "subagent_codex_attended", "Persistent Codex thread with approval RPC.");
}
