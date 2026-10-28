import { authorize, toolCatalog } from "@unitqc/company-agent-core/runtime";

export const name = "company-agent-policy";
export const inject = ["tools"];

const contractRows = toolCatalog();
const contractTools = new Set(contractRows.map((row) => String(row.name || "")));

if (contractTools.size !== contractRows.length) {
  throw new Error("company-agent policy received duplicate contract tools");
}

async function policyCheck(tool, args = {}, signal) {
  const name = String(tool || "");
  if (contractTools.has(name)) {
    const result = await authorize(name, args, signal);
    if (result.decision === "ask" && (
      !ASK_ROUTED_TOOLS.has(name)
      || !new Set(["lab", "sign"]).has(process.env.COMPANY_AGENT_PRESET)
      || process.env.COMPANY_AGENT_PROFILE !== "company-agent"
    )) {
      return { decision: "deny", error: "approval is unavailable for this tool or preset" };
    }
    return result;
  }
  if (name.startsWith("company_") || name.startsWith("quantum_") || name.startsWith("hpc_")) {
    return { decision: "deny", error: "unknown Company Agent tool" };
  }
  return null;
}

// Ask decisions in lab/sign route through the DSH session approval channel;
// the set covers every tool whose contract wires a human approval gate.
const ASK_ROUTED_TOOLS = new Set([
  "quantum_device_run",
  "hpc_submit",
  "hpc_stage_file",
  "hpc_job_cancel",
  "hpc_dir_create",
  "hpc_file_remove",
  "quantum_cloud_submit",
  "company_latex_edit",
  "company_latex_batch_edit",
  "company_latex_revert",
  "company_latex_push",
  "company_latex_overleaf_push",
  "company_latex_issue_note",
  "company_plan_issue_create",
  "company_plan_note_create",
  "company_plan_issue_write",
  "company_plan_milestone_create",
]);

const DEVICE_PROVIDER = "ionstack-twinrun";
const DEVICE_APPROVAL_REASON_MAX_BYTES = 700;

function deviceApprovalReason(tool, args) {
  if (tool === "hpc_submit") {
    return `Company Agent HPC submission approval: provider=hpc-slurm-ssh; job_name=${args?.job_name}; script=${args?.script}; partition=${args?.partition ?? "default"}; nodes=${args?.nodes ?? "default"}; walltime=${args?.walltime ?? "default"}`;
  }
  if (tool === "hpc_stage_file") {
    return `Company Agent HPC file upload approval: provider=hpc-slurm-ssh; gateway_path=${args?.gateway_path}; workspace_path=${args?.workspace_path}`;
  }
  if (tool === "hpc_job_cancel") {
    return `Company Agent HPC job cancel approval: provider=hpc-slurm-ssh; slurm_number=${args?.slurm_number}`;
  }
  if (tool === "hpc_dir_create") {
    return `Company Agent HPC directory create approval: provider=hpc-slurm-ssh; path=${args?.path}`;
  }
  if (tool === "hpc_file_remove") {
    return `Company Agent HPC file remove approval: provider=hpc-slurm-ssh; path=${args?.path}`;
  }
  if (tool === "quantum_cloud_submit") {
    return `Company Agent cloud simulator submission approval: provider=uqc-cloud; program_path=${args?.program_path}; target=${args?.target}; shots=${args?.shots}`;
  }
  if (tool === "company_latex_edit") {
    return `Company Agent latex edit approval: provider=company-latex; project=${args?.project}; path=${args?.path}`;
  }
  if (tool === "company_latex_batch_edit") {
    const rows = args?.files;
    return `Company Agent latex batch edit approval: provider=company-latex; project=${args?.project}; files=${Array.isArray(rows) ? rows.length : "invalid"}`;
  }
  if (tool === "company_latex_revert") {
    return `Company Agent latex revert approval: provider=company-latex; project=${args?.project}; target=${args?.target ?? "project"}`;
  }
  if (tool === "company_latex_push") {
    return `Company Agent latex push approval: provider=company-latex; project=${args?.project}; repo=${args?.repo}`;
  }
  if (tool === "company_latex_overleaf_push") {
    return `Company Agent latex overleaf push approval: provider=company-latex; project=${args?.project}; project_id=${args?.project_id}; branch=${args?.branch ?? "main"}`;
  }
  if (tool === "company_latex_issue_note") {
    return `Company Agent latex issue note approval: provider=company-latex; project=${args?.project}; repo=${args?.repo}; issue_iid=${args?.issue_iid}; artifact=${args?.artifact}`;
  }
  if (tool === "company_plan_issue_create") {
    return `Company Agent plan issue create approval: provider=company-plan; project=${args?.project}; title=${args?.title}`;
  }
  if (tool === "company_plan_note_create") {
    return `Company Agent plan note approval: provider=company-plan; project=${args?.project}; target=${args?.target}; iid=${args?.iid}`;
  }
  if (tool === "company_plan_issue_write") {
    const fields = ["title", "description", "state_event", "labels", "milestone_id"].filter((name) => args?.[name] !== undefined);
    return `Company Agent plan issue write approval: provider=company-plan; project=${args?.project}; iid=${args?.iid}; fields=${fields.length ? fields.join("+") : "none"}`;
  }
  if (tool === "company_plan_milestone_create") {
    return `Company Agent plan milestone create approval: provider=company-plan; project=${args?.project}; title=${args?.title}; due=${args?.due_date ?? "unset"}`;
  }
  if (tool !== "quantum_device_run") return "company-agent-policy";
  const circuitId = typeof args?.circuit_id === "string" ? args.circuit_id : "invalid";
  const shots = Number.isSafeInteger(args?.shots) ? String(args.shots) : "invalid";
  const reason = `Company Agent device execution approval: provider=${DEVICE_PROVIDER}; circuit_id=${circuitId}; shots=${shots}`;
  if (Buffer.byteLength(reason, "utf8") > DEVICE_APPROVAL_REASON_MAX_BYTES) {
    return `Company Agent device execution approval: provider=${DEVICE_PROVIDER}; parameters=invalid`;
  }
  return reason;
}

export async function policyDecision(tool, args = {}, signal) {
  const result = await policyCheck(tool, args, signal);
  return result?.decision ?? null;
}

export function apply(ctx) {
  ctx.on("tools/pre-execute", async (exec, next) => {
    const result = await policyCheck(exec?.name, exec?.arguments || {}, exec?.signal);
    if (result === null) return next();
    if (result.decision === "deny") {
      return { kind: "deny", reason: result.error || "company-agent-policy" };
    }
    if (result.decision === "ask") {
      return { kind: "ask", reason: deviceApprovalReason(exec?.name, exec?.arguments) };
    }
    return next();
  });
}
