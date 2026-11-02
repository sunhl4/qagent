# adapters/stub

本目录只包含**测试替身**，不是生产适配器。

## 1. 定位

本工程（research-layer）不实现云平台、HPC、本地模型、身份、对象存储和凭据。这些属于 harness-core。为了让本工程可以在没有 harness-core 的情况下独立开发、编译和测试，这里提供一组内存桩。

## 2. 强制约束

- 每个桩的 `manifest().degraded` 必须为 `true`。
- 必须提供 `degradedReason`。
- 不得访问网络。
- 不得读取真实凭据。
- 不得写真实数据库或对象存储。
- 行为必须确定、可重复。
- 不得用桩冒充生产实现。

## 3. 桩清单

| 桩 | 端口 | 行为 |
|---|---|---|
| `StubIdentityPort` | identity | 内存 token 映射、grant 签发与撤销 |
| `StubObjectStorePort` | object_store | 内存内容寻址、sha256 校验、8MB 内联上限 |
| `StubCredentialsPort` | credentials | 短期 token、拒绝明文长期密钥、TTL 上限 |
| `StubModelPort` | model | 确定性假输出、数据等级检查、不支持流式 |
| `StubHpcPort` | hpc | 内存作业状态机、报价、对账、unknown 场景 |
| `StubCloudPort` | cloud | 同 HPC，provider 不同、单价不同 |
| `StubSessionPort` | session | 脚本化轮次、事件顺序、预算超限、失败注入 |
| `StubTelemetryPort` | telemetry | 内存收集、敏感字段拒绝、高基数拒绝 |

## 4. 失败注入

```ts
createStubStack({
  hpc: { scenario: "unknown" },   // 模拟无法确认是否执行
  model: { failNextWith: "TIMEOUT" },
  session: { exceedBudget: true },
});
```

## 5. 合并时会发生什么

合并后：

- harness-core 提供真实端口实现；
- 本工程的 `createStubStack` 仅用于测试；
- 两个实现跑同一组 `contracts/conformance/cases.md`；
- 通过后，本工程的业务代码不需要修改。

## 6. 不允许的扩展

- 在这里实现 Slurm 客户端。
- 在这里实现云厂商 SDK 调用。
- 在这里缓存真实凭据。
- 在这里模拟“已经生产可用”。
