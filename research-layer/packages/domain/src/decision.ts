/**
 * 决策引擎：把观测结果与预注册规则比较，输出保留/撤销/扩展/停止/升级。
 *
 * 该模块是纯函数，不做 IO，便于单测与回放。
 */

import type { ExperimentSpec } from "./experiment.ts";

export type DecisionAction = "keep" | "discard" | "extend" | "stop" | "escalate";

export interface ObservedResult {
  /** 与基线比较后的主指标改进量；按优化方向已转为“正数代表改善”。 */
  primaryDelta: number | null;
  /** 各护栏指标的退化比例；0.05 表示退化 5%。 */
  guardrailDegradations: Record<string, number>;
  /** 每次重复的指标值；用于稳定性判断。 */
  seedValues?: number[];
  cost: number;
  currency: string;
  artifactsPresent: string[];
  executionState: "succeeded" | "failed" | "unknown_execution" | "partial";
}

export interface DecisionCheck {
  name: string;
  passed: boolean;
  detail: string;
}

export interface Decision {
  action: DecisionAction;
  reasons: string[];
  checks: DecisionCheck[];
}

function mean(values: number[]): number {
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function stddev(values: number[]): number {
  if (values.length < 2) return 0;
  const avg = mean(values);
  const variance =
    values.reduce((sum, value) => sum + (value - avg) ** 2, 0) / (values.length - 1);
  return Math.sqrt(variance);
}

/**
 * 决策优先级（从高到低）：
 * 1. 未知执行 → escalate（绝不重试）
 * 2. 失败 → stop
 * 3. 部分结果 → escalate
 * 4. 缺主指标 → escalate
 * 5. 超预算 → stop
 * 6. 缺必需产物 → escalate
 * 7. 主指标未达最小效应 → discard
 * 8. 护栏退化超阈值 → discard
 * 9. 方差过大 → extend
 * 10. 通过 → keep
 */
export function decide(spec: ExperimentSpec, observed: ObservedResult): Decision {
  const checks: DecisionCheck[] = [];
  const reasons: string[] = [];

  const add = (name: string, passed: boolean, detail: string): void => {
    checks.push({ name, passed, detail });
    if (!passed) reasons.push(detail);
  };

  if (observed.executionState === "unknown_execution") {
    add("execution_known", false, "执行状态未知，必须人工对账，禁止重试");
    return { action: "escalate", reasons, checks };
  }

  if (observed.executionState === "failed") {
    add("execution_succeeded", false, "执行失败");
    return { action: "stop", reasons, checks };
  }

  if (observed.executionState === "partial") {
    add("execution_complete", false, "仅部分结果有效");
    return { action: "escalate", reasons, checks };
  }

  add("execution_succeeded", true, "执行成功");

  if (observed.primaryDelta === null || Number.isNaN(observed.primaryDelta)) {
    add("primary_metric_present", false, "缺少主指标结果");
    return { action: "escalate", reasons, checks };
  }
  add("primary_metric_present", true, `主指标改进 ${observed.primaryDelta}`);

  if (observed.currency !== spec.resources.currency) {
    add("currency_match", false, `币种不一致: ${observed.currency} vs ${spec.resources.currency}`);
    return { action: "escalate", reasons, checks };
  }

  if (observed.cost > spec.resources.max_cost) {
    add("budget_respected", false, `成本 ${observed.cost} 超过预算 ${spec.resources.max_cost}`);
    return { action: "stop", reasons, checks };
  }
  add("budget_respected", true, `成本 ${observed.cost} 在预算内`);

  const missing = spec.artifacts.required.filter(
    (artifact) => !observed.artifactsPresent.includes(artifact),
  );
  if (missing.length > 0) {
    add("artifacts_complete", false, `缺少产物: ${missing.join(", ")}`);
    return { action: "escalate", reasons, checks };
  }
  add("artifacts_complete", true, "必需产物齐全");

  const moe = spec.metrics.minimum_observable_effect ?? 0;
  if (observed.primaryDelta < moe) {
    add(
      "effect_reached",
      false,
      `主指标改进 ${observed.primaryDelta} 未达到最小可观测效应 ${moe}`,
    );
    return { action: "discard", reasons, checks };
  }
  add("effect_reached", true, `主指标改进 ${observed.primaryDelta} ≥ ${moe}`);

  for (const guardrail of spec.metrics.guardrails ?? []) {
    const degradation = observed.guardrailDegradations[guardrail.name];
    if (degradation === undefined) {
      add(`guardrail:${guardrail.name}`, false, `缺少护栏指标: ${guardrail.name}`);
      return { action: "escalate", reasons, checks };
    }
    if (degradation > guardrail.max_degradation) {
      add(
        `guardrail:${guardrail.name}`,
        false,
        `护栏 ${guardrail.name} 退化 ${degradation}，超过阈值 ${guardrail.max_degradation}`,
      );
      return { action: "discard", reasons, checks };
    }
    add(`guardrail:${guardrail.name}`, true, `护栏 ${guardrail.name} 退化 ${degradation} 在阈值内`);
  }

  const seedValues = observed.seedValues ?? [];
  if (seedValues.length >= 2) {
    const avg = mean(seedValues);
    const sd = stddev(seedValues);
    const relative = avg === 0 ? 0 : sd / Math.abs(avg);
    if (relative > 0.5) {
      add("stability", false, `结果方差过大（相对标准差 ${relative.toFixed(2)}），需更多重复`);
      return { action: "extend", reasons, checks };
    }
    add("stability", true, `相对标准差 ${relative.toFixed(2)}`);
  } else if ((spec.metrics.repeats ?? 1) >= 2) {
    add("stability", false, "声明了多次重复但没有种子级结果");
    return { action: "extend", reasons, checks };
  } else {
    add("stability", true, "单次实验，未做稳定性判断");
  }

  add("decision_passed", true, "所有预注册条件通过");
  return { action: "keep", reasons, checks };
}
