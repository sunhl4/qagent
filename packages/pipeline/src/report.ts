/**
 * 基础日报：把当天的循环结果聚合成人类可读的日报。
 *
 * 设计约束：
 * - 聚合是纯函数，输入 LoopSummary，输出确定性的报告对象与 Markdown。
 * - 只陈述可追溯的事实：决策、失败类别、成本、需要人工处理的事项。
 * - 不把模型输出当事实；日报不生成新的实验结论。
 */

import type { ArtifactRef, ArtifactStorePort } from "../../../contracts/src/index.ts";
import type { DecisionAction, FailureCategory, Finding } from "../../domain/src/index.ts";
import { FAILURE_CATEGORIES } from "../../domain/src/index.ts";
import type { LoopSummary } from "./loop.ts";

export interface DailyReportInput {
  /** ISO 日期，格式 YYYY-MM-DD。 */
  date: string;
  loops?: LoopSummary[];
  goals?: string[];
  planned?: string[];
  humanDecisions?: string[];
  /** 固定生成时间，便于测试；默认当前时间。 */
  generatedAt?: string;
}

export interface DailyExperimentSummary {
  experiment_id: string;
  attempts: number;
  kept: number;
  discarded: number;
  failed: number;
  costs: Record<string, number>;
}

export interface DailyKeyResult {
  experiment_id: string;
  run_id: string;
  decision: DecisionAction;
  reason: string | null;
}

export interface DailyNegativeResult {
  experiment_id: string;
  run_id: string;
  category: FailureCategory | null;
  code: string | null;
  message: string | null;
}

export interface DailyFailureGroup {
  category: FailureCategory;
  count: number;
  codes: string[];
}

export interface DailyReport {
  report_id: string;
  date: string;
  generated_at: string;
  goals: string[];
  experiments: DailyExperimentSummary[];
  key_results: DailyKeyResult[];
  negative_results: DailyNegativeResult[];
  failures: DailyFailureGroup[];
  costs: Record<string, number>;
  human_decisions: string[];
  next_steps: string[];
  markdown: string;
}

export interface DailyReportWriteResult {
  report: DailyReport;
  jsonRef?: ArtifactRef;
  markdownRef?: ArtifactRef;
  findings: Finding[];
}

function formatAmount(value: number): string {
  const rounded = Math.round(value * 100) / 100;
  return Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(2);
}

function bullets(items: readonly string[], empty: string): string {
  if (items.length === 0) return `- ${empty}`;
  return items.map((item) => `- ${item}`).join("\n");
}

function formatCosts(costs: Record<string, number>): string {
  const entries = Object.entries(costs).filter(([, amount]) => amount > 0);
  if (entries.length === 0) return "无";
  return entries.map(([currency, amount]) => `${currency} ${formatAmount(amount)}`).join("；");
}

function renderMarkdown(report: DailyReport): string {
  const experimentRows =
    report.experiments.length === 0
      ? "| - | 0 | 0 | 0 | 0 |"
      : report.experiments
          .map(
            (experiment) =>
              `| ${experiment.experiment_id} | ${experiment.attempts} | ${experiment.kept} | ${experiment.discarded} | ${experiment.failed} |`,
          )
          .join("\n");

  const keyResults =
    report.key_results.length === 0
      ? "- 无"
      : report.key_results
          .map(
            (result) =>
              `- ${result.experiment_id} / ${result.run_id}：${result.decision}${result.reason ? ` — ${result.reason}` : ""}`,
          )
          .join("\n");

  const failures =
    report.negative_results.length === 0
      ? "- 无"
      : report.negative_results
          .map(
            (failure) =>
              `- [${failure.category ?? "unknown"}/${failure.code ?? "unknown"}] ${failure.message ?? "无说明"}（${failure.experiment_id} / ${failure.run_id}）`,
          )
          .join("\n");

  return [
    `# 日报 ${report.date}`,
    "",
    `生成时间：${report.generated_at}`,
    "",
    "## 今日目标",
    "",
    bullets(report.goals, "未填写目标"),
    "",
    "## 完成的实验",
    "",
    "| 实验 | 尝试 | 保留 | 撤销 | 失败 |",
    "|---|---|---|---|---|",
    experimentRows,
    "",
    "## 关键结果",
    "",
    keyResults,
    "",
    "## 失败与原因",
    "",
    failures,
    "",
    "## 资源消耗",
    "",
    `- ${formatCosts(report.costs)}`,
    "",
    "## 明日计划",
    "",
    bullets(report.next_steps, "未填写计划"),
    "",
    "## 需要人工决策",
    "",
    bullets(report.human_decisions, "无"),
    "",
  ].join("\n");
}

/**
 * 聚合当天的循环结果。
 *
 * - `keep` 进入关键结果；`discard` 作为负结果保留。
 * - 失败按类别分组，并保留稳定错误码。
 * - 需要审批、升级、阻塞或没有候选的循环进入人工决策清单。
 */
