import { test } from "node:test";
import assert from "node:assert/strict";

import type { PaperRecord } from "../packages/domain/src/index.ts";
import { buildLiteratureCorpus, deduplicatePapers } from "../packages/domain/src/index.ts";
import { loadSchema, validateJsonSchema } from "./schema-validator.ts";

const NOW = new Date("2026-11-02T00:00:00.000Z");

function record(overrides: Partial<PaperRecord> & { paper_id: string }): PaperRecord {
  return {
    title: "示例论文标题",
    authors: ["A. Author"],
    year: 2026,
    source: "openalex",
    topics: [],
    ...overrides,
  };
}

test("文献去重：相同 DOI 合并，较新年份为主记录", () => {
  const result = deduplicatePapers([
    record({ paper_id: "P1", doi: "10.1/a", year: 2024, venue: "Workshop" }),
    record({ paper_id: "P2", doi: "https://doi.org/10.1/A", year: 2025, venue: "Journal" }),
    record({ paper_id: "P3", doi: "10.1/b", year: 2025, title: "另一篇论文" }),
  ]);

  assert.equal(result.ok, true, JSON.stringify(result.findings));
  assert.equal(result.merged.length, 2);
  const first = result.merged.find((merged) => merged.paper.paper_id === "P2");
  assert.ok(first);
  assert.equal(first!.paper.year, 2025);
  assert.deepEqual(first!.versions.map((version) => version.paper_id), ["P1"]);
  assert.ok(first!.merge_reasons.includes("doi_match"));
  assert.equal(result.review_candidates.length, 0);
});

test("文献去重：arXiv 预印本并入正式版；标题相似进入人工确认", () => {
  const result = deduplicatePapers([
    record({ paper_id: "P1", doi: "10.1/a", arxiv_id: "2401.00001", year: 2024 }),
    record({ paper_id: "P2", arxiv_id: "2401.00001", year: 2023, source: "arxiv" }),
    record({ paper_id: "P3", doi: "10.1/c", title: "Same Title Here", authors: ["Bob"], year: 2025 }),
    record({ paper_id: "P4", doi: "10.1/d", title: "Same Title Here", authors: ["Bob"], year: 2025 }),
    record({ paper_id: "P5", title: "Preprint Only", authors: ["Cara"], year: 2026, source: "arxiv" }),
    record({ paper_id: "P6", title: "Preprint Only", authors: ["Cara"], year: 2026, source: "arxiv" }),
  ]);

  assert.equal(result.ok, true, JSON.stringify(result.findings));

  const mergedPaper = result.merged.find((merged) => merged.paper.paper_id === "P1");
  assert.ok(mergedPaper);
  assert.ok(mergedPaper!.merge_reasons.includes("arxiv_link"));
  assert.deepEqual(mergedPaper!.versions.map((version) => version.paper_id), ["P2"]);

  assert.equal(result.review_candidates.length, 2);
  const candidateIds = result.review_candidates.flatMap((candidate) => candidate.paper_ids);
  assert.ok(candidateIds.includes("P3") && candidateIds.includes("P4"));
  assert.ok(candidateIds.includes("P5") && candidateIds.includes("P6"));
  assert.ok(result.findings.some((item) => item.code === "W_LIT_REVIEW"));
});

test("文献去重：非法记录被排除", () => {
  const result = deduplicatePapers([
    record({ paper_id: "", title: "缺 ID" }),
    record({ paper_id: "P9", title: "缺年份", year: Number.NaN }),
    record({ paper_id: "P10", title: "合法记录" }),
  ]);
  assert.equal(result.ok, false);
  assert.equal(result.findings.filter((item) => item.severity === "error").length, 2);
  assert.equal(result.merged.length, 1);
  assert.equal(result.merged[0].paper.paper_id, "P10");
});

test("语料：引用边解析到主记录，未知端点告警并跳过", async () => {
  const built = buildLiteratureCorpus({
    corpus_id: "CORPUS-1",
    records: [
      record({ paper_id: "P1", doi: "10.1/a", arxiv_id: "2401.00001", topics: ["contrastive"] }),
      record({ paper_id: "P2", arxiv_id: "2401.00001", topics: ["contrastive"], source: "arxiv" }),
      record({ paper_id: "P3", doi: "10.1/c" }),
    ],
    edges: [
      { from_paper_id: "P1", to_paper_id: "P3", direction: "backward" },
      { from_paper_id: "P2", to_paper_id: "P1", direction: "forward" },
      { from_paper_id: "NOPE", to_paper_id: "P1", direction: "backward" },
    ],
    now: NOW,
  });

  assert.equal(built.ok, true, JSON.stringify(built.findings));
  const corpus = built.corpus!;
  assert.equal(corpus.papers.length, 2);
  assert.equal(corpus.citations.length, 1);
  assert.deepEqual(
    corpus.citations.map((edge) => `${edge.from_paper_id}->${edge.to_paper_id}`),
    ["P1->P3"],
  );
  assert.ok(built.findings.some((item) => item.code === "W_LIT_EDGE_UNKNOWN"));
  assert.ok(built.findings.some((item) => item.code === "W_LIT_EDGE_SELF"));

  const sameTopic = corpus.clusters.find((cluster) => cluster.topic === "contrastive");
  assert.ok(sameTopic);
  assert.deepEqual(sameTopic!.paper_ids, ["P1"]);

  const schema = await loadSchema("literature-corpus.schema.json");
  assert.deepEqual(validateJsonSchema(corpus, schema), []);
});
