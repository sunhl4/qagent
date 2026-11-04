# 公司 Super DSH 架构

日期：2026-11-04。全公司只用这一套结构。上游 `dsh-superagent-prototype` 仍未作为正式产品发布，所以公司实现它的对象模型和失败闭合，不复制它的内部表、提示词或第二套运行时。

## 三个面

```text
员工、工作区、研究事实
        │
        ▼
控制面  Source → Trigger → Eval → Mandate → Ticket → Assignment → Subscription
        │  Mandate 只有 boot / lab / algo / sign
        ▼
执行面  一个 DSH 会话 + 公司工具包
        ▲
平台时钟  research-layer：实验、租约、预算、证据
        └── 只投递 research 触发
```

| 面 | 拥有 | 不拥有 |
|---|---|---|
| 控制面 | 工单账本、受理模式 `off` / `observe` / `auto` | 模型循环、科学结果、资源调度 |
| 执行面 | DSH 会话、现有公司工具包、审批策略 | 第二个 Agent、shell 工人、未发布的官方 Super-agent 包 |
| 平台时钟 | `research-layer/` 的实验和证据 | 根目录 `contracts/`、工单终态、设备批准 |

## 公司使用规则

1. 一个员工、一个租户、一张工单，都进入同一个控制面。GitHub 和飞书通道先关闭，合同里显式标成 `false`。
2. 平台时钟不能直接开工单。`company_work_item` 的 `signal` 只记录 `research` 候选触发。要开工单，必须再做一次 `evaluate`，并且 `mode` 为 `auto`、`strength` 为 `explicit`，范围只能是四个公司 preset。`observe` 和 `off` 只记决策。`unknown` 执行仍可查询；结案只走 `reconcile`，不能改回执行中，也不能改绑会话。
3. Watchdog 是现有公司策略，不是新的巡检循环。它不能改策略、不能在执行状态未知时重试、不能自己打开工单。
4. 设备执行继续服从原策略：`lab` / `sign` 询问，`boot` / `algo` 拒绝。
5. 根目录工具合同和研究层契约保持两套。研究层需要计算或模型时，调用根目录已有 provider，不另写云、HPC 或模型网关。

## 合同

- `contracts/superagent.json` 是这套架构的机器可读合同，当前 `1.3.0`。
- `company-agent architecture` 输出拓扑。
- `company-agent harness` 在公司工具包无法映射到同一个 DSH 会话时失败。
- 工单执行只记录 `dsh:` 会话引用和公司工具包名称。`recover` 按租户把这组短字段读回来。会话正文、科学结果和密钥留在控制面外面。未知执行不能改绑到另一会话。
