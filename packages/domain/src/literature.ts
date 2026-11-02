/**
 * 文献去重、语料组装与方法卡校验。
 *
 * 检索与解析由文献插件调用外部服务完成（arXiv/OpenAlex/Crossref 等），
 * 本模块只做纯领域处理：
 * - 去重与版本合并：相同 DOI 合并；arXiv 预印本合并进正式版。
 * - 标题+作者+年份相似：进入人工确认候选，不自动合并。
 * - 引用图：接受显式的前向/后向引用边，未知端点只告警。
 * - 方法卡：没有证据定位的结论不得进入下游。
 */

import type { Finding } from "./experiment.ts";

export interface PaperRecord {
  paper_id: string;
  title: string;
  authors: string[];
  year: number;
  doi?: string | null;
  arxiv_id?: string | null;
  venue?: string | null;
  source: string;
  code_url?: string | null;
  topics?: string[];
}

export interface MergedPaper {
  paper: PaperRecord;
  versions: PaperRecord[];
  merge_reasons: string[];
}

export interface ReviewCandidate {
  paper_ids: string[];
  reason: string;
}

export type CitationDirection = "backward" | "forward";

export interface CitationEdge {
  from_paper_id: string;
  to_paper_id: string;
  direction: CitationDirection;
}

export interface TopicCluster {
  topic: string;
  paper_ids: string[];
}

export interface LiteratureCorpus {
  corpus_id: string;
  generated_at: string;
  papers: MergedPaper[];
  review_candidates: ReviewCandidate[];
  citations: CitationEdge[];
  clusters: TopicCluster[];
}

export interface DeduplicateResult {
  ok: boolean;
  merged: MergedPaper[];
  review_candidates: ReviewCandidate[];
  findings: Finding[];
}

export interface MethodCardEvidence {
  type:
    | "paper_page"
    | "paper_section"
    | "figure"
    | "table"
    | "equation"
    | "code_line"
    | "issue"
    | "abstract";
  location: string;
  quote?: string | null;
  ref?: string | null;
}

export interface MethodCard {
  method_card_id: string;
  paper: {
    paper_id: string;
    title: string;
    authors: string[];
    year: number;
    doi?: string | null;
    arxiv_id?: string | null;
    venue?: string | null;
    source?: string | null;
    code_url?: string | null;
  };
  problem: string;
  method_summary: string;
  claims: string[];
  inputs?: string[];
  outputs?: string[];
  datasets?: string[];
  preprocessing?: string[];
  model_or_algorithm?: string | null;
  hyperparameters?: { name: string; value: unknown }[];
  baselines?: string[];
  metrics?: { name: string; direction: "minimize" | "maximize" }[];
  train_test_split?: string | null;
  hardware?: string | null;
  runtime?: string | null;
  original_code_url?: string | null;
  reproduction_status: "not_attempted" | "in_progress" | "succeeded" | "partial" | "failed";
  reproduction_difficulty?: string | null;
  missing_information?: string[];
  suspicious_assumptions?: string[];
  improvement_opportunities?: string[];
  evidence_locations: MethodCardEvidence[];
  created_at: string;
  revision?: number;
}

function finding(
  severity: "error" | "warning",
  code: string,
  message: string,
  path?: string,
): Finding {
  return { severity, code, message, path };
}

