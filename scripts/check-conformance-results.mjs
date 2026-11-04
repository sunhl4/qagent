#!/usr/bin/env node
/**
 * 校验一致性结果交换文件并打印汇总。
 *
 * 用法：
 *   node scripts/check-conformance-results.mjs [--file <path>] [--require-pass]
 *
 * 退出码：
 * - 0：无硬错误（默认模式下允许存在未判用例，仅打印）；
 * - 1：--require-pass 模式下存在 MUST 用例不是通过的；
 * - 2：文件不存在、不是 JSON、存在硬错误。
 */

import { readFile } from "node:fs/promises";
import {
  DEFAULT_RESULTS_FILE,
  formatSummary,
  loadCases,
  loadContractVersion,
  validateResultsDoc,
} from "./conformance.mjs";

function parseArgs(argv) {
  const args = { file: DEFAULT_RESULTS_FILE, requirePass: false };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--file") args.file = argv[(i += 1)];
    else if (arg === "--require-pass") args.requirePass = true;
    else if (arg === "--help" || arg === "-h") {
      console.log("用法: node scripts/check-conformance-results.mjs [--file <path>] [--require-pass]");
      process.exit(0);
    }
  }
  return args;
}

const args = parseArgs(process.argv.slice(2));

let raw;
try {
  raw = await readFile(args.file, "utf8");
} catch (error) {
  console.error(`无法读取结果文件 ${args.file}：${error.message}`);
  process.exit(2);
}

let doc;
try {
  doc = JSON.parse(raw);
} catch (error) {
  console.error(`结果文件不是合法 JSON：${error.message}`);
  process.exit(2);
}

const [cases, contractVersion] = await Promise.all([loadCases(), loadContractVersion()]);
const report = validateResultsDoc(doc, cases, contractVersion);

console.log(`文件：${args.file}`);
console.log(`版本口径：结果 contract_version=${doc.contract_version ?? "(缺失)"}，contracts/VERSION=${contractVersion}`);
console.log(`provenance：${doc.provenance ?? "(缺失)"}`);
for (const line of formatSummary(report)) console.log(line);

if (report.advisories.length > 0) {
  console.log("提示（不阻断）：");
  for (const advisory of report.advisories.slice(0, 50)) console.log(`  - ${advisory}`);
  if (report.advisories.length > 50) console.log(`  - ...另有 ${report.advisories.length - 50} 条`);
}

if (report.errors.length > 0) {
  console.error("硬错误：");
  for (const error of report.errors) console.error(`  - ${error}`);
  process.exit(2);
}

const must = report.summary.perLevel.MUST;
if (args.requirePass && (must.passed.length < must.total || must.missing.length > 0)) {
  console.error(
    `--require-pass：MUST 用例仍有未通过的（通过 ${must.passed.length}/${must.total}，未覆盖 ${must.missing.length}）`,
  );
  process.exit(1);
}

console.log("格式与覆盖检查通过（默认模式；正式验收需 --require-pass 且 provenance=harness-core）。");
