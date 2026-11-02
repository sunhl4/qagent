/**
 * 复现难度评估、声明比较与复现报告编译。
 *
 * 纯函数，不做 IO。运行与产物由流水线通过端口完成；
 * 本模块决定：声明是否落在容差内、结论如何判定、哪些字段缺失会阻断结论。
 *
 * 三层验证对应 docs/04 的语义/数值/可推广性：
 * - 语义复现：semantic_checks 必须存在；判定成功时必须全部通过。
 * - 数值复现：每个 claim 需要种子值，均值与原文差值落在 tolerance 内。
 * - 可推广性：判定成功时至少一个独立设置方向一致。
 * - 执行状态未知：结论只能是 not_attempted，转人工。
 */

import type { Finding } from "./experiment.ts";

export type CodeAvailability = "official" | "third_party" | "none";
export type DataAvailability = "public" | "partial" | "private";
export type HyperparameterCompleteness = "complete" | "partial" | "missing";
export type ComputeRequirement = "single_gpu" | "multi_gpu" | "cluster";
export type DependencyRisk = "standard" | "medium" | "high";
export type EvaluationClarity = "script_available" | "described" | "text_only";
export type DifficultyLevel = "low" | "medium" | "high";

export interface DifficultyInput {
  code_available: CodeAvailability;
  data_available: DataAvailability;
  hyperparameters_complete: HyperparameterCompleteness;
  compute_requirement: ComputeRequirement;
  dependency_risk: DependencyRisk;
  evaluation_clarity: EvaluationClarity;
}

export interface DifficultyScore {
  dimension: string;
  score: number;
}

export interface DifficultyAssessment {
  overall: DifficultyLevel;
  total: number;
  scores: DifficultyScore[];
}

const THREE_LEVEL_SCORES: Record<string, number> = {
  official: 0,
  third_party: 1,
  none: 2,
  public: 0,
  partial: 1,
  private: 2,
  complete: 0,
  missing: 2,
  single_gpu: 0,
  multi_gpu: 1,
  cluster: 2,
  standard: 0,
  medium: 1,
  high: 2,
  script_available: 0,
  described: 1,
  text_only: 2,
};

/**
 * 复现难度评分：六个维度各 0–2 分，总分 ≤4 低、≤9 中、>9 高。
 */
export function assessDifficulty(input: DifficultyInput): DifficultyAssessment {
  const scores: DifficultyScore[] = [
    { dimension: "code_available", score: THREE_LEVEL_SCORES[input.code_available] },
    { dimension: "data_available", score: THREE_LEVEL_SCORES[input.data_available] },
    { dimension: "hyperparameters_complete", score: THREE_LEVEL_SCORES[input.hyperparameters_complete] },
    { dimension: "compute_requirement", score: THREE_LEVEL_SCORES[input.compute_requirement] },
    { dimension: "dependency_risk", score: THREE_LEVEL_SCORES[input.dependency_risk] },
    { dimension: "evaluation_clarity", score: THREE_LEVEL_SCORES[input.evaluation_clarity] },
  ];
  const total = scores.reduce((sum, item) => sum + item.score, 0);
  const overall: DifficultyLevel = total <= 4 ? "low" : total <= 9 ? "medium" : "high";
  return { overall, total, scores };
}

export interface ClaimSpecInput {
  claim_id: string;
  claim: string;
  metric_name: string;
  original_value: number;
  tolerance: number;
}

export interface ClaimEvaluation {
  mean: number | null;
  std: number | null;
  count: number;
  within_tolerance: boolean | null;
}

/**
 * 声明的数值比较：种子值均值与原文差值是否落在容差内。
 * 没有任何种子值时三项均为 null，报告不得据此判定成功。
 */
export function evaluateClaim(
  claim: { original_value: number; tolerance: number },
  values: readonly number[],
): ClaimEvaluation {
  if (values.length === 0) {
    return { mean: null, std: null, count: 0, within_tolerance: null };
  }
  const mean = values.reduce((sum, value) => sum + value, 0) / values.length;
  const variance =
    values.reduce((sum, value) => sum + (value - mean) * (value - mean), 0) / values.length;
  const std = Math.sqrt(variance);
  return {
    mean,
    std,
    count: values.length,
    within_tolerance: Math.abs(mean - claim.original_value) <= claim.tolerance,
  };
}

export type RunStatus = "succeeded" | "failed" | "unknown" | "cancelled" | "skipped";

export interface RunOutcome {
  run_id: string;
  name: string;
  command?: string | null;
  seeds: number[];
  status: RunStatus;
  metric_name?: string | null;
  values?: number[];
  cost?: number | null;
  currency?: string | null;
  lease_ids?: string[];
}

