# DeepSeekHarness 统一架构

## 1. 架构目标

以 DSH 作为公司统一的 Agent Harness，在其上构建：

- 统一的插件体系
- 统一的服务与事件模型
- 统一的模型接入与路由
- 统一的沙箱与工具
- 多用户、多租户的共享平台
- 可长期运行、可恢复、可审计的研发流程

## 2. DSH 的职责边界

### 2.1 DSH 适合承担

| 能力 | 说明 |
|---|---|
| 会话管理 | 维护多轮对话、上下文、工具调用序列 |
| 工具调用 | 把模型意图转为结构化工具调用 |
| 插件扩展 | 通过 Cordis 服务与事件扩展能力 |
| 模型适配 | 通过 `ctx.llm` 接入不同模型供应商 |
| 技能与提示模板 | 组织可复用的工作方法 |
| 执行轨迹 | 提供运行时信息与工具调用排障 |
| 交互界面 | Web 与桌面入口 |
| 无界面运行 | headless 与 SDK 驱动 |

### 2.2 DSH 不适合独担

| 能力 | 原因 | 应交由 |
|---|---|---|
| 跨天/跨月的实验、租约与审批 | 会话生命周期不是业务生命周期 | Temporal |
| 仓库内编码协作的连续会话 | 双层路由、工单和订阅属于上游 Super-agent | 接入开源 Super-agent，不在本工程重写 |
| 资源所有权 | Harness 不是调度器 | Slurm/K8s/SkyPilot |
| 租户与计费 | 需要服务端事实源 | 平台控制面 + Postgres |
| 密钥长期托管 | 会话环境不可信 | 凭据代理 |
| 科学结论判定 | 模型输出不等于证据 | 证据层 + 人工 |
| 硬件安全闭环 | 实时控制不能经过网络/LLM | 设备控制器 |

## 3. 组件视图

```text
┌──────────────────────────────────────────────────────────────┐
│ 入口层                                                        │
│  Web 门户 / 桌面 DSH / CLI / API / 定时触发 / Webhook          │
└───────────────┬──────────────────────────────────────────────┘
                │
┌───────────────▼──────────────────────────────────────────────┐
│ 平台控制面                                                    │
│  IAM / 租户 / 项目 / 预算 / 配额 / 策略 / 审批 / 计费           │
│  Task API / Run API / Artifact API / Model API                │
└───────┬───────────────────────────────┬──────────────────────┘
        │                               │
┌───────▼──────────────┐      ┌─────────▼──────────────────────┐
│ 平台时钟              │      │ 模型网关                        │
│ Temporal             │      │ 路由 / 配额 / 回退 / 评测 / 审计  │
│ 实验/租约/审批/证据   │      └─────────┬──────────────────────┘
└───────┬──────────────┘                │
        │                               │
┌───────▼───────────────────────────────▼──────────────────────┐
│ Agent 时钟：上游 Super-agent（DSH 插件，本工程不实现）          │
│  Router / Worker / Trigger / Ticket / 订阅直通 / Watchdog     │
│  计划假设五模块会完成并开源；未冻结前阶段 4 走单工单降级        │
└───────┬──────────────────────────────────────────────────────┘
        │
┌───────▼──────────────────────────────────────────────────────┐
│ DSH 运行时                                                    │
│  Agent / Session / Tools / Skills / Plugins / LLM adapters    │
│  形态：Web / 桌面 / headless / SDK stdio JSON-RPC              │
└───────┬──────────────────────────────────────────────────────┘
        │
┌───────▼──────────────────────────────────────────────────────┐
│ 能力插件层                                                    │
│  goal liteature evidence experiment resource software        │
│  memory report policy observability sandbox                  │
└───────┬───────────────────────────┬──────────────────────────┘
        │                           │
┌───────▼──────────────┐   ┌────────▼─────────────────────────┐
│ 沙箱层                │   │ 资源适配层                       │
│ Docker/gVisor/微虚机  │   │ Slurm / Kueue / SkyPilot / QPU   │
└───────┬──────────────┘   └────────┬─────────────────────────┘
        │                           │
┌───────▼───────────────────────────▼──────────────────────────┐
│ 证据与数据层                                                  │
│ 对象存储 / Postgres / MLflow / DVC / 向量库 / 审计日志          │
└──────────────────────────────────────────────────────────────┘
```