function normalizeDoi(doi: string | null | undefined): string {
  if (!doi) return "";
  return doi
    .trim()
    .toLowerCase()
    .replace(/^https?:\/\/(dx\.)?doi\.org\//, "");
}

function normalizeTitle(title: string): string {
  return title.trim().toLowerCase().replace(/\s+/g, " ");
}

function titleKey(record: PaperRecord): string {
  const firstAuthor = (record.authors[0] ?? "").trim().toLowerCase();
  return `${normalizeTitle(record.title)}|${record.year}|${firstAuthor}`;
}

function primaryScore(record: PaperRecord): number {
  return (normalizeDoi(record.doi) ? 1_000_000 : 0) + record.year;
}

/**
 * 去重与版本合并。
 *
 * - 相同 DOI（忽略大小写与 doi.org 前缀）合并，正式版中较新年份为主记录。
 * - 无 DOI 的 arXiv 记录：能通过 arXiv ID 关联到正式版时并入，否则按 arXiv ID 自分。
 * - 剩余记录按 标题+年份+第一作者 聚类：多于一条时进入人工确认，绝不自动合并。
 */
export function deduplicatePapers(records: readonly PaperRecord[]): DeduplicateResult {
  const findings: Finding[] = [];
  const valid = new Map<string, PaperRecord>();
  for (const record of records) {
    if (!record.paper_id?.trim() || !record.title?.trim() || record.authors.length === 0) {
      findings.push(finding("error", "E_LIT_RECORD", "文献记录缺少 paper_id、title 或 authors", record.paper_id || undefined));
      continue;
    }
    if (!Number.isInteger(record.year)) {
      findings.push(finding("error", "E_LIT_RECORD", "文献记录年份必须是整数", record.paper_id));
      continue;
    }
    valid.set(record.paper_id, record);
  }

  const groupOf = new Map<string, number>();
  const groups: { members: PaperRecord[]; reasons: Set<string>; origin: "doi" | "arxiv" | "title" }[] = [];
  const addGroup = (record: PaperRecord, origin: "doi" | "arxiv" | "title"): number => {
    const index = groups.push({ members: [record], reasons: new Set<string>(), origin }) - 1;
    groupOf.set(record.paper_id, index);
    return index;
  };
  const joinGroup = (index: number, record: PaperRecord, reason: string): void => {
    groups[index].members.push(record);
    groups[index].reasons.add(reason);
    groupOf.set(record.paper_id, index);
  };

  const doiIndex = new Map<string, number>();
  const arxivToPublished = new Map<string, number>();
  for (const record of valid.values()) {
    const doi = normalizeDoi(record.doi);
    if (!doi) continue;
    const existing = doiIndex.get(doi);
    if (existing !== undefined) {
      joinGroup(existing, record, "doi_match");
    } else {
      const index = addGroup(record, "doi");
      doiIndex.set(doi, index);
      const arxiv = (record.arxiv_id ?? "").trim();
      if (arxiv) arxivToPublished.set(arxiv.toLowerCase(), index);
    }
  }

  const arxivIndex = new Map<string, number>();
  for (const record of valid.values()) {
    if (groupOf.has(record.paper_id)) continue;
    const arxiv = (record.arxiv_id ?? "").trim().toLowerCase();
    if (!arxiv) continue;
    const published = arxivToPublished.get(arxiv);
    if (published !== undefined) {
      joinGroup(published, record, "arxiv_link");
    } else {
      const existing = arxivIndex.get(arxiv);
      if (existing !== undefined) {
        joinGroup(existing, record, "arxiv_match");
      } else {
        const index = addGroup(record, "arxiv");
        arxivIndex.set(arxiv, index);
      }
    }
  }

  const titleClusters = new Map<string, PaperRecord[]>();
  for (const record of valid.values()) {
    if (groupOf.has(record.paper_id)) continue;
    const key = titleKey(record);
    const cluster = titleClusters.get(key) ?? [];
    cluster.push(record);
    titleClusters.set(key, cluster);
  }
  const reviewCandidates: ReviewCandidate[] = [];
  for (const cluster of titleClusters.values()) {
    if (cluster.length >= 2) {
      reviewCandidates.push({
        paper_ids: cluster.map((record) => record.paper_id),
        reason: "title_author_year_similarity",
      });
      findings.push(
        finding(
          "warning",
          "W_LIT_REVIEW",
          `标题+作者+年份相似，需要人工确认: ${cluster.map((record) => record.paper_id).join(", ")}`,
        ),
      );
    }
    for (const record of cluster) addGroup(record, "title");
  }

  /* 跨 DOI 的同名同作者同年：不自动合并，进入人工确认。 */
  const primaryByKey = new Map<string, string[]>();
  for (const group of groups) {
    if (group.origin !== "doi") continue;
    const primary = [...group.members].sort((a, b) => primaryScore(b) - primaryScore(a))[0];
    const key = titleKey(primary);
    const ids = primaryByKey.get(key) ?? [];
    ids.push(primary.paper_id);
    primaryByKey.set(key, ids);
  }
  for (const ids of primaryByKey.values()) {
    if (ids.length >= 2) {
      reviewCandidates.push({ paper_ids: ids, reason: "same_title_author_year" });
      findings.push(
        finding(
          "warning",
          "W_LIT_REVIEW",
          `不同 DOI 但标题+作者+年份相似，需要人工确认: ${ids.join(", ")}`,
        ),
      );
    }
  }

  const merged: MergedPaper[] = groups.map((group) => {
    const sorted = [...group.members].sort((a, b) => primaryScore(b) - primaryScore(a));
    return {
      paper: sorted[0],
      versions: sorted.slice(1),
      merge_reasons: [...group.reasons],
    };
  });

  return {
    ok: !findings.some((item) => item.severity === "error"),
    merged,
    review_candidates: reviewCandidates,
    findings,
  };
}

export interface BuildCorpusInput {
  corpus_id: string;
  records: readonly PaperRecord[];
  edges?: readonly CitationEdge[];
  now?: Date;
}

export interface BuildCorpusResult {
  ok: boolean;
  corpus?: LiteratureCorpus;
  findings: Finding[];
}

/**
 * 组装语料：去重结果 + 引用边（端点解析到合并后的主记录）+ 主题聚类。
 */
export function buildLiteratureCorpus(input: BuildCorpusInput): BuildCorpusResult {
  const dedup = deduplicatePapers(input.records);
  const findings = [...dedup.findings];
  if (!input.corpus_id?.trim()) {
    findings.push(finding("error", "E_LIT_CORPUS_ID", "corpus_id 不能为空"));
    return { ok: false, findings };
  }

  const idToPrimary = new Map<string, string>();
  for (const merged of dedup.merged) {
    idToPrimary.set(merged.paper.paper_id, merged.paper.paper_id);
    for (const version of merged.versions) {
      idToPrimary.set(version.paper_id, merged.paper.paper_id);
    }
  }

  const citations: CitationEdge[] = [];
  for (const edge of input.edges ?? []) {
    const from = idToPrimary.get(edge.from_paper_id);
    const to = idToPrimary.get(edge.to_paper_id);
    if (!from || !to) {
      findings.push(
        finding(
          "warning",
          "W_LIT_EDGE_UNKNOWN",
          `引用边端点不在语料中，已跳过: ${edge.from_paper_id} -> ${edge.to_paper_id}`,
        ),
      );
      continue;
    }
    if (from === to) {
      findings.push(
        finding(
          "warning",
          "W_LIT_EDGE_SELF",
          `引用边两端是同一记录（或其版本），已跳过: ${edge.from_paper_id}`,
        ),
      );
      continue;
    }
    citations.push({ from_paper_id: from, to_paper_id: to, direction: edge.direction });
  }

  const clusterMap = new Map<string, Set<string>>();
  for (const merged of dedup.merged) {
    const topics = [
      ...(merged.paper.topics ?? []),
      ...merged.versions.flatMap((version) => version.topics ?? []),
    ];
    for (const topic of topics) {
      const ids = clusterMap.get(topic) ?? new Set<string>();
      ids.add(merged.paper.paper_id);
      clusterMap.set(topic, ids);
    }
  }
  const clusters: TopicCluster[] = [...clusterMap.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([topic, ids]) => ({ topic, paper_ids: [...ids] }));

  return {
    ok: !findings.some((item) => item.severity === "error"),
    corpus: {
      corpus_id: input.corpus_id,
      generated_at: (input.now ?? new Date()).toISOString(),
      papers: dedup.merged,
      review_candidates: dedup.review_candidates,
      citations,
      clusters,
    },
    findings,
  };
}

/**
 * 方法卡编译：结构缺失报错，下游可用性缺失（基线、代码等）告警。
 *
 * 硬性规则：至少一条证据定位；没有证据定位的结论不可进入下游。
 */
export function compileMethodCard(card: MethodCard): {
  ok: boolean;
  errors: Finding[];
  warnings: Finding[];
} {
  const errors: Finding[] = [];
  const warnings: Finding[] = [];

  if (!card.method_card_id?.trim()) {
    errors.push(finding("error", "E_METHOD_CARD_ID", "method_card_id 不能为空", "method_card_id"));
  }
  if (!card.paper?.paper_id?.trim()) {
    errors.push(finding("error", "E_METHOD_CARD_PAPER", "paper.paper_id 不能为空", "paper.paper_id"));
  }
  if (!card.paper?.title?.trim()) {
    errors.push(finding("error", "E_METHOD_CARD_TITLE", "paper.title 不能为空", "paper.title"));
  }
  if (!card.paper?.authors?.length) {
    errors.push(finding("error", "E_METHOD_CARD_AUTHORS", "paper.authors 不能为空", "paper.authors"));
  }
  if (!Number.isInteger(card.paper?.year)) {
    errors.push(finding("error", "E_METHOD_CARD_YEAR", "paper.year 必须是整数", "paper.year"));
  }
  if (!card.problem?.trim()) {
    errors.push(finding("error", "E_METHOD_CARD_PROBLEM", "problem 不能为空", "problem"));
  }
  if (!card.method_summary?.trim()) {
    errors.push(finding("error", "E_METHOD_CARD_SUMMARY", "method_summary 不能为空", "method_summary"));
  }
  if (!card.evidence_locations?.length) {
    errors.push(
      finding(
        "error",
        "E_METHOD_CARD_EVIDENCE",
        "缺少证据定位；没有定位的结论不可进入下游",
        "evidence_locations",
      ),
    );
  }

  if (!card.claims?.length) {
    warnings.push(finding("warning", "W_METHOD_CARD_NO_CLAIMS", "没有声明 claims", "claims"));
  }
  if (!card.metrics?.length) {
    warnings.push(finding("warning", "W_METHOD_CARD_NO_METRICS", "没有声明指标", "metrics"));
  }
  if (!card.baselines?.length) {
    warnings.push(finding("warning", "W_METHOD_CARD_NO_BASELINES", "没有声明基线", "baselines"));
  }
  if (!card.hyperparameters?.length) {
    warnings.push(
      finding("warning", "W_METHOD_CARD_NO_HYPERPARAMS", "没有声明超参数", "hyperparameters"),
    );
  }
  if (!card.datasets?.length) {
    warnings.push(finding("warning", "W_METHOD_CARD_NO_DATASETS", "没有声明数据集", "datasets"));
  }
  if (!card.original_code_url && !card.paper?.code_url) {
    warnings.push(finding("warning", "W_METHOD_CARD_NO_CODE", "没有代码链接，复现难度高", "original_code_url"));
  }

  return { ok: errors.length === 0, errors, warnings };
}
