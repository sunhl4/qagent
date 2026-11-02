import type {
  DomainEvent,
  EventCapabilities,
  EventFilter,
  EventHandler,
  EventPort,
  PortResult,
} from "../../../contracts/src/index.ts";
import { fail, ok } from "../../../contracts/src/index.ts";
import { StubBase } from "./common.ts";
import type { StubBaseOptions } from "./common.ts";

interface Subscription {
  filter: EventFilter;
  handler: EventHandler;
}

export class StubEventPort extends StubBase implements EventPort {
  private readonly published = new Set<string>();
  private readonly events: DomainEvent[] = [];
  private readonly subscriptions: Subscription[] = [];

  constructor(options: Partial<StubBaseOptions> = {}) {
    super({
      implementation: options.implementation ?? "stub-event",
      degradedReason: options.degradedReason ?? "内存实现：无持久化、无跨进程投递、无重放",
      features: options.features ?? ["publish", "subscribe"],
      clock: options.clock,
      residency: options.residency,
    });
  }

  async describe(): Promise<PortResult<EventCapabilities>> {
    return ok({
      ...this.caps(),
      delivery: "at_least_once",
      ordering: "per_resource",
      maxPayloadBytes: 256 * 1024,
      retentionSeconds: 0,
    });
  }

  async publish(event: DomainEvent): Promise<PortResult<void>> {
    if (!event.id || !event.type) return fail("INVALID_ARGUMENT", "缺少 id 或 type");
    if (!event.tenantId) return fail("INVALID_ARGUMENT", "缺少 tenantId");
    if (event.dataContentType !== "application/json") {
      return fail("INVALID_ARGUMENT", "只支持 application/json");
    }
    if (this.published.has(event.id)) return ok(undefined);
    this.published.add(event.id);
    this.events.push(event);

    for (const subscription of this.subscriptions) {
      if (subscription.filter.tenantId !== event.tenantId) continue;
      if (subscription.filter.projectId && subscription.filter.projectId !== event.projectId) continue;
      if (subscription.filter.types && !subscription.filter.types.includes(event.type)) continue;
      await subscription.handler(event);
    }
    return ok(undefined);
  }

  async subscribe(
    filter: EventFilter,
    handler: EventHandler,
  ): Promise<PortResult<() => Promise<void>>> {
    const subscription: Subscription = { filter, handler };
    this.subscriptions.push(subscription);
    return ok(async () => {
      const index = this.subscriptions.indexOf(subscription);
      if (index >= 0) this.subscriptions.splice(index, 1);
    });
  }

  /** 测试辅助。 */
  publishedEvents(): readonly DomainEvent[] {
    return this.events;
  }
}
