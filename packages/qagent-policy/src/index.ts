import type { Context, ToolExecution } from "../../../seams/dsh.d.ts";
import { qagentDecide } from "../../../seams/qagent_bridge.ts";

const SOUTHBOUND = new Set([
  "cal_edit",
  "shuttle_write",
  "execute_twin_run",
  "cordis_define",
  "cordis_run",
]);

export const name = "qagent-policy";
export const inject = ["tools"];

function asExec(value: unknown): ToolExecution {
  const call = value && typeof value === "object" ? (value as ToolExecution) : { name: "", arguments: {} };
  return { name: String(call.name || ""), arguments: call.arguments ?? {} };
}

export function apply(ctx: Context) {
  ctx.on("tools/pre-execute", (exec: unknown, next?: () => unknown) => {
    const call = asExec(exec);
    const decision = qagentDecide(call.name, call.arguments);
    if (decision === "deny") {
      return { kind: "deny", reason: "qagent-policy" };
    }
    if (decision === "ask") {
      return { kind: "ask", reason: "qagent-policy" };
    }
    return typeof next === "function" ? next() : { kind: "allow" };
  });

  ctx.tools.guard?.((execution) => {
    if (SOUTHBOUND.has(execution.name)) {
      return "qagent-policy: southbound denied";
    }
    if (qagentDecide(execution.name, execution.arguments) === "deny") {
      return "qagent-policy";
    }
    return undefined;
  });
}
