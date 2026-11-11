import { authorize, clearApprovalCard, markApprovalCard, visibleToolCatalog } from "@unitqc/company-agent-core/runtime";

export const name = "company-agent-policy";
export const inject = ["tools"];

const contractRows = visibleToolCatalog();
const contractTools = new Set(contractRows.map((row) => String(row.name || "")));

if (contractTools.size !== contractRows.length) {
  throw new Error("company-agent policy received duplicate contract tools");
}

async function policyCheck(tool, args = {}, signal, session) {
  const name = String(tool || "");
  if (contractTools.has(name)) {
    const result = await authorize(name, args, signal, session);
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
  "company_research_run",
  "company_dingtalk_reply",
  "company_grant_open",
  "company_knowledge_note",
]);

const DEVICE_PROVIDER = "ionstack-twinrun";
const DEVICE_APPROVAL_REASON_MAX_BYTES = 700;

function seatText(args, handoff) {
  const subject = args?.subject;
  let subjectLabel = "unset";
  let limitLabel = "unset";
  if (subject && typeof subject === "object") {
    const kind = typeof subject.kind === "string" ? subject.kind : "unset";
    const id = typeof subject.id === "string" ? subject.id : "unset";
    const limitKind = typeof subject.limit_kind === "string" ? subject.limit_kind : "unset";
    const limit = Number.isSafeInteger(subject.limit) ? String(subject.limit) : "unset";
    subjectLabel = `${kind}:${id}`;
    limitLabel = `${limitKind}:${limit}`;
  } else if (typeof args?.circuit_id === "string") {
    subjectLabel = `circuit:${args.circuit_id}`;
  } else if (typeof args?.experiment_id === "string") {
    subjectLabel = `experiment:${args.experiment_id}`;
  } else if (typeof args?.program_sha256 === "string") {
    subjectLabel = `program:${args.program_sha256}`;
  }
  if (limitLabel === "unset" && Number.isSafeInteger(args?.shots)) {
    limitLabel = `shots:${args.shots}`;
  } else if (limitLabel === "unset" && Number.isSafeInteger(args?.nodes)) {
    limitLabel = `node_hours:${args.nodes}`;
  }
  return `subject=${subjectLabel}; limit=${limitLabel}; handoff=${handoff ? "yes" : "no"}`;
}

function deviceApprovalReason(tool, args, handoff = false) {
  if (tool === "hpc_submit") {
    return `Company Agent HPC submission approval: provider=hpc-slurm-ssh; job_name=${args?.job_name}; script=${args?.script}; partition=${args?.partition ?? "default"}; nodes=${args?.nodes ?? "default"}; walltime=${args?.walltime ?? "default"}; ${seatText(args, handoff)}`;
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
    return `Company Agent cloud simulator submission approval: provider=uqc-cloud; program_path=${args?.program_path}; target=${args?.target}; shots=${args?.shots}; ${seatText(args, handoff)}`;
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
  if (tool === "company_dingtalk_reply") {
    const threadId = typeof args?.thread_id === "string" ? args.thread_id : "invalid";
    const triggerId = typeof args?.trigger_id === "string" && /^trg_[0-9a-f]{32}$/.test(args.trigger_id)
      ? args.trigger_id
      : "invalid";
    const bytes = typeof args?.text === "string" ? String(Buffer.byteLength(args.text, "utf8")) : "invalid";
    const reason = `Company Agent DingTalk reply approval: provider=company-dingtalk; thread_id=${threadId}; trigger_id=${triggerId}; bytes=${bytes}`;
    if (Buffer.byteLength(reason, "utf8") > DEVICE_APPROVAL_REASON_MAX_BYTES) {
      return "Company Agent DingTalk reply approval: provider=company-dingtalk; parameters=invalid";
    }
    return reason;
  }
  if (tool === "company_knowledge_note") {
    return `Company Agent knowledge note approval: experiment_id=${args?.experiment_id}; stop_reason=${args?.stop_reason}; ${seatText(args, handoff)}`;
  }
  if (tool === "company_research_run") {
    const attempts = Number.isSafeInteger(args?.max_attempts) ? String(args.max_attempts) : "invalid";
    return `Company Agent research loop approval: provider=company-research; experiment_id=${args?.experiment_id}; task_id=${args?.task_id}; attempts=${attempts}; resource_type=${args?.resource_type ?? "unset"}`;
  }
  if (tool === "company_plan_milestone_create") {
    return `Company Agent plan milestone create approval: provider=company-plan; project=${args?.project}; title=${args?.title}; due=${args?.due_date ?? "unset"}`;
  }
  if (tool === "company_grant_open") {
    const names = Array.isArray(args?.tools)
      ? args.tools.filter((item) => typeof item === "string").join(",")
      : "invalid";
    const calls = Number.isSafeInteger(args?.max_calls) ? String(args.max_calls) : "invalid";
    const ttl = Number.isSafeInteger(args?.ttl_seconds) ? String(args.ttl_seconds) : "invalid";
    const reason = `Company Agent session grant approval: tools=${names}; max_calls=${calls}; ttl_seconds=${ttl}; ${seatText(args, handoff)}`;
    if (Buffer.byteLength(reason, "utf8") > DEVICE_APPROVAL_REASON_MAX_BYTES) {
      return "Company Agent session grant approval: parameters=invalid";
    }
    return reason;
  }
  if (tool !== "quantum_device_run") return "company-agent-policy";
  const circuitId = typeof args?.circuit_id === "string" ? args.circuit_id : "invalid";
  const shots = Number.isSafeInteger(args?.shots) ? String(args.shots) : "invalid";
  const reason = `Company Agent device execution approval: provider=${DEVICE_PROVIDER}; circuit_id=${circuitId}; shots=${shots}; ${seatText(args, handoff)}`;
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
    clearApprovalCard(exec);
    const sessionTurn = String(exec?.agent?.id ?? exec?.agent?.session?.header?.id ?? "");
    const session = sessionTurn ? `dsh:${sessionTurn}` : undefined;
    let result;
    try {
      result = await policyCheck(exec?.name, exec?.arguments || {}, exec?.signal, session);
    } catch {
      return { kind: "deny", reason: "company-agent-policy" };
    }
    if (result === null) return next();
    if (result.decision === "deny") {
      return { kind: "deny", reason: result.error || "company-agent-policy" };
    }
    if (result.decision === "ask") {
      markApprovalCard(exec);
      return { kind: "ask", reason: deviceApprovalReason(exec?.name, exec?.arguments, result.handoff === true) };
    }
    return next();
  });
}