export function buildDailyReport(input: DailyReportInput): DailyReport {
  const generatedAt = input.generatedAt ?? new Date().toISOString();
  const experiments = new Map<string, DailyExperimentSummary>();
  const keyResults: DailyKeyResult[] = [];
  const negativeResults: DailyNegativeResult[] = [];
  const failureMap = new Map<FailureCategory, { count: number; codes: Set<string> }>();
  const humanDecisions: string[] = [...(input.humanDecisions ?? [])];

  for (const loop of input.loops ?? []) {
    for (const attempt of loop.attempts) {
      let experiment = experiments.get(attempt.experiment_id);
      if (!experiment) {
        experiment = {
          experiment_id: attempt.experiment_id,
          attempts: 0,
          kept: 0,
          discarded: 0,
          failed: 0,
          costs: {},
        };
        experiments.set(attempt.experiment_id, experiment);
      }
      experiment.attempts += 1;
      experiment.costs[attempt.currency] =
        (experiment.costs[attempt.currency] ?? 0) + attempt.cost;

      if (attempt.decision === "keep") {
        experiment.kept += 1;
        keyResults.push({
          experiment_id: attempt.experiment_id,
          run_id: attempt.run_id,
          decision: "keep",
          reason: attempt.reason ?? null,
        });
      } else if (attempt.decision === "discard") {
        experiment.discarded += 1;
      } else if (
        attempt.state === "failed" ||
        attempt.state === "unknown_execution" ||
        attempt.state === "rejected" ||
        attempt.state === "denied" ||
        attempt.state === "infeasible" ||
        attempt.state === "escalated" ||
        attempt.state === "needs_approval"
      ) {
        experiment.failed += 1;
      }

      if (attempt.decision === "discard" || attempt.failure) {
        negativeResults.push({
          experiment_id: attempt.experiment_id,
          run_id: attempt.run_id,
          category: attempt.failure?.category ?? null,
          code: attempt.failure?.code ?? null,
          message: attempt.failure?.message ?? attempt.reason ?? null,
        });
      }

      if (attempt.failure) {
        const group = failureMap.get(attempt.failure.category) ?? {
          count: 0,
          codes: new Set<string>(),
        };
        group.count += 1;
        group.codes.add(attempt.failure.code);
        failureMap.set(attempt.failure.category, group);
      }

      if (attempt.state === "needs_approval") {
        humanDecisions.push(
          `实验 ${attempt.experiment_id} 第 ${attempt.attempt} 轮需要人工审批`,
        );
      }
    }

    if (
      loop.stop_reason === "escalated" ||
      loop.stop_reason === "blocked" ||
      loop.stop_reason === "invalid_candidate" ||
      loop.stop_reason === "no_candidate"
    ) {
      humanDecisions.push(
        `实验 ${loop.experiment_id}：${loop.stop_reason}${loop.stop_detail ? `（${loop.stop_detail}）` : ""}`,
      );
    }
  }

  const costs: Record<string, number> = {};
  for (const experiment of experiments.values()) {
    for (const [currency, amount] of Object.entries(experiment.costs)) {
      costs[currency] = (costs[currency] ?? 0) + amount;
    }
  }

  const failures: DailyFailureGroup[] = FAILURE_CATEGORIES.filter((category) =>
    failureMap.has(category),
  ).map((category) => {
    const group = failureMap.get(category)!;
    return {
      category,
      count: group.count,
      codes: [...group.codes].sort(),
    };
  });

  const report: DailyReport = {
    report_id: `daily-${input.date}`,
    date: input.date,
    generated_at: generatedAt,
    goals: [...(input.goals ?? [])],
    experiments: [...experiments.values()].sort((left, right) =>
      left.experiment_id.localeCompare(right.experiment_id),
    ),
    key_results: keyResults,
    negative_results: negativeResults,
    failures,
    costs,
    human_decisions: [...new Set(humanDecisions)],
    next_steps: [...(input.planned ?? [])],
    markdown: "",
  };

  report.markdown = renderMarkdown(report);
  return report;
}

/**
 * 写入日报 JSON 与 Markdown。两次写入互相独立；任一失败返回 finding。
 */
export async function writeDailyReport(
  report: DailyReport,
  deps: { artifacts: ArtifactStorePort },
  context: { tenantId: string; projectId?: string },
): Promise<DailyReportWriteResult> {
  const findings: Finding[] = [];
  const prefix = `reports/daily/${report.date}`;

  const jsonText = JSON.stringify(report, null, 2);
  const jsonPut = await deps.artifacts.put({
    tenantId: context.tenantId,
    projectId: context.projectId,
    key: `${prefix}/report.json`,
    contentType: "application/json",
    bytes: new TextEncoder().encode(jsonText),
    idempotencyKey: `${report.report_id}:json`,
  });
  if (!jsonPut.ok) {
    findings.push({
      severity: "warning",
      code: "W_DAILY_REPORT_JSON",
      message: `日报 JSON 写入失败: ${jsonPut.error.code} ${jsonPut.error.message}`,
    });
  }

  const markdownPut = await deps.artifacts.put({
    tenantId: context.tenantId,
    projectId: context.projectId,
    key: `${prefix}/report.md`,
    contentType: "text/markdown",
    bytes: new TextEncoder().encode(report.markdown),
    idempotencyKey: `${report.report_id}:md`,
  });
  if (!markdownPut.ok) {
    findings.push({
      severity: "warning",
      code: "W_DAILY_REPORT_MD",
      message: `日报 Markdown 写入失败: ${markdownPut.error.code} ${markdownPut.error.message}`,
    });
  }

  return {
    report,
    jsonRef: jsonPut.ok ? jsonPut.value : undefined,
    markdownRef: markdownPut.ok ? markdownPut.value : undefined,
    findings,
  };
}
