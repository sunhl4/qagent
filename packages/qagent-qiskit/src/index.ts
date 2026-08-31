import type { Context } from "../../../seams/dsh.d.ts";
import { registerInvokeTool } from "../../../seams/qagent_tool.ts";

export const name = "qagent-qiskit";
export const inject = ["tools"];

export function apply(ctx: Context) {
  registerInvokeTool(ctx, "qiskit_import_circuit", "QASM / QuantumCircuit → circuit_id.");
  registerInvokeTool(
    ctx,
    "qiskit_export_circuit",
    "circuit_id → QASM3. Do not call this to draw a diagram; the face draws from circuit_id.",
  );
  registerInvokeTool(ctx, "qiskit_transpile", "Qiskit transpile. Not a twin signoff.");
  registerInvokeTool(ctx, "qiskit_aer_run", "Aer approximate. provenance=aer. No twin_id.");
  registerInvokeTool(ctx, "qiskit_ibm_run", "Reserved foreign backend. Default deny.");
}
