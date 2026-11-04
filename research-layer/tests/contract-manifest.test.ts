/**
 * 契约自检：验证桩的 IntegrationManifest 与 CapabilityDescriptor 形状。
 *
 * 不依赖第三方库；只检查跨工程联调真正依赖的字段。
 */

import { readFileSync } from "node:fs";
import { test } from "node:test";
import assert from "node:assert/strict";

import { CONTRACT_VERSION } from "../contracts/src/index.ts";
import { createStubStack } from "../adapters/stub/src/index.ts";

const manifest = JSON.parse(
  readFileSync(new URL("../contracts/fixtures/integration-manifest.stub.json", import.meta.url), "utf8"),
) as {
  implementation: { name: string; version: string; owner: string };
  contractVersion: string;
  environment: string;
  ports: Array<{
    name: string;
    version: string;
    transport: string;
    features: string[];
    degraded?: boolean;
  }>;
  knownLimitations: string[];
};

const VALID_PORTS = new Set([
  "model-gateway",
  "compute",
  "hpc-scheduler",
  "artifact-store",
  "identity",
  "secrets",
  "events",
  "session",
  "telemetry",
]);

const VALID_TRANSPORTS = new Set(["in_process", "stdio_jsonrpc", "http", "grpc"]);

test("integration manifest 结构合法", () => {
  assert.equal(manifest.contractVersion, CONTRACT_VERSION);
  assert.ok(manifest.implementation.name.length > 0);
  assert.ok(manifest.implementation.owner.length > 0);
  assert.ok(["local", "staging", "production"].includes(manifest.environment));
  assert.ok(manifest.ports.length >= 7);

  for (const port of manifest.ports) {
    assert.ok(VALID_PORTS.has(port.name), `未知端口: ${port.name}`);
    assert.ok(VALID_TRANSPORTS.has(port.transport), `未知 transport: ${port.transport}`);
    assert.ok(Array.isArray(port.features) && port.features.length > 0, `${port.name} 缺少 features`);
    assert.equal(port.version, CONTRACT_VERSION);
  }
});

test("本地桩 manifest 必须全部标记 degraded", () => {
  for (const port of manifest.ports) {
    assert.equal(port.degraded, true, `${port.name} 必须声明 degraded`);
  }
  assert.ok(manifest.knownLimitations.length >= 1);
  assert.ok(manifest.knownLimitations.some((item) => item.includes("仅用于")));
});

test("manifest 覆盖实际桩提供的每个端口", async () => {
  const stack = createStubStack();
  const declared = new Set(manifest.ports.map((port) => port.name));

  assert.ok(declared.has("identity"));
  assert.ok(declared.has("secrets"));
  assert.ok(declared.has("artifact-store"));
  assert.ok(declared.has("model-gateway"));
  assert.ok(declared.has("compute"));
  assert.ok(declared.has("hpc-scheduler"));
  assert.ok(declared.has("events"));
  assert.ok(declared.has("session"));
  assert.ok(declared.has("telemetry"));

  for (const port of [
    stack.identity,
    stack.secrets,
    stack.artifacts,
    stack.model,
    stack.compute,
    stack.events,
    stack.session,
    stack.telemetry,
  ]) {
    const described = await port.describe();
    assert.equal(described.ok, true);
    if (described.ok) {
      assert.equal(described.value.degraded, true);
      assert.equal(described.value.contractVersion, CONTRACT_VERSION);
    }
  }
});
