/**
 * 有界实验循环：在预算、截止时间与尝试次数内反复执行 ExperimentSpec。
 *
 * 设计约束：
 * - 不使用 `while true`；循环上限来自规格与调用方，取两者较小值。
 * - 每轮有唯一 run_id，每次尝试单独写 manifest。
 * - 未知执行、需要审批、策略拒绝都立即停止，不自动重试。
 * - 所有尝试（含失败与负结果）都写入循环摘要，禁止只记录成功。
 * - 循环只依赖端口与领域逻辑，不依赖任何 DSH、云或 HPC 实现。
 */

import { createHash } from "node:crypto";
import type { ArtifactRef, DataClass, Subject } from "../../../contracts/src/index.ts";
import type {
  CheckpointRecord,
  CostLedger,
  DecisionAction,
  ExperimentSpec,
  FailureCandidate,
  FailureEntry,
  FailureRecord,
  Finding,
  PreviousAttemptState,
} from "../../domain/src/index.ts";
import { buildFailureEntries, buildPlatformSignal, classifyFailure, failureStats, planResume } from "../../domain/src/index.ts";
import type { WorktreeRecord } from "../../workspace/src/index.ts";
import { createExperimentWorktree } from "../../workspace/src/index.ts";
import { runExperiment } from "./run.ts";
import type { PipelineState, RunDeps, RunInput, RunOptions } from "./run.ts";

export type LoopStopReason =
  | "kept"
  | "exhausted"
  | "budget_exhausted"
  | "deadline"
  | "stopped"
  | "escalated"
  | "blocked"
  | "consecutive_failures"
  | "no_candidate"
  | "invalid_candidate";

export interface LoopAttemptRecord {
  attempt: number;
  run_id: string;
  experiment_id: string;
  state: PipelineState;
  decision: DecisionAction | null;
  reason?: string | null;
  failure?: FailureRecord;
  cost: number;
  currency: string;
  manifest_ref?: string | null;
  error_code?: string | null;
  resume_plan?: string | null;
  resume_from?: string | null;
  started_at: string;
  finished_at: string;
}

export interface LoopSummary {
  loop_id: string;
  task_id: string;
  experiment_id: string;
  stop_reason: LoopStopReason;
  stop_detail?: string | null;
  attempts: LoopAttemptRecord[];
  total_cost: number;
  currency: string;
  budget_total: number;
  remaining_budget: number;
  started_at: string;
  finished_at: string;
}

export interface LoopOutcome {
  state: LoopStopReason;
  attempts: LoopAttemptRecord[];
  failures: FailureEntry[];
  worktrees: WorktreeRecord[];
  totalCost: number;
  remainingBudget: number;
  summary: LoopSummary;
  summaryRef?: ArtifactRef;
  failureRef?: ArtifactRef;
  /** 启用租约时返回最终共享账本，可直接交给 sweepLeases 继续扫描。 */
  ledger?: CostLedger;
  findings: Finding[];
}

export interface ProposeContext {
  /** 即将执行的轮次，从 2 开始。 */
  attempt: number;
  previous?: RunOutcomeLike;
  previous_spec: ExperimentSpec;
  history: readonly LoopAttemptRecord[];
}

/** 只暴露提案需要的上一轮信息，避免循环依赖 run.ts 的完整类型。 */
export interface RunOutcomeLike {
  state: PipelineState;
  decision?: { action: DecisionAction };
  failure?: FailureRecord;
}

/** 本地 worktree 配置；未提供时由调用方自行准备代码目录。 */
export interface LoopWorkspaceOptions {
  repoRoot: string;
  baseDir?: string;
  baseRef?: string;
  timeoutMs?: number;
}

/** 租约门控：每轮尝试走 预留→提交→释放结算，账本由循环统一持有。 */
export interface LoopLeaseOptions {
  /** 外部初始账本；未提供时从空开始。 */
  ledger?: CostLedger;
  /** 租约 TTL；默认每轮按规格 `max_wall_clock_seconds`。 */
  ttlSeconds?: number;
}