export interface SemanticCheckInput {
  item: string;
  passed: boolean;
  note?: string | null;
}

export interface GeneralityCheckInput {
  setting: string;
  direction_consistent: boolean;
  note?: string | null;
}

export type DifferenceKind =
  | "data"
  | "implementation"
  | "evaluation"
  | "hardware"
  | "randomness"
  | "other";

export interface DifferenceEntry {
  kind: DifferenceKind;
  description: string;
  evidence?: string | null;
}

export interface ReproductionReportInput {
  reproduction_id: string;
  task_id: string;
  paper: {
    title?: string | null;
    doi?: string | null;
    arxiv_id?: string | null;
    code_url?: string | null;
  };
  difficulty: DifficultyInput;
  environment: {
    container?: string | null;
    python?: string | null;
    framework?: string | null;
    cuda?: string | null;
    lockfile_hash?: string | null;
    hardware?: string | null;
  };
  data: {
    source: string;
    hash?: string | null;
    split?: string | null;
    preprocessing_notes?: string[];
  };
  runs: RunOutcome[];
  claims: ClaimSpecInput[];
  semantic_checks: SemanticCheckInput[];
  generality_checks: GeneralityCheckInput[];
  differences: DifferenceEntry[];
  reusable_assets?: string[];
  open_questions?: string[];
  created_at?: Date;
}

export type ReproductionConclusion = "succeeded" | "partial" | "failed" | "not_attempted";

export interface ReproductionReport {
  reproduction_id: string;
  task_id: string;
  paper: ReproductionReportInput["paper"];
  difficulty: DifficultyInput & {
    overall: DifficultyLevel;
    total: number;
    scores: DifficultyScore[];
  };
  environment: ReproductionReportInput["environment"];
  data: ReproductionReportInput["data"];
  runs: RunOutcome[];
  claims_to_verify: (ClaimSpecInput & {
    mean: number | null;
    std: number | null;
    count: number;
    within_tolerance: boolean | null;
  })[];
  semantic_checks: SemanticCheckInput[];
  generality_checks: GeneralityCheckInput[];
  differences: DifferenceEntry[];
  conclusion: ReproductionConclusion;
  reusable_assets: string[];
  open_questions: string[];
  created_at: string;
  revision: number;
}

export interface CompileReproductionResult {
  ok: boolean;
  report?: ReproductionReport;
  errors: Finding[];
  warnings: Finding[];
  conclusion?: ReproductionConclusion;
}

const LOCKFILE_PATTERN = /^[a-f0-9]{64}$/;

function finding(
  severity: "error" | "warning",
  code: string,
  message: string,
  path?: string,
): Finding {
  return { severity, code, message, path };
}

/**
 * 编译复现报告。
 *
 * 规则：
 * - 执行状态未知 → 结论 not_attempted，其余字段照常保留。
 * - 结论 succeeded 需要：语义检查全部通过、每个 claim 都有种子值且全部在容差内、
 *   至少一个可推广性设置方向一致、环境锁与硬件已记录。
 * - 结论 partial/failed 必须给出至少一条差异归因，否则编译失败。
 * - 全部运行无种子值时结论为 failed。
 */
