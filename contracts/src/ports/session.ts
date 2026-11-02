/**
 * SessionPort：DSH 会话的唯一入口。
 *
 * 由 harness-core 实现（把 DeepSeek Harness 的会话能力适配成端口）。
 * 本工程只负责生成任务说明、预算、允许工具与验收，不直接驱动 Cordis。
 */

import type {
  ArtifactRef,
  Iso8601,
  PortCapabilities,
  PortResult,
  Usage,
} from "../types.ts";

export interface SessionBudget {
  maxCost?: number;
  currency?: string;
  maxTurns: number;
  maxToolCalls: number;
  maxWallClockSeconds: number;
}

export interface SessionRequest {
  sessionId: string;
  tenantId: string;
  projectId?: string;
  taskId: string;
  agentId: string;
  workspaceId: string;
  /** 允许的工具名；空表示只读。 */
  allowedTools: string[];
  budget: SessionBudget;
  instruction: string;
  inputs?: ArtifactRef[];
  modelPolicy?: {
    preferredModelId?: string;
    allowedProviders?: string[];
  };
  /** 审批范围；高风险动作必须带。 */
  approval?: { approvalId: string; scope: string; expiresAt: Iso8601 };
}

export type SessionEvent =
  | { type: "turn_started"; turn: number; at: Iso8601 }
  | { type: "message"; turn: number; role: "assistant" | "tool"; content: string; at: Iso8601 }
  | {
      type: "tool_call";
      turn: number;
      callId: string;
      name: string;
      arguments: Record<string, unknown>;
      at: Iso8601;
    }
  | {
      type: "tool_result";
      turn: number;
      callId: string;
      ok: boolean;
      summary: string;
      at: Iso8601;
    }
  | { type: "turn_finished"; turn: number; usage: Usage; at: Iso8601 }
  | { type: "error"; code: string; message: string; retryable: boolean; at: Iso8601 };

export interface SessionResult {
  sessionId: string;
  state: "completed" | "failed" | "cancelled" | "timeout" | "budget_exceeded";
  turns: number;
  toolCalls: number;
  output?: string;
  artifacts: ArtifactRef[];
  usage: Usage;
  error?: { code: string; message: string; retryable: boolean };
}

export interface SessionCapabilities extends PortCapabilities {
  supportsStreamingEvents?: boolean;
  supportsToolRestriction?: boolean;
  supportsBudgetEnforcement?: boolean;
  maxTurns?: number;
}

/**
 * 实现方必须保证：
 * - 会话不是业务事实源；状态必须回写平台。
 * - 事件顺序单调，轮次递增。
 * - 超出预算必须停止，不得继续消耗。
 * - 未授权工具不得执行。
 * - 取消后不再产生新的 turn。
 */
export interface SessionPort {
  describe(): Promise<PortResult<SessionCapabilities>>;
  start(request: SessionRequest): Promise<PortResult<{ sessionId: string; state: "started" | "queued" }>>;
  /** 订阅事件；返回取消订阅函数。 */
  subscribe(sessionId: string, onEvent: (event: SessionEvent) => void): Promise<PortResult<() => void>>;
  wait(sessionId: string): Promise<PortResult<SessionResult>>;
  cancel(sessionId: string, reason: string): Promise<PortResult<void>>;
}
