/**
 * 失败分类：把编译、策略、端口与决策结果映射到稳定的失败类别。
 *
 * 目标：
 * - 失败必须入库，且类别可比、可检索。
 * - 未知执行永远不可重试。
 * - 分类不依赖端口实现，只接受错误码字符串，避免反向依赖 contracts/。
 *
 * 类别与 docs/04 的失败分类表、schemas/run-manifest.schema.json 的
 * failure.category 枚举保持一致。
 */

export const FAILURE_CATEGORIES = [
  "implementation",
  "data",
  "metric",
  "resource",
  "hypothesis",
  "environment",
  "instability",
  "policy",
  "unknown",
] as const;

export type FailureCategory = (typeof FAILURE_CATEGORIES)[number];

export const FAILURE_STAGES = [
  "compile",
  "policy",
  "quote",
  "submit",
  "execution",
  "artifacts",
  "decision",
  "unknown_execution",
  "loop",
] as const;

export type FailureStage = (typeof FAILURE_STAGES)[number];

export interface FailureInput {
  stage: FailureStage;
  /** 领域错误码，例如 E_MOE、E_INFEASIBLE。 */
  code?: string | null;
  /** 端口错误码，例如 UNKNOWN_EXECUTION、TIMEOUT。 */
  portErrorCode?: string | null;
  message?: string | null;
  /** 决策动作，用于 decision 阶段。 */
  decision?: string | null;
  /** 决策原因，用于 decision 阶段归类。 */
  reasons?: string[];
  /** 显式覆盖可重试性；未知执行仍会被强制为 false。 */
  retryable?: boolean;
}

export interface FailureRecord {
  category: FailureCategory;
  code: string;
  message: string;
  retryable: boolean;
  stage: FailureStage;
}

interface PortMapping {
  category: FailureCategory;
  retryable: boolean;
}

const PORT_ERROR_CATEGORY: Readonly<Record<string, PortMapping>> = {
  INVALID_ARGUMENT: { category: "implementation", retryable: false },
  UNAUTHENTICATED: { category: "policy", retryable: false },
  PERMISSION_DENIED: { category: "policy", retryable: false },
  NOT_FOUND: { category: "environment", retryable: false },
  CONFLICT: { category: "implementation", retryable: false },
  QUOTA_EXCEEDED: { category: "resource", retryable: false },
  NOT_SUPPORTED: { category: "environment", retryable: false },
  UNAVAILABLE: { category: "environment", retryable: true },
  TIMEOUT: { category: "environment", retryable: true },
  UNKNOWN_EXECUTION: { category: "unknown", retryable: false },
  INTERNAL: { category: "implementation", retryable: false },
};

const COMPILE_CATEGORY: Readonly<Record<string, FailureCategory>> = {
  E_ID: "implementation",
  E_TASK: "implementation",
  E_HYPOTHESIS: "hypothesis",
  E_FALSIFIABLE: "hypothesis",
  E_BASELINE_NOT_REPRODUCED: "hypothesis",
  E_BASELINE_METRIC: "hypothesis",
  E_NO_VARIABLE: "implementation",
  E_FORBIDDEN_PATH: "implementation",
  E_OUT_OF_SCOPE: "implementation",
  E_PRIMARY_METRIC: "metric",
  E_DIRECTION: "implementation",
  E_MOE: "hypothesis",
  E_MOE_NEGATIVE: "hypothesis",
  E_GUARDRAIL_NAME: "metric",
  E_GUARDRAIL_DUP: "metric",
  E_GUARDRAIL_NEGATIVE: "metric",
  E_REPEATS: "resource",
  E_BUDGET: "resource",
  E_WALLCLOCK: "resource",
  E_CURRENCY: "implementation",
  E_CHECKPOINT_REQUIRED: "resource",
  E_ATTEMPTS: "resource",
  E_FAILURES: "resource",
  E_DEADLINE: "resource",
  E_KEEP_IF: "hypothesis",
  E_DISCARD_IF: "hypothesis",
  E_ARTIFACT: "metric",
  E_UNKNOWN_RETRY_FORBIDDEN: "policy",
};

