/**
 * ModelGatewayPort：模型调用的唯一入口。
 *
 * 由 harness-core 实现（本地模型、官方 API、采购模型）。
 * 本工程只调用，不部署推理引擎、不保存模型权重、不管理供应商密钥。
 */

import type {
  DataClass,
  Iso8601,
  PortCapabilities,
  PortResult,
  Usage,
} from "../types.ts";

export type ChatRole = "system" | "user" | "assistant" | "tool";

export interface ChatMessage {
  role: ChatRole;
  content: string;
  /** 工具调用 id，role=tool 时使用。 */
  toolCallId?: string;
  /** 名称，便于审计。 */
  name?: string;
}

export interface ToolSchema {
  name: string;
  description: string;
  /** JSON Schema。 */
  parameters: Record<string, unknown>;
}

export interface ToolCall {
  id: string;
  name: string;
  /** 已解析的参数。 */
  arguments: Record<string, unknown>;
}

export type ResponseFormat =
  | { type: "text" }
  | { type: "json_object" }
  | { type: "json_schema"; name: string; schema: Record<string, unknown>; strict?: boolean };

export interface ModelRequest {
  /** 调用方生成，用于幂等与审计。 */
  requestId: string;
  tenantId: string;
  projectId?: string;
  /** 任务类型，用于路由。 */
  taskType:
    | "planning"
    | "coding"
    | "literature"
    | "extraction"
    | "review"
    | "report"
    | "classification"
    | "embedding";
  messages: ChatMessage[];
  tools?: ToolSchema[];
  responseFormat?: ResponseFormat;
  maxOutputTokens?: number;
  temperature?: number;
  /** 固定采样，便于复现。 */
  seed?: number;
  /** 数据分类，决定可用模型。 */
  dataClass: DataClass;
  /** 数据驻留要求。 */
  residency?: "cn" | "eu" | "us" | "on_prem" | "external";
  /** 成本上限。 */
  budget?: { maxCost?: number; currency?: string };
  /** 期望模型，可能被路由覆盖。 */
  preferredModelId?: string;
  /** 不允许使用的模型。 */
  deniedModelIds?: string[];
  /** 追踪。 */
  traceId?: string;
}

export interface ModelResponse {
  requestId: string;
  modelId: string;
  modelVersion: string;
  text?: string;
  /** responseFormat 为 json 时的解析结果。 */
  json?: unknown;
  toolCalls?: ToolCall[];
  usage: Usage;
  latencyMs: number;
  finishReason: "stop" | "length" | "tool_calls" | "content_filter" | "error";
  /** 供应商侧 ID，用于对账。 */
  providerRequestId?: string;
  /** 是否发生了路由回退。 */
  fallbackFrom?: string[];
}

export interface ModelDescriptor {
  modelId: string;
  provider: string;
  version: string;
  capabilities: string[];
  contextTokens?: number;
  residency?: string;
  dataClassMax?: DataClass;
  status: "active" | "degraded" | "disabled" | "canary";
}

export interface ModelCapabilities extends PortCapabilities {
  models: ModelDescriptor[];
}

export type ModelStreamEvent =
  | { type: "text_delta"; text: string }
  | { type: "tool_call_delta"; index: number; id?: string; name?: string; argumentsDelta?: string }
  | { type: "usage"; usage: Usage }
  | { type: "done"; response: ModelResponse }
  | { type: "error"; error: { code: string; message: string; retryable: boolean } };

export interface EmbeddingRequest {
  requestId: string;
  tenantId: string;
  modelId?: string;
  input: string[];
  dataClass: DataClass;
}

export interface EmbeddingResponse {
  requestId: string;
  modelId: string;
  modelVersion: string;
  vectors: number[][];
  usage: Usage;
}

/**
 * 实现方必须保证：
 * - complete/embed 对同一 requestId 幂等（同一请求体返回同一结果）。
 * - 未知 requestId 不得返回伪造结果。
 * - 失败时返回结构化错误，不抛未捕获异常。
 * - 成本与 token 必须可归因到 tenantId/projectId。
 * - dataClass 为 restricted 时不得路由到外部供应商。
 */
export interface ModelGatewayPort {
  describe(): Promise<PortResult<ModelCapabilities>>;
  complete(request: ModelRequest): Promise<PortResult<ModelResponse>>;
  stream(request: ModelRequest): AsyncIterable<ModelStreamEvent>;
  embed?(request: EmbeddingRequest): Promise<PortResult<EmbeddingResponse>>;
  /** 健康检查，便于熔断与路由。 */
  health(): Promise<PortResult<{ healthy: boolean; checkedAt: Iso8601 }>>;
}
