import { test } from "node:test";
import assert from "node:assert/strict";

import type { ArtifactStorePort, PortResult, ArtifactRef } from "../contracts/src/index.ts";
import { fail } from "../contracts/src/index.ts";
import { createStubStack, StubArtifactStorePort } from "../adapters/stub/src/index.ts";
import type { PaperRecord } from "../packages/domain/src/index.ts";
import { assembleMethodCard, ingestLiterature } from "../packages/pipeline/src/index.ts";
import { loadSchema, validateJsonSchema } from "./schema-validator.ts";

const NOW = new Date("2026-11-02T08:00:00.000Z");

function paperRecord(overrides: Partial<PaperRecord> & { paper_id: string }): PaperRecord {
  return {
    title: "示例论文标题",
    authors: ["A. Author"],
    year: 2026,
    source: "openalex",
    topics: [],
    ...overrides,
  };
}

function makeBaseCard() {
  return {
    paper: {
      paper_id: "P-1",
      title: "示例论文标题",
      authors: ["A. Author"],
      year: 2026,
      doi: "10.0/x",
      arxiv_id: null,
      venue: "ICML",
      source: "openalex",
      code_url: "https://github.com/x",
    },
    problem: "示例问题",
    method_summary: "示例方法概述",
    claims: ["方法 A 在数据集 D 上达到指标 M"],
    metrics: [{ name: "accuracy", direction: "maximize" as const }],
    baselines: ["基线 B"],
    hyperparameters: [{ name: "lr", value: 0.001 }],
    datasets: ["示例数据集"],
    reproduction_status: "not_attempted" as const,
    evidence_locations: [{ type: "table" as const, location: "Table 2", quote: "acc 90.1", ref: null }],
  };
}

test("文献编排：方法卡组装并补齐 ID/时间/版本", async () => {
  const assembled = assembleMethodCard(makeBaseCard(), { method_card_id: "MC-1", created_at: NOW });
  assert.equal(assembled.ok, true, JSON.stringify(assembled.errors));
  assert.equal(assembled.card!.method_card_id, "MC-1");
  assert.equal(assembled.card!.created_at, "2026-11-02T08:00:00.000Z");
  assert.equal(assembled.card!.revision, 1);

  const schema = await loadSchema("method-card.schema.json");
  assert.deepEqual(validateJsonSchema(assembled.card, schema), []);
});

test("文献编排：缺少证据定位时组装失败且不返回卡片", () => {
  const assembled = assembleMethodCard(
    { ...makeBaseCard(), evidence_locations: [] },
    { method_card_id: "MC-2", created_at: NOW },
  );
  assert.equal(assembled.ok, false);
  assert.equal(assembled.card, undefined);
  assert.ok(assembled.errors.some((item) => item.code === "E_METHOD_CARD_EVIDENCE"));
});

test("文献编排：语料与人工确认清单写入 ArtifactStore", async () => {
  const stack = createStubStack();
  const result = await ingestLiterature(
    {
      corpus_id: "CORPUS-1",
      records: [
        paperRecord({ paper_id: "P1", doi: "10.1/a", arxiv_id: "2401.00001", topics: ["contrastive"] }),
        paperRecord({ paper_id: "P2", arxiv_id: "2401.00001", source: "arxiv" }),
        paperRecord({ paper_id: "P3", doi: "10.1/c", title: "Same Title", authors: ["Bob"], year: 2025, venue: null }),
        paperRecord({ paper_id: "P4", doi: "10.1/d", title: "Same Title", authors: ["Bob"], year: 2025, venue: null }),
      ],
      edges: [{ from_paper_id: "P1", to_paper_id: "P3", direction: "backward" }],
    },
    { artifacts: stack.artifacts, now: () => NOW },
    { tenantId: "tenant-demo", projectId: "project-demo" },
  );

  assert.equal(result.ok, true, JSON.stringify(result.findings));
  assert.equal(result.corpus!.papers.length, 3);
  assert.ok(result.reviewRef!.uri.includes("literature/CORPUS-1/review-candidates.md"));
  assert.ok(result.findings.some((item) => item.code === "W_LIT_REVIEW"));

  const readJson = await stack.artifacts.get({ tenantId: "tenant-demo", uri: result.jsonRef!.uri });
  assert.equal(readJson.ok, true);
  if (readJson.ok) {
    const corpus = JSON.parse(new TextDecoder().decode(readJson.value.bytes));
    const schema = await loadSchema("literature-corpus.schema.json");
    assert.deepEqual(validateJsonSchema(corpus, schema), []);
  }

  const readMd = await stack.artifacts.get({ tenantId: "tenant-demo", uri: result.reviewRef!.uri });
  assert.equal(readMd.ok, true);
  if (readMd.ok) {
    const markdown = new TextDecoder().decode(readMd.value.bytes);
    assert.ok(markdown.includes("P3, P4"));
    assert.ok(markdown.includes("same_title_author_year"));
  }
});

test("文献编排：产物写入失败只告警，语料照常返回", async () => {
  const failingPort: ArtifactStorePort = {
    describe: () => new StubArtifactStorePort().describe(),
    get: (request) => new StubArtifactStorePort().get(request),
    put: async (): Promise<PortResult<ArtifactRef>> => fail("UNAVAILABLE", "存储不可用"),
  };
  const result = await ingestLiterature(
    {
      corpus_id: "CORPUS-2",
      records: [paperRecord({ paper_id: "P1", doi: "10.1/a" })],
    },
    { artifacts: failingPort, now: () => NOW },
    { tenantId: "tenant-demo" },
  );

  assert.equal(result.ok, true, JSON.stringify(result.findings));
  assert.ok(result.corpus);
  assert.ok(result.findings.some((item) => item.code === "W_LIT_INGEST_JSON"));
  assert.ok(result.findings.some((item) => item.code === "W_LIT_INGEST_MD"));
  assert.equal(result.jsonRef, undefined);
});

test("文献编排：非法记录导致语料阶段失败", async () => {
  const stack = createStubStack();
  const result = await ingestLiterature(
    {
      corpus_id: "CORPUS-3",
      records: [paperRecord({ paper_id: "", title: "缺 ID" })],
    },
    { artifacts: stack.artifacts, now: () => NOW },
    { tenantId: "tenant-demo" },
  );
  assert.equal(result.ok, false);
  assert.equal(result.corpus, undefined);
  assert.ok(result.findings.some((item) => item.severity === "error"));
});