const POLICY_RULE_CATEGORY: Readonly<Record<string, FailureCategory>> = {
  "R-UNKNOWN-NO-RETRY": "unknown",
  "R-AGENT-NO-INTERNET": "policy",
  "R-DATA-RESIDENCY": "policy",
  "R-BUDGET": "resource",
  "R-QPU-APPROVAL": "policy",
  "R-PRODUCTION-APPROVAL": "policy",
  "R-IRREVERSIBLE-APPROVAL": "policy",
  "R-RISK-APPROVAL": "policy",
  "R-APPROVED-LIMIT": "policy",
  "R-MEDIUM-IRREVERSIBLE": "policy",
};

const DEFAULT_CODE: Readonly<Record<FailureStage, string>> = {
  compile: "E_COMPILE",
  policy: "E_POLICY",
  quote: "E_QUOTE",
  submit: "E_SUBMIT",
  execution: "E_EXECUTION",
  artifacts: "E_ARTIFACT_STORE",
  decision: "E_DECISION",
  unknown_execution: "UNKNOWN_EXECUTION",
  loop: "E_LOOP",
};

function messageOf(input: FailureInput): string {
  if (input.message && input.message.trim().length > 0) return input.message;
  return input.code ?? DEFAULT_CODE[input.stage];
}

function decisionCategory(input: FailureInput): FailureCategory {
  if (input.decision === "extend") return "instability";
  const text = (input.reasons ?? []).join("；");
  if (text.includes("方差") || text.includes("稳定性") || text.includes("重复")) {
    return "instability";
  }
  if (text.includes("护栏")) return "hypothesis";
  if (text.includes("最小可观测效应") || text.includes("主指标")) return "hypothesis";
  if (text.includes("缺少产物") || text.includes("产物")) return "metric";
  if (text.includes("预算") || text.includes("成本") || text.includes("币种")) return "resource";
  if (text.includes("执行失败") || text.includes("部分结果")) return "unknown";
  return "unknown";
}

/**
 * 把一次失败映射为稳定记录。
 *
 * 优先级：未知执行 > 端口错误码 > 策略规则 > 编译错误码 > 决策原因 > 阶段默认。
 */
export function classifyFailure(input: FailureInput): FailureRecord {
  const stage = input.stage;
  const code = input.code ?? input.portErrorCode ?? DEFAULT_CODE[stage];
  const message = messageOf(input);

  if (
    stage === "unknown_execution" ||
    input.portErrorCode === "UNKNOWN_EXECUTION" ||
    input.code === "UNKNOWN_EXECUTION"
  ) {
    return {
      category: "unknown",
      code: "UNKNOWN_EXECUTION",
      message,
      retryable: false,
      stage,
    };
  }

  const portMapping = input.portErrorCode
    ? PORT_ERROR_CATEGORY[input.portErrorCode]
    : undefined;
  if (portMapping) {
    return {
      category: portMapping.category,
      code,
      message,
      retryable: input.retryable ?? portMapping.retryable,
      stage,
    };
  }

  if (stage === "policy") {
    const ruleCategory = input.code ? POLICY_RULE_CATEGORY[input.code] : undefined;
    return {
      category: ruleCategory ?? "policy",
      code,
      message,
      retryable: false,
      stage,
    };
  }

  if (stage === "compile") {
    return {
      category: (input.code && COMPILE_CATEGORY[input.code]) || "implementation",
      code,
      message,
      retryable: false,
      stage,
    };
  }

  if (stage === "decision") {
    return {
      category: decisionCategory(input),
      code,
      message,
      retryable: false,
      stage,
    };
  }

  const stageDefault: Record<Exclude<FailureStage, "policy" | "compile" | "decision">, FailureCategory> = {
    quote: "resource",
    submit: "environment",
    execution: "unknown",
    artifacts: "environment",
    unknown_execution: "unknown",
    loop: "implementation",
  };

  return {
    category: stageDefault[stage],
    code,
    message,
    retryable: input.retryable ?? false,
    stage,
  };
}
