/**
 * 桩装配：一次创建全部端口，供本工程独立运行。
 *
 * 该文件只用于本地开发与测试，永远不会用于生产。
 * 合并后由 harness-core 提供真实实现，接口保持不变。
 */

import type {
  ArtifactStorePort,
  ComputeCapabilities,
  EventPort,
  HpcSchedulerPort,
  IdentityPort,
  ModelGatewayPort,
  SecretPort,
  SessionPort,
  TelemetryPort,
} from "../../../contracts/src/index.ts";
import { CONTRACT_VERSION } from "../../../contracts/src/index.ts";
import type { Clock } from "./common.ts";
import { StubIdentityPort } from "./identity.ts";
import type { StubIdentityOptions } from "./identity.ts";
import { StubSecretPort } from "./secrets.ts";
import type { StubSecretOptions } from "./secrets.ts";
import { StubArtifactStorePort } from "./artifact-store.ts";
import type { StubArtifactStoreOptions } from "./artifact-store.ts";
import { StubModelGateway } from "./model-gateway.ts";
import type { StubModelOptions } from "./model-gateway.ts";
import { StubComputePort } from "./compute.ts";
import type { StubComputeOptions } from "./compute.ts";
import { StubEventPort } from "./events.ts";
import { StubSessionPort } from "./session.ts";
import type { StubSessionOptions } from "./session.ts";
import { StubTelemetryPort } from "./telemetry.ts";
import type { StubTelemetryOptions } from "./telemetry.ts";

export interface StubStackOptions {
  contractVersion?: string;
  clock?: Clock;
  identity?: StubIdentityOptions;
  secrets?: StubSecretOptions;
  artifacts?: StubArtifactStoreOptions;
  model?: StubModelOptions;
  compute?: StubComputeOptions;
  session?: StubSessionOptions;
  telemetry?: StubTelemetryOptions;
}

export interface StubStack {
  contractVersion: string;
  identity: IdentityPort;
  secrets: SecretPort;
  artifacts: ArtifactStorePort;
  model: ModelGatewayPort;
  compute: HpcSchedulerPort;
  events: EventPort;
  session: SessionPort;
  telemetry: TelemetryPort;
}

export function createStubStack(options: StubStackOptions = {}): StubStack {
  const clock = options.clock;
  const withClock = <T extends { clock?: Clock }>(item: T | undefined): T => ({
    ...(item ?? ({} as T)),
    clock: item?.clock ?? clock,
  });

  return {
    contractVersion: options.contractVersion ?? CONTRACT_VERSION,
    identity: new StubIdentityPort(withClock(options.identity)),
    secrets: new StubSecretPort(withClock(options.secrets)),
    artifacts: new StubArtifactStorePort(withClock(options.artifacts)),
    model: new StubModelGateway(withClock(options.model)),
    compute: new StubComputePort(withClock(options.compute)),
    events: new StubEventPort({ clock }),
    session: new StubSessionPort(withClock(options.session)),
    telemetry: new StubTelemetryPort(withClock(options.telemetry)),
  };
}

export { StubIdentityPort, StubSecretPort, StubArtifactStorePort };
export { StubModelGateway, StubComputePort, StubEventPort, StubSessionPort, StubTelemetryPort };
export type { StubComputeOptions, JobScenario } from "./compute.ts";
export type { ComputeCapabilities };
