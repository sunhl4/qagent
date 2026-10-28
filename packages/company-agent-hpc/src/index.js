import { registerCapabilityTools } from "@unitqc/company-agent-core/runtime";

export const name = "company-agent-hpc";
export const inject = ["tools"];

export function apply(ctx) {
  // Tool registration follows the preset's visible_tools contract: boot gets no
  // HPC tool, algo only the hpc_queue read-only probe, lab/sign also hpc_submit.
  // hpc_submit stays a human-ask tool in lab/sign and is denied in boot/algo by
  // the mounted policy contract; the plugin itself adds no extra approval path.
  registerCapabilityTools(ctx, ["compute.hpc"]);
}
