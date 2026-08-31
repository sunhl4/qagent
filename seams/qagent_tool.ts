import type { Context } from "./dsh.d.ts";
import { currentPreset, qagentInvoke } from "./qagent_bridge.ts";

export function executeTool(
  tool: string,
  args: Record<string, unknown> = {},
  approved = false,
): Record<string, unknown> {
  const result = qagentInvoke(tool, args, currentPreset(), approved);
  if (result.status === "needs_ask") {
    return { ask: true, tool, decision: result.decision };
  }
  if (result.status === "ok") {
    return (result.payload as Record<string, unknown>) ?? {};
  }
  throw new Error(`${tool}: ${result.status}${result.slot_id ? ` ${result.slot_id}` : ""}`);
}

export function registerInvokeTool(
  ctx: Context,
  name: string,
  description: string,
  parameters: Record<string, unknown> = { type: "object", properties: {} },
): void {
  ctx.tools.register({
    name,
    description,
    parameters,
    output: {
      schema: { type: "object", additionalProperties: true },
      render: (_args: unknown, value: unknown) => [
        { type: "text", text: JSON.stringify(value) },
      ],
    },
    // dsh runs execute only after tools/pre-execute ask is resolved.
    execute: async (args) => executeTool(name, args, true),
  });
}
