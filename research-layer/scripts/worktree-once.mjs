import { readFileSync } from "node:fs";

const moduleUrl = new URL("../packages/workspace/src/worktree.ts", import.meta.url);
const mod = await import(moduleUrl.href);
const input = JSON.parse(readFileSync(0, "utf8"));
const fn = input.action === "remove" ? mod.removeExperimentWorktree : mod.createExperimentWorktree;
const result = fn({
  repoRoot: input.repoRoot,
  experiment_id: input.experiment_id,
  attempt: input.attempt,
  timeoutMs: 15000,
});
process.stdout.write(JSON.stringify(result));
