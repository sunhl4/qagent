# H33 Cloudflare Agents：持久调度与重试语义复核

- 项目：`cloudflare/agents`。
- SHA：`f404547453d412d04aafedff7d624d384c6e70d8`，提交2026-10-21T17:54:27+01:00。
- 来源：`/tmp/oss-cloudflare-agents`。
- 验证：静态阅读；未部署 Workers/Durable Objects。

## 主调用链

当前 Scheduler 解析 Date/延迟秒数/cron/interval，解析后将具名 callback 和 payload 推入 Lifecycle 持久 job queue。
Lifecycle 而非 Scheduler 自己负责 alarm 事件循环、重试与物理 alarm 调度；源码头部对此明确说明。
这纠正“无状态边缘 agent”的笼统概括：持久状态和宿主运行机制是其重要依赖。
证据：`packages/agents/src/schedules/scheduler.ts:1-35`。

## 三个关键机制

1. **时间类型判别联合。** schedule-timing.ts 区分 scheduled/delayed/cron/interval，单次与周期任务不是同一个布尔开关。cron 使用 parseCronExpression 得到下次时间，输出统一为秒。
2. **间隔范围检查。** validateIntervalSeconds 拒绝非数值、非正间隔以及超过30天上限。此处代码未显式 Number.isFinite，不能把该函数单独认定为完整数值验证；上游其他入口可能另做检查，未在本篇验证。
3. **版本迁移与重试默认。** Scheduler schema version=2，将旧 recovery callback 名称映射到 recoveryLoop 标记，避免迁移后逃过 breaker；默认 maxAttempts=3，baseDelay=100ms，maxDelay=3000ms。

```92:96:packages/agents/src/schedules/scheduler.ts
const DEFAULT_RETRY: Required<RetryOptions> = {
  maxAttempts: 3,
  baseDelayMs: 100,
  maxDelayMs: 3000
};
```

## 与量子/HPC 的冲突

框架默认三次重试不适用于公司设备提交；当前合同 automatic_retries=0。
调度任务被再次执行，不能视为原平台请求幂等；必须携带关联信息并查询平台事实。
Durable Object 持久队列也不能代替成熟 HPC 排队调度或 QPU 资源调度器。
边缘服务部署与公司内网数据/账号体系的网络边界需独立评估。

## 测试证据

`packages/agents/src/tests/schedules/timing.test.ts:12-42` 检查 Date、延迟、cron 与未知类型。
`:45-68` 检查非正间隔、超过上限及边界值。
`:71-85` 检查周期判断和下一执行时间严格晚于当前时间。
测试直接使用固定 NOW_MS，适合复现时间行为；不证明多租户隔离和外部调用 exactly-once。
本轮未运行测试。

## 公司落点

- `contracts/` 新增周期自动化前先定义动作风险、审批和重试边界，不能直接沿用调度器默认。
- Python adapter 复用现有 HPC/QPU 平台调度；DSH 不另起通用任务循环。
- 对内校准任务也要区分只读分析、模拟与真机执行，不能因“内部自动化”免除设备 ask。
- 测试覆盖重复 alarm、升级恢复、无效时间值和平台已受理后的网络丢包。

## 许可与取舍

根 `LICENSE:1-20` 已核为 MIT；仅借持久调度机制，当前不引入边缘运行时替代公司后端。
观察到的默认重试与恢复迁移值得作为公司反例，而不是即插即用候选。

## 证据

`packages/agents/src/schedules/scheduler.ts:1-35,75-95`；`schedule-timing.ts:11-45,76-117,127-139`；`packages/agents/src/tests/schedules/timing.test.ts:12-85`。
