/**
 * 跨工程契约包入口。
 *
 * 版本规则：
 * - 主版本：不兼容变更（删除方法、改变语义、必填字段变化）。
 * - 次版本：向后兼容新增（新端口、新可选字段）。
 * - 修订号：文档与类型修正。
 */

export const CONTRACT_VERSION = "0.1.0";

/** 与 contracts/VERSION 保持一致；自检脚本会核对。 */
export const CONTRACT_PACKAGE = "@company/dsh-contracts";

export type * from "./types.ts";
export {
  ok,
  fail,
  unwrap,
  isRetryable,
} from "./types.ts";

export type * from "./ports/identity.ts";
export type * from "./ports/secrets.ts";
export type * from "./ports/artifact-store.ts";
export type * from "./ports/model-gateway.ts";
export type * from "./ports/compute.ts";
export type * from "./ports/events.ts";
export type * from "./ports/session.ts";
export type * from "./ports/telemetry.ts";
