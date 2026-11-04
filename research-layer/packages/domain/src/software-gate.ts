/**
 * 软件合并门禁。
 *
 * 这是阶段 4 在上游 Super-agent 未冻结时的降级规则，不是编码路由器。
 * 不创建会话、不保存工单库、不解释模型输出。证据必须由调用方传入。
 */

import type { Finding } from "./experiment.ts";

export type SoftwareRuntime = "degraded" | "upstream";
export type SoftwareDelivery = "requested" | "proactive";
export type SoftwareMergeDecision = "allow_merge" | "deny" | "record_only" | "needs_approval";

export interface AcceptanceCheck {
  id: string;
  command: string;
}

export interface SoftwareSpec {
  spec_id: string;
  goal: string;
  non_goals: string[];
  acceptance: AcceptanceCheck[];
  rollback: string;
}

export type SoftwareGateName = "unit" | "integration" | "e2e" | "security";

export interface GateEvidence {
  name: SoftwareGateName;
  passed: boolean;
  evidence_uri: string;
}

export interface IndependentReview {
  reviewer_id: string;
  blockers: number;
}

export interface SoftwareMergeInput {
  work_id: string;
  author_id: string;
  workspace_id: string;
  runtime: SoftwareRuntime;
  upstream_version?: string | null;
  spec: SoftwareSpec;
  gates: GateEvidence[];
  review?: IndependentReview | null;
  approval_id?: string | null;
  delivery: SoftwareDelivery;
  written_rule_version?: string | null;
  /** Watchdog、投机执行或其他调用方要求跳过门禁。 */
  bypass_requested?: boolean;
  session_id?: string | null;
  evaluated_at?: string;
}

export interface SoftwareCheck {
  name: string;
  passed: boolean;
  detail: string;
}

export interface SoftwareMergeRecord {
  record_id: string;
  work_id: string;
  author_id: string;
  workspace_id: string;
  runtime: SoftwareRuntime;
  degraded: boolean;
  upstream_version: string | null;
  spec_id: string;
  session_id: string | null;
  decision: SoftwareMergeDecision;
  reason: string;
  checks: SoftwareCheck[];
  evaluated_at: string;
}

export interface SoftwareMergeResult {
  ok: boolean;
  record?: SoftwareMergeRecord;
  findings: Finding[];
}

const REQUIRED_GATES: SoftwareGateName[] = ["unit", "integration", "e2e", "security"];

function finding(code: string, message: string, path?: string): Finding {
  return { severity: "error", code, message, path };
}

function nonEmpty(value: string | null | undefined): boolean {
  return typeof value === "string" && value.trim().length > 0;
}

export function validateSoftwareSpec(spec: SoftwareSpec): Finding[] {
  const findings: Finding[] = [];
  if (!nonEmpty(spec.spec_id)) findings.push(finding("E_SPEC_ID", "规格标识不能为空", "spec_id"));
  if (!nonEmpty(spec.goal)) findings.push(finding("E_SPEC_GOAL", "规格必须有目标", "goal"));
  if (!Array.isArray(spec.non_goals)) {
    findings.push(finding("E_SPEC_NON_GOALS", "非目标必须是列表", "non_goals"));
  }
  if (!Array.isArray(spec.acceptance) || spec.acceptance.length === 0) {
    findings.push(finding("E_SPEC_ACCEPTANCE", "至少要有一条可执行验收命令", "acceptance"));
  } else {
    spec.acceptance.forEach((item, index) => {
      if (!nonEmpty(item.id) || !nonEmpty(item.command)) {
        findings.push(finding("E_SPEC_ACCEPTANCE", "验收命令必须有标识和命令", `acceptance[${index}]`));
      }
    });
  }
  if (!nonEmpty(spec.rollback)) findings.push(finding("E_SPEC_ROLLBACK", "必须写明回滚方式", "rollback"));
  return findings;
}

function check(checks: SoftwareCheck[], name: string, passed: boolean, detail: string): void {
  checks.push({ name, passed, detail });
}

/**
 * 结构预检：工单、作者、工作区与规格是否可评估。
 * 启动会话前调用，避免用一次执行去暴露结构错误。
 */
