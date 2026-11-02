import type {
  DataClass,
  ModelCapabilities,
  ModelDescriptor,
  ModelGatewayPort,
  ModelRequest,
  ModelResponse,
  ModelStreamEvent,
  PortResult,
} from "../../../contracts/src/index.ts";
import { fail, ok } from "../../../contracts/src/index.ts";
import { StubBase } from "./common.ts";
import type { StubBaseOptions } from "./common.ts";

const DATA_CLASS_ORDER: Record<DataClass, number> = {
  public: 0,
  internal: 1,
  confidential: 2,
  restricted: 3,
};

export interface StubModelOptions extends Partial<StubBaseOptions> {
  modelId?: string;
  modelVersion?: string;
  provider?: string;
  maxDataClass?: DataClass;
  supportsStreaming?: boolean;
}

export class StubModelGateway extends StubBase implements ModelGatewayPort {
  private readonly model: ModelDescriptor;
  private readonly maxDataClass: DataClass;
  private readonly supportsStreaming: boolean;
  private readonly idempotency = new Map<string, ModelResponse>();
  private calls = 0;

  constructor(options: StubModelOptions = {}) {
    super({
      implementation: options.implementation ?? "stub-model-gateway",
      degradedReason:
        options.degradedReason ?? "确定性假模型：不产生真实语义输出，仅用于流程测试",
      features: options.features ?? ["complete", "stream", "health"],
      clock: options.clock,
      residency: options.residency ?? "local_process",
    });
    this.maxDataClass = options.maxDataClass ?? "internal";
    this.supportsStreaming = options.supportsStreaming ?? true;
    this.model = {
      modelId: options.modelId ?? "stub-model-1",
      provider: options.provider ?? "stub",
      version: options.modelVersion ?? "0.0.0",
      capabilities: ["chat", "json"],
      contextTokens: 8192,
      residency: "local_process",
      dataClassMax: this.maxDataClass,
      status: "degraded",
    };
  }

  async describe(): Promise<PortResult<ModelCapabilities>> {
    return ok({ ...this.caps(), models: [this.model] });
  }

  async complete(request: ModelRequest): Promise<PortResult<ModelResponse>> {
    if (request.requestId && this.idempotency.has(request.requestId)) {
      return ok(this.idempotency.get(request.requestId)!);
    }
    if (!request.messages || request.messages.length === 0) {
      return fail("INVALID_ARGUMENT", "messages 不能为空");
    }
    if (DATA_CLASS_ORDER[request.dataClass] > DATA_CLASS_ORDER[this.maxDataClass]) {
      return fail("PERMISSION_DENIED", "数据等级超出模型允许范围", {
        requested: request.dataClass,
        max: this.maxDataClass,
      });
    }

    this.calls += 1;
    const last = request.messages.at(-1)?.content ?? "";
    let text: string;
    let json: unknown;

    if (request.responseFormat?.type === "json_schema") {
      json = { stub: true, echo: last };
      text = JSON.stringify(json);
    } else if (request.responseFormat?.type === "json_object") {
      json = { stub: true };
      text = JSON.stringify(json);
    } else {
      text = `stub-response-${this.calls}`;
    }

    const response: ModelResponse = {
      requestId: request.requestId,
      modelId: this.model.modelId,
      modelVersion: this.model.version,
      text,
      json,
      toolCalls: [],
      usage: {
        inputTokens: request.messages.reduce((sum, message) => sum + message.content.length, 0),
        outputTokens: text.length,
        cost: 0,
        currency: "CNY",
      },
      latencyMs: 0,
      finishReason: "stop",
      providerRequestId: `stub-provider-${this.calls}`,
    };
    this.idempotency.set(request.requestId, response);
    return ok(response);
  }

  async *stream(request: ModelRequest): AsyncIterable<ModelStreamEvent> {
    if (!this.supportsStreaming) {
      yield {
        type: "error",
        error: { code: "NOT_SUPPORTED", message: "该实现不支持流式输出", retryable: false },
      };
      return;
    }
    const result = await this.complete(request);
    if (!result.ok) {
      yield {
        type: "error",
        error: {
          code: result.error.code,
          message: result.error.message,
          retryable: result.error.retryable,
        },
      };
      return;
    }
    const text = result.value.text ?? "";
    for (const chunk of text.match(/.{1,8}/g) ?? []) {
      yield { type: "text_delta", text: chunk };
    }
    yield { type: "usage", usage: result.value.usage };
    yield { type: "done", response: result.value };
  }

  async health(): Promise<PortResult<{ healthy: boolean; checkedAt: string }>> {
    return ok({ healthy: true, checkedAt: this.now() });
  }

  /** 测试辅助。 */
  callCount(): number {
    return this.calls;
  }
}
