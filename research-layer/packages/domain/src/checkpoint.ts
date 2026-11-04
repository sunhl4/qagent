/**
 * 检查点与恢复决策。
 *
 * 与 docs/06 的恢复规则对应：
 * - 从最近有效检查点恢复。
 * - 新 attempt 不覆盖旧产物。
 * - 记录恢复原因；多次恢复失败进入人工处理。
 * - 执行状态未知时绝不自动恢复或重试，必须先对账。
 */

import type { Finding } from "./experiment.ts";

export type PreviousAttemptState =
  | "succeeded"
  | "failed"
  | "partial"
  | "unknown_execution"
  | "cancelled";

export type ResumeAction = "resume" | "restart" | "escalate" | "none";

export interface CheckpointRecord {
  checkpoint_id: string;
  experiment_id: string;
  attempt: number;
  uri: string;
  sha256: string;
  step: number;
  created_at: string;
  code_commit: string;
  environment_hash: string;
  seed?: number | null;
  size_bytes?: number | null;
  valid?: boolean;
}

export interface CheckpointPolicy {
  required: boolean;
  interval_seconds?: number | null;
  /** 超过该时长的检查点视为过期；null/未设置表示不检查。 */
  max_age_seconds?: number | null;
  /** 连续恢复次数上限；达到后转人工。 */
  max_resumes: number;
}

export interface ResumeRequest {
  experiment_id: string;
  previous_attempt: number;
  previous_state: PreviousAttemptState;
  checkpoints: CheckpointRecord[];
  policy: CheckpointPolicy;
  current_code_commit: string;
  current_environment_hash: string;
  /** 已尝试过的恢复次数。 */
  resume_count: number;
  now?: Date;
}

export interface ResumeFromCheckpoint {
  checkpoint_id: string;
  uri: string;
  step: number;
}

export interface ResumeDecision {
  action: ResumeAction;
  next_attempt: number;
  from_checkpoint?: ResumeFromCheckpoint;
  reason: string;
  findings: Finding[];
}

const SHA256_PATTERN = /^[a-f0-9]{64}$/;

function finding(
  severity: "error" | "warning",
  code: string,
  message: string,
): Finding {
  return { severity, code, message };
}

