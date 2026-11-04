import type {
  PortResult,
  TelemetryCapabilities,
  TelemetryEvent,
  TelemetryPort,
} from "../../../contracts/src/index.ts";
import { fail, ok } from "../../../contracts/src/index.ts";
import { StubBase } from "./common.ts";
import type { StubBaseOptions } from "./common.ts";

const SENSITIVE_KEYS = [
  "token",
  "secret",
  "password",
  "authorization",
  "api_key",
  "apikey",
  "private_key",
];

const MAX_ATTRIBUTES = 32;

export interface StubTelemetryOptions extends Partial<StubBaseOptions> {
  maxEvents?: number;
}

export class StubTelemetryPort extends StubBase implements TelemetryPort {
  private readonly events: TelemetryEvent[] = [];
  private readonly maxEvents: number;

  constructor(options: StubTelemetryOptions = {}) {
    super({
      implementation: options.implementation ?? "stub-telemetry",
      degradedReason:
        options.degradedReason ?? "内存实现：不导出到真实 OTel 后端，进程退出即丢失",
      features: options.features ?? ["emit"],
      clock: options.clock,
      residency: options.residency,
    });
    this.maxEvents = options.maxEvents ?? 10000;
  }

  async describe(): Promise<PortResult<TelemetryCapabilities>> {
    return ok({
      ...this.caps(),
      backend: "memory",
      supportsMetrics: true,
      supportsLogs: true,
      supportsTraces: true,
    });
  }

  async emit(event: TelemetryEvent): Promise<PortResult<void>> {
    if (!event.redactionApplied) {
      return fail("INVALID_ARGUMENT", "遥测必须标记脱敏");
    }
    if (!event.traceId || !event.tenantId) {
      return fail("INVALID_ARGUMENT", "traceId 或 tenantId 缺失");
    }
    const attributes = event.attributes ?? {};
    const keys = Object.keys(attributes);
    if (keys.length > MAX_ATTRIBUTES) {
      return fail("INVALID_ARGUMENT", "attributes 过多，疑似高基数标签", {
        count: keys.length,
      });
    }
    for (const key of keys) {
      const lowered = key.toLowerCase();
      if (SENSITIVE_KEYS.some((sensitive) => lowered.includes(sensitive))) {
        return fail("INVALID_ARGUMENT", "遥测包含敏感字段名", { key });
      }
    }

    if (this.events.length >= this.maxEvents) this.events.shift();
    this.events.push(event);
    return ok(undefined);
  }

  /** 测试辅助。 */
  collected(): readonly TelemetryEvent[] {
    return this.events;
  }

  countByName(name: string): number {
    return this.events.filter((event) => event.name === name).length;
  }
}
