/**
 * TelemetryPort：指标、日志与追踪的唯一出口。
 *
 * 由 harness-core 或公司可观测平台实现。
 * 本工程只描述事件，不决定后端。
 */

import type { Iso8601, PortCapabilities, PortResult } from "../types.ts";

export interface MetricSample {
  name: string;
  value: number;
  unit?: string;
  /** 低基数标签；禁止放 jobId 之类的随机值。 */
  labels?: Record<string, string>;
}

export interface TelemetryEvent {
  name: string;
  at: Iso8601;
  traceId: string;
  tenantId: string;
  projectId?: string;
  attributes?: Record<string, string | number | boolean>;
  metrics?: MetricSample[];
  /** 必须为 true；实现方拒绝未脱敏数据。 */
  redactionApplied: boolean;
}

export interface TelemetryCapabilities extends PortCapabilities {
  backend?: string;
  supportsMetrics?: boolean;
  supportsLogs?: boolean;
  supportsTraces?: boolean;
}

/**
 * 实现方必须保证：
 * - 拒绝或脱敏敏感字段（token、密钥、完整提示、用户数据）。
 * - 指标标签低基数；高基数内容只进日志。
 * - 不得因为遥测失败而阻断业务调用。
 */
export interface TelemetryPort {
  describe(): Promise<PortResult<TelemetryCapabilities>>;
  emit(event: TelemetryEvent): Promise<PortResult<void>>;
}
