/**
 * 复现流水线：把复现计划接到 ComputePort。
 *
 * 每个种子是一次独立提交，幂等键 = reproduction_id:run:seed。
 * - 每个资源申请都走 acquireLease（先预留、后提交）。
 * - 执行状态未知立即停止：保留预留、不释放结算、不重新提交，转人工。
 * - 预算耗尽后剩余种子跳过，失败与跳过都保留在报告里。
 * - 报告由领域编译函数生成；全部测试桩环境即可验证。
 */

import type { ComputePort, ResourceRequest } from "../../../contracts/src/index.ts";
import { emptyCostLedger } from "../../domain/src/index.ts";
import type {
  CostLedger,
  DifferenceEntry,
  Finding,
  GeneralityCheckInput,
  SemanticCheckInput,
  RunOutcome as DomainRunOutcome,
} from "../../domain/src/index.ts";
import type {
  ClaimSpecInput,
  DifficultyInput,
  ReproductionReport,
  ReproductionReportInput,
  RunStatus,
} from "../../domain/src/index.ts";
import { buildReproductionReport } from "../../domain/src/index.ts";
import { acquireLease, releaseLease } from "./lease.ts";

export type { ClaimSpecInput, DifficultyInput, ReproductionReport };

export interface ReproductionRunSpec {
  name: string;
  kind: "cpu" | "gpu";
  wall_clock_seconds: number;
  max_cost: number;
  command?: string | null;
  seeds: number[];
  metric_name: string;
}

export interface ReproductionJobInput {
  reproduction_id: string;
  task_id: string;
  tenant_id: string;
  project_id?: string | null;
  data_residency?: string | null;
  budget: { limit: number; currency: string };
  runs: ReproductionRunSpec[];
  claims: ClaimSpecInput[];
  paper: ReproductionReportInput["paper"];
  difficulty: DifficultyInput;
  environment: ReproductionReportInput["environment"];
  data: ReproductionReportInput["data"];
  semantic_checks: SemanticCheckInput[];
  generality_checks: GeneralityCheckInput[];
  differences?: DifferenceEntry[];
  reusable_assets?: string[];
  open_questions?: string[];
  max_polls?: number;
  ttl_seconds?: number;
  ledger?: CostLedger;
}

export interface SeedResult {
  seed: number;
  status: RunStatus;
  value: number | null;
  cost: number | null;
  lease_id: string | null;
}

export interface ReproductionRunResult {
  ok: boolean;
  report?: ReproductionReport;
  ledger: CostLedger;
  runs: DomainRunOutcome[];
  findings: Finding[];
  error?: { code: string; message: string; retryable: boolean };
}

function finding(
  severity: "error" | "warning",
  code: string,
  message: string,
): Finding {
  return { severity, code, message };
}

const TERMINAL_HANDLE_STATES = new Set(["succeeded", "failed", "cancelled"]);

/**
 * 执行一个复现计划并生成报告。
 *
 * 未知执行会在第一次出现时停止全部后续种子与运行。
 */