export function validateSoftwareMergeInput(input: SoftwareMergeInput): Finding[] {
  const findings: Finding[] = [];
  if (!nonEmpty(input.work_id)) findings.push(finding("E_WORK_ID", "工单标识不能为空", "work_id"));
  if (!nonEmpty(input.author_id)) findings.push(finding("E_AUTHOR", "作者不能为空", "author_id"));
  if (!nonEmpty(input.workspace_id)) findings.push(finding("E_WORKSPACE", "必须有独立工作区", "workspace_id"));
  findings.push(...validateSoftwareSpec(input.spec));
  return findings;
}

/**
 * 合并判断。结构不合法时不产出记录；其余情况都产出一条可审计决定。
 */
export function evaluateSoftwareMerge(input: SoftwareMergeInput): SoftwareMergeResult {
  const findings = validateSoftwareMergeInput(input);
  if (findings.length > 0) return { ok: false, findings };

  const evaluatedAt = input.evaluated_at ?? new Date().toISOString();
  const checks: SoftwareCheck[] = [];
  const upstreamVersion = nonEmpty(input.upstream_version) ? input.upstream_version!.trim() : null;
  let decision: SoftwareMergeDecision = "allow_merge";
  let reason = "门禁通过，允许进入人工合并";

  const deny = (name: string, detail: string): void => {
    check(checks, name, false, detail);
    if (decision === "allow_merge") {
      decision = "deny";
      reason = detail;
    }
  };

  if (input.bypass_requested) {
    deny("no_bypass", "Watchdog 或投机执行不能跳过合并门禁");
  } else {
    check(checks, "no_bypass", true, "没有要求跳过门禁");
  }

  if (input.runtime === "upstream" && !upstreamVersion) {
    deny("upstream_pin", "未锁定上游版本时不能声称运行在 Super-agent 上");
  } else if (input.runtime === "degraded") {
    check(checks, "runtime", true, "上游未冻结，按降级单工单执行");
  } else {
    check(checks, "runtime", true, `上游版本 ${upstreamVersion}`);
  }

  if (input.delivery === "proactive" && !nonEmpty(input.written_rule_version)) {
    check(checks, "proactive_rule", false, "没有书面规则的主动行为只记录，不交付");
  } else {
    check(checks, "proactive_rule", true, "交付有请求或书面规则");
  }

  for (const name of REQUIRED_GATES) {
    const evidence = input.gates.find((item) => item.name === name);
    if (!evidence || !evidence.passed || !nonEmpty(evidence.evidence_uri)) {
      deny(`gate_${name}`, `缺少通过的 ${name} 证据`);
    } else {
      check(checks, `gate_${name}`, true, evidence.evidence_uri);
    }
  }

  const review = input.review;
  if (!review || !nonEmpty(review.reviewer_id)) {
    deny("independent_review", "缺少独立评审");
  } else if (review.reviewer_id === input.author_id) {
    deny("independent_review", "作者不能审查自己的变更");
  } else if (review.blockers > 0) {
    deny("independent_review", "独立评审仍有阻断项");
  } else {
    check(checks, "independent_review", true, `评审人 ${review.reviewer_id}`);
  }

  if (decision === "allow_merge" && !nonEmpty(input.approval_id)) {
    check(checks, "approval", false, "合并主分支需要人工审批");
    decision = "needs_approval";
    reason = "合并主分支需要人工审批";
  } else if (decision === "allow_merge" && nonEmpty(input.approval_id)) {
    check(checks, "approval", true, `审批 ${input.approval_id}`);
  }

  if (nonEmpty(input.session_id)) {
    check(checks, "session_recorded", true, input.session_id!.trim());
  }

  if (
    (decision === "allow_merge" || decision === "needs_approval") &&
    input.delivery === "proactive" &&
    !nonEmpty(input.written_rule_version)
  ) {
    decision = "record_only";
    reason = "没有书面规则的主动行为只记录，不交付";
  }

  const record: SoftwareMergeRecord = {
    record_id: `${input.work_id}:${evaluatedAt}`,
    work_id: input.work_id,
    author_id: input.author_id,
    workspace_id: input.workspace_id,
    runtime: input.runtime,
    degraded: input.runtime === "degraded",
    upstream_version: input.runtime === "upstream" ? upstreamVersion : null,
    spec_id: input.spec.spec_id,
    session_id: nonEmpty(input.session_id) ? input.session_id!.trim() : null,
    decision,
    reason,
    checks,
    evaluated_at: evaluatedAt,
  };
  return { ok: true, record, findings };
}
