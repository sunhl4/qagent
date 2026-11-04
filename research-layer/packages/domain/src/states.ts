/**
 * 研究任务状态机。
 *
 * 状态只允许按表迁移；非终态可以取消；终态不可回退。
 */

export type TaskState =
  | "draft"
  | "queued"
  | "waiting_approval"
  | "waiting_resource"
  | "running"
  | "partial"
  | "succeeded"
  | "failed"
  | "cancelled";

export type TaskEvent =
  | "submit"
  | "approve"
  | "reject"
  | "resource_ready"
  | "start"
  | "complete"
  | "fail"
  | "partial"
  | "cancel";

export interface TransitionResult {
  ok: boolean;
  state: TaskState;
  reason?: string;
}

const TERMINAL: ReadonlySet<TaskState> = new Set<TaskState>([
  "succeeded",
  "failed",
  "cancelled",
]);

const TABLE: Record<TaskState, Partial<Record<TaskEvent, TaskState>>> = {
  draft: {
    submit: "queued",
    cancel: "cancelled",
  },
  queued: {
    approve: "waiting_approval",
    resource_ready: "waiting_resource",
    start: "running",
    cancel: "cancelled",
    fail: "failed",
  },
  waiting_approval: {
    approve: "queued",
    reject: "cancelled",
    cancel: "cancelled",
  },
  waiting_resource: {
    resource_ready: "waiting_resource",
    start: "running",
    fail: "failed",
    cancel: "cancelled",
  },
  running: {
    complete: "succeeded",
    fail: "failed",
    partial: "partial",
    cancel: "cancelled",
  },
  partial: {
    complete: "succeeded",
    fail: "failed",
  },
  succeeded: {},
  failed: {},
  cancelled: {},
};

export function isTerminal(state: TaskState): boolean {
  return TERMINAL.has(state);
}

export function transition(state: TaskState, event: TaskEvent): TransitionResult {
  const next = TABLE[state]?.[event];
  if (!next) {
    return {
      ok: false,
      state,
      reason: `状态 ${state} 不允许事件 ${event}`,
    };
  }
  return { ok: true, state: next };
}

export function allowedEvents(state: TaskState): TaskEvent[] {
  return Object.keys(TABLE[state] ?? {}) as TaskEvent[];
}
