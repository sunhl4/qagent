# 公司 Super DSH 架构

日期：2026-11-04。2026-11-06 起，上游 Super-agent 的整条流程是控制面基座。Router、订阅和注意力面板属于这条流程，用来承接大量任务和没有人逐条输入的任务。原型仍未作为正式产品发布，所以本地账本只做这条流程的薄替身，不复制它的内部表、提示词或第二套运行时。锁定版本之后，由上游的 Router 和订阅接管事件分发；公司继续拥有工具包、审批策略和平台时钟。

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

## 基座

上游流程是：来源进入工作项，工作项带终态、预算和截止，书面规则写进 Mandate，一次 DSH 会话在能力边界内调用工具，结果回到原对话，只有必须由人决定时才占用注意力。

公司功能都嵌在这条流程里。办公、超算、云、真机、LaTeX、GitLab 计划和研究时钟是会话里的工具。实验卡是书面规则。平台时钟只投递候选触发，开工单仍走同一条 `evaluate`。本地 SQLite 账本的角色是 `stand_in: local-control-plane`。它不升成全公司事实源，也不再长出第二套队列。

`contracts/superagent.json` 的 `architecture.flow_foundation` 记录这个划分：`required_upstream` 含 `router`、`subscription`、`attention`。无人输入的任务从 Source 事件进入；没有书面规则时受理模式保持 `observe`；书面规则打开工单后，公司策略仍然询问或拒绝超算、云和真机。锁定后被替换的只是替身账本和替身里的线程绑定，不是 Router 本身。本地 `subscriptions` 表只记录工单和线程的对应，不负责把外部事件推进会话。

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