function isNonEmpty(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

function isValidCheckpoint(checkpoint: CheckpointRecord): boolean {
  return (
    isNonEmpty(checkpoint.checkpoint_id) &&
    isNonEmpty(checkpoint.uri) &&
    typeof checkpoint.step === "number" &&
    Number.isFinite(checkpoint.step) &&
    checkpoint.step >= 0 &&
    !Number.isNaN(Date.parse(checkpoint.created_at)) &&
    SHA256_PATTERN.test(checkpoint.sha256) &&
    checkpoint.valid !== false
  );
}

/**
 * 选择最近的可用检查点：优先 step，再按创建时间。
 */
export function latestCheckpoint(
  checkpoints: readonly CheckpointRecord[],
  experimentId: string,
  attempt: number,
): CheckpointRecord | undefined {
  return checkpoints
    .filter(
      (checkpoint) =>
        checkpoint.experiment_id === experimentId &&
        checkpoint.attempt === attempt &&
        isValidCheckpoint(checkpoint),
    )
    .sort((left, right) => {
      if (left.step !== right.step) return right.step - left.step;
      return Date.parse(right.created_at) - Date.parse(left.created_at);
    })[0];
}

/**
 * 判定是否应恢复、重启或升级人工。
 *
 * 新 attempt 始终是 previous_attempt + 1，避免覆盖旧产物。
 */
export function planResume(request: ResumeRequest): ResumeDecision {
  const findings: Finding[] = [];
  const now = request.now ?? new Date();
  const nextAttempt = request.previous_attempt + 1;

  if (
    !isNonEmpty(request.experiment_id) ||
    !Number.isInteger(request.previous_attempt) ||
    request.previous_attempt < 1 ||
    !Number.isInteger(request.resume_count) ||
    request.resume_count < 0 ||
    !Number.isInteger(request.policy.max_resumes) ||
    request.policy.max_resumes < 0 ||
    !isNonEmpty(request.current_code_commit) ||
    !isNonEmpty(request.current_environment_hash)
  ) {
    findings.push(finding("error", "E_RESUME_INPUT", "恢复请求参数不合法"));
    return { action: "escalate", next_attempt: nextAttempt, reason: "恢复请求不合法", findings };
  }

  if (request.previous_state === "succeeded") {
    return {
      action: "none",
      next_attempt: nextAttempt,
      reason: "上一次尝试已成功，不需要恢复",
      findings,
    };
  }

  if (request.previous_state === "cancelled") {
    return {
      action: "none",
      next_attempt: nextAttempt,
      reason: "上一次尝试已取消，不自动恢复",
      findings,
    };
  }

  if (request.previous_state === "unknown_execution") {
    findings.push(
      finding(
        "error",
        "E_RESUME_UNKNOWN_EXECUTION",
        "执行状态未知，必须先人工对账，禁止自动恢复或重试",
      ),
    );
    return {
      action: "escalate",
      next_attempt: nextAttempt,
      reason: "执行状态未知",
      findings,
    };
  }

  if (request.resume_count >= request.policy.max_resumes) {
    findings.push(
      finding(
        "error",
        "E_RESUME_LIMIT",
        `已恢复 ${request.resume_count} 次，达到上限 ${request.policy.max_resumes}`,
      ),
    );
    return {
      action: "escalate",
      next_attempt: nextAttempt,
      reason: "恢复次数达到上限",
      findings,
    };
  }

  const checkpoint = latestCheckpoint(
    request.checkpoints,
    request.experiment_id,
    request.previous_attempt,
  );

  if (!checkpoint) {
    findings.push(
      finding(
        "warning",
        "W_CHECKPOINT_MISSING",
        `第 ${request.previous_attempt} 次尝试没有可用检查点，只能重启`,
      ),
    );
    return {
      action: "restart",
      next_attempt: nextAttempt,
      reason: "没有可用检查点",
      findings,
    };
  }

  if (checkpoint.code_commit !== request.current_code_commit) {
    findings.push(
      finding(
        "warning",
        "W_CHECKPOINT_CODE_MISMATCH",
        `检查点代码版本 ${checkpoint.code_commit} 与当前 ${request.current_code_commit} 不一致`,
      ),
    );
    return {
      action: "restart",
      next_attempt: nextAttempt,
      reason: "代码版本不一致，不能恢复",
      findings,
    };
  }

  if (checkpoint.environment_hash !== request.current_environment_hash) {
    findings.push(
      finding(
        "warning",
        "W_CHECKPOINT_ENV_MISMATCH",
        "检查点环境与当前环境不一致",
      ),
    );
    return {
      action: "restart",
      next_attempt: nextAttempt,
      reason: "环境不一致，不能恢复",
      findings,
    };
  }

  if (
    typeof request.policy.max_age_seconds === "number" &&
    request.policy.max_age_seconds >= 0
  ) {
    const ageSeconds = (now.getTime() - Date.parse(checkpoint.created_at)) / 1000;
    if (ageSeconds > request.policy.max_age_seconds) {
      findings.push(
        finding(
          "warning",
          "W_CHECKPOINT_STALE",
          `检查点已过期 ${Math.round(ageSeconds)} 秒，超过上限 ${request.policy.max_age_seconds} 秒`,
        ),
      );
      return {
        action: "restart",
        next_attempt: nextAttempt,
        reason: "检查点过期",
        findings,
      };
    }
  }

  return {
    action: "resume",
    next_attempt: nextAttempt,
    from_checkpoint: {
      checkpoint_id: checkpoint.checkpoint_id,
      uri: checkpoint.uri,
      step: checkpoint.step,
    },
    reason: `从第 ${request.previous_attempt} 次尝试的检查点 ${checkpoint.checkpoint_id} 恢复`,
    findings,
  };
}

/**
 * 生成检查点产物的确定性 key。新 attempt 使用新前缀，不会覆盖旧产物。
 */
export function checkpointArtifactKey(
  experimentId: string,
  attempt: number,
  checkpointId: string,
): string {
  const experiment = encodeURIComponent(experimentId);
  const checkpoint = encodeURIComponent(checkpointId);
  return `experiments/${experiment}/attempt-${attempt}/checkpoints/${checkpoint}.json`;
}

export function attemptArtifactPrefix(experimentId: string, attempt: number): string {
  return `experiments/${encodeURIComponent(experimentId)}/attempt-${attempt}/`;
}
