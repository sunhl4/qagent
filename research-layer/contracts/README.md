# 跨工程端口契约（contracts/）

本目录是 `research-layer`（本工程）与 `harness-core`（另一台电脑上的工程）之间唯一的集成面。

## 1. 目标

两个工程独立开发、后期合并，最大风险不是代码冲突，而是隐式耦合：

- 本工程直接 import harness-core 的内部模块；
- harness-core 改接口，本工程在不知情下编译失败；
- 两边各实现一遍云提交、HPC 队列、模型认证；
- 用桩冒充生产实现，联调时才发现语义不一致。

`contracts/` 把集成面缩小到一组显式端口，使双方都能独立编译、独立测试，合并时只核对版本与一致性用例。

## 2. 所有权

| 路径 | 所有者 |
|---|---|
| `contracts/src/types.ts` | 双方共同 |
| `contracts/src/ports/*.ts` | 双方共同 |
| `contracts/schemas/*.json` | 双方共同 |
| `contracts/conformance/*` | 双方共同 |
| `contracts/VERSION` | 双方共同 |
| `adapters/stub/` | 本工程（仅本地） |
| 真实端口实现 | harness-core |

规则：

- 修改 `contracts/` 必须双方评审。
- 主版本变更必须双方同步升级。
- 不得单方面增加只有自己知道的字段。

## 3. 端口清单

| 端口 | 方法 | 语义要点 |
|---|---|---|
| `IdentityPort` | describe、verify、authorize、revoke | 默认拒绝；token 只在内存；决策可解释 |
| `SecretPort` | describe、issue、revoke、status | 只发短期凭据；禁止通配 scope；不记录明文 |
| `ArtifactStorePort` | describe、put、stat、get、signedUrl、list、setRetention | 写入后校验哈希；租户隔离；大对象流式 |
| `ModelGatewayPort` | describe、complete、stream、embed?、health | 数据等级约束；requestId 幂等；不得伪造结果 |
| `ComputePort` | describe、quote、submit、status、list、cancel、reconcile、logs、release | 幂等提交；取消幂等；无法确认执行返回 unknown |
| `HpcSchedulerPort` | ComputePort + reserve、releaseReservation、queueInfo | 预留与队列深度；不支持时降级为普通提交 |
| `EventPort` | describe、publish、subscribe | 按 id 去重；单资源顺序单调；不含密钥 |
| `SessionPort` | describe、start、subscribe、wait、cancel | 会话不是事实源；预算强制；工具白名单 |
| `TelemetryPort` | describe、emit | 强制脱敏；低基数标签；失败不阻断业务 |

## 4. 结果封装

所有方法返回：

```ts
type PortResult<T> = { ok: true; value: T } | { ok: false; error: PortErrorInfo };
```

`PortErrorInfo` 含稳定 `code`、`message`、`retryable`、`details`、`traceId`。

### 错误码

| 错误码 | 可重试 | 说明 |
|---|---|---|
| `INVALID_ARGUMENT` | 否 | 请求不合法 |
| `UNAUTHENTICATED` | 否 | 未认证 |
| `PERMISSION_DENIED` | 否 | 越权或策略拒绝 |
| `NOT_FOUND` | 否 | 不存在或无权感知 |
| `CONFLICT` | 否 | 幂等冲突或状态冲突 |
| `QUOTA_EXCEEDED` | 否 | 配额不足 |
| `NOT_SUPPORTED` | 否 | 能力缺失，不得假装支持 |
| `UNAVAILABLE` | 是 | 暂时不可用 |
| `TIMEOUT` | 是 | 只代表调用方未收到响应 |
| `UNKNOWN_EXECUTION` | 否 | **必须先对账，禁止自动重试** |
| `INTERNAL` | 视情况 | 实现内部错误 |

`UNKNOWN_EXECUTION` 是整个契约里最重要的错误：它保护的是“重复执行昂贵或不可逆操作”这一类事故。`reconcile()` 返回 `unknown` 时同样禁止重试。

## 5. 能力声明

每个端口通过 `describe()` 返回 `PortCapabilities`，至少包含：

- `contractVersion`
- `implementation`
- `degraded` 与 `degradedReason`
- `features`
- `residency`
- `limits`

调用方必须：

- 检查 `degraded`，不得把桩当生产。
- 检查 `features`，缺失时降级而不是假设存在。
- 检查 `contractVersion`，不兼容时拒绝启动。

对应的 JSON Schema：`schemas/capability-descriptor.schema.json`。

## 6. 集成清单

harness-core 在联调前生成 `IntegrationManifest`（见 `schemas/integration-manifest.schema.json`），声明：

- 实现名、版本、所有者
- 契约版本
- 环境（local / staging / production）
- 每个端口的 transport 与 endpoint 引用
- features、limits、degraded
- 数据驻留与已知限制

本工程用 `contracts/fixtures/integration-manifest.stub.json` 描述桩实现，并在测试中校验。

## 7. 版本与兼容

```text
主版本：删除方法、改变语义、必填字段变化
次版本：新增端口、新增可选字段、新增错误码
修订号：文档、注释、类型修正
```

当前版本：`0.1.0`（见 `VERSION`）。

联调检查：

1. 双方 `IntegrationManifest.contractVersion` 一致。
2. 一致性用例全部通过（`conformance/cases.yaml`）。
3. 新增字段必须可选且有默认行为。
4. 删除字段必须先 deprecated 一个版本。

## 8. 一致性用例

`conformance/cases.yaml` 是可机读用例集，`cases.md` 是文字说明。每个端口至少覆盖：

- 正常路径
- 幂等重放
- 超时
- 未知执行
- 权限拒绝
- 能力缺失

本工程用 `adapters/stub` 跑这些用例；harness-core 用真实实现跑同一组用例。结果按 `conformance/README.md` 的 `results.json` 格式交换。

## 9. 与 DSH 的关系

DSH 是 Harness，不是端口实现。`SessionPort` 由 harness-core 适配到 DSH 会话能力；本工程不直接依赖 DSH 或 Cordis 类型。

好处：

- DSH 升级不影响本工程编译；
- 本工程可先用 `StubSessionPort` 跑通全流程；
- 合并时只需 harness-core 提供一个 `SessionPort` 实现。

## 10. 不允许的行为

- 在本工程内实现云/HPC/模型适配器。
- 在契约里写供应商专有字段。
- 用 `degraded: false` 标记桩。
- 让 Agent 拿到长期密钥。
- 把 `UNKNOWN_EXECUTION` 当可重试错误。
- 在错误信息里泄露密钥或完整请求体。
