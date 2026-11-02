/**
 * EventPort：领域事件的唯一发布/订阅入口。
 *
 * 由 harness-core 或公司事件总线实现。
 * 本工程不建第二套消息系统。
 */

import type { Iso8601, PortCapabilities, PortResult } from "../types.ts";

export interface DomainEvent<T = unknown> {
  /** 全局唯一事件 ID，用于去重。 */
  id: string;
  /** CloudEvents 类型，如 experiment.completed.v1。 */
  type: string;
  /** 事件源。 */
  source: string;
  /** 主体。 */
  subject?: string;
  tenantId: string;
  projectId?: string;
  /** 资源 ID。 */
  resourceId?: string;
  /** 资源版本，用于拒绝旧事件。 */
  resourceVersion?: number;
  /** 发生时间。 */
  time: Iso8601;
  /** 内容类型。 */
  dataContentType: "application/json";
  data: T;
  /** 追踪。 */
  traceId?: string;
}

export interface EventFilter {
  tenantId: string;
  types?: string[];
  projectId?: string;
  resourceId?: string;
}

export interface EventCapabilities extends PortCapabilities {
  delivery: "at_most_once" | "at_least_once";
  ordering: "none" | "per_resource" | "global";
  maxPayloadBytes?: number;
  retentionSeconds?: number;
}

export type EventHandler = (event: DomainEvent) => Promise<"ack" | "nack" | "drop">;

/**
 * 实现方必须保证：
 * - publish 幂等：同一事件 id 重复发布不产生重复投递。
 * - 至少一次投递时，消费方按 id 去重。
 * - 单资源顺序（若声明）必须保证同 resourceId 的 resourceVersion 单调。
 * - 事件不得包含密钥或未脱敏用户数据。
 */
export interface EventPort {
  describe(): Promise<PortResult<EventCapabilities>>;
  publish(event: DomainEvent): Promise<PortResult<void>>;
  subscribe(filter: EventFilter, handler: EventHandler): Promise<PortResult<() => Promise<void>>>;
}
