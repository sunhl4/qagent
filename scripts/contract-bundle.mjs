#!/usr/bin/env node
/**
 * 联调交换包（contract bundle）体检与交接清单打印。
 *
 * 检查：
 * 1. contracts/VERSION 与 contracts/src/index.ts 的 CONTRACT_VERSION 一致；
 * 2. 一致性用例解析数量与版本口径（cases.yaml 的 contract 字段 vs contracts/VERSION，不同只提示不修改）；
 * 3. schema / fixtures / examples 清点；
 * 4. 结果交换样例通过 scripts/conformance.mjs 校验（无硬错误）。
 *
 * 退出码：0 无硬错误；2 有硬错误。
 */

import { readFile, readdir } from "node:fs/promises";
import { join } from "node:path";
import {
  CASES_YAML,
  DEFAULT_RESULTS_FILE,
  ROOT,
  formatSummary,
  loadCases,
  loadContractVersion,
  validateResultsDoc,
} from "./conformance.mjs";

const errors = [];
const advisories = [];

function note(message) {
  console.log(`  ${message}`);
}
function warn(message) {
  advisories.push(message);
  console.log(`  [提示] ${message}`);
}
function hardError(message) {
  errors.push(message);
  console.log(`  [硬错误] ${message}`);
}

console.log("== DeepSeekHarness 联调交换包体检 ==");

// 1. 契约版本
console.log("1) 契约版本口径");
let version = "";
try {
  version = await loadContractVersion();
  note(`contracts/VERSION = ${version}`);
} catch (error) {
  hardError(`contracts/VERSION 读取失败：${error.message}`);
}

try {
  const indexText = await readFile(join(ROOT, "contracts", "src", "index.ts"), "utf8");
  if (version && !indexText.includes(`CONTRACT_VERSION = "${version}"`)) {
    hardError(`contracts/src/index.ts 中找不到 CONTRACT_VERSION = "${version}" 标记`);
  }
} catch (error) {
  hardError(`contracts/src/index.ts 读取失败：${error.message}`);
}

// cases.yaml 的 contract 字段
let casesContractField = "";
try {
  const casesText = await readFile(CASES_YAML, "utf8");
  const m = casesText.match(/^contract:\s*(?:["'])([^"']+)["']\s*$/m);
  if (m) casesContractField = m[1];
} catch (error) {
  hardError(`contracts/conformance/cases.yaml 读取失败：${error.message}`);
}
if (casesContractField && version && casesContractField !== version) {
  warn(
    `cases.yaml 的 contract 字段（${casesContractField}）与 contracts/VERSION（${version}）不同口径，` +
      "交换前需双方评审确认；本脚本不修改契约。",
  );
}

// 2. 一致性用例
console.log("2) 一致性用例");
let cases = [];
try {
  cases = await loadCases();
  const must = cases.filter((item) => item.level === "MUST").length;
  note(`解析 ${cases.length} 条用例（MUST ${must}，SHOULD ${cases.length - must}）`);
  if (cases.length === 0) hardError("cases.yaml 未解析出任何用例");
  const uniqueIds = new Set(cases.map((item) => item.id));
  if (uniqueIds.size !== cases.length) hardError("cases.yaml 存在重复用例 ID");
} catch (error) {
  hardError(`用例解析失败：${error.message}`);
}

// 3. 清点
console.log("3) 交付物清点");
async function countJson(relativeDir) {
  try {
    const files = (await readdir(join(ROOT, relativeDir))).filter((name) => name.endsWith(".json"));
    note(`${relativeDir}/: ${files.length} 个 JSON`);
    return files;
  } catch (error) {
    hardError(`${relativeDir}/ 读取失败：${error.message}`);
    return [];
  }
}
const schemaFiles = await countJson("schemas");
await countJson("contracts/schemas");
try {
  const fixtures = await readdir(join(ROOT, "contracts", "fixtures"));
  note(`contracts/fixtures/: ${fixtures.join("、") || "(空)"}`);
} catch (error) {
  hardError(`contracts/fixtures/ 读取失败：${error.message}`);
}
try {
  const examples = await readdir(join(ROOT, "examples"));
  note(`examples/: ${examples.join("、")}`);
} catch (error) {
  hardError(`examples/ 读取失败：${error.message}`);
}

if (!schemaFiles.includes("conformance-results.schema.json")) {
  hardError("schemas/conformance-results.schema.json 缺失，结果交换格式不完整");
}

// 4. 结果交换样例
console.log("4) 结果交换样例");
try {
  const doc = JSON.parse(await readFile(DEFAULT_RESULTS_FILE, "utf8"));
  const report = validateResultsDoc(doc, cases, version);
  for (const line of formatSummary(report)) note(line);
  if (report.advisories.length > 0) note(`样例提示 ${report.advisories.length} 条（默认样例允许 pending）`);
  if (report.errors.length > 0) for (const error of report.errors) hardError(`结果样例：${error}`);
} catch (error) {
  hardError(`examples/conformance-results.stub.json 读取/校验失败：${error.message}`);
}

// 5. 打包建议
console.log("5) 打包与交换建议（命令仅提示，脚本不执行）");
console.log("  git archive --format=tar.gz -o /tmp/dsh-contract-bundle.tar.gz contracts schemas examples/conformance-results.stub.json");
console.log("  对端换取：integration-manifest + 本脚本同名体检输出 + conformance 结果文件（provenance=harness-core）");

if (errors.length > 0) {
  console.error(`交换包体检未通过：${errors.length} 个硬错误`);
  process.exit(2);
}
if (advisories.length > 0) {
  console.log(`体检通过，另有 ${advisories.length} 条提示需双方评审确认。`);
} else {
  console.log("交换包体检通过。");
}
