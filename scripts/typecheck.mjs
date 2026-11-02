#!/usr/bin/env node
/**
 * 契约与包的类型/可加载性检查。
 *
 * 优先使用本地 tsc（若安装）；否则退化为：
 * 1. 检查所有 .ts 文件不含 Node 类型擦除不支持的结构（enum、namespace、parameter properties）。
 * 2. 动态 import 每个入口，确保模块图可解析、可执行。
 *
 * 这不是完整类型检查，但能在离线环境捕获绝大多数破坏性错误。
 */

import { readdir, readFile } from "node:fs/promises";
import { join, relative } from "node:path";
import { pathToFileURL } from "node:url";
import { spawnSync } from "node:child_process";

const root = new URL("..", import.meta.url).pathname;

async function walk(dir) {
  const entries = await readdir(dir, { withFileTypes: true });
  const files = [];
  for (const entry of entries) {
    if (entry.name === "node_modules" || entry.name === ".git") continue;
    const full = join(dir, entry.name);
    if (entry.isDirectory()) {
      files.push(...(await walk(full)));
    } else if (entry.name.endsWith(".ts")) {
      files.push(full);
    }
  }
  return files;
}

function tryTsc() {
  const candidates = [
    join(root, "node_modules", ".bin", "tsc"),
    join(root, "node_modules", "typescript", "bin", "tsc"),
  ];
  for (const candidate of candidates) {
    const result = spawnSync(candidate, ["--noEmit", "-p", join(root, "tsconfig.json")], {
      stdio: "inherit",
    });
    if (result.error) continue;
    return result.status === 0;
  }
  return null;
}

const failures = [];

const tscResult = tryTsc();
if (tscResult === null) {
  console.log("[跳过] 本地未安装 tsc，使用降级检查（语法擦除兼容性 + 模块可加载性）");
} else if (tscResult === false) {
  console.error("tsc 类型检查失败");
  process.exit(1);
} else {
  console.log("tsc 类型检查通过");
}

const files = await walk(root);
const forbidden = [
  { pattern: /^\s*export\s+enum\s/m, name: "enum" },
  { pattern: /^\s*enum\s/m, name: "enum" },
  { pattern: /^\s*namespace\s/m, name: "namespace" },
  { pattern: /constructor\s*\([^)]*(public|private|protected|readonly)\s+/m, name: "parameter property" },
];

for (const file of files) {
  const text = await readFile(file, "utf8");
  for (const rule of forbidden) {
    if (rule.pattern.test(text)) {
      failures.push(`${relative(root, file)} 使用了 Node 类型擦除不支持的结构: ${rule.name}`);
    }
  }
}

const entries = [
  "contracts/src/index.ts",
  "packages/domain/src/index.ts",
  "packages/pipeline/src/index.ts",
  "packages/workspace/src/index.ts",
  "adapters/stub/src/index.ts",
];

for (const entry of entries) {
  const full = join(root, entry);
  try {
    await import(pathToFileURL(full).href + `?t=${Date.now()}`);
  } catch (error) {
    failures.push(`${entry} 无法加载: ${error instanceof Error ? error.message : String(error)}`);
  }
}

if (failures.length > 0) {
  console.error("\n检查失败：");
  for (const failure of failures) console.error(`  - ${failure}`);
  process.exit(1);
}

console.log(`契约与包检查通过（${files.length} 个 .ts 文件）`);
