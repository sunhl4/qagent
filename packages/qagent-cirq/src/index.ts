import type { Context } from "../../../seams/dsh.d.ts";
import { registerInvokeTool } from "../../../seams/qagent_tool.ts";

export const name = "qagent-cirq";
export const inject = ["tools"];

export function apply(ctx: Context) {
  registerInvokeTool(ctx, "cirq_import_circuit", "Cirq Circuit / QASM → circuit_id.");
  registerInvokeTool(ctx, "cirq_export_circuit", "circuit_id → QASM3.");
  registerInvokeTool(ctx, "cirq_simulator_run", "Cirq simulator. provenance=cirq. No third handle.");
}
