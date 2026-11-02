/**
 * 假设质量门。
 *
 * 对应 docs/04 的假设质量门：
 * - 可证伪：必须写明能推翻它的实验结果。
 * - 有依据：来源（文献缺口、复现异常、失败模式、迁移）必须带证据引用。
 * - 有最小实验：有限预算且重复次数明确；少于 3 次重复只告警。
 * - 有预期效应与风险：缺失即不通过。
 */

import { compileExperiment } from "./experiment.ts";
import type {
  ArtifactKind,
  Baseline,
  ExperimentSpec,
  Finding,
  Guardrail,
  MetricDirection,
  OnUnknown,
  ResourceType,
  Variables,
} from "./experiment.ts";

export type HypothesisOriginType =
  | "literature_gap"
  | "reproduction_anomaly"
  | "failure_pattern"
  | "transfer";

export interface HypothesisRecord {
  hypothesis_id: string;
  statement: string;
  origin: {
    type: HypothesisOriginType;
    evidence: string[];
  };
  falsifiable_by: string;
  expected_effect?: string | null;
  minimal_test: {
    dataset?: string | null;
    metric?: string | null;
    budget?: string | null;
    repeats: number;
  };
  risks: string[];
  status: "proposed" | "validated" | "rejected" | "superseded";
  source_reproduction_id?: string | null;
  created_at: string;
  revision?: number;
}

export interface HypothesisCheckResult {
  ok: boolean;
  errors: Finding[];
  warnings: Finding[];
}

function finding(
  severity: "error" | "warning",
  code: string,
  message: string,
  path?: string,
): Finding {
  return { severity, code, message, path };
}

/**
 * 质量门检查。通过时假设才允许编译成 ExperimentSpec 进入实验阶段。
 */
export function checkHypothesis(hypothesis: HypothesisRecord): HypothesisCheckResult {
  const errors: Finding[] = [];
  const warnings: Finding[] = [];

  if (!hypothesis.hypothesis_id?.trim()) {
    errors.push(finding("error", "E_HYP_ID", "hypothesis_id 不能为空", "hypothesis_id"));
  }
  if (!hypothesis.statement?.trim()) {
    errors.push(finding("error", "E_HYP_STATEMENT", "statement 不能为空", "statement"));
  }
  if (!hypothesis.falsifiable_by?.trim()) {
    errors.push(
      finding("error", "E_HYP_FALSIFIABLE", "falsifiable_by 不能为空；不可证伪的假设不进入实验", "falsifiable_by"),
    );
  }
  if (!hypothesis.origin?.type) {
    errors.push(finding("error", "E_HYP_ORIGIN_TYPE", "origin.type 不能为空", "origin.type"));
  }
  if (!hypothesis.origin?.evidence?.length) {
    errors.push(
      finding("error", "E_HYP_ORIGIN_EVIDENCE", "origin.evidence 不能为空；假设必须带依据", "origin.evidence"),
    );
  }
  if (!hypothesis.minimal_test?.budget?.trim()) {
    errors.push(finding("error", "E_HYP_BUDGET", "minimal_test.budget 不能为空", "minimal_test.budget"));
  }
  const repeats = hypothesis.minimal_test?.repeats;
  if (!Number.isInteger(repeats) || repeats < 1) {
    errors.push(
      finding("error", "E_HYP_REPEATS", "minimal_test.repeats 必须是大于 0 的整数", "minimal_test.repeats"),
    );
  } else if (repeats < 3) {
    warnings.push(
      finding("warning", "W_HYP_REPEATS", "重复次数少于 3；正式结论要求至少 3 个种子", "minimal_test.repeats"),
    );
  }
  if (!hypothesis.risks?.length) {
    errors.push(finding("error", "E_HYP_RISKS", "risks 不能为空；假设必须声明失败原因", "risks"));
  }
  if (!hypothesis.expected_effect?.trim()) {
    warnings.push(
      finding("warning", "W_HYP_NO_EFFECT", "未写明预期效应", "expected_effect"),
    );
  }

  return { ok: errors.length === 0, errors, warnings };
}

/** 从复现结果草拟假设时自动填入的证据链接。 */
export interface ReproductionDraftLinks {
  /** 源复现报告 ID，必填。 */
  source_reproduction_id: string;
  /** 触发该假设的声明 ID；会生成 reproduction:<id>#<claim_id> 形式的引用。 */
  claim_ids?: string[];
  /** 触发该假设的差异类型原文，例如 "implementation"。 */
  difference_notes?: string[];
}

export interface HypothesisDraftInput extends ReproductionDraftLinks {
  hypothesis_id: string;
  statement: string;
  falsifiable_by: string;
  expected_effect?: string | null;
  minimal_test: HypothesisRecord["minimal_test"];
  risks: string[];
  created_at?: Date;
}

export interface HypothesisDraftResult {
  ok: boolean;
  record?: HypothesisRecord;
  errors: Finding[];
  warnings: Finding[];
}

/**
 * 从一次复现草拟假设候选（origin.type 固定 reproduction_anomaly）。
 *
 * 内容（statement、可证伪方式、风险）仍由研究侧输入；
 * 本函数只自动化证据链接：reproduction:<id> 与逐声明引用，然后过质量门。
 */
