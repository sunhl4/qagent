/**
 * 失败库检索（IO 侧）：从 ArtifactStorePort 读回各循环写入的 failures.json，
 * 合并成跨任务可检索的库。存储访问只经由端口，读到格式非法的对象记 finding 并跳过。
 */

import type { ArtifactStorePort } from "../../../contracts/src/index.ts";
import type { FailureEntry, Finding } from "../../domain/src/index.ts";
import { mergeFailureEntries } from "../../domain/src/index.ts";

export interface FailureLibrarySourceResult {
  uri: string;
  ok: boolean;
  count: number;
  error_code?: string;
  error_message?: string;
}

export interface LoadedFailureLibrary {
  entries: FailureEntry[];
  sources: FailureLibrarySourceResult[];
  findings: Finding[];
}

function isFailureEntry(value: unknown): value is FailureEntry {
  if (value === null || typeof value !== "object") return false;
  const record = value as Record<string, unknown>;
  return (
    typeof record.entry_id === "string" &&
    record.entry_id.length > 0 &&
    typeof record.category === "string" &&
    typeof record.code === "string" &&
    typeof record.occurred_at === "string"
  );
}

export interface LoadFailureLibraryInput {
  tenantId: string;
  projectId?: string | null;
  /** 各循环总结中记录的 `failures.json` URI。 */
  uris: string[];
}

/**
 * 读取并合并多个失败库文件。
 *
 * - 读不到或格式非法 → finding + 记录该来源，不阻断其余来源。
 * - 每个 URI 读取幂等；caller 决定调用时机（任务开始前的召回）。
 */
export async function loadFailureLibrary(
  deps: { artifacts: ArtifactStorePort },
  input: LoadFailureLibraryInput,
): Promise<LoadedFailureLibrary> {
  const findings: Finding[] = [];
  const sources: FailureLibrarySourceResult[] = [];
  const collected: FailureEntry[] = [];

  for (const uri of input.uris) {
    const read = await deps.artifacts.get({
      tenantId: input.tenantId,
      projectId: input.projectId ?? undefined,
      uri,
    });
    if (!read.ok) {
      sources.push({ uri, ok: false, count: 0, error_code: read.error.code, error_message: read.error.message });
      findings.push({
        severity: "warning",
        code: "W_FAILURE_RECALL_READ",
        message: `失败库读取失败: ${read.error.code} ${read.error.message}（${uri}）`,
      });
      continue;
    }

    let parsed: unknown;
    try {
      parsed = JSON.parse(new TextDecoder().decode(read.value.bytes));
    } catch (error) {
      sources.push({ uri, ok: false, count: 0, error_code: "E_JSON", error_message: String(error) });
      findings.push({
        severity: "warning",
        code: "W_FAILURE_RECALL_JSON",
        message: `失败库 JSON 非法（${uri}）: ${error instanceof Error ? error.message : String(error)}`,
      });
      continue;
    }

    const entries = (parsed as { entries?: unknown }).entries;
    if (!Array.isArray(entries)) {
      sources.push({ uri, ok: false, count: 0, error_code: "E_SHAPE", error_message: "entries 不是数组" });
      findings.push({
        severity: "warning",
        code: "W_FAILURE_RECALL_SHAPE",
        message: `失败库缺少 entries 数组（${uri}）`,
      });
      continue;
    }

    const valid = entries.filter(isFailureEntry);
    if (valid.length !== entries.length) {
      findings.push({
        severity: "warning",
        code: "W_FAILURE_RECALL_INVALID_ENTRIES",
        message: `失败库包含非法条目，已跳过 ${entries.length - valid.length} 条（${uri}）`,
      });
    }
    sources.push({ uri, ok: true, count: valid.length });
    collected.push(...valid);
  }

  return { entries: mergeFailureEntries(collected), sources, findings };
}
