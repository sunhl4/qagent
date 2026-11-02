import { test } from "node:test";
import assert from "node:assert/strict";
import { existsSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { spawnSync } from "node:child_process";

import {
  createExperimentWorktree,
  removeExperimentWorktree,
  worktreeLocation,
} from "../packages/workspace/src/index.ts";
import type { Subject } from "../contracts/src/index.ts";
import { createStubStack } from "../adapters/stub/src/index.ts";
import type { ExperimentSpec } from "../packages/domain/src/index.ts";
import { runExperimentLoop } from "../packages/pipeline/src/index.ts";
import { loadSchema, validateJsonSchema } from "./schema-validator.ts";

const gitAvailable =
  spawnSync("git", ["--version"], { encoding: "utf8" }).status === 0;
const skip = gitAvailable ? false : "本机没有 git，跳过 worktree 测试";

function git(cwd: string, args: string[]): string {
  const result = spawnSync("git", args, { cwd, encoding: "utf8" });
  assert.equal(result.status, 0, result.stderr);
  return (result.stdout ?? "").trim();
}

function makeRepo(): string {
  const dir = mkdtempSync(join(tmpdir(), "research-worktree-"));
  git(dir, ["init", "-b", "main"]);
  git(dir, ["config", "user.email", "test@example.com"]);
  git(dir, ["config", "user.name", "Test"]);
  git(dir, ["config", "commit.gpgsign", "false"]);
  writeFileSync(join(dir, "README.md"), "# test\n");
  git(dir, ["add", "README.md"]);
  git(dir, ["commit", "-m", "init"]);
  return dir;
}

function cleanup(path: string): void {
  rmSync(path, { recursive: true, force: true });
}

test("worktree：位置由实验与尝试号确定性派生", () => {
  const location = worktreeLocation({
    repoRoot: "/tmp/example-repo",
    experiment_id: "EXP-1",
    attempt: 2,
  });
  assert.equal(location.ok, true);
  if (!location.ok) return;
  assert.equal(location.value.branch, "exp/exp-1/attempt-2");
  assert.ok(location.value.path.endsWith("exp-1-attempt-2"));
  assert.equal(location.value.worktree_id, "EXP-1:attempt-2");

  const relativeBase = worktreeLocation({
    repoRoot: "/tmp/example-repo",
    experiment_id: "EXP-1",
    attempt: 1,
    baseDir: ".custom-worktrees",
  });
  assert.equal(relativeBase.ok, true);
  if (relativeBase.ok) {
    assert.ok(relativeBase.value.path.startsWith("/tmp/example-repo/.custom-worktrees/"));
  }

  const invalidId = worktreeLocation({
    repoRoot: "/tmp/example-repo",
    experiment_id: "..",
    attempt: 1,
  });
  assert.equal(invalidId.ok, false);
  if (!invalidId.ok) assert.equal(invalidId.error.code, "INVALID_ARGUMENT");

  const invalidAttempt = worktreeLocation({
    repoRoot: "/tmp/example-repo",
    experiment_id: "EXP-1",
    attempt: 0,
  });
  assert.equal(invalidAttempt.ok, false);
});

test("worktree：创建后分支、基线与文件正确", { skip }, async () => {
  const repo = makeRepo();
  try {
    const head = git(repo, ["rev-parse", "HEAD"]);
    const created = createExperimentWorktree({
      repoRoot: repo,
      experiment_id: "EXP-1",
      attempt: 1,
    });

    assert.equal(created.ok, true);
    if (!created.ok) return;
    assert.equal(created.value.state, "created");
    assert.equal(created.value.base_commit, head);
    assert.ok(existsSync(join(created.value.path, "README.md")));
    assert.equal(
      git(repo, ["-C", created.value.path, "rev-parse", "--abbrev-ref", "HEAD"]),
      created.value.branch,
    );

    const schema = await loadSchema("worktree-record.schema.json");
    assert.deepEqual(validateJsonSchema(created.value, schema), []);
  } finally {
    cleanup(repo);
  }
});

test("worktree：重复创建复用同一路径", { skip }, () => {
  const repo = makeRepo();
  try {
    const first = createExperimentWorktree({
      repoRoot: repo,
      experiment_id: "EXP-1",
      attempt: 1,
    });
    assert.equal(first.ok, true);
    if (!first.ok) return;

    const second = createExperimentWorktree({
      repoRoot: repo,
      experiment_id: "EXP-1",
      attempt: 1,
    });
    assert.equal(second.ok, true);
    if (!second.ok) return;
    assert.equal(second.value.state, "reused");
    assert.equal(second.value.path, first.value.path);
    assert.equal(second.value.base_commit, first.value.base_commit);
  } finally {
    cleanup(repo);
  }
});

test("worktree：目录缺失但元数据仍在时拒绝复用", { skip }, () => {
  const repo = makeRepo();
  try {
    const first = createExperimentWorktree({
      repoRoot: repo,
      experiment_id: "EXP-STALE",
      attempt: 1,
    });
    assert.equal(first.ok, true);
    if (!first.ok) return;
    rmSync(first.value.path, { recursive: true, force: true });

    const second = createExperimentWorktree({
      repoRoot: repo,
      experiment_id: "EXP-STALE",
      attempt: 1,
    });
    assert.equal(second.ok, false);
    if (!second.ok) assert.equal(second.error.code, "NOT_FOUND");
  } finally {
    cleanup(repo);
  }
});

test("worktree：不同尝试使用不同路径与分支", { skip }, () => {
  const repo = makeRepo();
  try {
    const first = createExperimentWorktree({
      repoRoot: repo,
      experiment_id: "EXP-1",
      attempt: 1,
    });
    const second = createExperimentWorktree({
      repoRoot: repo,
      experiment_id: "EXP-1",
      attempt: 2,
    });
    assert.equal(first.ok, true);
    assert.equal(second.ok, true);
    if (!first.ok || !second.ok) return;
    assert.notEqual(first.value.path, second.value.path);
    assert.notEqual(first.value.branch, second.value.branch);
    assert.ok(existsSync(first.value.path));
    assert.ok(existsSync(second.value.path));
  } finally {
    cleanup(repo);
  }
});

test("worktree：脏工作树拒绝删除，清理后保留分支", { skip }, async () => {
  const repo = makeRepo();
  try {
    const created = createExperimentWorktree({
      repoRoot: repo,
      experiment_id: "EXP-DIRTY",
      attempt: 1,
    });
    assert.equal(created.ok, true);
    if (!created.ok) return;

    writeFileSync(join(created.value.path, "scratch.txt"), "uncommitted\n");
    const refused = removeExperimentWorktree({
      repoRoot: repo,
      experiment_id: "EXP-DIRTY",
      attempt: 1,
    });
    assert.equal(refused.ok, false);
    if (!refused.ok) assert.equal(refused.error.code, "DIRTY");
    assert.ok(existsSync(created.value.path));

    rmSync(join(created.value.path, "scratch.txt"));
    const removed = removeExperimentWorktree({
      repoRoot: repo,
      experiment_id: "EXP-DIRTY",
      attempt: 1,
    });
    assert.equal(removed.ok, true);
    if (!removed.ok) return;
    assert.equal(removed.value.state, "removed");
    assert.equal(existsSync(created.value.path), false);
    assert.notEqual(git(repo, ["branch", "--list", created.value.branch]), "");

    const schema = await loadSchema("worktree-record.schema.json");
    assert.deepEqual(validateJsonSchema(removed.value, schema), []);
  } finally {
    cleanup(repo);
  }
});

test("worktree：清理不存在的尝试是幂等的", { skip }, () => {
  const repo = makeRepo();
  try {
    const removed = removeExperimentWorktree({
      repoRoot: repo,
      experiment_id: "EXP-NONE",
      attempt: 1,
    });
    assert.equal(removed.ok, true);
    if (!removed.ok) return;
    assert.equal(removed.value.state, "absent");
    assert.equal(removed.value.base_commit, null);
  } finally {
    cleanup(repo);
  }
});

test("worktree：分支已存在但未登记时拒绝创建", { skip }, () => {
  const repo = makeRepo();
  try {
    const location = worktreeLocation({
      repoRoot: repo,
      experiment_id: "EXP-BRANCH",
      attempt: 1,
    });
    assert.equal(location.ok, true);
    if (!location.ok) return;
    git(repo, ["branch", location.value.branch]);

    const created = createExperimentWorktree({
      repoRoot: repo,
      experiment_id: "EXP-BRANCH",
      attempt: 1,
    });
    assert.equal(created.ok, false);
    if (!created.ok) assert.equal(created.error.code, "BRANCH_EXISTS");
  } finally {
    cleanup(repo);
  }
});

test("worktree：非 git 仓库与非法 baseRef 返回明确错误", { skip }, () => {
  const plain = mkdtempSync(join(tmpdir(), "research-not-git-"));
  const repo = makeRepo();
  try {
    const notRepo = createExperimentWorktree({
      repoRoot: plain,
      experiment_id: "EXP-1",
      attempt: 1,
    });
    assert.equal(notRepo.ok, false);
    if (!notRepo.ok) assert.equal(notRepo.error.code, "NOT_A_REPOSITORY");

    const badRef = createExperimentWorktree({
      repoRoot: repo,
      experiment_id: "EXP-REF",
      attempt: 1,
      baseRef: "does-not-exist",
    });
    assert.equal(badRef.ok, false);
    if (!badRef.ok) assert.equal(badRef.error.code, "GIT_FAILED");
  } finally {
    cleanup(plain);
    cleanup(repo);
  }
});

test("worktree：空仓库没有提交时返回 NO_COMMITS", { skip }, () => {
  const repo = mkdtempSync(join(tmpdir(), "research-empty-git-"));
  try {
    git(repo, ["init", "-b", "main"]);
    const created = createExperimentWorktree({
      repoRoot: repo,
      experiment_id: "EXP-EMPTY",
      attempt: 1,
    });
    assert.equal(created.ok, false);
    if (!created.ok) assert.equal(created.error.code, "NO_COMMITS");
  } finally {
    cleanup(repo);
  }
});

const agent: Subject = {
  type: "agent",
  id: "agent-worktree",
  tenantId: "tenant-demo",
  projectId: "project-demo",
  scopes: ["experiment:submit"],
};

const environment = {
  containerDigest: `sha256:${"a".repeat(64)}`,
  lockfileHash: "b".repeat(64),
};

function makeExperimentSpec(): ExperimentSpec {
  return {
    experiment_id: "EXP-WT-1",
    task_id: "TASK-WT-1",
    hypothesis: {
      statement: "加入预热可以降低验证损失",
      falsifiable_by: "若验证损失未下降，则假设不成立",
    },
    baseline: {
      name: "无预热基线",
      source: "内部复现",
      reproduced: true,
      metric_value: 1.0,
    },
    variables: {
      changed: ["src/train/scheduler.py"],
      controlled: ["dataset", "split"],
    },
    metrics: {
      primary: "val_loss",
      direction: "minimize",
      minimum_observable_effect: 0.02,
      guardrails: [{ name: "train_time_seconds", max_degradation: 0.1 }],
      repeats: 1,
      seeds: [13],
    },
    resources: {
      type: "gpu",
      count: 1,
      max_wall_clock_seconds: 600,
      max_cost: 5,
      currency: "CNY",
      checkpoint_required: true,
    },
    stopping: { max_attempts: 1, max_consecutive_failures: 1 },
    decision: {
      keep_if: "val_loss 下降 >= 0.02",
      discard_if: "护栏退化超过阈值",
    },
    artifacts: {
      required: ["code_hash", "env_lock", "raw_metrics", "manifest"],
    },
  };
}

test("worktree：接入实验循环并写入 manifest 分支与基线", { skip }, async () => {
  const repo = makeRepo();
  try {
    const head = git(repo, ["rev-parse", "HEAD"]);
    const stack = createStubStack({ compute: { scenario: "success", baseCostPerHour: 24 } });
    const outcome = await runExperimentLoop(
      {
        spec: makeExperimentSpec(),
        subject: agent,
        traceId: "trace-worktree-loop",
        idempotencyKey: "idem-worktree-loop",
        code: { repo: "local/repo", commit: head },
        environment,
        budget: { total: 100, currency: "CNY" },
        baselineGuardrails: { train_time_seconds: 200 },
        workspace: { repoRoot: repo },
      },
      { compute: stack.compute, artifacts: stack.artifacts },
    );

    assert.equal(outcome.state, "kept");
    assert.equal(outcome.worktrees.length, 1);
    const worktree = outcome.worktrees[0];
    assert.ok(existsSync(worktree.path));
    assert.equal(worktree.base_commit, head);

    const manifestUri = outcome.attempts[0].manifest_ref;
    assert.ok(manifestUri);
    const read = await stack.artifacts.get({
      tenantId: agent.tenantId,
      uri: manifestUri!,
    });
    assert.equal(read.ok, true);
    if (read.ok) {
      const manifest = JSON.parse(new TextDecoder().decode(read.value.bytes)) as {
        code: { branch: string; commit: string };
      };
      assert.equal(manifest.code.branch, worktree.branch);
      assert.equal(manifest.code.commit, head);
    }
  } finally {
    cleanup(repo);
  }
});

test("worktree：准备失败时不执行实验", { skip }, async () => {
  const plain = mkdtempSync(join(tmpdir(), "research-loop-no-git-"));
  const stack = createStubStack({ compute: { scenario: "success", baseCostPerHour: 24 } });
  try {
    const outcome = await runExperimentLoop(
      {
        spec: makeExperimentSpec(),
        subject: agent,
        traceId: "trace-worktree-fail",
        idempotencyKey: "idem-worktree-fail",
        code: { repo: "local/repo", commit: "c0ffee" },
        environment,
        budget: { total: 100, currency: "CNY" },
        baselineGuardrails: { train_time_seconds: 200 },
        workspace: { repoRoot: plain },
      },
      { compute: stack.compute, artifacts: stack.artifacts },
    );

    assert.equal(outcome.state, "stopped");
    assert.equal(outcome.attempts.length, 0);
    assert.equal(outcome.worktrees.length, 0);
    assert.ok(outcome.findings.some((finding) => finding.code === "E_WORKTREE"));
  } finally {
    cleanup(plain);
  }
});