/** 检查点恢复决策；同时提供 `checkpoints` 与 `resume` 时启用。 */
export interface LoopResumeOptions {
  /** 上限内允许多少次“从检查点恢复”。达到后转人工。 */
  max_resumes: number;
  /** 检查点最大可用时长（秒）；null 表示不检查。 */
  max_age_seconds?: number | null;
  /** 无检查点只告警不算错误时设为 true。 */
  required?: boolean;
}

export interface LoopInput {
  spec: ExperimentSpec;
  subject: Subject;
  traceId: string;
  idempotencyKey: string;
  code: RunInput["code"];
  environment: RunInput["environment"];
  budget: {
    total: number;
    currency: string;
    approvedActions?: string[];
    approvalId?: string;
  };
  baselineGuardrails?: Record<string, number>;
  dataClass?: DataClass;
  /** 配置后，每轮在执行前创建或复用隔离 worktree，并把分支与基线提交写入 manifest。 */
  workspace?: LoopWorkspaceOptions;
  /** 配置后，每轮试用租约门控执行；结束统一释放并结算到共享账本。 */
  lease?: LoopLeaseOptions;
  /** 上一轮尝试留下的检查点记录，配合 `resume` 生成恢复决策。 */
  checkpoints?: CheckpointRecord[];
  /** 恢复策略上限；与 `checkpoints` 同时提供才启用。 */
  resume?: LoopResumeOptions;
  /** 循环 ID；默认由 experiment_id 与幂等键派生。 */
  loopId?: string;
  /** 第二轮及以后生成候选规格；返回 null 表示没有下一轮。 */
  propose?: (context: ProposeContext) => ExperimentSpec | null | Promise<ExperimentSpec | null>;
  /** 覆盖最大尝试次数，但不会超过规格中的 max_attempts。 */
  maxAttempts?: number;
  /** 覆盖最大连续失败次数。 */
  maxConsecutiveFailures?: number;
  /** 连续多少轮没有保留结果后早停；0 或未设置表示不启用。 */
  earlyStopAfterDiscards?: number;
  /** 覆盖规格中的截止时间。 */
  deadlineAt?: string | null;
}

function sha256(value: string): string {
  return createHash("sha256").update(value).digest("hex");
}

function isBlocked(state: PipelineState): boolean {
  return state === "rejected" || state === "denied" || state === "infeasible";
}

