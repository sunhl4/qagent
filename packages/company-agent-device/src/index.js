import { registerCapabilityTools } from "@unitqc/company-agent-core/runtime";

export const name = "company-agent-device";
export const inject = ["tools"];

export function apply(ctx) {
  if (process.env.COMPANY_AGENT_PROFILE !== "company-agent") {
    throw new Error("company-agent-device may only load in the full company-agent profile");
  }
  const preset = process.env.COMPANY_AGENT_PRESET;
  if (preset === "boot" || preset === "algo") return;
  if (preset !== "lab" && preset !== "sign") {
    throw new Error("company-agent-device received an invalid preset");
  }
  registerCapabilityTools(ctx, ["quantum.device"]);
}