export function buildReproductionReport(input: ReproductionReportInput): CompileReproductionResult {
  const errors: Finding[] = [];
  const warnings: Finding[] = [];
  const at = input.created_at ?? new Date();

  if (!input.reproduction_id?.trim()) {
    errors.push(finding("error", "E_REPRO_ID", "reproduction_id 不能为空", "reproduction_id"));
  }
  if (!input.task_id?.trim()) {
    errors.push(finding("error", "E_REPRO_TASK", "task_id 不能为空", "task_id"));
  }
  if (!input.claims?.length) {
    errors.push(finding("error", "E_REPRO_NO_CLAIMS", "缺少待验证声明", "claims"));
  }
  if (!input.runs?.length) {
    errors.push(finding("error", "E_REPRO_NO_RUNS", "缺少运行记录", "runs"));
  }
  if (!input.semantic_checks?.length) {
    warnings.push(
      finding("warning", "W_REPRO_NO_SEMANTIC", "没有语义复现检查项", "semantic_checks"),
    );
  }
  if (!input.generality_checks?.length) {
    warnings.push(
      finding("warning", "W_REPRO_NO_GENERALITY", "没有可推广性检查项", "generality_checks"),
    );
  }
  if (!input.data?.hash) {
    warnings.push(finding("warning", "W_REPRO_DATA_HASH", "缺少数据版本哈希", "data.hash"));
  }
  if (input.environment?.lockfile_hash && !LOCKFILE_PATTERN.test(input.environment.lockfile_hash)) {
    warnings.push(finding("warning", "W_REPRO_LOCK_FORMAT", "lockfile_hash 不是 64 位十六进制", "environment.lockfile_hash"));
  }

  const evaluationById = new Map<string, ClaimEvaluation>();
  for (const claim of input.claims ?? []) {
    const values = (input.runs ?? [])
      .filter((run) => run.metric_name === claim.metric_name && run.status === "succeeded")
      .flatMap((run) => run.values ?? []);
    evaluationById.set(claim.claim_id, evaluateClaim(claim, values));
  }
  const claimsToVerify = (input.claims ?? []).map((claim) => {
    const evaluation = evaluationById.get(claim.claim_id)!;
    return {
      claim_id: claim.claim_id,
      claim: claim.claim,
      metric_name: claim.metric_name,
      original_value: claim.original_value,
      tolerance: claim.tolerance,
      mean: evaluation.mean,
      std: evaluation.std,
      count: evaluation.count,
      within_tolerance: evaluation.within_tolerance,
    };
  });

  const anyUnknown = (input.runs ?? []).some((run) => run.status === "unknown");
  const anyValues = claimsToVerify.some((claim) => claim.count > 0);
  const semanticOk = (input.semantic_checks ?? []).length > 0 &&
    input.semantic_checks.every((check) => check.passed);
  const generalityOk = (input.generality_checks ?? []).some((check) => check.direction_consistent);
  const allWithin = claimsToVerify.length > 0 &&
    claimsToVerify.every((claim) => claim.count > 0 && claim.within_tolerance === true);
  const numericReady = anyValues && allWithin;

  let conclusion: ReproductionConclusion;
  if (anyUnknown) {
    conclusion = "not_attempted";
    warnings.push(
      finding(
        "warning",
        "W_REPRO_UNKNOWN",
        "存在执行状态未知的运行；结论记为 not_attempted，转人工对账",
      ),
    );
  } else if (!anyValues) {
    conclusion = "failed";
  } else if (semanticOk && generalityOk && numericReady) {
    conclusion = "succeeded";
  } else {
    conclusion = "partial";
  }

  if (!anyUnknown && numericReady && semanticOk && !generalityOk) {
    errors.push(
      finding(
        "error",
        "E_REPRO_GENERALITY",
        "数值与语义全部达标但缺少可推广性验证；补充后再判定成功",
        "generality_checks",
      ),
    );
  }
  if (conclusion === "succeeded") {
    if (!input.environment?.lockfile_hash) {
      errors.push(
        finding("error", "E_REPRO_ENV_LOCK", "判定成功需要环境锁哈希", "environment.lockfile_hash"),
      );
    }
    if (!input.environment?.hardware) {
      errors.push(
        finding("error", "E_REPRO_ENV_HARDWARE", "判定成功需要记录硬件型号", "environment.hardware"),
      );
    }
  }
  if ((conclusion === "partial" || conclusion === "failed") && !input.differences?.length) {
    errors.push(
      finding(
        "error",
        "E_REPRO_NO_DIFFERENCE",
        "partial/failed 结论必须提供差异归因",
        "differences",
      ),
    );
  }
  const beyondTolerance = claimsToVerify.filter(
    (claim) => claim.within_tolerance === false,
  );
  if (beyondTolerance.length > 0 && !input.differences?.length) {
    errors.push(
      finding(
        "error",
        "E_REPRO_DIFFERENCE_REQUIRED",
        `有声明超出容差（${beyondTolerance.map((claim) => claim.claim_id).join(", ")}），必须给出差异归因`,
      ),
    );
  }

  const ok = errors.length === 0;
  const result: CompileReproductionResult = { ok, errors, warnings, conclusion };
  if (ok) {
    result.report = {
      reproduction_id: input.reproduction_id,
      task_id: input.task_id,
      paper: input.paper,
      difficulty: {
        ...input.difficulty,
        ...assessDifficulty(input.difficulty),
      },
      environment: input.environment,
      data: input.data,
      runs: input.runs,
      claims_to_verify: claimsToVerify,
      semantic_checks: input.semantic_checks,
      generality_checks: input.generality_checks,
      differences: input.differences,
      conclusion,
      reusable_assets: input.reusable_assets ?? [],
      open_questions: input.open_questions ?? [],
      created_at: at.toISOString(),
      revision: 1,
    };
  }
  return result;
}
