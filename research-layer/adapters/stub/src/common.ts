/**
 * 桩公共基类。
 *
 * 所有桩都通过 `describe()` 如实声明 degraded，且不访问网络、不读真实凭据。
 */

import type { PortCapabilities, PortResult } from "../../../contracts/src/index.ts";
import { CONTRACT_VERSION, ok } from "../../../contracts/src/index.ts";

export type Clock = () => Date;

export interface StubBaseOptions {
  implementation?: string;
  degradedReason: string;
  contractVersion?: string;
  features?: string[];
  residency?: string;
  limits?: Record<string, unknown>;
  clock?: Clock;
}

export abstract class StubBase {
  protected readonly clock: Clock;
  private readonly options: StubBaseOptions;

  constructor(options: StubBaseOptions) {
    this.options = options;
    this.clock = options.clock ?? (() => new Date());
  }

  protected now(): string {
    return this.clock().toISOString();
  }

  protected caps(extra: Partial<PortCapabilities> = {}): PortCapabilities {
    return {
      ...extra,
      contractVersion: this.options.contractVersion ?? CONTRACT_VERSION,
      implementation: this.options.implementation ?? "research-stub",
      degraded: true,
      degradedReason: this.options.degradedReason,
      features: this.options.features ?? [],
      residency: this.options.residency ?? "local_process",
      limits: this.options.limits,
    };
  }

  protected async describeWith(extra: Partial<PortCapabilities> = {}): Promise<PortResult<PortCapabilities>> {
    return ok(this.caps(extra));
  }
}

/** 生成稳定递增 ID。 */
export function makeId(prefix: string, counter: number): string {
  return `${prefix}-${counter}`;
}
