import { test } from "node:test";
import assert from "node:assert/strict";

import { readFile } from "node:fs/promises";

import type { MethodCard, ReproductionCandidateInput } from "../packages/domain/src/index.ts";
import {
  admitCodeChange,
  buildReproductionReport,
  compileMethodCard,
  compileReproductionCandidate,
} from "../packages/domain/src/index.ts";
import { loadSchema, validateJsonSchema } from "./schema-validator.ts";

const NOW = "2026-11-02T00:00:00.000Z";

function makeCard(overrides: Partial<MethodCard> = {}): MethodCard {
  return {
    method_card_id: "MC-2026-001",
    paper: {
      paper_id: "P-1",
      title: "示例论文标题",
      authors: ["A. Author", "B. Author"],
      year: 2026,
      doi: "10.0000/example",
      arxiv_id: "2601.00000",
      venue: "Example Venue",
      source: "openalex",
      code_url: "https://github.com/example/repo",
    },
    problem: "示例问题",
    method_summary: "示例方法概述",
    claims: ["方法 A 在数据集 D 上达到指标 M"],
    inputs: ["图像"],
    outputs: ["分类标签"],
    datasets: ["示例数据集"],
    preprocessing: ["标准化"],
    model_or_algorithm: "示例模型",
    hyperparameters: [{ name: "learning_rate", value: 0.001 }],
    baselines: ["基线 B"],
    metrics: [{ name: "accuracy", direction: "maximize" }],
    train_test_split: "按论文 8:1:1",
    hardware: "A100-40GB",
    runtime: "2 GPU-hour",
    reproduction_status: "not_attempted",
    evidence_locations: [
      { type: "table", location: "Table 2", quote: "acc 90.1", ref: null },
    ],
    created_at: NOW,
    ...overrides,
  };
}

test("方法卡：合法记录通过 schema 与编译", async () => {
  const card = makeCard();
  const compiled = compileMethodCard(card);
  assert.equal(compiled.ok, true, JSON.stringify(compiled.errors));
  assert.equal(compiled.warnings.length, 0, JSON.stringify(compiled.warnings));

  const schema = await loadSchema("method-card.schema.json");
  assert.deepEqual(validateJsonSchema(card, schema), []);
});

test("方法卡：缺少证据定位被硬性拒绝", () => {
  const compiled = compileMethodCard(makeCard({ evidence_locations: [] }));
  assert.equal(compiled.ok, false);
  assert.ok(compiled.errors.some((item) => item.code === "E_METHOD_CARD_EVIDENCE"));
});

test("方法卡：缺失基线/代码/数据集/超参给出警告但通过", () => {
  const compiled = compileMethodCard(
    makeCard({
      baselines: [],
      hyperparameters: [],
      datasets: [],
      original_code_url: null,
      paper: { ...makeCard().paper, code_url: null },
    }),
  );
  assert.equal(compiled.ok, true);
  const codes = compiled.warnings.map((item) => item.code);
  assert.ok(codes.includes("W_METHOD_CARD_NO_BASELINES"));
  assert.ok(codes.includes("W_METHOD_CARD_NO_HYPERPARAMS"));
  assert.ok(codes.includes("W_METHOD_CARD_NO_CODE"));
});

function candidate(overrides: Partial<ReproductionCandidateInput> = {}): ReproductionCandidateInput {
  return {
    method_card: makeCard({
      evidence_locations: [
        { type: "equation", location: "eq:energy", quote: "E \\approx E_0", ledger_id: "F-energy" },
      ],
      missing_information: [],
    }),
    metrics: [
      { name: "val_loss", unit: "dimensionless", platform_metric_eligible: true, tolerance: 0.01 },
    ],
    train_test_split: "fixed validation split",
    code_availability: "official",
    code_commit: "0123456789abcdef",
    attachments: [{ attachment_id: "A-log", parsed: true, claim_ids: ["C1"] }],
    ...overrides,
  };
}

