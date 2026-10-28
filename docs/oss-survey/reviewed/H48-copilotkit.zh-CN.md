# H48 CopilotKit：前端事件与运行实例一致性

对象 `CopilotKit/CopilotKit`；SHA `54dddf799b9dd2be67731baba35416ef5feafa21`，提交2026-10-21T22:08:10+00:00；来源 `/tmp/oss-CopilotKit-CopilotKit`。静态复核core连接状态、运行参数及实例通知回归；未接入其Runtime。许可以根LICENSE及选用包为准。

## 实现链与边界

前端注册agent → 连接远端Runtime并发现能力 → 按thread取运行实例 → 订阅AG-UI事件 → 更新工具/中断/消息展示。它同时包含前端组件和执行编排能力，公司只能按边界取用显示/协议适配部分，不能整体引入成为第二Agent Runtime。

注册表区分`ok/failed/aborted/ignored`：nonCritical请求失败忽略；用户取消且非超时归aborted；其余归failed。可选Inspector元数据超时5秒，不应把这种非关键探测失败显示成整个计算平台不可用。连接代次和in-flight状态用于阻止并发探测与过期响应混淆；UI状态分类不构成后台任务终态。

```59:68:packages/core/src/core/agent-registry.ts
  error: unknown,
  meta: RuntimeRequestMeta | undefined,
): RuntimeRequestOutcome {
  if (meta?.nonCritical) {
    return "ignored";
  }
  if (isAbortError(error) && !meta?.timedOut) {
    return "aborted";
  }
  return "failed";
```

run-handler显式区分用户停止当前审批与切换历史/thread导致的取消；前者要保留错误结果，后者可丢弃旧结果。`runId`、`resume`是交互协议标识，不是云/HPC/QPU幂等键或额外科学资源句柄。`runTool`可选择模型follow-up，公司不能直接把该选项接成额外模型循环。

## 测试证据

`packages/core/src/__tests__/core-agent-run-started.test.ts:24-67`复现每thread的clone不在注册表、导致只订阅注册表的Inspector丢事件的问题；要求通知实际运行实例，递归follow-up只通知一次。借鉴点是订阅对象必须是实际会话实例，而非碰巧同名的注册对象。本轮未执行测试。

## 公司落点

三栏工作台可统一显示DSH对话事件、平台作业事件和制品变化，但必须分开来源、版本与状态。Web/本地客户端共享同一服务端事实，不以两个页面的临时状态互相覆盖；断线重连先重新查询任务，停止对话不代表取消平台作业。

前端批准按钮仅发送审批意图；宿主再次核验身份、租户、参数版本和权限。前端工具若能发外部副作用，仍须经过公司合同入口，不能把AG-UI完成事件当平台受理证明。

证据范围：`packages/core/src/core/agent-registry.ts:51-68,134-158`；`packages/core/src/core/run-handler.ts:25-62,74-90`；上述回归`:24-67`；根LICENSE。此范围不证明完整前后端协议与DSH兼容。
