/**
 * 领域对象：实验规格。
 *
 * 与 schemas/experiment-spec.schema.json 对应。schema 是跨工程/跨语言契约，
 * 本文件是 TypeScript 侧的编译与校验实现。
 */

export type MetricDirection = "minimize" | "maximize";
export type ResourceType = "cpu" | "gpu" | "hpc" | "qpu" | "cloud" | "browser";
export type OnUnknown = "escalate" | "discard";
export type ArtifactKind =
  | "code_hash"
  | "env_lock"
  | "container_digest"
  | "config"
  | "raw_metrics"
  | "logs"
  | "checkpoint"
  | "manifest"
  | "report";

export interface Hypothesis {
  statement: string;
  origin?: string;
  evidence_refs?: string[];
  falsifiable_by: string;
  expected_effect?: string | null;
}

export interface Baseline {
  name: string;
  source: string;
  run_id?: string | null;
  reproduced: boolean;
  metric_value?: number | null;
  uncertainty?: number | null;
}

export interface Variables {
  changed: string[];
  controlled: string[];
  allowed_paths?: string[];
  forbidden_paths?: string[];
}

export interface Guardrail {
  name: string;
  max_degradation: number;
}

export interface Metrics {
  primary: string;
  direction: MetricDirection;
  minimum_observable_effect?: number | null;
  guardrails?: Guardrail[];
  statistic?: "mean" | "median" | "confidence_interval";
  repeats?: number;
  seeds?: number[];
}

export interface Resources {
  type: ResourceType;
  count?: number;
  accelerator?: string | null;
  max_wall_clock_seconds: number;
  max_cost: number;
  currency: string;
  checkpoint_required?: boolean;
  checkpoint_interval_seconds?: number | null;
}

export interface Stopping {
  max_attempts: number;
  max_consecutive_failures: number;
  deadline_at?: string | null;
  early_stop?: string | null;
}

export interface DecisionRules {
  keep_if: string;
  discard_if: string;
  on_unknown?: OnUnknown;
}

export interface Approval {
  required?: boolean;
  reasons?: string[];
  approved_by?: string | null;
}

export interface Artifacts {
  required: ArtifactKind[];
  optional?: string[];
}

export interface ExperimentSpec {
  experiment_id: string;
  task_id: string;
  hypothesis: Hypothesis;
  baseline: Baseline;
  variables: Variables;
  data?: {
    dataset_ref?: string | null;
    dataset_hash?: string | null;
    split?: string | null;
    leakage_check?: string | null;
  };
  metrics: Metrics;
  resources: Resources;
  stopping: Stopping;
  decision: DecisionRules;
  approval?: Approval;
  artifacts: Artifacts;
  created_at?: string;
  revision?: number;
}

export type FindingSeverity = "error" | "warning";

export interface Finding {
  severity: FindingSeverity;
  code: string;
  message: string;
  path?: string;
}

export interface CompileResult {
  ok: boolean;
  errors: Finding[];
  warnings: Finding[];
  /** 需要审批的原因；空数组表示无需审批。 */
  approvalReasons: string[];
}

const REQUIRED_ARTIFACTS: ArtifactKind[] = ["code_hash", "env_lock", "raw_metrics", "manifest"];

