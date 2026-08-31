import type { Context } from "../../../seams/dsh.d.ts";
import { registerInvokeTool } from "../../../seams/qagent_tool.ts";

export const name = "qagent-twin";
export const inject = ["tools"];

export function apply(ctx: Context) {
  registerInvokeTool(ctx, "ionstack_twin_identity", "GET /v1/twin/identity. Machine identity only; never emits twin_id.");
  registerInvokeTool(ctx, "ionstack_twin_run", "POST /v1/twin/run. mode=pipeline, shots, and circuit_id from pin. Never call with {}.", {
    type: "object",
    required: ["mode", "shots", "circuit_id"],
    properties: {
      mode: { type: "string", enum: ["pipeline", "signoff"] },
      shots: { type: "integer", minimum: 1 },
      circuit_id: { type: "string" },
    },
  });
  registerInvokeTool(ctx, "ionstack_compile_estimate", "makespan only, no signoff ok. Pass circuit_id from pin.", {
    type: "object",
    required: ["circuit_id"],
    properties: { circuit_id: { type: "string" } },
  });
}
