import { registerCapabilityTools } from "@unitqc/company-agent-core/runtime";

export const name = "company-agent-research";
export const inject = ["tools"];

export function apply(ctx) {
  // lab can compile, run, read status, and read the tenant digest.
  // algo can compile, read status, and read the digest. boot and sign see none
  // of these tools. The run tool asks in lab. hpc and cloud stay handoffs, and
  // the digest does not open a ticket.
  registerCapabilityTools(ctx, ["company.research"]);
}