export function draftHypothesisFromReproduction(
  input: HypothesisDraftInput,
): HypothesisDraftResult {
  const evidence = [
    `reproduction:${input.source_reproduction_id}`,
    ...(input.claim_ids ?? []).map((claimId) => `reproduction:${input.source_reproduction_id}#${claimId}`),
    ...(input.difference_notes ?? []),
  ];
  const record: HypothesisRecord = {
    hypothesis_id: input.hypothesis_id,
    statement: input.statement,
    origin: { type: "reproduction_anomaly", evidence },
    falsifiable_by: input.falsifiable_by,
    expected_effect: input.expected_effect ?? null,
    minimal_test: input.minimal_test,
    risks: input.risks,
    status: "proposed",
    source_reproduction_id: input.source_reproduction_id,
    created_at: (input.created_at ?? new Date()).toISOString(),
    revision: 1,
  };
  const checked = checkHypothesis(record);
  return { ...checked, record: checked.ok ? record : undefined };
}

/**
 * 假设 → 实验规格编译（docs/04 §6.1）。
 *
 * 输入必须先通过 `checkHypothesis()` 质量门；输出交给
 * `compileExperiment()` 做完整规格校验。决策文案由假设派生，
 * 使规格中的保留/撤销规则可追溯到假设本身。
 */

import type {
  ArtifactKind,
  Baseline,
  DataSeed,
  ExperimentSpec,
  Finding,
  Guardrail,
  MetricDirection,
  OnUnknown,
  ResourceType,
  Variables,
} from "./experiment.ts";

export interface HypothesisSpecMetric {
  name: string;
  direction: MetricDirection;
  minimum_observable_effect: number;
}

export interface HypothesisSpecResources {
  type: ResourceType;
  count?: number;
  accelerator?: string | null;
  max_wall_clock_seconds: number;
  max_cost: number;
  currency: string;
  checkpoint_required?: boolean;
  checkpoint_interval_seconds?: number | null;
}

export interface HypothesisSpecInput {
  hypothesis: HypothesisRecord;
  experiment_id: string;
  task_id: string;
  /** 已复现、带指标值的基线；未复现会被 compileExperiment 拒绝。 */
  baseline: Baseline;
  primary: HypothesisSpecMetric;
  guardrails?: Guardrail[];
  variables: Variables;
  resources: HypothesisSpecResources;
  seeds?: number[];
  data?: ExperimentSpec["data"];
  extraOptionalArtifacts?: ArtifactKind[];
  maxAttempts?: number;
  maxConsecutiveFailures?: number;
  deadlineAt?: string | null;
  onUnknown?: OnUnknown;
}

export interface HypothesisSpecResult {
  ok: boolean;
  spec?: ExperimentSpec;
  findings: Finding[];
}

export function compileHypothesisSpec(input: HypothesisSpecInput): HypothesisSpecResult {
  const findings: Finding[] = [];
  const gate = checkHypothesis(input.hypothesis);
  const gateErrors = gate.errors;
  findings.push(...gate.warnings);
  if (!gate.ok) {
    findings.push(...gateErrors);
    return { ok: false, findings };
  }

  const optional: ArtifactKind[] = ["report", ...(input.extraOptionalArtifacts ?? [])];
  const repeats = Math.max(1, input.hypothesis.minimal_test.repeats);
  const statement = input.hypothesis.expected_effect
    ? `${input.hypothesis.expected_effect}（假设 ${input.hypothesis.hypothesis_id}）`
    : input.hypothesis.statement;

  const spec: ExperimentSpec = {
    experiment_id: input.experiment_id,
    task_id: input.task_id,
    hypothesis: {
      statement: input.hypothesis.statement,
      origin: input.hypothesis.origin.type,
      evidence_refs: input.hypothesis.origin.evidence,
      falsifiable_by: input.hypothesis.falsifiable_by,
      expected_effect: input.hypothesis.expected_effect ?? null,
    },
    baseline: input.baseline,
    variables: input.variables,
    data: input.data,
    metrics: {
      primary: input.primary.name,
      direction: input.primary.direction,
      minimum_observable_effect: input.primary.minimum_observable_effect,
      guardrails: input.guardrails ?? [],
      statistic: "mean",
      repeats,
      seeds: input.seeds ?? [],
    },
    resources: input.resources,
    stopping: {
      max_attempts: Math.max(1, input.maxAttempts ?? 3),
      max_consecutive_failures: Math.max(1, input.maxConsecutiveFailures ?? 1),
      deadline_at: input.deadlineAt ?? null,
      early_stop: null,
    },
    decision: {
      keep_if: `假设成立：${statement}`,
      discard_if: `假设不成立：${input.hypothesis.falsifiable_by}`,
      on_unknown: input.onUnknown ?? "escalate",
    },
    artifacts: {
      required: ["code_hash", "env_lock", "raw_metrics", "manifest"],
      optional,
    },
  };

  const compiled = compileExperiment(spec);
  findings.push(...compiled.warnings, ...compiled.errors);
  if (!compiled.ok) return { ok: false, findings };

  return { ok: true, spec, findings };
}
