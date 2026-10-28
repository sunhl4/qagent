import { registerCapabilityTools } from "@unitqc/company-agent-core/runtime";

export const name = "company-agent-latex";
export const inject = ["tools"];

export function apply(ctx) {
  // The preset catalog filter decides visibility: lab sees the full company.latex
  // roster, boot/algo only the read-only probes, sign none. Every operation
  // resolves the bounded workspace the core runtime forwards, and the four
  // write tools route through the policy plugin's human-ask gate.
  registerCapabilityTools(ctx, ["company.latex"]);
}
