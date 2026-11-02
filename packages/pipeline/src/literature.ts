/**
 * 文献阶段编排：方法卡组装、语料落盘与人工确认清单。
 *
 * 检索与字段抽取仍由文献插件完成（联网、GROBID/Marker 等外部工具），
 * 本模块只做降级路径上的编排：
 * - 方法卡：把插件抽取的字段组装成完整记录并过编译校验（证据定位硬规则）。
 * - 语料：去重 → 写入 ArtifactStore（corpus.json + review-candidates.md）。
 * - 写入失败返回 finding，不抛异常；产物按幂等键重复写入安全。
 */

import type { ArtifactRef, ArtifactStorePort } from "../../../contracts/src/index.ts";
import type { Finding } from "../../domain/src/index.ts";
import type { CitationEdge, LiteratureCorpus, MethodCard, PaperRecord } from "../../domain/src/index.ts";
import { buildLiteratureCorpus, compileMethodCard } from "../../domain/src/index.ts";

export interface MethodCardAssembly {
  method_card_id: string;
  created_at?: Date;
  revision?: number;
}

export interface AssembleMethodCardResult {
  ok: boolean;
  card?: MethodCard;
  errors: Finding[];
  warnings: Finding[];
}

/**
 * 组装方法卡：补齐 ID、时间与版本号，然后过领域编译。
 * 编译失败时不返回 card，调用方必须先处理 errors。
 */
export function assembleMethodCard(
  base: Omit<MethodCard, "method_card_id" | "created_at" | "revision"> &
    Partial<Pick<MethodCard, "method_card_id" | "created_at" | "revision">>,
  meta: MethodCardAssembly,
): AssembleMethodCardResult {
  const card: MethodCard = {
    ...base,
    method_card_id: meta.method_card_id,
    created_at: (meta.created_at ?? new Date()).toISOString(),
    revision: meta.revision ?? 1,
  };
  const compiled = compileMethodCard(card);
  return { ...compiled, card: compiled.ok ? card : undefined };
}

export interface IngestLiteratureInput {
  corpus_id: string;
  records: PaperRecord[];
  edges?: CitationEdge[];
}

export interface IngestLiteratureDeps {
  artifacts: ArtifactStorePort;
  now?: () => Date;
}

export interface IngestLiteratureContext {
  tenantId: string;
  projectId?: string;
}

export interface IngestLiteratureResult {
  ok: boolean;
  corpus?: LiteratureCorpus;
  jsonRef?: ArtifactRef;
  reviewRef?: ArtifactRef;
  findings: Finding[];
}

function finding(
  severity: "error" | "warning",
  code: string,
  message: string,
): Finding {
  return { severity, code, message };
}

function renderReviewCandidates(corpus: LiteratureCorpus): string {
  const lines: string[] = [
    `# 文献人工确认清单：${corpus.corpus_id}`,
    "",
    `生成时间：${corpus.generated_at}`,
    "",
  ];
  if (corpus.review_candidates.length === 0) {
    lines.push("- 无（全部合并均为确定性规则：DOI 相同或 arXiv 直接关联）");
  } else {
    lines.push("| 候选记录 | 原因 |");
    lines.push("|---|---|");
    for (const candidate of corpus.review_candidates) {
      lines.push(`| ${candidate.paper_ids.join(", ")} | ${candidate.reason} |`);
    }
    lines.push("");
    lines.push("以上记录未自动合并；确认后请在源数据中标注关联关系。");
  }
  return `${lines.join("\n")}\n`;
}

/**
 * 去重并把语料与人工确认清单写入 ArtifactStore。
 *
 * ok 的含义：去重与组装成功。产物写入失败只记 warning，
 * 语料本身仍会返回，供调用方继续下游（复现计划）使用。
 */
export async function ingestLiterature(
  input: IngestLiteratureInput,
  deps: IngestLiteratureDeps,
  context: IngestLiteratureContext,
): Promise<IngestLiteratureResult> {
  const findings: Finding[] = [];
  const built = buildLiteratureCorpus({
    corpus_id: input.corpus_id,
    records: input.records,
    edges: input.edges,
    now: deps.now?.(),
  });
  findings.push(...built.findings);
  if (!built.ok || !built.corpus) {
    return { ok: false, findings };
  }
  const corpus = built.corpus;
  const encoder = new TextEncoder();

  const jsonPut = await deps.artifacts.put({
    tenantId: context.tenantId,
    projectId: context.projectId,
    key: `literature/${corpus.corpus_id}/corpus.json`,
    contentType: "application/json",
    bytes: encoder.encode(JSON.stringify(corpus, null, 2)),
    idempotencyKey: `${corpus.corpus_id}:corpus`,
  });
  if (!jsonPut.ok) {
    findings.push(
      finding("warning", "W_LIT_INGEST_JSON", `语料 JSON 写入失败: ${jsonPut.error.code} ${jsonPut.error.message}`),
    );
  }

  const reviewPut = await deps.artifacts.put({
    tenantId: context.tenantId,
    projectId: context.projectId,
    key: `literature/${corpus.corpus_id}/review-candidates.md`,
    contentType: "text/markdown",
    bytes: encoder.encode(renderReviewCandidates(corpus)),
    idempotencyKey: `${corpus.corpus_id}:review`,
  });
  if (!reviewPut.ok) {
    findings.push(
      finding("warning", "W_LIT_INGEST_MD", `人工确认清单写入失败: ${reviewPut.error.code} ${reviewPut.error.message}`),
    );
  }

  return {
    ok: true,
    corpus,
    jsonRef: jsonPut.ok ? jsonPut.value : undefined,
    reviewRef: reviewPut.ok ? reviewPut.value : undefined,
    findings,
  };
}
