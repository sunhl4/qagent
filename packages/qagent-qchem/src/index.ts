import type { Context } from "../../../seams/dsh.d.ts";
import { registerInvokeTool } from "../../../seams/qagent_tool.ts";

export const name = "qagent-qchem";
export const inject = ["tools"];

export function apply(ctx: Context) {
  registerInvokeTool(
    ctx,
    "qchem_run",
    "Company qchem-run. Pass the scenario that matches this request. Returns asset_id. Some scenarios also pin circuit_id. Do not pick a scenario the human did not ask for. Never pass a2_chem_pes as circuit_id. Do not TwinRun from here. Do not name the scenario to the human.",
    {
      type: "object",
      required: ["scenario"],
      properties: {
        scenario: {
          type: "string",
          description: "Scenario name from the request. Examples: minimal_vqe, uccsd_pauli. Do not default to uccsd_pauli.",
        },
      },
    },
  );
  registerInvokeTool(ctx, "qchem_export_parity", "qchem-export-parity");
}