function isNonEmpty(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

function pathMatches(pattern: string, path: string): boolean {
  if (pattern === path) return true;
  if (pattern.endsWith("/**")) {
    const prefix = pattern.slice(0, -3);
    return path === prefix || path.startsWith(`${prefix}/`);
  }
  if (pattern.endsWith("/*")) {
    const prefix = pattern.slice(0, -2);
    if (!path.startsWith(`${prefix}/`)) return false;
    return !path.slice(prefix.length + 1).includes("/");
  }
  return false;
}

/**
 * 编译并校验实验规格。
 *
 * 设计原则：宁可拒绝，也不要让一个无法判定的实验进入昂贵资源。
 */
export function compileExperiment(spec: ExperimentSpec): CompileResult {
  const errors: Finding[] = [];
  const warnings: Finding[] = [];
  const approvalReasons: string[] = [];

  const error = (code: string, message: string, path?: string): void => {
    errors.push({ severity: "error", code, message, path });
  };
  const warn = (code: string, message: string, path?: string): void => {
    warnings.push({ severity: "warning", code, message, path });
  };

  if (!isNonEmpty(spec.experiment_id)) error("E_ID", "experiment_id 缺失", "experiment_id");
  if (!isNonEmpty(spec.task_id)) error("E_TASK", "task_id 缺失", "task_id");

  /* hypothesis */
  if (!isNonEmpty(spec.hypothesis?.statement)) {
    error("E_HYPOTHESIS", "假设陈述缺失", "hypothesis.statement");
  }
  if (!isNonEmpty(spec.hypothesis?.falsifiable_by)) {
    error("E_FALSIFIABLE", "缺少可证伪条件", "hypothesis.falsifiable_by");
  }
  if (!spec.hypothesis?.evidence_refs || spec.hypothesis.evidence_refs.length === 0) {
    warn("W_NO_EVIDENCE", "假设没有引用任何证据来源", "hypothesis.evidence_refs");
  }

  /* baseline */
  if (!spec.baseline?.reproduced) {
    error("E_BASELINE_NOT_REPRODUCED", "基线未复现，不允许进入实验", "baseline.reproduced");
  }
  if (spec.baseline?.metric_value === null || spec.baseline?.metric_value === undefined) {
    error("E_BASELINE_METRIC", "基线缺少指标值，无法判定改进", "baseline.metric_value");
  }

  /* variables */
  if (!spec.variables?.changed || spec.variables.changed.length === 0) {
    error("E_NO_VARIABLE", "没有声明被改变的变量", "variables.changed");
  }
  if (!spec.variables?.controlled || spec.variables.controlled.length === 0) {
    warn("W_NO_CONTROL", "没有声明受控变量，结论可能不可比", "variables.controlled");
  }

  const changed = spec.variables?.changed ?? [];
  const forbidden = spec.variables?.forbidden_paths ?? [];
  const allowed = spec.variables?.allowed_paths ?? [];

  for (const item of changed) {
    for (const blocked of forbidden) {
      if (pathMatches(blocked, item) || item === blocked) {
        error("E_FORBIDDEN_PATH", `变更命中禁止路径: ${blocked}`, "variables.changed");
      }
    }
  }
  if (allowed.length > 0) {
    for (const item of changed) {
      const covered = allowed.some((pattern) => pathMatches(pattern, item));
      if (!covered) {
        error("E_OUT_OF_SCOPE", `变更不在允许路径内: ${item}`, "variables.changed");
      }
    }
  }

  /* metrics */
  if (!isNonEmpty(spec.metrics?.primary)) {
    error("E_PRIMARY_METRIC", "主指标缺失", "metrics.primary");
  }
  if (spec.metrics?.direction !== "minimize" && spec.metrics?.direction !== "maximize") {
    error("E_DIRECTION", "指标方向非法", "metrics.direction");
  }
  if (
    spec.metrics?.minimum_observable_effect === null ||
    spec.metrics?.minimum_observable_effect === undefined
  ) {
    error("E_MOE", "缺少最小可观测效应，无法判定是否值得保留", "metrics.minimum_observable_effect");
  } else if (spec.metrics.minimum_observable_effect < 0) {
    error("E_MOE_NEGATIVE", "最小可观测效应不能为负", "metrics.minimum_observable_effect");
  }

  const guardrails = spec.metrics?.guardrails ?? [];
  const seenGuardrails = new Set<string>();
  for (const guardrail of guardrails) {
    if (!isNonEmpty(guardrail.name)) {
      error("E_GUARDRAIL_NAME", "护栏指标缺少名称", "metrics.guardrails");
      continue;
    }
    if (seenGuardrails.has(guardrail.name)) {
      error("E_GUARDRAIL_DUP", `护栏指标重复: ${guardrail.name}`, "metrics.guardrails");
    }
    seenGuardrails.add(guardrail.name);
    if (guardrail.max_degradation < 0) {
      error("E_GUARDRAIL_NEGATIVE", "护栏退化阈值不能为负", "metrics.guardrails");
    }
  }

  const repeats = spec.metrics?.repeats ?? 1;
  if (repeats < 1) {
    error("E_REPEATS", "重复次数必须大于 0", "metrics.repeats");
  }
  const seeds = spec.metrics?.seeds ?? [];
  if (seeds.length > 0 && seeds.length < repeats) {
    warn("W_SEEDS", "种子数量少于重复次数", "metrics.seeds");
  }
  if (repeats < 3) {
    warn("W_FEW_REPEATS", "重复次数少于 3，正式结论可信度不足", "metrics.repeats");
  }

  /* resources */
  if (!spec.resources || spec.resources.max_cost <= 0) {
    error("E_BUDGET", "预算必须大于 0", "resources.max_cost");
  }
  if (!spec.resources || spec.resources.max_wall_clock_seconds <= 0) {
    error("E_WALLCLOCK", "运行时长必须大于 0", "resources.max_wall_clock_seconds");
  }
  if (!isNonEmpty(spec.resources?.currency) || spec.resources.currency.length !== 3) {
    error("E_CURRENCY", "币种必须是三位代码", "resources.currency");
  }
  if (spec.resources?.checkpoint_required === false && spec.resources.max_wall_clock_seconds > 1800) {
    warn("W_CHECKPOINT", "长任务未启用检查点，失败后需重跑", "resources.checkpoint_required");
  }
  if (spec.resources?.max_wall_clock_seconds > 3600 && spec.resources.checkpoint_required !== true) {
    error("E_CHECKPOINT_REQUIRED", "超过 1 小时的任务必须启用检查点", "resources.checkpoint_required");
  }

  /* stopping */
  if (!spec.stopping || spec.stopping.max_attempts < 1) {
    error("E_ATTEMPTS", "最大尝试次数必须大于 0", "stopping.max_attempts");
  }
  if (!spec.stopping || spec.stopping.max_consecutive_failures < 1) {
    error("E_FAILURES", "最大连续失败次数必须大于 0", "stopping.max_consecutive_failures");
  }
  if (spec.stopping?.deadline_at && Number.isNaN(Date.parse(spec.stopping.deadline_at))) {
    error("E_DEADLINE", "截止时间不是合法时间", "stopping.deadline_at");
  }

  /* decision */
  if (!isNonEmpty(spec.decision?.keep_if)) error("E_KEEP_IF", "缺少保留条件", "decision.keep_if");
  if (!isNonEmpty(spec.decision?.discard_if)) {
    error("E_DISCARD_IF", "缺少撤销条件", "decision.discard_if");
  }
  if ((spec.decision?.on_unknown as string | undefined) === "retry_once") {
    error(
      "E_UNKNOWN_RETRY_FORBIDDEN",
      "执行状态未知时禁止自动重试，on_unknown 只能是 escalate 或 discard",
      "decision.on_unknown",
    );
  }

  /* artifacts */
  const required = spec.artifacts?.required ?? [];
  for (const artifact of REQUIRED_ARTIFACTS) {
    if (!required.includes(artifact)) {
      error("E_ARTIFACT", `缺少必需产物: ${artifact}`, "artifacts.required");
    }
  }

  /* approval */
  if (spec.resources?.type === "qpu") {
    approvalReasons.push("使用真实量子设备");
  }
  if (spec.resources?.type === "hpc") {
    approvalReasons.push("使用 HPC 长任务");
  }
  if (spec.resources?.type === "gpu" && (spec.resources.count ?? 1) > 1) {
    approvalReasons.push("使用多卡 GPU");
  }
  if ((spec.resources?.max_cost ?? 0) > 100) {
    approvalReasons.push("单实验预算超过 100");
  }
  if (spec.approval?.required === true && !isNonEmpty(spec.approval.approved_by)) {
    approvalReasons.push("规格声明需要审批但未记录批准人");
  }

  return {
    ok: errors.length === 0,
    errors,
    warnings,
    approvalReasons: Array.from(new Set(approvalReasons)),
  };
}
