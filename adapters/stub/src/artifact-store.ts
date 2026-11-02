import { createHash, randomUUID } from "node:crypto";
import type {
  ArtifactRef,
  ArtifactStoreCapabilities,
  ArtifactStorePort,
  GetArtifactInput,
  PortResult,
  PutArtifactInput,
  SignedUrl,
} from "../../../contracts/src/index.ts";
import { fail, ok } from "../../../contracts/src/index.ts";
import { StubBase } from "./common.ts";
import type { StubBaseOptions } from "./common.ts";

interface StoredObject {
  ref: ArtifactRef;
  bytes: Uint8Array;
  tenantId: string;
}

const MAX_OBJECT_BYTES = 8 * 1024 * 1024;

export interface StubArtifactStoreOptions extends Partial<StubBaseOptions> {
  maxObjectBytes?: number;
}

export class StubArtifactStorePort extends StubBase implements ArtifactStorePort {
  private readonly objects = new Map<string, StoredObject>();
  private readonly byId = new Map<string, string>();
  private readonly idempotency = new Map<string, ArtifactRef>();
  private readonly maxObjectBytes: number;
  private counter = 0;

  constructor(options: StubArtifactStoreOptions = {}) {
    super({
      implementation: options.implementation ?? "stub-artifact-store",
      degradedReason:
        options.degradedReason ?? "内存实现：无持久化、无加密、无版本化、无跨进程共享",
      features: options.features ?? ["put", "get", "stat", "signedUrl", "list"],
      clock: options.clock,
      residency: options.residency,
    });
    this.maxObjectBytes = options.maxObjectBytes ?? MAX_OBJECT_BYTES;
  }

  async describe(): Promise<PortResult<ArtifactStoreCapabilities>> {
    return ok({
      ...this.caps(),
      maxObjectBytes: this.maxObjectBytes,
      supportsSignedUrl: true,
      supportsVersioning: false,
      supportsRetention: true,
      supportsServerSideEncryption: false,
    });
  }

  async put(input: PutArtifactInput): Promise<PortResult<ArtifactRef>> {
    if (input.idempotencyKey) {
      const cached = this.idempotency.get(input.idempotencyKey);
      if (cached) return ok(cached);
    }
    if (!input.tenantId) return fail("INVALID_ARGUMENT", "tenantId 缺失");
    if (!input.key || input.key.includes("..")) {
      return fail("INVALID_ARGUMENT", "key 非法");
    }

    let bytes: Uint8Array;
    if (input.bytes) {
      bytes = input.bytes;
    } else if (input.stream) {
      const chunks: Uint8Array[] = [];
      for await (const chunk of input.stream) chunks.push(chunk);
      const total = chunks.reduce((sum, chunk) => sum + chunk.byteLength, 0);
      if (total > this.maxObjectBytes) {
        return fail("INVALID_ARGUMENT", "对象超过上限", { sizeBytes: total });
      }
      bytes = new Uint8Array(total);
      let offset = 0;
      for (const chunk of chunks) {
        bytes.set(chunk, offset);
        offset += chunk.byteLength;
      }
    } else {
      return fail("INVALID_ARGUMENT", "必须提供 bytes 或 stream");
    }

    if (bytes.byteLength > this.maxObjectBytes) {
      return fail("INVALID_ARGUMENT", "对象超过上限", {
        sizeBytes: bytes.byteLength,
        maxObjectBytes: this.maxObjectBytes,
      });
    }

    const sha256 = createHash("sha256").update(bytes).digest("hex");
    if (input.expectedSha256 && input.expectedSha256 !== sha256) {
      return fail("INVALID_ARGUMENT", "sha256 不匹配", {
        declared: input.expectedSha256,
        actual: sha256,
      });
    }

    this.counter += 1;
    const artifactId = `art-${this.counter}`;
    const uri = `stub://artifacts/${input.tenantId}/${input.key}`;
    const ref: ArtifactRef = {
      artifactId,
      uri,
      sha256,
      sizeBytes: bytes.byteLength,
      contentType: input.contentType,
      createdAt: this.now(),
      retention: input.retention ?? "standard",
    };
    this.objects.set(uri, { ref, bytes, tenantId: input.tenantId });
    this.byId.set(artifactId, uri);
    if (input.idempotencyKey) this.idempotency.set(input.idempotencyKey, ref);
    return ok(ref);
  }

  private resolve(input: GetArtifactInput): StoredObject | undefined {
    const uri =
      input.uri ?? (input.artifactId ? this.byId.get(input.artifactId) : undefined);
    if (!uri) return undefined;
    return this.objects.get(uri);
  }

  async stat(input: GetArtifactInput): Promise<PortResult<ArtifactRef>> {
    const stored = this.resolve(input);
    if (!stored) return fail("NOT_FOUND", "产物不存在");
    if (stored.tenantId !== input.tenantId) {
      return fail("PERMISSION_DENIED", "跨租户访问");
    }
    return ok(stored.ref);
  }

  async get(input: GetArtifactInput): Promise<PortResult<{ ref: ArtifactRef; bytes: Uint8Array }>> {
    const stored = this.resolve(input);
    if (!stored) return fail("NOT_FOUND", "产物不存在");
    if (stored.tenantId !== input.tenantId) {
      return fail("PERMISSION_DENIED", "跨租户访问");
    }
    return ok({ ref: stored.ref, bytes: stored.bytes });
  }

  async signedUrl(
    input: GetArtifactInput & { method: "GET" | "PUT"; ttlSeconds: number },
  ): Promise<PortResult<SignedUrl>> {
    if (input.ttlSeconds <= 0 || input.ttlSeconds > 3600) {
      return fail("INVALID_ARGUMENT", "ttlSeconds 必须在 1..3600");
    }
    if (input.method === "GET") {
      const stored = this.resolve(input);
      if (!stored) return fail("NOT_FOUND", "产物不存在");
      if (stored.tenantId !== input.tenantId) {
        return fail("PERMISSION_DENIED", "跨租户访问");
      }
    }
    return ok({
      url: `stub://signed/${randomUUID()}?method=${input.method}`,
      expiresAt: new Date(this.clock().getTime() + input.ttlSeconds * 1000).toISOString(),
      method: input.method,
    });
  }

  async list(input: {
    tenantId: string;
    projectId?: string;
    prefix: string;
    limit?: number;
    cursor?: string;
  }): Promise<PortResult<{ items: ArtifactRef[]; nextCursor?: string }>> {
    const limit = input.limit ?? 50;
    const all = [...this.objects.values()]
      .filter((item) => item.tenantId === input.tenantId)
      .filter((item) => item.ref.uri.includes(input.prefix))
      .map((item) => item.ref);
    return ok({ items: all.slice(0, limit) });
  }

  async setRetention(input: {
    tenantId: string;
    artifactId: string;
    retention: string;
    until?: string;
  }): Promise<PortResult<ArtifactRef>> {
    const uri = this.byId.get(input.artifactId);
    const stored = uri ? this.objects.get(uri) : undefined;
    if (!stored) return fail("NOT_FOUND", "产物不存在");
    if (stored.tenantId !== input.tenantId) return fail("PERMISSION_DENIED", "跨租户访问");
    stored.ref.retention = input.retention;
    return ok(stored.ref);
  }

  /** 测试辅助。 */
  size(): number {
    return this.objects.size;
  }
}