平台时钟可以直接启动 DSH headless 实验会话。Super-agent 只位于编码协作路径，并且运行在 DSH 之内。图中把它画在运行时之上，表示本工程从平台侧看到的接入边界，不表示本工程拥有它的实现。

## 4. Cordis 服务设计

### 4.1 服务键规划

| 服务键 | 提供者插件 | 主要方法（示意） |
|---|---|---|
| `ctx.goal` | goal | `listGoals`、`createTaskDraft`、`validateBudget` |
| `ctx.literature` | literature | `search`、`dedupe`、`fetchFullText`、`extractMethodCard` |
| `ctx.evidence` | evidence | `register`、`locate`、`verifyCitation`、`buildGraph` |
| `ctx.experiment` | experiment | `compile`、`validate`、`estimate`、`decide` |
| `ctx.resource` | resource | `request`、`renew`、`release`、`reconcile` |
| `ctx.software` | software | `createWorktree`、`applyPatch`、`runTests`、`openPR` |
| `ctx.memory` | memory | `remember`、`recall`、`recordFailure` |
| `ctx.report` | report | `daily`、`weekly`、`reproductionReport` |
| `ctx.sandbox` | sandbox | `create`、`exec`、`destroy`、`snapshot` |
| `ctx.llm` | model | 由 DSH 提供，扩展路由与配额 |

方法名是设计建议，不是 DSH 现有 API。实现前必须按锁定版本核对。`ctx.software` 的工单、目录和 PR 回复在上游 Super-agent 冻结后改为调用其 Channel；本工程保留规格、测试门禁和合并策略。

### 4.2 服务定义规则

1. 一个服务只负责一个能力域。
2. 服务接口用 TypeScript 类型声明并导出。
3. 服务方法必须幂等或明确声明非幂等。
4. 所有跨服务调用带 trace 上下文。
5. 服务内部不直接读全局配置，通过注入。
6. 服务卸载时必须释放连接、定时器、租约。

### 4.3 事件设计

| 事件 | 分发模式 | 用途 |
|---|---|---|
| `tool:before` | waterfall | 策略拦截、参数改写、审计 |
| `tool:after` | parallel | 指标、日志、结果登记 |
| `session:start` | emit | 初始化工作区、租约 |
| `session:end` | emit | 释放资源、生成摘要 |
| `model:before` | waterfall | 路由、预算、脱敏 |
| `model:after` | parallel | 成本、质量、延迟记录 |
| `experiment:submit` | waterfall | 预算、审批、资源检查 |
| `experiment:complete` | emit | 决策、报告、清理 |
| `policy:denied` | emit | 告警、审计 |

事件名是设计建议。实现时以 DSH 锁定版本的公开事件目录为准。

## 5. 三种运行形态的接入

### 5.1 编码协作形态

- 人在 IM、GitHub 或面板上对同一个 Super-agent 说话。
- Router 负责评估与对外回复，Worker 按工单在隔离目录中执行。
- 同一工单的后续事件直通该 Worker。
- 高风险工具仍走平台网关。投机执行和 Watchdog 不能绕过审批、预算和未知执行规则。
- 工单状态以上游 Ticket 为准；实验、租约和证据仍写回平台。
- 接入条件、约束和降级见 `docs/15_Super-agent接入与两套时钟.md`。

### 5.2 headless 形态

- 平台为一次实验尝试启动一个新的 headless 会话。
- 输入：实验规格、上下文、允许工具、预算、超时。
- 输出：结构化结果、产物引用、日志、退出码。
- 必须有硬超时与沙箱。
- 编码工单在上游可用时不走这条一次性会话；上游未冻结时，阶段 4 以此形态降级，并标记 `degraded`。

