import { registerCapabilityTools } from "@unitqc/company-agent-core/runtime";

export const name = "company-agent-quantum";
export const inject = ["tools"];

export function apply(ctx) {
  registerCapabilityTools(ctx, ["company.algorithm", "company.asset", "quantum.simulation", "quantum.compilation", "compute.cloud"]);
}
