import { registerCapabilityTools } from "./runtime.js";

export {
  authorize,
  decide,
  dshSchema,
  invoke,
  registerCapabilityTools,
  registerTool,
  toolCatalog,
  validate,
} from "./runtime.js";

export const name = "company-agent-core";
export const inject = ["tools"];

export function apply(ctx) {
  // Portal open facts ride the core registration so every profile can hand the
  // workspace one kind+route answer; the preset catalog keeps sign out.
  registerCapabilityTools(ctx, [
    "company.workflow", "company.knowledge", "company.portal", "company.dingtalk",
  ]);
}
