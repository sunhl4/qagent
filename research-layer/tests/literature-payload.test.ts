import { test } from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

import { buildLiteratureCorpus, compileMethodCard } from "../packages/domain/src/index.ts";
import type { MethodCard, PaperRecord, CitationEdge } from "../packages/domain/src/index.ts";
import { loadSchema, validateJsonSchema } from "./schema-validator.ts";

const payload = JSON.parse(
  await readFile(new URL("../examples/literature-plugin-payload.example.json", import.meta.url), "utf8"),
);

test("文献插件样例符合载荷 schema，方法卡可编译", async () => {
  const envelope = await loadSchema("literature-plugin-payload.schema.json");
  assert.deepEqual(validateJsonSchema(payload, envelope), []);

  const cardSchema = await loadSchema("method-card.schema.json");
  assert.equal(payload.method_cards.length, 1);
  assert.deepEqual(validateJsonSchema(payload.method_cards[0], cardSchema), []);

  const compiled = compileMethodCard(payload.method_cards[0] as MethodCard);
  assert.equal(compiled.ok, true, JSON.stringify(compiled.errors));
  assert.deepEqual(compiled.errors, []);
});

test("文献插件样例可直接进入语料去重：预印本合并，标题冲突只进人工确认", () => {
  const built = buildLiteratureCorpus({
    corpus_id: "CORPUS-PLUGIN",
    records: payload.records as PaperRecord[],
    edges: payload.edges as CitationEdge[],
    now: new Date("2026-11-03T00:00:00.000Z"),
  });
  assert.equal(built.ok, true, JSON.stringify(built.findings));
  assert.equal(built.corpus?.papers.length, 3);
  const merged = built.corpus?.papers.find((item) => item.paper.paper_id === "P-2401");
  assert.ok(merged);
  assert.equal(merged.versions.length, 1);
  assert.equal(merged.versions[0].paper_id, "P-arxiv");
  assert.ok(merged.merge_reasons.includes("arxiv_link"));
  assert.deepEqual(
    built.corpus?.review_candidates.map((item) => item.paper_ids),
    [["P-dup-a", "P-dup-b"]],
  );
});
