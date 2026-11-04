/**
 * 平台时钟发出的事实事件。
 *
 * 这些事件以后可以交给上游 Super-agent 的 Source，但本身不是 Trigger、Thread 或 Ticket。
 * 事件只携带标识和状态，不携带会话正文、提示词或凭据。
 */

import type { Finding } from "./experiment.ts";

export type PlatformSignalType =
  | "experiment.completed.v1"
  | "lease.changed.v1"
  | "budget.exhausted.v1";

export type SignalValue = string | number | boolean | null;

export interface PlatformSignal {
  id: string;
  type: PlatformSignalType;
  source: "research-layer";
  tenant_id: string;
  project_id: string | null;
  resource_id: string;
  resource_version: number;
  time: string;
  data: Record<string, SignalValue>;
}

export interface PlatformSignalResult {
  ok: boolean;
  signal?: PlatformSignal;
  findings: Finding[];
}

const FORBIDDEN_DATA = /secret|token|password|prompt|credential|api_key/i;

export interface PlatformSignalInput {
  type: PlatformSignalType;
  tenant_id: string;
  project_id?: string | null;
  resource_id: string;
  resource_version: number;
  time: string;
  data: Record<string, SignalValue>;
}

function finding(code: string, message: string): Finding {
  return { severity: "error", code, message };
}

export function buildPlatformSignal(input: PlatformSignalInput): PlatformSignalResult {
  const findings: Finding[] = [];
  if (!input.tenant_id.trim() || !input.resource_id.trim()) {
    findings.push(finding("E_SIGNAL_ID", "租户和资源标识不能为空"));
  }
  if (!Number.isInteger(input.resource_version) || input.resource_version < 1) {
    findings.push(finding("E_SIGNAL_VERSION", "资源版本必须是正整数"));
  }
  if (Number.isNaN(Date.parse(input.time))) {
    findings.push(finding("E_SIGNAL_TIME", "时间必须是 ISO8601"));
  }
  for (const key of Object.keys(input.data)) {
    if (FORBIDDEN_DATA.test(key)) {
      findings.push(finding("E_SIGNAL_SENSITIVE", `事件数据不能包含 ${key}`));
    }
  }
  if (findings.length > 0) return { ok: false, findings };

  return {
    ok: true,
    findings,
    signal: {
      id: `${input.type}:${input.resource_id}:${input.resource_version}`,
      type: input.type,
      source: "research-layer",
      tenant_id: input.tenant_id,
      project_id: input.project_id ?? null,
      resource_id: input.resource_id,
      resource_version: input.resource_version,
      time: input.time,
      data: input.data,
    },
  };
}
