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
  registerInvokeTool(ctx, "qagent_hub_list", "List company algorithm cards. Optional kind filter.", {
    type: "object",
    properties: {
      kind: { type: "string" },
    },
  });
  registerInvokeTool(ctx, "qagent_hub_describe", "Describe one algo-hub card.", {
    type: "object",
    required: ["id"],
    properties: {
      id: { type: "string" },
    },
  });
  registerInvokeTool(ctx, "qagent_hub_choose", "Choose Q-chem VQE vs uqc HEA-VQE. Do not merge ids.", {
    type: "object",
    properties: {
      has_molecule: { type: "boolean" },
      hint: { type: "string" },
    },
  });
  registerInvokeTool(ctx, "qagent_hub_validate", "Validate a hub/v1 config. Does not run.", {
    type: "object",
    required: ["config"],
    properties: {
      config: { type: "object" },
    },
  });
  registerInvokeTool(ctx, "qagent_hub_translate", "Map company-pack or foreign JSON onto hub/v1. Does not run.", {
    type: "object",
    properties: {
      config: { type: "object" },
      text: { type: "string" },
    },
  });
  registerInvokeTool(ctx, "qagent_circuit_job", "Circuit job FSM after pin. Twin still asks. Face has no twin_id.", {
    type: "object",
    properties: {
      action: { type: "string", enum: ["start", "status"] },
      circuit_id: { type: "string" },
      assignment_id: { type: "string" },
      shots: { type: "number" },
      backend: { type: "string", enum: ["twin", "aer"] },
    },
  });
}
