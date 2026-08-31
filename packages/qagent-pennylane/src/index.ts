import type { Context } from "../../../seams/dsh.d.ts";
import { registerInvokeTool } from "../../../seams/qagent_tool.ts";

export const name = "qagent-pennylane";
export const inject = ["tools"];

export function apply(ctx: Context) {
  registerInvokeTool(ctx, "pennylane_import_circuit", "Pennylane Circuit / QASM → circuit_id. Reserved deny.");
  registerInvokeTool(ctx, "pennylane_export_circuit", "circuit_id → QASM3. Reserved deny.");
  registerInvokeTool(ctx, "pennylane_simulator_run", "Pennylane simulator. provenance=pennylane. No third handle. Reserved deny.");
}
