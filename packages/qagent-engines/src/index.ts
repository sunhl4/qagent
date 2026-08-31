import type { Context } from "../../../seams/dsh.d.ts";
import { registerInvokeTool } from "../../../seams/qagent_tool.ts";

export const name = "qagent-engines";
export const inject = ["tools"];

export function apply(ctx: Context) {
  registerInvokeTool(ctx, "qagent_list_engines", "List registered engine packs. Optional preset=lab|algo|sign switches the session.", {
    type: "object",
    properties: {
      preset: { type: "string", enum: ["lab", "algo", "sign"] },
    },
  });
  registerInvokeTool(ctx, "qagent_pin_circuit", "Pin a cross-engine circuit handle. Returns circuit_id only.", {
    type: "object",
    required: ["source"],
    properties: {
      source: { type: "string", enum: ["qchem", "qiskit", "qdata", "logical", "qasm3"] },
      qasm3: { type: "string" },
      logical: { type: "object" },
      asset_id: { type: "string" },
    },
  });
}
