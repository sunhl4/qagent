/**
 * 一致性用例与结果交换的共享解析/校验库。
 *
 * 设计约束：
 * - 不引入运行时依赖：`cases.yaml` 只解析本工程固定使用的小节（id/port/level/title），
 *   结构校验仍由 `scripts/validate.py` 与官方 YAML 库覆盖。
 * - 本文件只读取 `contracts/`，不写任何契约内容；契约口径不一致时报告而不是修改。
 */

import { readFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
export const ROOT = join(HERE, "..");
export const CASES_YAML = join(ROOT, "contracts", "conformance", "cases.yaml");
export const CONTRACT_VERSION_FILE = join(ROOT, "contracts", "VERSION");
export const DEFAULT_RESULTS_FILE = join(ROOT, "examples", "conformance-results.stub.json");

export const RESULT_STATUSES = ["passed", "failed", "pending", "blocked"];
export const CASE_LEVELS = ["MUST", "SHOULD"];

function trimQuote(value) {
  const text = String(value).trim();
  if (
    (text.startsWith('"') && text.endsWith('"') && text.length >= 2) ||
    (text.startsWith("'") && text.endsWith("'") && text.length >= 2)
  ) {
    return text.slice(1, -1);
  }
  return text;
}

/** 解析 cases.yaml 的固定子集，返回 [{ id, port, level, title }]。 */
export function parseCases(yamlText) {
  const cases = [];
  let current = null;
  let inCases = false;
  for (const rawLine of String(yamlText).split(/\r?\n/)) {
    const line = rawLine.replace(/\t/g, "    ");
    if (/^cases:\s*$/.test(line)) {
      inCases = true;
      current = null;
      continue;
    }
    if (!inCases) continue;
    if (/^\S/.test(line)) {
      inCases = false;
      continue;
    }
    const caseMatch = line.match(/^\s*-\s*id:\s*(\S+)\s*$/);
    if (caseMatch) {
      current = { id: caseMatch[1], port: "", level: "", title: "" };
      cases.push(current);
      continue;
    }
    if (!current) continue;
    let m;
    if ((m = line.match(/^\s+port:\s*(\S+)\s*$/))) current.port = m[1];
    else if ((m = line.match(/^\s+level:\s*(\S+)\s*$/))) current.level = m[1];
    else if ((m = line.match(/^\s+title:\s*(.*)\s*$/))) current.title = trimQuote(m[1]);
  }
  return cases.filter((item) => item.id);
}

export async function loadCases() {
  return parseCases(await readFile(CASES_YAML, "utf8"));
}

export async function loadContractVersion() {
  const text = await readFile(CONTRACT_VERSION_FILE, "utf8");
  return text.trim();
}

function levelBucket(total) {
  return {
    total,
    passed: [],
    failed: [],
    pending: 0,
    blocked: [],
    missing: [],
  };
}

/**
 * 校验结果交换文档。
 *
 * 返回 { errors, advisories, summary }：
 * - errors：违反格式的硬错误（CLI 以非零退出）；
 * - advisories：不阻断但应告知双方的问题（覆盖不全、缺 notes、契约口径差异）；
 * - summary：按 level 汇总的状态与未覆盖清单。
 */
export function validateResultsDoc(doc, cases, expectedContractVersion) {
  const errors = [];
  const advisories = [];

  const caseById = new Map(cases.map((item) => [item.id, item]));
  const summary = { byStatus: { passed: 0, failed: 0, pending: 0, blocked: 0 }, perLevel: {} };
  for (const level of CASE_LEVELS) {
    summary.perLevel[level] = levelBucket(cases.filter((item) => item.level === level).length);
  }

  if (doc === null || typeof doc !== "object" || Array.isArray(doc)) {
    errors.push("结果文件顶层必须是对象");
    return { errors, advisories, summary };
  }

  const requiredTop = ["schema_version", "contract_version", "generated_at", "provenance", "run_context", "results"];
  for (const key of requiredTop) {
    if (!(key in doc)) errors.push(`缺少必填字段 ${key}`);
  }
  const allowedTop = new Set(requiredTop);
  for (const key of Object.keys(doc)) {
    if (!allowedTop.has(key)) errors.push(`未知字段 ${key}`);
  }

  if (doc.schema_version !== "0.1") {
    errors.push(`schema_version 必须是 0.1，实际 ${JSON.stringify(doc.schema_version ?? null)}`);
  }

  if (typeof doc.contract_version !== "string" || !/^[0-9]+\.[0-9]+\.[0-9]+$/.test(doc.contract_version)) {
    errors.push(`contract_version 缺失或不是 x.y.z：${JSON.stringify(doc.contract_version ?? null)}`);
  } else if (expectedContractVersion && doc.contract_version !== expectedContractVersion) {
    errors.push(
      `contract_version（${doc.contract_version}）与 contracts/VERSION（${expectedContractVersion}）不一致`,
    );
  }

  if (typeof doc.generated_at !== "string" || Number.isNaN(Date.parse(doc.generated_at))) {
    errors.push(`generated_at 不是合法 date-time：${JSON.stringify(doc.generated_at ?? null)}`);
  }

  if (doc.provenance !== "stub" && doc.provenance !== "harness-core") {
    errors.push(`provenance 必须是 stub 或 harness-core，实际 ${JSON.stringify(doc.provenance ?? null)}`);
  }

  const context = doc.run_context;
  if (
    context === null ||
    typeof context !== "object" ||
    Array.isArray(context) ||
    typeof context.env !== "string" ||
    context.env.length < 1
  ) {
    errors.push("run_context.env 必须是非空字符串");
  }

  if (!Array.isArray(doc.results) || doc.results.length === 0) {
    errors.push("results 必须是非空数组");
    return { errors, advisories, summary };
  }

  const seen = new Map();
  for (const [index, item] of doc.results.entries()) {
    const path = `results[${index}]`;
    if (item === null || typeof item !== "object" || Array.isArray(item)) {
      errors.push(`${path} 必须是对象`);
      continue;
    }
    const caseId = item.case_id;
    const known = typeof caseId === "string" ? caseById.get(caseId) : undefined;
    if (!known) {
      errors.push(`${path}: case_id ${JSON.stringify(caseId ?? null)} 不在 cases.yaml 中`);
      continue;
    }
    if (seen.has(caseId)) {
      errors.push(`${path}: 用例 ${caseId} 重复（首次出现在 results[${seen.get(caseId)}]）`);
      continue;
    }
    seen.set(caseId, String(index));

    if (item.port !== known.port) {
      errors.push(`${path}: port（${JSON.stringify(item.port ?? null)}）与 cases.yaml 的 ${known.port} 不一致`);
    }
    if (item.level !== known.level) {
      errors.push(`${path}: level（${JSON.stringify(item.level ?? null)}）与 cases.yaml 的 ${known.level} 不一致`);
    }
    if (!RESULT_STATUSES.includes(item.status)) {
      errors.push(
        `${path}: status（${JSON.stringify(item.status ?? null)}）不在枚举 ${RESULT_STATUSES.join("/")} 内`,
      );
      continue;
    }
    if ((item.status === "failed" || item.status === "blocked") && !item.notes) {
      advisories.push(`${path}: ${item.status} 建议写明 notes 原因`);
    }
    if (item.notes !== undefined && typeof item.notes !== "string") {
      errors.push(`${path}: notes 必须是字符串`);
    }
    if (item.status in summary.byStatus) summary.byStatus[item.status] += 1;
    const bucket = summary.perLevel[known.level];
    if (item.status === "passed") bucket.passed.push(caseId);
    else if (item.status === "failed") bucket.failed.push(caseId);
    else if (item.status === "blocked") bucket.blocked.push(caseId);
    else bucket.pending += 1;
  }

  for (const item of cases) {
    if (seen.has(item.id)) continue;
    summary.perLevel[item.level].missing.push(item.id);
    advisories.push(`缺少用例结果: ${item.id}（${item.level}，${item.port}）`);
  }

  return { errors, advisories, summary };
}

function describeStat(stat) {
  const bits = [];
  if (stat.passed.length) bits.push(`通过 ${stat.passed.length}`);
  if (stat.failed.length) bits.push(`失败 ${stat.failed.length}（${stat.failed.join("、")}）`);
  if (stat.pending) bits.push(`未判 ${stat.pending}`);
  if (stat.blocked.length) bits.push(`阻塞 ${stat.blocked.length}（${stat.blocked.join("、")}）`);
  if (stat.missing.length) bits.push(`未覆盖 ${stat.missing.length}（${stat.missing.join("、")}）`);
  if (!bits.length) bits.push("无记录");
  return bits.join("，");
}

/** 人类可读的汇总文本；供 CLI 打印。 */
export function formatSummary(report) {
  const out = [];
  for (const level of CASE_LEVELS) {
    out.push(`${level}: ${report.summary.perLevel[level].total} 条 -- ${describeStat(report.summary.perLevel[level])}`);
  }
  const byStatus = Object.entries(report.summary.byStatus)
    .map(([status, count]) => `${status} ${count}`)
    .join("，");
  out.push(`状态合计：${byStatus}`);
  return out;
}