test("方法卡：补充材料、数据文件和账本编号仍能通过宽松编译", async () => {
  const card = makeCard({
    evidence_locations: [
      { type: "supplement", location: "supplement.tex", quote: "附录公式", ledger_id: null },
      { type: "data_file", location: "results.csv", quote: null, ledger_id: null },
    ],
  });
  assert.equal(compileMethodCard(card).ok, true);
  const schema = await loadSchema("method-card.schema.json");
  assert.deepEqual(validateJsonSchema(card, schema), []);
});

test("方法卡：引用超过 500 字不能通过 schema", async () => {
  const card = makeCard({
    evidence_locations: [{ type: "table", location: "Table 1", quote: "x".repeat(501) }],
  });
  const schema = await loadSchema("method-card.schema.json");
  assert.ok(validateJsonSchema(card, schema).some((item) => item.includes("500")));
});

test("复现候选：合法记录通过，且不进入研究时钟", async () => {
  const input = candidate();
  const compiled = compileReproductionCandidate(input);
  assert.equal(compiled.ok, true, JSON.stringify(compiled.errors));
  assert.equal(compiled.platform_metric_eligible, true);
  assert.equal(compiled.clock_admitted, false);

  const example = JSON.parse(
    await readFile(new URL("../examples/reproduction-candidate.example.json", import.meta.url), "utf8"),
  ) as ReproductionCandidateInput;
  const fromExample = compileReproductionCandidate(example);
  assert.equal(fromExample.ok, true, JSON.stringify(fromExample.errors));
  const cardSchema = await loadSchema("method-card.schema.json");
  assert.deepEqual(validateJsonSchema(example.method_card, cardSchema), []);
});

test("复现候选：缺锚点、账本、单位、容差、划分、commit 或未解析附件时失败", () => {
  const noAnchor = compileReproductionCandidate(
    candidate({
      method_card: makeCard({
        evidence_locations: [{ type: "abstract", location: "abstract" }],
      }),
    }),
  );
  assert.ok(noAnchor.errors.some((item) => item.code === "E_CANDIDATE_ANCHOR"));

  const noLedger = compileReproductionCandidate(
    candidate({
      method_card: makeCard({
        evidence_locations: [{ type: "equation", location: "eq:energy", ledger_id: null }],
      }),
    }),
  );
  assert.ok(noLedger.errors.some((item) => item.code === "E_CANDIDATE_LEDGER"));

  const noUnit = compileReproductionCandidate(
    candidate({ metrics: [{ name: "mHa", unit: "", platform_metric_eligible: false, tolerance: 0.1 }] }),
  );
  assert.ok(noUnit.errors.some((item) => item.code === "E_CANDIDATE_UNIT"));

  const badPlatformUnit = compileReproductionCandidate(
    candidate({
      metrics: [{ name: "energy", unit: "mHa", platform_metric_eligible: true, tolerance: 0.1 }],
    }),
  );
  assert.ok(badPlatformUnit.errors.some((item) => item.code === "E_CANDIDATE_UNIT"));

  const noTolerance = compileReproductionCandidate(
    candidate({
      metrics: [
        {
          name: "val_loss",
          unit: "dimensionless",
          platform_metric_eligible: true,
          tolerance: Number.NaN,
        },
      ],
    }),
  );
  assert.ok(noTolerance.errors.some((item) => item.code === "E_CANDIDATE_TOLERANCE"));

  const noSplit = compileReproductionCandidate(
    candidate({
      train_test_split: "",
      method_card: makeCard({
        train_test_split: null,
        evidence_locations: [
          { type: "table", location: "Table 1", quote: "1.0", ledger_id: null },
        ],
      }),
    }),
  );
  assert.ok(noSplit.errors.some((item) => item.code === "E_CANDIDATE_SPLIT"));

  const noCommit = compileReproductionCandidate(candidate({ code_commit: "" }));
  assert.ok(noCommit.errors.some((item) => item.code === "E_CANDIDATE_COMMIT"));

  const noMissing = compileReproductionCandidate(
    candidate({
      code_availability: "none",
      code_commit: null,
      method_card: makeCard({
        missing_information: [],
        evidence_locations: [{ type: "table", location: "Table 1" }],
      }),
    }),
  );
  assert.ok(noMissing.errors.some((item) => item.code === "E_CANDIDATE_MISSING_CODE"));

  const unparsed = compileReproductionCandidate(
    candidate({ attachments: [{ attachment_id: "A-si", parsed: false, claim_ids: ["C1"] }] }),
  );
  assert.ok(unparsed.errors.some((item) => item.code === "E_CANDIDATE_ATTACHMENT"));
});

