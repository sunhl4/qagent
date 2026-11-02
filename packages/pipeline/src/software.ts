/**
 * 阶段 4 降级执行的第一步：为一张工单启动唯一一次 headless 会话。
 *
 * 合并评估是独立一步，由调用方在拿到外部证据（单测、集成、E2E、安全扫描、
 * 独立评审、审批）后调用 `evaluateSoftwareMerge`。会话输出不作为证据。
 *
 * 不实现 Router、Worker、Watchdog 或工单库。
 */

import type { SessionBudget, SessionPort } from "../../../contracts/src/index.ts";
import type { Finding } from "../../domain/src/index.ts";
import {
  validateSoftwareMergeInput,
  validateSoftwareSpec,
} from "../../domain/src/index.ts";
import type { SoftwareSpec } from "../../domain/src/index.ts";

export interface StartDegradedSoftwareDeps {
  session: SessionPort;
}

export interface StartDegradedSoftwareInput {
  workId: string;
  authorId: string;
  tenantId: string;
  projectId?: string;
  workspaceId: string;
  agentId: string;
  spec: SoftwareSpec;
  budget: SessionBudget;
  /** 该工单已经启动过的会话。非空时拒绝，保证一工单一次会话。 */
  priorSessionIds?: string[];
  allowedTools?: string[];
}

export interface StartDegradedSoftwareResult {
  ok: boolean;
  sessionStarted: boolean;
  sessionId?: string;
  state?: string;
  findings: Finding[];
}

function sessionIdFor(workId: string): string {
  return `sw-${workId}`;
}

export async function startDegradedSoftwareSession(
  deps: StartDegradedSoftwareDeps,
  input: StartDegradedSoftwareInput,
): Promise<StartDegradedSoftwareResult> {
  const findings: Finding[] = [];
  if (!input.workId.trim() || !input.authorId.trim() || !input.workspaceId.trim()) {
    findings.push({ severity: "error", code: "E_WORK_INFO", message: "工单、作者与工作区标识不能为空" });
  }
  findings.push(...validateSoftwareSpec(input.spec));
  const prior = input.priorSessionIds ?? [];
  if (prior.length > 0) {
    findings.push({
      severity: "error",
      code: "E_SESSION_EXISTS",
      message: `降级路径下一张工单只允许一次会话，已存在 ${prior.length} 次`,
    });
  }
  if (findings.length > 0) {
    return { ok: false, sessionStarted: false, findings };
  }

  const sessionId = sessionIdFor(input.workId);
  const started = await deps.session.start({
    sessionId,
    tenantId: input.tenantId,
    projectId: input.projectId,
    taskId: input.workId,
    agentId: input.agentId,
    workspaceId: input.workspaceId,
    allowedTools: input.allowedTools ?? ["bash"],
    budget: input.budget,
    instruction: [
      "按规格在当前工作区完成一次实现。",
      "不要合并主分支，不要读取或输出密钥。",
      `目标：${input.spec.goal}`,
      ...input.spec.acceptance.map((item) => `验收 ${item.id}: ${item.command}`),
    ].join("\n"),
  });
  if (!started.ok) {
    return {
      ok: false,
      sessionStarted: false,
      findings: [
        { severity: "error", code: started.error.code, message: started.error.message },
      ],
    };
  }

  const waited = await deps.session.wait(sessionId);
  if (!waited.ok) {
    return {
      ok: false,
      sessionStarted: true,
      sessionId,
      findings: [
        { severity: "error", code: waited.error.code, message: waited.error.message },
      ],
    };
  }
  const completed = waited.value.state === "completed";
  return {
    ok: completed,
    sessionStarted: true,
    sessionId,
    state: waited.value.state,
    findings: completed
      ? []
      : [
          {
            severity: "error",
            code: "SESSION_NOT_COMPLETED",
            message: `会话未完成，状态 ${waited.value.state}；会话输出不能作为门禁证据`,
          },
        ],
  };
}

/** 合并评估的轻量包装：保证调用方意识到会话记录只是追踪信息。 */
export {
  evaluateSoftwareMerge,
  validateSoftwareMergeInput,
} from "../../domain/src/index.ts";

/** 导出合并决定类型，避免调用方重复 import 领域包。 */
export type {
  SoftwareMergeInput,
  SoftwareMergeRecord,
  SoftwareMergeResult,
} from "../../domain/src/index.ts";
