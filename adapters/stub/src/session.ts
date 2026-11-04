import type {
  PortResult,
  SessionCapabilities,
  SessionEvent,
  SessionPort,
  SessionRequest,
  SessionResult,
} from "../../../contracts/src/index.ts";
import { fail, ok } from "../../../contracts/src/index.ts";
import { StubBase } from "./common.ts";
import type { StubBaseOptions } from "./common.ts";

export interface StubSessionOptions extends Partial<StubBaseOptions> {
  turns?: number;
  exceedBudget?: boolean;
  fail?: boolean;
  /** 注入一次不在 allowedTools 中的工具名；命中时记录拒绝且不执行。 */
  unauthorizedTool?: string;
}

interface LiveSession {
  request: SessionRequest;
  subscribers: Array<(event: SessionEvent) => void>;
  state: "started" | "completed" | "failed" | "cancelled" | "timeout" | "budget_exceeded";
  cancelled: boolean;
}

export class StubSessionPort extends StubBase implements SessionPort {
  private readonly sessions = new Map<string, LiveSession>();
  private readonly turns: number;
  private readonly exceedBudget: boolean;
  private readonly fail: boolean;
  private readonly unauthorizedTool?: string;

  constructor(options: StubSessionOptions = {}) {
    super({
      implementation: options.implementation ?? "stub-session",
      degradedReason:
        options.degradedReason ?? "脚本化会话：不调用真实 DSH harness，不产生真实模型输出",
      features: options.features ?? ["start", "subscribe", "wait", "cancel"],
      clock: options.clock,
      residency: options.residency,
    });
    this.turns = Math.max(1, options.turns ?? 1);
    this.exceedBudget = options.exceedBudget ?? false;
    this.fail = options.fail ?? false;
    this.unauthorizedTool = options.unauthorizedTool;
  }

  async describe(): Promise<PortResult<SessionCapabilities>> {
    return ok({
      ...this.caps(),
      supportsStreamingEvents: true,
      supportsToolRestriction: true,
      supportsBudgetEnforcement: true,
      maxTurns: 100,
    });
  }

  async start(
    request: SessionRequest,
  ): Promise<PortResult<{ sessionId: string; state: "started" | "queued" }>> {
    if (!request.tenantId || !request.taskId) {
      return fail("INVALID_ARGUMENT", "tenantId 或 taskId 缺失");
    }
    if (request.allowedTools.length === 0) {
      return fail("PERMISSION_DENIED", "只读会话不能作为研究任务执行器");
    }
    if (request.budget.maxTurns <= 0 || request.budget.maxToolCalls <= 0) {
      return fail("INVALID_ARGUMENT", "预算必须为正");
    }
    if (this.sessions.has(request.sessionId)) {
      return fail("CONFLICT", "会话已存在", { sessionId: request.sessionId });
    }
    this.sessions.set(request.sessionId, {
      request,
      subscribers: [],
      state: "started",
      cancelled: false,
    });
    return ok({ sessionId: request.sessionId, state: "started" });
  }

  async subscribe(
    sessionId: string,
    onEvent: (event: SessionEvent) => void,
  ): Promise<PortResult<() => void>> {
    const session = this.sessions.get(sessionId);
    if (!session) return fail("NOT_FOUND", "会话不存在", { sessionId });
    session.subscribers.push(onEvent);
    return ok(() => {
      session.subscribers = session.subscribers.filter((item) => item !== onEvent);
    });
  }

  async wait(sessionId: string): Promise<PortResult<SessionResult>> {
    const session = this.sessions.get(sessionId);
    if (!session) return fail("NOT_FOUND", "会话不存在", { sessionId });

    const emit = (event: SessionEvent): void => {
      for (const subscriber of session.subscribers) subscriber(event);
    };

    if (session.cancelled) {
      session.state = "cancelled";
      return ok({
        sessionId,
        state: "cancelled",
        turns: 0,
        toolCalls: 0,
        artifacts: [],
        usage: {},
      });
    }

    if (this.unauthorizedTool && !session.request.allowedTools.includes(this.unauthorizedTool)) {
      const name = this.unauthorizedTool;
      emit({ type: "turn_started", turn: 1, at: this.now() });
      emit({
        type: "tool_call",
        turn: 1,
        callId: "call-unauth",
        name,
        arguments: {},
        at: this.now(),
      });
      emit({
        type: "tool_result",
        turn: 1,
        callId: "call-unauth",
        ok: false,
        summary: "拒绝：工具不在 allowedTools，未执行",
        at: this.now(),
      });
      emit({
        type: "error",
        code: "PERMISSION_DENIED",
        message: "未授权工具",
        retryable: false,
        at: this.now(),
      });
      session.state = "failed";
      return ok({
        sessionId,
        state: "failed",
        turns: 1,
        toolCalls: 0,
        artifacts: [],
        usage: {},
        error: { code: "PERMISSION_DENIED", message: "未授权工具", retryable: false },
      });
    }

    let toolCalls = 0;
    for (let turn = 1; turn <= this.turns; turn += 1) {
      emit({ type: "turn_started", turn, at: this.now() });
      emit({
        type: "message",
        turn,
        role: "assistant",
        content: `stub turn ${turn}`,
        at: this.now(),
      });

      if (this.fail && turn === this.turns) {
        emit({
          type: "error",
          code: "INTERNAL",
          message: "桩：注入会话失败",
          retryable: false,
          at: this.now(),
        });
        session.state = "failed";
        return ok({
          sessionId,
          state: "failed",
          turns: turn,
          toolCalls,
          artifacts: [],
          usage: {},
          error: { code: "INTERNAL", message: "桩：注入会话失败", retryable: false },
        });
      }

      toolCalls += 1;
      emit({ type: "turn_finished", turn, usage: {}, at: this.now() });

      if (this.exceedBudget) {
        session.state = "budget_exceeded";
        return ok({
          sessionId,
          state: "budget_exceeded",
          turns: turn,
          toolCalls,
          artifacts: [],
          usage: {},
          error: { code: "QUOTA_EXCEEDED", message: "超过预算", retryable: false },
        });
      }
    }

    session.state = "completed";
    return ok({
      sessionId,
      state: "completed",
      turns: this.turns,
      toolCalls,
      output: `stub session ${sessionId} completed`,
      artifacts: [],
      usage: {},
    });
  }

  async cancel(sessionId: string, _reason: string): Promise<PortResult<void>> {
    const session = this.sessions.get(sessionId);
    if (!session) return fail("NOT_FOUND", "会话不存在", { sessionId });
    session.cancelled = true;
    session.state = "cancelled";
    return ok(undefined);
  }

  /** 测试辅助。 */
  stateOf(sessionId: string): string | undefined {
    return this.sessions.get(sessionId)?.state;
  }
}
