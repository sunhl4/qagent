import { registerCapabilityTools } from "@unitqc/company-agent-core/runtime";

export const name = "company-agent-plan";
export const inject = ["tools"];

export function apply(ctx) {
  // The preset catalog filter decides visibility: lab sees the full
  // company.plan roster, algo only the read-only probes, boot/sign none.
  // Reads and writes resolve the configured GitLab endpoint with a fail-closed
  // adapter, and the two write tools route through the policy plugin's
  // human-ask gate like every other external-effect tool.
  registerCapabilityTools(ctx, ["company.plan"]);
}