test("复现候选：化学误差可以留下但不能进入平台指标", () => {
  const compiled = compileReproductionCandidate(
    candidate({
      metrics: [{ name: "energy", unit: "mHa", platform_metric_eligible: false, tolerance: 1 }],
    }),
  );
  assert.equal(compiled.ok, true, JSON.stringify(compiled.errors));
  assert.equal(compiled.platform_metric_eligible, false);
  assert.equal(compiled.clock_admitted, false);
});

test("三本账 schema 接受合成条目", async () => {
  const formula = await loadSchema("formula-ledger.schema.json");
  assert.deepEqual(
    validateJsonSchema(
      {
        ledger_id: "F-energy",
        paper_id: "demo",
        source_kind: "arxiv_src",
        version: "v1",
        anchor: "eq:energy",
        tex: "E \\approx E_0",
        role: "definition",
        fidelity: "copied",
      },
      formula,
    ),
    [],
  );
  const attachment = await loadSchema("attachment-ledger.schema.json");
  assert.deepEqual(
    validateJsonSchema(
      {
        attachment_id: "A-si",
        paper_id: "demo",
        source_kind: "arxiv_src",
        version: "v1",
        kind: "proof",
        name: "supplement.tex",
        parsed: false,
        anchor: "supplement.tex",
      },
      attachment,
    ),
    [],
  );
  const code = await loadSchema("code-ledger.schema.json");
  assert.deepEqual(
    validateJsonSchema(
      {
        code_id: "C-demo",
        paper_id: "demo",
        source_kind: "arxiv_src",
        version: "v1",
        availability: "official",
        url: "https://github.com/example/demo",
        commit: "0123456789abcdef",
        license: null,
        missing_information: [],
      },
      code,
    ),
    [],
  );
});

test("内部基线：val_loss 方法卡可以编出容差内的复现报告", () => {
  const card = makeCard({
    method_card_id: "MC-VAL-BASE",
    problem: "内部验证损失",
    method_summary: "日志行 val_loss=<数字>",
    claims: ["val_loss 落在 0.01 内"],
    metrics: [{ name: "val_loss", direction: "minimize" }],
    train_test_split: "fixed validation split",
    evidence_locations: [
      { type: "code_line", location: "train.log val_loss=<number>", quote: "val_loss=1.0" },
    ],
  });
  assert.equal(compileMethodCard(card).ok, true);
  const report = buildReproductionReport({
    reproduction_id: "REP-VAL",
    task_id: "TASK-VAL",
    paper: { title: card.paper.title, doi: null, arxiv_id: null, code_url: card.paper.code_url },
    difficulty: {
      code_available: "official",
      data_available: "public",
      hyperparameters_complete: "complete",
      compute_requirement: "single_gpu",
      dependency_risk: "standard",
      evaluation_clarity: "script_available",
    },
    environment: { lockfile_hash: "a".repeat(64), hardware: "cpu" },
    data: { source: "internal log", split: card.train_test_split },
    runs: [
      {
        run_id: "R1",
        name: "baseline",
        seeds: [1],
        status: "succeeded",
        metric_name: "val_loss",
        values: [1.0],
      },
    ],
    claims: [
      {
        claim_id: "C-val",
        claim: "val_loss = 1.0",
        metric_name: "val_loss",
        original_value: 1.0,
        tolerance: 0.01,
      },
    ],
    semantic_checks: [{ item: "日志行格式为 val_loss=<number>", passed: true }],
    generality_checks: [{ setting: "同一划分另一随机种子方向一致", direction_consistent: true }],
    differences: [],
    created_at: new Date(NOW),
  });
  assert.equal(report.ok, true, JSON.stringify(report.errors));
  assert.equal(report.conclusion, "succeeded");
});

