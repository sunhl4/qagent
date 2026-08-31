import type { Context } from "../../../seams/dsh.d.ts";
import { registerInvokeTool } from "../../../seams/qagent_tool.ts";

export const name = "qagent-docs";
export const inject = ["tools"];

export function apply(ctx: Context) {
  registerInvokeTool(ctx, "qccd_docs_search", "In-stack docs only.");
}
