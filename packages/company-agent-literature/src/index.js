import { registerCapabilityTools } from "@unitqc/company-agent-core/runtime";

export const name = "company-agent-literature";
export const inject = ["tools"];

export function apply(ctx) {
  // lab can search, fetch, and index one paper at a time.
  // algo can search and index. boot and sign see none of these tools.
  // The tools do not submit jobs or start a research loop.
  registerCapabilityTools(ctx, ["company.literature"]);
}
