# DSH 插件与服务开发规范

## 1. 适用范围

本规范约束公司所有基于 DeepSeek Harness（Cordis）开发的插件、服务、工具和事件。

目标：

- 统一结构
- 可组合
- 可测试
- 可观测
- 可安全审查
- 可回滚

## 2. 插件分类

| 类型 | 作用 | 示例 |
|---|---|---|
| 服务插件 | 提供 `ctx.<name>` 能力 | `ctx.literature` |
| 工具插件 | 向模型暴露工具 | `search_papers` |
| 策略插件 | 监听事件并决策 | 预算检查 |
| 适配器插件 | 接入外部系统 | Slurm、模型供应商 |
| 界面插件 | 扩展 UI | 报告面板 |
| 技能包 | 提示与方法 | 复现流程 |

## 3. 目录结构

```text
packages/plugin-<name>/
  package.json
  tsconfig.json
  src/
    index.ts          # 插件入口
    service.ts        # 服务实现
    schema.ts         # 配置与输入输出 schema
    events.ts         # 事件声明
    errors.ts         # 错误码
    types.ts          # 公共类型
  test/
    unit/
    contract/
    integration/
  README.md
  CHANGELOG.md
  LICENSE
```

## 4. 命名

| 对象 | 规范 | 示例 |
|---|---|---|
| 包名 | `@company/dsh-plugin-<domain>` | `@company/dsh-plugin-literature` |
| 服务键 | `ctx.<domain>` | `ctx.literature` |
| 事件名 | `<domain>:<phase>` | `experiment:submit` |
| 错误码 | `<DOMAIN>_<REASON>` | `EXPERIMENT_BUDGET_EXCEEDED` |
| 配置键 | 小写短横线 | `max-concurrency` |

## 5. 服务实现规则

1. 一个服务只负责一个能力域。
2. 服务接口必须有 TypeScript 类型。
3. 所有公开方法必须有 JSDoc。
4. 方法必须声明是否幂等。
5. 跨服务调用通过 `inject`。
6. 不直接读全局配置。
7. 不直接持有长期凭据。
8. 卸载时释放所有资源。

## 6. 生命周期

```text
load
  → validate manifest
  → check version range
  → check permissions
  → register schema
  → inject dependencies
  → start
  → ready
  → serve / listen
  → drain
  → dispose
  → unload
```

### 6.1 加载失败

- 版本不兼容 → 拒绝加载。
- 依赖缺失 → 等待或拒绝。
- 权限超限 → 拒绝加载。
- schema 无效 → 拒绝加载。

### 6.2 运行失败

- 单次调用失败 → 返回结构化错误。
- 连续失败 → 熔断。
- 资源泄漏 → 告警并回收。

### 6.3 卸载

- 停止接受新请求。
- 等待进行中请求完成或超时。
- 释放连接、定时器、租约。
- 注销事件。
- 记录残留。

## 7. 可逆副作用

每个注册必须返回 disposer：

```text
const dispose = ctx.effect(() => {
  const handle = registerSomething()
  return () => handle.close()
})
```

禁止：

- 注册后不注销。
- 在模块顶层做副作用。
- 用全局变量保存状态。
- 卸载后仍有定时器运行。

## 8. 事件

### 8.1 分发模式选择

| 需求 | 模式 |
|---|---|
| 只通知 | `emit` |
| 允许包装/短路 | `waterfall` |
| 并行观察 | `parallel` |
| 顺序执行并收集 | `serial` |
| 首个有效值即停 | `bail` |

### 8.2 策略事件

```text
ctx.on('tool:before', async (call, next) => {
  const decision = await policy.evaluate(call)
  if (decision === 'DENY') return deny(call)
  if (decision === 'REQUIRE_APPROVAL') return requireApproval(call)
  return next()
})
```

规则：

- 有决策权时短路。
- 仅观察时必须 `next()`。
- 不得在策略中执行副作用。
- 决策必须可解释。

## 9. 工具设计

### 9.1 工具定义

```text
name
description（何时使用、何时不用）
input schema
output schema
side effects（none / read / write / irreversible）
cost estimate
timeout
idempotency
permissions
```

### 9.2 工具粒度

- 一个工具做一件事。
- 参数不要过多。
- 错误要可区分。
- 输出要结构化。
- 大结果用引用，不直接塞上下文。

### 9.3 高风险工具

真实设备、生产变更、外发数据类工具：

- 不直接暴露给模型。
- 通过平台网关代理。
- 强制审批与审计。
- 短期凭据。
- 幂等与去重。

## 10. 配置

```yaml
plugin: "@company/dsh-plugin-experiment"
version: "1.0.0"
config:
  maxConcurrentExperiments: 4
  budget:
    defaultMaxCost: 100
    currency: "CNY"
  approval:
    requireFor:
      - "gpu_count > 1"
      - "resource_type == 'hpc'"
```

规则：

- 配置必须有 schema。
- 未知字段报错。
- 敏感值用引用，不写明文。
- 配置变更需审计。

## 11. 错误处理

### 11.1 错误结构

```json
{
  "code": "EXPERIMENT_BUDGET_EXCEEDED",
  "message": "Estimated cost exceeds budget",
  "retryable": false,
  "details": {"estimated": 150, "budget": 100},
  "trace_id": "..."
}
```

### 11.2 错误分类

| 类型 | 可重试 | 处理 |
|---|---|---|
| 输入错误 | 否 | 返回修正建议 |
| 权限错误 | 否 | 记录审计 |
| 资源不足 | 是（延迟） | 排队或降级 |
| 外部超时 | 视情况 | 先对账 |
| 未知执行 | 否 | 人工处理 |
| 内部错误 | 是（有限） | 退避重试 |

## 12. 可观测

每个插件必须提供：

- 健康检查。
- 关键指标。
- 结构化日志。
- trace span。
- 错误计数。
- 延迟直方图。

指标命名：

```text
dsh_plugin_<domain>_requests_total
dsh_plugin_<domain>_errors_total
dsh_plugin_<domain>_duration_seconds
dsh_plugin_<domain>_inflight
```

## 13. 测试

| 类型 | 内容 |
|---|---|
| 单元 | 纯逻辑、边界、错误 |
| 契约 | 输入输出 schema |
| 集成 | 与真实依赖 |
| 生命周期 | 加载、卸载、重载 |
| 并发 | 竞态、幂等 |
| 故障 | 依赖不可用、超时 |
| 安全 | 权限、注入、越权 |

覆盖率目标：

- 核心服务 ≥ 80%
- 策略 ≥ 95%
- 资源适配器 ≥ 80%

## 14. 版本

- 语义化版本。
- 主版本变更表示不兼容。
- 插件声明兼容的 DSH 版本范围。
- 破坏性变更需迁移指南。
- 保留旧版本至少一个发布周期。

## 15. 发布

```text
[ ] 测试通过
[ ] 覆盖率达标
[ ] 安全扫描
[ ] SBOM
[ ] 变更日志
[ ] 迁移脚本
[ ] 回滚方案
[ ] 文档
[ ] 示例
[ ] 兼容性矩阵
```

## 16. 反模式

1. 插件直接 import 另一个插件的实现。
2. 注册不注销。
3. 在顶层执行副作用。
4. 工具参数过多。
5. 把大结果塞进上下文。
6. 高风险工具直接暴露。
7. 配置无 schema。
8. 错误不可区分。
9. 无健康检查。
10. 无版本兼容声明。
