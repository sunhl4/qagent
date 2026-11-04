# Temporal 持久工作流实施方案

本文档把实验外循环的持久化编排（Temporal）从原则落到可实施的边界与步骤。原则已在 `docs/02_四类范式组合决策.md` 定论：`while true` 循环没有恢复、没有预算、没有并发控制，必须由 Temporal 工作流替代；实验尝试每轮使用新上下文。本文档只做设计冻结，不引入代码依赖；安装与接入是外部阻塞项，触发条件见 `docs/19_执行计划.md` 的 E-03。

## 1. 范围

| 范围 | 说明 |
|---|---|
| 属于本设计 | 实验循环、租约续期与对账、审批等待、多种子复现、文献阶段编排、周期回收扫描的持久化编排 |
| 不属于本设计 | 云 / HPC / 模型适配器（由 harness-core 提供，见 AGENTS.md 与 `docs/13`）；编码协作底座（见 `docs/15`） |

平台事实：Temporal 是开源持久化工作流引擎，本设计以官方 TypeScript SDK（`@temporalio/workflow`、`@temporalio/activity`、`@temporalio/worker`、`@temporalio/client`、`@temporalio/testing`）为实施载体，官方文档见 https://docs.temporal.io 。本工程当前未安装该依赖，本文件是设计冻结而非依赖声明。

## 2. 设计原则

1. **Workflow 只做决策，Activity 做副作用。** 工作流内部只调用 `packages/domain` 的纯函数给出「下一步做什么」，一切 IO（提交作业、续租、写产物、调用模型）全部进入 Activity。
2. **决定论。** 工作流内禁止 `Date.now()`、`Math.random()` 与直接读环境，由 Temporal 的时间与随机设施或 Workflow 输入提供；这与 `docs/15` 第 3 节的「两套时钟」一致：人机时钟走会话，平台时钟（小时到数月）只走 Temporal。
3. **副作用只经契约端口。** Activity 不直接调用云 SDK，而是通过 `contracts/` 的 9 个端口调用；SDK 级转发由 harness-core 侧的网关完成（`docs/12` 第 4 节的 IntegrationGateway 边界）。本工程不实现任何云 / HPC / 模型适配器。
4. **未知执行状态先对账，不自动重试。** 供应商返回 `unknown_execution` 时禁止盲目重试：进入专门的核对 Activity（以 `reconcileLease` / 收尾对账为准），对出终态后按事实分支。
5. **可重试性来自领域层，不来自 Temporal 默认。** 失败分类与可重试性判定（`packages/domain/src/failure.ts`）作为 Activity 重试策略的输入；策略拒绝（如 `POLICY_DENIED`）一律不可重试。
6. **审批是 Signal，不是循环轮询。** 等待人工审批用 Temporal Signal + 可更新计时器实现，禁止任何轮询循环。
7. **常驻对账用 Schedule，不用 DSH 定时任务。** `sweepLeases()` 已是可重复调用、带幂等键的单轮扫描（`docs/06` 第 4 节），Temporal Schedule 只负责周期性触发它。

## 3. Workflow 与现有代码的映射

现有实现已经是「引擎无关」的纯函数与输入输出结构；Temporal 接入层只包编排，不改业务代码。

| Temporal 对象 | 映射的实现 | 说明 |
|---|---|---|
| Workflow：实验任务循环 | `packages/pipeline/src/loop.ts` 的输入输出契约 | 工作流持有任务级状态与停止条件 |
| Activity：单次尝试 | `packages/pipeline/src/run.ts` 的 `runExperiment` | 每轮独立 Activity，天然满足「每轮新上下文」 |
| Activity：租约获取与结算 | `packages/pipeline/src/lease.ts` 的 `acquireLease` / `releaseLease` | 幂等键沿用现有 idempotencyKey |
| Activity：租约对账 | `packages/pipeline/src/lease.ts` 的 `reconcileLease` | 唯一允许处理 `unknown_execution` 的地方 |
| Activity：失败读回 | `packages/pipeline/src/retrieval.ts` 的 `loadFailureLibrary` | 新任务开始前召回历史失败 |
| Activity：复现批次 | `packages/pipeline/src/reproduction.ts` 的 `runReproduction` | 逐种子细化为子活动 |
| Workflow：周期回收扫描 | `packages/pipeline/src/reclaim.ts` 的 `sweepLeases` | 由 Temporal Schedule 周期触发，SCAN 幂等 |
| Signal / Query | 审批、取消、查询进度 | 审批记录照旧经策略评估落盘为 `PolicyDecisionRecord` |