export async function runExperimentLoop(
  input: LoopInput,
  deps: RunDeps,
  options: RunOptions = {},
): Promise<LoopOutcome> {
  const now = deps.now ?? (() => new Date());
  const startedAt = now().toISOString();
  const loopId =
    input.loopId ?? `${input.spec.experiment_id}-loop-${sha256(input.idempotencyKey).slice(0, 8)}`;

  const specMaxAttempts = Math.max(1, input.spec.stopping?.max_attempts ?? 1);
  const maxAttempts = Math.max(
    1,
    Math.min(input.maxAttempts ?? specMaxAttempts, specMaxAttempts),
  );
  const maxConsecutiveFailures = Math.max(
    1,
    input.maxConsecutiveFailures ?? input.spec.stopping?.max_consecutive_failures ?? 1,
  );
  const deadlineAt = input.deadlineAt ?? input.spec.stopping?.deadline_at ?? null;
  const deadlineMs = deadlineAt ? Date.parse(deadlineAt) : null;

  const currency = input.budget.currency;
  let remainingBudget = input.budget.total;
  let totalCost = 0;
  let consecutiveFailures = 0;
  let consecutiveDiscards = 0;
  let resumesSoFar = 0;
  let sharedLedger: CostLedger = input.lease?.ledger ?? { entries: [] };

  const attempts: LoopAttemptRecord[] = [];
  const failureCandidates: FailureCandidate[] = [];
  const worktrees: WorktreeRecord[] = [];
  const findings: Finding[] = [];
  let currentSpec = input.spec;
  let previousOutcome: RunOutcomeLike | undefined;

  /** 发布实验完成 / 预算耗尽事实事件；失败只记 finding，不改变循环结果。 */
  const emitLoopSignal = async (
    type: "experiment.completed.v1" | "budget.exhausted.v1",
    data: Record<string, string | number | boolean | null>,
  ): Promise<void> => {
    if (!deps.events) return;
    const built = buildPlatformSignal({
      type,
      tenant_id: input.subject.tenantId,
      project_id: input.subject.projectId ?? null,
      resource_id: input.spec.experiment_id,
      resource_version: attempts.length + 1,
      time: now().toISOString(),
      data,
    });
    if (!built.ok || !built.signal) {
      findings.push({
        severity: "warning",
        code: "W_SIGNAL_BUILD",
        message: `平台事件构造失败: ${built.findings.map((item) => item.message).join("; ")}`,
      });
      return;
    }
    const published = await deps.events.publish({
      id: built.signal.id,
      type: built.signal.type,
      source: "research-layer",
      tenantId: input.subject.tenantId,
      projectId: input.subject.projectId,
      resourceId: built.signal.resource_id,
      resourceVersion: built.signal.resource_version,
      time: built.signal.time,
      dataContentType: "application/json",
      data: built.signal.data,
      traceId: input.traceId,
    });
    if (!published.ok) {
      findings.push({
        severity: "warning",
        code: "W_SIGNAL_PUBLISH",
        message: `平台事件发布失败: ${published.error.code} ${published.error.message}`,
      });
    }
  };

  const finish = async (
    stopReason: LoopStopReason,
    stopDetail: string | null,
  ): Promise<LoopOutcome> => {
    const summary: LoopSummary = {
      loop_id: loopId,
      task_id: input.spec.task_id,
      experiment_id: input.spec.experiment_id,
      stop_reason: stopReason,
      stop_detail: stopDetail,
      attempts,
      total_cost: totalCost,
      currency,
      budget_total: input.budget.total,
      remaining_budget: remainingBudget,
      started_at: startedAt,
      finished_at: now().toISOString(),
    };

    const summaryJson = JSON.stringify(summary, null, 2);
    const put = await deps.artifacts.put({
      tenantId: input.subject.tenantId,
      projectId: input.subject.projectId,
      key: `experiments/${input.spec.experiment_id}/loops/${loopId}/summary.json`,
      contentType: "application/json",
      bytes: new TextEncoder().encode(summaryJson),
      expectedSha256: sha256(summaryJson),
      metadata: {
        task_id: input.spec.task_id,
        stop_reason: stopReason,
        attempt_count: String(attempts.length),
      },
      idempotencyKey: `${input.idempotencyKey}:loop-summary`,
    });
    if (!put.ok) {
      findings.push({
        severity: "warning",
        code: "W_LOOP_SUMMARY_UPLOAD",
        message: `循环摘要写入失败: ${put.error.code} ${put.error.message}`,
      });
    }

    const failures = buildFailureEntries(failureCandidates);
    let failureRef: ArtifactRef | undefined;
    if (failures.length > 0) {
      const libraryJson = JSON.stringify(
        { entries: failures, stats: failureStats(failures) },
        null,
        2,
      );
      const libraryPut = await deps.artifacts.put({
        tenantId: input.subject.tenantId,
        projectId: input.subject.projectId,
        key: `experiments/${input.spec.experiment_id}/loops/${loopId}/failures.json`,
        contentType: "application/json",
        bytes: new TextEncoder().encode(libraryJson),
        expectedSha256: sha256(libraryJson),
        metadata: {
          task_id: input.spec.task_id,
          entry_count: String(failures.length),
        },
        idempotencyKey: `${input.idempotencyKey}:failures`,
      });
      if (libraryPut.ok) {
        failureRef = libraryPut.value;
      } else {
        findings.push({
          severity: "warning",
          code: "W_FAILURE_LIBRARY_UPLOAD",
          message: `失败库写入失败: ${libraryPut.error.code} ${libraryPut.error.message}`,
        });
      }
    }

    if (stopReason === "kept") {
      await emitLoopSignal("experiment.completed.v1", {
        stop_reason: stopReason,
        attempts: attempts.length,
        last_decision: attempts.at(-1)?.decision ?? null,
      });
    }
    if (stopReason === "budget_exhausted") {
      await emitLoopSignal("budget.exhausted.v1", {
        stop_reason: stopReason,
        attempts: attempts.length,
        remaining_budget: remainingBudget,
        currency,
      });
    }

    return {
      state: stopReason,
      attempts,
      failures,
      worktrees,
      totalCost,
      remainingBudget,
      summary,
      summaryRef: put.ok ? put.value : undefined,
      failureRef,
      ledger: input.lease ? sharedLedger : undefined,
      findings,
    };
  };

  for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
    /* 1. 截止时间：每轮开始前检查 */
    if (deadlineMs !== null && Number.isFinite(deadlineMs) && now().getTime() >= deadlineMs) {
      findings.push({
        severity: "warning",
        code: "W_LOOP_DEADLINE",
        message: `已到达截止时间 ${deadlineAt}，停止循环`,
      });
      return finish("deadline", deadlineAt);
    }

    /* 2. 预算耗尽 */
    if (remainingBudget <= 0) {
      findings.push({
        severity: "warning",
        code: "W_LOOP_BUDGET",
        message: "剩余预算为 0，停止循环",
      });
      return finish("budget_exhausted", "剩余预算为 0");
    }

    /* 3. 生成下一轮候选 */
    if (attempt > 1) {
      if (!input.propose) {
        return finish("no_candidate", "没有提供 propose，无法生成下一轮");
      }
      try {
        const next = await input.propose({
          attempt,
          previous: previousOutcome,
          previous_spec: currentSpec,
          history: attempts,
        });
        if (!next) {
          return finish("no_candidate", `第 ${attempt} 轮没有候选`);
        }
        if (
          next.experiment_id !== input.spec.experiment_id ||
          next.task_id !== input.spec.task_id
        ) {
          findings.push({
            severity: "error",
            code: "E_LOOP_SPEC_MISMATCH",
            message: `候选必须保持 experiment_id=${input.spec.experiment_id} 与 task_id=${input.spec.task_id}`,
          });
          return finish("invalid_candidate", "候选的 experiment_id 或 task_id 不一致");
        }
        currentSpec = next;
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        findings.push({
          severity: "error",
          code: "E_LOOP_PROPOSER",
          message: `propose 抛出异常: ${message}`,
        });
        return finish("stopped", `propose 异常: ${message}`);
      }
    }

    /* 4. 单轮预算占用检查：max_cost 视为本轮预留上限 */
    if (remainingBudget < currentSpec.resources.max_cost) {
      findings.push({
        severity: "warning",
        code: "W_LOOP_BUDGET",
        message: `剩余预算 ${remainingBudget} 低于本轮上限 ${currentSpec.resources.max_cost}`,
      });
      return finish(
        "budget_exhausted",
        `剩余预算 ${remainingBudget} 低于本轮上限 ${currentSpec.resources.max_cost}`,
      );
    }

    /* 5. 准备隔离工作区 */
    let attemptCode = input.code;
    if (input.workspace) {
      const workspace = createExperimentWorktree({
        repoRoot: input.workspace.repoRoot,
        baseDir: input.workspace.baseDir,
        baseRef: input.workspace.baseRef,
        timeoutMs: input.workspace.timeoutMs,
        experiment_id: currentSpec.experiment_id,
        attempt,
      });
      if (!workspace.ok) {
        findings.push({
          severity: "error",
          code: "E_WORKTREE",
          message: `worktree 准备失败: ${workspace.error.code} ${workspace.error.message}`,
        });
        return finish("stopped", `worktree 准备失败: ${workspace.error.code}`);
      }
      worktrees.push(workspace.value);
      attemptCode = {
        ...input.code,
        repo: input.code.repo || workspace.value.repo_root,
        commit: workspace.value.base_commit ?? input.code.commit,
        branch: workspace.value.branch,
      };
    }

    /* 6. 执行一轮 */
    const runId = `${loopId}-run-${attempt}`;
    const attemptStartedAt = now().toISOString();

    let outcome: Awaited<ReturnType<typeof runExperiment>>;
    try {
      outcome = await runExperiment(
        {
          spec: currentSpec,
          subject: input.subject,
          traceId: input.traceId,
          idempotencyKey: `${input.idempotencyKey}:attempt:${attempt}`,
          code: attemptCode,
          environment: input.environment,
          budget: {
            remaining: remainingBudget,
            currency,
            approvedActions: input.budget.approvedActions,
            approvalId: input.budget.approvalId,
          },
          lease: input.lease
            ? {
                budget: { limit: remainingBudget, currency },
                ledger: sharedLedger,
                ttlSeconds: input.lease.ttlSeconds,
              }
            : undefined,
          baselineGuardrails: input.baselineGuardrails,
          dataClass: input.dataClass,
          attempt,
          runId,
        },
        deps,
        options,
      );
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      const failure = classifyFailure({
        stage: "loop",
        code: "E_PIPELINE_THROW",
        message: `流水线抛出异常: ${message}`,
      });
      findings.push({ severity: "error", code: "E_PIPELINE_THROW", message: failure.message });
      failureCandidates.push({
        task_id: input.spec.task_id,
        experiment_id: currentSpec.experiment_id,
        run_id: runId,
        failure,
        decision: null,
        occurred_at: now().toISOString(),
      });
      attempts.push({
        attempt,
        run_id: runId,
        experiment_id: currentSpec.experiment_id,
        state: "failed",
        decision: null,
        reason: failure.message,
        failure,
        cost: 0,
        currency,
        manifest_ref: null,
        error_code: "E_PIPELINE_THROW",
        started_at: attemptStartedAt,
        finished_at: now().toISOString(),
      });
      return finish("stopped", `流水线异常: ${message}`);
    }

    const cost = outcome.manifest?.resources.cost ?? 0;
    const outcomeCurrency = outcome.manifest?.resources.currency ?? currency;
    if (outcomeCurrency !== currency) {
      findings.push({
        severity: "warning",
        code: "W_LOOP_CURRENCY",
        message: `本轮币种 ${outcomeCurrency} 与预算币种 ${currency} 不一致`,
      });
    }
    totalCost += cost;
    if (input.lease && outcome.ledger) {
      /* 租约路径：以账本“已承诺成本”为准，预留占用同样计入剩余预算。 */
      sharedLedger = outcome.ledger;
      const committedNow = (outcome.costTotals ?? [])
        .filter((totals) => totals.currency === currency)
        .reduce((sum, totals) => sum + totals.committed, 0);
      remainingBudget = Math.max(0, input.budget.total - committedNow);
    } else {
      remainingBudget = Math.max(0, remainingBudget - cost);
    }
    previousOutcome = outcome;

    const reason = outcome.decision?.reasons.join("; ") || null;
    if (outcome.failure) {
      failureCandidates.push({
        task_id: input.spec.task_id,
        experiment_id: currentSpec.experiment_id,
        run_id: runId,
        failure: outcome.failure,
        decision: outcome.decision?.action ?? null,
        occurred_at: now().toISOString(),
      });
    }

    attempts.push({
      attempt,
      run_id: runId,
      experiment_id: currentSpec.experiment_id,
      state: outcome.state,
      decision: outcome.decision?.action ?? null,
      reason,
      failure: outcome.failure,
      cost,
      currency,
      manifest_ref: outcome.manifestRef?.uri ?? null,
      error_code: outcome.error?.code ?? null,
      resume_plan: null,
      resume_from: null,
      started_at: attemptStartedAt,
      finished_at: now().toISOString(),
    });

    /* 6.1 恢复决策：说明如何继续（恢复/重启），达到上限则转人工 */
    let resumeEscalation: string | null = null;
    if (input.checkpoints && input.resume) {
      const previousState: PreviousAttemptState | null =
        outcome.state === "unknown_execution"
          ? "unknown_execution"
          : outcome.decision?.action === "extend"
            ? "partial"
            : outcome.decision?.action === "stop" && outcome.failure?.category !== "resource"
              ? "failed"
              : null;
      if (previousState) {
        const plan = planResume({
          experiment_id: currentSpec.experiment_id,
          previous_attempt: attempt,
          previous_state: previousState,
          checkpoints: input.checkpoints,
          policy: {
            required: input.resume.required ?? true,
            max_resumes: input.resume.max_resumes,
            max_age_seconds: input.resume.max_age_seconds ?? null,
          },
          current_code_commit: attemptCode.commit,
          current_environment_hash: input.environment.lockfileHash,
          resume_count: resumesSoFar,
          now: now(),
        });
        const last = attempts[attempts.length - 1];
        last.resume_plan = plan.action === "none" ? null : `${plan.action}: ${plan.reason}`;
        last.resume_from = plan.from_checkpoint?.checkpoint_id ?? null;
        if (plan.action === "resume") resumesSoFar += 1;
        if (plan.action === "escalate") {
          resumeEscalation = plan.reason;
          findings.push({
            severity: "error",
            code: "E_RESUME_ESCALATE",
            message: `恢复决策要求人工处理: ${plan.reason}`,
          });
        }
      }
    }

    /* 7. 终态判断 */
    if (resumeEscalation) {
      return finish("escalated", resumeEscalation);
    }
    if (outcome.state === "needs_approval") {
      findings.push({
        severity: "warning",
        code: "E_LOOP_APPROVAL",
        message: "本轮需要人工审批，循环停止",
      });
      return finish("escalated", "需要人工审批");
    }
    if (outcome.state === "unknown_execution") {
      return finish("escalated", "执行状态未知，禁止自动重试");
    }
    if (isBlocked(outcome.state)) {
      return finish("blocked", `本轮状态 ${outcome.state}，不继续消耗预算`);
    }

    const action = outcome.decision?.action;
    if (action === "keep") {
      return finish("kept", `第 ${attempt} 轮保留`);
    }
    if (action === "escalate") {
      return finish("escalated", outcome.decision?.reasons.join("; ") || "决策要求升级");
    }
    if (action === "discard" || action === "extend") {
      consecutiveDiscards += 1;
      consecutiveFailures = 0;
      if (input.earlyStopAfterDiscards && consecutiveDiscards >= input.earlyStopAfterDiscards) {
        return finish(
          "stopped",
          `连续 ${consecutiveDiscards} 轮没有保留结果，触发早停`,
        );
      }
      continue;
    }
    if (action === "stop") {
      if (outcome.failure?.category === "resource") {
        return finish(
          "budget_exhausted",
          outcome.decision?.reasons.join("; ") || "成本超出本轮预算",
        );
      }
      consecutiveFailures += 1;
      if (consecutiveFailures >= maxConsecutiveFailures) {
        return finish(
          "consecutive_failures",
          `连续 ${consecutiveFailures} 轮失败，达到上限 ${maxConsecutiveFailures}`,
        );
      }
      continue;
    }

    findings.push({
      severity: "error",
      code: "E_LOOP_NO_DECISION",
      message: `第 ${attempt} 轮没有可判定的决策，停止循环`,
    });
    return finish("stopped", "本轮没有决策");
  }

  return finish("exhausted", `达到最大尝试次数 ${maxAttempts}`);
}