test("代码准入：只接收严格候选、commit 和安全路径，并拒绝作者自审", () => {
  const compiled = compileReproductionCandidate(candidate());
  const admitted = admitCodeChange({
    candidate: compiled,
    code_commit: "0123456789ABCDEF",
    changed_path: " src/train/scheduler.py ",
    author_id: "author-a",
    reviewer_id: "reviewer-b",
  });
  assert.equal(admitted.ok, true, JSON.stringify(admitted.errors));
  assert.equal(admitted.changed_path, "src/train/scheduler.py");
  assert.equal(admitted.code_commit, "0123456789abcdef");
  assert.equal(admitted.candidate_ok, true);

  const branch = admitCodeChange({
    candidate: compiled,
    code_commit: "HEAD",
    changed_path: "src/train/scheduler.py",
    author_id: "author-a",
    reviewer_id: "reviewer-b",
  });
  assert.equal(branch.ok, false);
  assert.equal(branch.code_commit, "");
  assert.ok(branch.errors.some((item) => item.code === "E_CODE_COMMIT"));

  const failed = compileReproductionCandidate(
    candidate({ metrics: [{ name: "energy", unit: "mHa", platform_metric_eligible: true, tolerance: 1 }] }),
  );
  assert.equal(admitCodeChange({
    candidate: failed,
    code_commit: "0123456789abcdef",
    changed_path: "src/train/scheduler.py",
    author_id: "author-a",
    reviewer_id: "reviewer-b",
  }).errors.some((item) => item.code === "E_CODE_CANDIDATE"), true);

  const clocked = admitCodeChange({
    candidate: { ...compiled, clock_admitted: true },
    code_commit: "0123456789abcdef",
    changed_path: "src/train/scheduler.py",
    author_id: "author-a",
    reviewer_id: "reviewer-b",
  });
  assert.ok(clocked.errors.some((item) => item.code === "E_CODE_CLOCK"));

  for (const changedPath of ["../secret.py", "/tmp/x.py", "C:/x.py", "src\\x.py", "src/../secret.py", "src/foo bar.py", "a".repeat(121)]) {
    const rejected = admitCodeChange({
      candidate: compiled,
      code_commit: "0123456789abcdef",
      changed_path: changedPath,
      author_id: "author-a",
      reviewer_id: "reviewer-b",
    });
    assert.equal(rejected.ok, false, changedPath);
    assert.equal(rejected.changed_path, "");
    assert.ok(rejected.errors.some((item) => item.code === "E_CODE_PATH"));
  }

  const selfReview = admitCodeChange({
    candidate: compiled,
    code_commit: "0123456789abcdef",
    changed_path: "src/train/scheduler.py",
    author_id: "author-a",
    reviewer_id: "Author-A",
  });
  assert.equal(selfReview.ok, false);
  assert.ok(selfReview.errors.some((item) => item.code === "E_CODE_SELF_REVIEW"));

  const missingReview = admitCodeChange({
    candidate: compiled,
    code_commit: "",
    changed_path: "src/train/scheduler.py",
    author_id: "author-a",
    reviewer_id: "",
  });
  assert.ok(missingReview.errors.some((item) => item.code === "E_CODE_COMMIT"));
  assert.ok(missingReview.errors.some((item) => item.code === "E_CODE_REVIEWER"));
});

test("方法卡：核心字段缺失被逐项拒绝", () => {
  const missingTitle = compileMethodCard(makeCard({ paper: { ...makeCard().paper, title: "" } }));
  assert.equal(missingTitle.ok, false);
  assert.ok(missingTitle.errors.some((item) => item.code === "E_METHOD_CARD_TITLE"));

  const missingSummary = compileMethodCard(makeCard({ method_summary: "" }));
  assert.equal(missingSummary.ok, false);
  assert.ok(missingSummary.errors.some((item) => item.code === "E_METHOD_CARD_SUMMARY"));
});
