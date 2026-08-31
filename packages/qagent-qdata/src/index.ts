import type { Context } from "../../../seams/dsh.d.ts";
import { registerInvokeTool } from "../../../seams/qagent_tool.ts";

export const name = "qagent-qdata";
export const inject = ["tools"];

export function apply(ctx: Context) {
  registerInvokeTool(ctx, "qdata_list_providers", "List problem providers.");
  registerInvokeTool(ctx, "qdata_run_recipe", "Run a frozen recipe.", {
    type: "object",
    required: ["name"],
    properties: { name: { type: "string" }, shots: { type: "integer" } },
  });
  registerInvokeTool(ctx, "qdata_submit_job", "Submit a qdata job.");
  registerInvokeTool(ctx, "qdata_get_job", "Poll job by job_id. Never bitstrings.", {
    type: "object",
    required: ["job_id"],
    properties: { job_id: { type: "string" } },
  });
  registerInvokeTool(ctx, "qdata_list_assets", "List assets.");
  registerInvokeTool(ctx, "qdata_get_run_record", "Read run_record by run_record_id. Short fields.", {
    type: "object",
    required: ["run_record_id"],
    properties: { run_record_id: { type: "string" } },
  });
  registerInvokeTool(ctx, "qdata_dequant_gate", "B3 verdict field.");
  // H-01i: 产品 dsh 不注册 sandbox。E11 仍走 Python invoke。模型空转不是评测。
}