> 落地分层：v0.1 可以把 `runExperimentLoop` 整体作为单个长 Activity（配合心跳与 `continueAsNew`），风险最低；v1.0 按上表细化为「每尝试一个 Activity」。两态都保持同一输入输出契约，业务代码不变。

## 4. 重试与停止语义

| 情形 | Temporal 侧策略 | 语义来源 |
|---|---|---|
| 环境类失败（timeout 等） | 指数退避，次数有限（默认 3 次） | 会话与领域预算约束 |
| 策略拒绝 | `NonRetryableError`，直接终止并升级 | `POLICY_DENIED` 不可重试 |
| 预算耗尽 | 不重试；发布预算耗尽事实事件 | `platform-signal` 已有事件 |
| 未知执行 | 不重试；先对账 Activity 出终态 | AGENTS.md 禁令与 `docs/06` 对账节 |
| 连续失败停止 | Workflow 内判 `max_consecutive_failures` | 任务规格 stopping 字段 |
| 截止时间 | Workflow 级 `failExceededTimeout`，伴随检查点评估 | 检查点决策已有 `planResume` |

## 5. 审批与取消

1. 需要人工审批的尝试（`needs_approval`）：Workflow 发起 `evaluatePolicy` 所需输入后等待 Signal（`approve` / `reject`），等待期间计时器可由新证据延长；审批结果与拒绝原因照旧写 `policy-decision` 产物。
2. 取消：`cancel` Signal 触发后，Workflow 先让在跑 Activity 结束或删除取消（设 `cancellationType` 为等待完成），保证租约能正常结算，再走对账。
3. 审批与取消都必须留下可审计记录，禁止静默丢弃。

## 6. 测试与验收

| 验收点 | 方法 |
|---|---|
| 决定论 | `@temporalio/testing` 的时间跳跃与重放测试；同一历史重放结果一致 |
| 崩溃恢复 | 杀掉 worker 中途再起，任务在检查点或租约处恢复，成本账本不重计 |
| 未知执行 | 注入 `unknown_execution`，确认先对账后分支，不出现自动重试 |
| 审批等待 | Signal 到达前任务可廉价挂起（不占 worker 线程） |
| 周期对账 | Schedule 与 `sweepLeases` 单轮等价，重复触发幂等 |

## 7. 落地步骤（触发后执行）

1. 安装 `@temporalio/*` 到新的编排包（建议 `packages/orchestration/`），`packages/domain` 与 `packages/pipeline` 不出现 Temporal import。
2. Worker 与队列：`experiment`（尝试与循环）、`reconcile`（对账与回收）、`report`（日报周报）三条队列；worker 进程与编排配置放 `deploy/`。
3. 把现有调用入口（CLI / 测试）切换为 Workflow client 提交，保留直调 `runExperimentLoop` 的旁路以便降级。
4. 接入事件与审计：Workflow 关键迁移经 `EventPort` 发事实事件，复用现有 `platform-signal` 通道。
5. 依第 6 节验收后，关闭 `docs/08` 阶段 2 中「控制面重启后续跑」对应的退出标准项。

## 8. 边界与回滚

- 本设计不改变契约版本、不改 `contracts/`，不新增除 `@temporalio/*` 之外的运行时依赖。
- 回滚方式：停用 worker，回到「直接函数调用 + 人工驱动」的当前形态；两个形态共用同一输入输出，业务代码零改动。
- 部署形态（自托管 vs Cloud）属于采购与基础设施决策，登记在 `docs/18_决策请求单.md` 的资源节，未确认前按自托管单机设计。