### 5.3 SDK 形态

- 平台后端通过 stdio JSON-RPC 驱动 DSH 子进程。
- 适合需要精细控制 turn、工具和事件流的场景。
- 需要处理进程崩溃、协议错误、背压和超时。

## 6. 沙箱设计

### 6.1 分级

| 级别 | 隔离 | 适用 |
|---|---|---|
| S0 | 进程 + 只读目录 | 只读分析、文档解析 |
| S1 | 容器 + 非特权 + 网络白名单 | 一般代码任务 |
| S2 | gVisor 或 Kata 微虚机 | 不可信代码、外部仓库 |
| S3 | 独立节点 + 无外网 + 专用存储 | 敏感数据、真实设备前置 |
| S4 | 硬件隔离 + 专用控制网 | 真实实验设备 |

### 6.2 SandboxProvider 契约

```text
create(spec) -> sandboxHandle
exec(handle, command, limits) -> result
copyIn(handle, path, artifactRef)
copyOut(handle, path) -> artifactRef
snapshot(handle) -> imageRef
destroy(handle)
```

约束：

- `exec` 必须有超时、内存、CPU、进程数限制。
- 默认无网络；需要网络时按域名白名单开通。
- 不允许挂载宿主 docker socket。
- 不允许访问云元数据服务。
- 销毁必须幂等。

## 7. 模型层

### 7.1 适配器

```text
ModelAdapter
  id / provider / version
  capabilities { context, tools, json, vision, streaming }
  cost { input, output, currency }
  limits { rpm, tpm, concurrency }
  health()
  complete(request) -> response
  stream(request) -> stream
```

### 7.2 路由策略

```text
route(task):
  candidates = filterByCapability(task)
  candidates = filterByResidency(task, candidates)
  candidates = filterByBudget(task, candidates)
  candidates = filterByHealth(candidates)
  if empty: fail with reason
  return argmin(cost + latencyPenalty + qualityPenalty)
```

### 7.3 提示与版本

- 提示模板版本化。
- 每次调用记录模板版本、模型版本、参数。
- 换模型必须重新评测，不能假设兼容。
- 结构化输出必须 schema 校验，失败可重试或降级。

## 8. 可观测性

### 8.1 统一关联

```text
trace_id
  -> workflow_id
  -> task_id
  -> run_id
  -> session_id
  -> tool_call_id
  -> resource_lease_id
  -> artifact_hash
```

### 8.2 必采指标

- 会话数、轮次、工具调用数、失败率
- 模型延迟、token、成本、回退次数
- 资源申请、排队、启动、执行、回收
- 实验成功/失败/部分成功
- 审批等待时间
- 沙箱创建/销毁失败
- 越权尝试与策略拒绝

### 8.3 日志

- 结构化 JSON。
- 脱敏：token、密钥、完整提示、用户数据。
- 保留期按合规要求。
- 审计日志与调试日志分离。

## 9. 部署拓扑

### 9.1 最小可用

- 1 个 Kubernetes 集群
- Temporal（自托管或云）
- PostgreSQL
- MinIO
- DSH 运行时（容器）
- 1 个 Slurm 集群适配
- 1 个模型后端（API 或自部署）

### 9.2 生产

- 控制面与执行面分离
- 多可用区
- 独立 GPU 节点池
- 独立沙箱节点池
- 独立存储与备份
- 出网代理与白名单
- 密钥管理服务
- 审计日志 WORM

## 10. 关键不变量

1. DSH 会话不是业务事实源。
2. 资源租约是资源使用的唯一凭据。
3. 执行前必须写 attempt。
4. 未知执行状态不得自动重试。
5. 长期密钥不进入沙箱。
6. 高风险动作必须经过策略检查。
7. 所有产物必须有哈希与来源。
8. 所有状态变更必须可审计。
9. 模型可替换，对象格式不绑定模型。
10. 插件必须可卸载、可回滚。
11. Super-agent 的路由器、工单库和 Watchdog 由上游提供。本工程不复制，也不把其预览期内部对象写入长期契约。