export async function runReproduction(
  input: ReproductionJobInput,
  deps: { compute: ComputePort; now?: () => Date },
): Promise<ReproductionRunResult> {
  const now = deps.now ?? (() => new Date());
  const findings: Finding[] = [];
  let ledger = input.ledger ?? emptyCostLedger();
  const seedResultsByRun: SeedResult[][] = [];
  let unknownHit = false;
  let budgetExhausted = false;
  let budgetNotified = false;

  for (const run of input.runs) {
    const seedResults: SeedResult[] = [];
    for (const seed of run.seeds) {
      if (stopped(unknownHit)) {
        seedResults.push({ seed, status: "skipped", value: null, cost: null, lease_id: null });
        continue;
      }
      if (budgetExhausted) {
        if (!budgetNotified) {
          findings.push(
            finding("warning", "W_REPRO_BUDGET", `剩余预算不足，后的种子与运行跳过（首个跳过: ${run.name} seed ${seed}）`),
          );
          budgetNotified = true;
        }
        seedResults.push({ seed, status: "skipped", value: null, cost: null, lease_id: null });
        continue;
      }

      const idempotencyKey = `${input.reproduction_id}:${run.name}:seed-${seed}`;
      const request: ResourceRequest = {
        idempotencyKey,
        requestId: `REQ-${input.reproduction_id}-${run.name}-s${seed}`,
        tenantId: input.tenant_id,
        ...(input.project_id ? { projectId: input.project_id } : {}),
        taskId: input.task_id,
        kind: run.kind,
        count: 1,
        wallClockSeconds: run.wall_clock_seconds,
        maxCost: run.max_cost,
        currency: input.budget.currency,
        ...(input.data_residency ? { dataResidency: input.data_residency } : {}),
        checkpoint: { required: true, intervalSeconds: 60 },
      };

      const acquire = await acquireLease(
        {
          request,
          holder: { type: "attempt", id: `${input.reproduction_id}-${run.name}-s${seed}` },
          ttlSeconds: input.ttl_seconds ?? 3600,
          budget: input.budget,
          ledger,
        },
        { compute: deps.compute, now },
      );
      if (!acquire.ok) {
        ledger = acquire.ledger;
        findings.push(...acquire.findings);
        if (acquire.error?.code === "E_BUDGET_EXCEEDED") {
          budgetExhausted = true;
          seedResults.push({ seed, status: "skipped", value: null, cost: null, lease_id: null });
          continue;
        }
        if (acquire.error?.code === "UNKNOWN_EXECUTION") {
          unknownHit = true;
          findings.push(
            finding(
              "error",
              "E_REPRO_UNKNOWN",
              `提交结果未知（${run.name} seed ${seed}）；预留已保留，转人工对账，禁止自动重试`,
            ),
          );
          seedResults.push({ seed, status: "unknown", value: null, cost: null, lease_id: null });
          continue;
        }
        findings.push(
          finding(
            "error",
            "E_REPRO_SUBMIT",
            `运行 ${run.name} seed ${seed} 资源申请失败: ${acquire.error?.code ?? ""} ${acquire.error?.message ?? ""}`,
          ),
        );
        seedResults.push({ seed, status: "failed", value: null, cost: null, lease_id: null });
        continue;
      }

      const lease = acquire.lease!;
      ledger = acquire.ledger;
      let handle = acquire.handle!;
      let pollState: "running" | "terminal" | "unknown" = "running";
      const maxPolls = input.max_polls ?? 30;
      for (let poll = 0; poll < maxPolls; poll += 1) {
        const status = await deps.compute.status(handle.handleId);
        if (!status.ok) {
          findings.push(
            finding(
              "error",
              "E_REPRO_STATUS",
              `状态查询失败（${run.name} seed ${seed}）: ${status.error.code} ${status.error.message}`,
            ),
          );
          handle = { ...handle, state: "failed" as const };
          pollState = "terminal";
          break;
        }
        handle = status.value;
        if (handle.state === "unknown") {
          pollState = "unknown";
          break;
        }
        if (TERMINAL_HANDLE_STATES.has(handle.state)) {
          pollState = "terminal";
          break;
        }
      }
      if (pollState === "running") {
        await deps.compute.cancel(handle.handleId, "reproduction_poll_limit");
        handle = { ...handle, state: "cancelled" as const };
        findings.push(
          finding("warning", "W_REPRO_POLL_LIMIT", `轮询超过上限，作业已取消: ${run.name} seed ${seed}`),
        );
        pollState = "terminal";
      }
      if (pollState === "unknown") {
        unknownHit = true;
        findings.push(
          finding(
            "error",
            "E_REPRO_UNKNOWN",
            `运行 ${run.name} seed ${seed} 执行状态未知；预留已保留，转人工对账，禁止释放结算与重新提交`,
          ),
        );
        seedResults.push({
          seed,
          status: "unknown",
          value: null,
          cost: null,
          lease_id: lease.lease_id,
        });
        continue;
      }

      if (!isLeaseTerminal(lease.state)) {
        const released = await releaseLease(
          {
            lease,
            ledger,
            taskId: input.task_id,
            reason: `reproduction:${handle.state}`,
          },
          { compute: deps.compute, now },
        );
        ledger = released.ledger;
        findings.push(...released.findings);
        if (!released.ok && released.error?.code === "UNKNOWN_EXECUTION") {
          unknownHit = true;
          break;
        }
      }

      const metricValue = (handle.metrics ?? []).find(
        (metric) => metric.name === run.metric_name,
      )?.value;
      const seedStatus: RunStatus =
        handle.state === "succeeded"
          ? "succeeded"
          : handle.state === "failed"
            ? "failed"
            : "cancelled";
      seedResults.push({
        seed,
        status: seedStatus,
        value: typeof metricValue === "number" ? metricValue : null,
        cost: handle.usage?.cost ?? null,
        lease_id: lease.lease_id,
      });
    }
    seedResultsByRun.push(seedResults);
  }

  const runsOut: DomainRunOutcome[] = input.runs.map((run, index) => {
    const seeds = seedResultsByRun[index];
    const leveraged = seeds.filter((item) => item.status !== "skipped");
    const values = seeds
      .filter((item) => item.status === "succeeded" && item.value !== null)
      .map((item) => item.value!);
    const status: RunStatus = leveraged.some((item) => item.status === "unknown")
      ? "unknown"
      : leveraged.some((item) => item.status === "succeeded")
        ? "succeeded"
        : leveraged.some((item) => item.status === "failed")
          ? "failed"
          : leveraged.some((item) => item.status === "cancelled")
            ? "cancelled"
            : "skipped";
    const costs = seeds
      .map((item) => item.cost)
      .filter((cost): cost is number => typeof cost === "number");
    const leaseIds = seeds
      .map((item) => item.lease_id)
      .filter((leaseId): leaseId is string => Boolean(leaseId));
    return {
      run_id: `${input.reproduction_id}-${run.name}`,
      name: run.name,
      command: run.command ?? null,
      seeds: run.seeds,
      status,
      metric_name: run.metric_name,
      values,
      cost: costs.length > 0 ? costs.reduce((sum, cost) => sum + cost, 0) : null,
      currency: costs.length > 0 ? input.budget.currency : null,
      lease_ids: leaseIds,
    };
  });

  const differences: DifferenceEntry[] = [...(input.differences ?? [])];
  const failedRuns = runsOut.filter(
    (run) => run.status === "failed" || run.status === "cancelled",
  );
  if (failedRuns.length > 0) {
    differences.push({
      kind: "other",
      description: `失败的运行: ${failedRuns.map((run) => run.name).join(", ")}`,
      evidence: null,
    });
  }
  const failedSeeds = runsOut.filter(
    (run) => run.status === "succeeded" && (run.values?.length ?? 0) < run.seeds.length,
  );
  if (failedSeeds.length > 0) {
    findings.push(
      finding(
        "warning",
        "W_REPRO_PARTIAL_SEEDS",
        `部分种子缺值: ${failedSeeds.map((run) => run.name).join(", ")}`,
      ),
    );
  }

  const compiled = buildReproductionReport({
    reproduction_id: input.reproduction_id,
    task_id: input.task_id,
    paper: input.paper,
    difficulty: input.difficulty,
    environment: input.environment,
    data: input.data,
    runs: runsOut,
    claims: input.claims,
    semantic_checks: input.semantic_checks,
    generality_checks: input.generality_checks,
    differences,
    reusable_assets: input.reusable_assets,
    open_questions: input.open_questions,
    created_at: now(),
  });
  findings.push(...compiled.errors, ...compiled.warnings);

  return {
    ok: compiled.ok && !unknownHit,
    report: compiled.report,
    ledger,
    runs: runsOut,
    findings,
    error: unknownHit
      ? {
          code: "UNKNOWN_EXECUTION",
          message: "复现执行状态未知；预留已保留，转人工对账",
          retryable: false,
        }
      : undefined,
  };
}

function stopped(unknownHit: boolean): boolean {
  return unknownHit;
}

function isLeaseTerminal(state: string): boolean {
  return ["RELEASED", "REVOKED", "EXPIRED", "FAILED"].includes(state);
}
