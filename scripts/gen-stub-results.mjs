#!/usr/bin/env node
/**
 * 生成一致性结果交换格式样例（stub provenance）。
 *
 * 输出 `examples/conformance-results.stub.json`：
 * - 实际执行 tests/conformance-run.ts，逐条写入 passed / blocked / failed；
 * - provenance 固定为 stub。blocked 表示现行契约或桩做不到，不是通过；
 * - 正式验收仍要 harness-core 在真实端口上重跑（provenance=harness-core，--require-pass）。
 *
 * 默认使用固定时间戳保证重跑内容不变；`--now` 写入当前时间。
 */

import { writeFile } from "node:fs/promises";
import { DEFAULT_RESULTS_FILE, loadCases, loadContractVersion } from "./conformance.mjs";
import { runStubConformance } from "../tests/conformance-run.ts";

function parseArgs(argv) {
  const args = { out: DEFAULT_RESULTS_FILE, now: false };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--out") args.out = argv[(i += 1)];
    else if (arg === "--now") args.now = true;
    else if (arg === "--help" || arg === "-h") {
      console.log("用法: node scripts/gen-stub-results.mjs [--out <path>] [--now]");
      process.exit(0);
    }
  }
  return args;
}

const args = parseArgs(process.argv.slice(2));
const cases = await loadCases();
if (cases.length === 0) {
  console.error("未能从 contracts/conformance/cases.yaml 解析出任何用例");
  process.exit(2);
}
const contractVersion = await loadContractVersion();
const results = await runStubConformance();
if (results.length !== cases.length || results.some((item, index) => item.case_id !== cases[index].id)) {
  console.error("运行结果与 cases.yaml 的用例顺序或编号不一致");
  process.exit(2);
}

const doc = {
  schema_version: "0.1",
  contract_version: contractVersion,
  generated_at: args.now ? new Date().toISOString() : "2026-11-03T00:00:00.000Z",
  provenance: "stub",
  run_context: {
    env: "本工程本地桩 adapters/stub（声明 degraded，仅供本地开发）",
    runner: "node scripts/gen-stub-results.mjs（执行 tests/conformance-run.ts）",
    notes:
      "用例文案与端口契约的对应：POLICY_DENIED 为 PERMISSION_DENIED 或 authorize=DENY；" +
      "INVALID_REQUEST 为 INVALID_ARGUMENT；submitted 为 queued 且带 submittedAt。" +
      "blocked 不是通过。正式验收须由 harness-core 以 provenance=harness-core 重跑，并用 --require-pass。",
  },
  results,
};

await writeFile(args.out, `${JSON.stringify(doc, null, 2)}\n`, "utf8");
const counts = { passed: 0, failed: 0, pending: 0, blocked: 0 };
for (const item of results) counts[item.status] += 1;
console.log(`已写出 ${args.out}`);
console.log(
  `用例 ${results.length} 条，contract_version=${contractVersion}，passed ${counts.passed}，blocked ${counts.blocked}，failed ${counts.failed}，pending ${counts.pending}`,
);
if (counts.failed > 0) {
  for (const item of results.filter((entry) => entry.status === "failed")) {
    console.error(`  ${item.case_id}: ${item.notes ?? ""}`);
  }
  process.exit(1);
}
console.log("提醒：provenance=stub。blocked 与 failed 都不是验收通过；harness-core 须重跑后才能 --require-pass。");
