import type { Context } from "../../../seams/dsh.d.ts";

export const name = "qagent-route";
export const inject = ["tools"];

export function compileEstimateBackend(): string {
  return process.env.QAGENT_ROUTE_BACKEND || "mapqccd";
}

export function apply(_ctx: Context) {
  // Do not register a second tool name. Swap QAGENT_ROUTE_BACKEND.
}
