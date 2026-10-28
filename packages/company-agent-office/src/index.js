import { registerCapabilityTools } from "@unitqc/company-agent-core/runtime";

export const name = "company-agent-office";
export const inject = ["tools"];

export function apply(ctx) {
  // company.office is the WPS-suite porting slice over the mounted workspace:
  // P1 bounded text extraction plus P2 bounded single-file artifact creation.
  // The preset catalog filter decides visibility (boot/lab/algo see it,
  // sign does not). Every call resolves the bounded workspace the core
  // runtime forwards and fails closed outside it; every part is standard-library
  // work over the mounted workspace, so no ask gate applies.
  registerCapabilityTools(ctx, ["company.office"]);
}
