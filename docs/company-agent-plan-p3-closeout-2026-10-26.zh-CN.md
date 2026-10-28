# P3 阶段收口记录：受管通用 Agent 能力（2026-10-26）

依据：[约 2000 人天计划](company-agent-2000-person-days-development-plan-v1.0.zh-CN.md) P3（180 人天）。本记录覆盖 P3 六个工作包在内核与门禁侧的完成状态与真实边界；批次链条：[P3-A1 网页抓取](company-agent-plan-p3a1-webfetch-2026-10-26.zh-CN.md) → [P3-A2 检索硬化](company-agent-plan-p3a2-webfetch-hardening-2026-10-26.zh-CN.md) → [P3-B1 终止预算](company-agent-plan-p3b1-budgets-2026-10-26.zh-CN.md) → [P3-B2/B3 数据与引用](company-agent-plan-p3b2-b3-data-reference-2026-10-26.zh-CN.md)。

## 1. 工作包状态

| P3 工作包（计划口径） | 批次 | 内核交付 | 状态 |
| --- | --- | --- | --- |
| 受管网页检索、注入隔离、来源引用、未完整状态 | P3-A1/A2 | `company_fetch`（allowlist 失效闭合、地址钉扎、title 引用、4 类注入信号、完备性标记） | ✅ 内核完成 |
| 终止预算（token/调用/墙钟/费用/审批等待） | P3-B1 | `contracts/budgets.json` + `budget.py` 按轮账本（调用 128/轮、墙钟 1.8×10⁶ ms/等待 16/真机 4/提交 16），invoke 派发前失效闭合 | ✅ 首切片（token/费用等 P7 对账接入） |
| 数据处理与协作插件 | P3-B2 | `company_table_profile` 有界 CSV 定型/摘要 | ✅ 数据处理切片；Office/PDF 转换未打开（见边界） |
| 会话、消息、文件引用、历史、任务拆分、工作区上下文 | P3-B3 | `company_workspace_reference` 元数据引用绑定（显式读取路径 + 字节预算 + 完备性） | 瓦 ✅ 引用切片；会话/历史/任务拆分为 DSH 运行时职责，内核不建第二 runtime |
| 受管代码执行和文件操作 provider | — | 未开（见边界 2） | ⏸ 待执行环境 Owner |
| WorkBuddy/Codex 类通用场景验收 | — | 既有门禁四类场景（normal/denied/fault/reconciliation 19 项）+ 每批次反例门禁 | ✅ 以确定性门禁承载（模型无判分） |

## 2. 关键边界（诚实的不完整）

1. **文件回读**由 DSH 原生 read 工具承担（带字节预算），内核不复制该职责；引用批次只提供哈希/形状绑定的元数据登记。
2. **受管代码执行 provider**：没有宿主执行环境（容器/命名空间/网络凭据裁定器）Owner 之前，本仓库不把「伪 sandbox」写进合同。合同侧安全姿态已就位：DSH 侧无 shell preset（managed_builtins 仍排除 bash/pwsh），官方 Codex 维持 `permissionMode: never`、`inheritsParentContext: false` 且拿不到设备工具；执行 provider 等待与 P4 平台适配一起按真实接口立项（预算 45 人天保留在 P3/P4 交界）。
3. **预算的 token/费用维度**等待 P7 计费事实源接入同一 `budget.py` 账本；先到账的维度是调用次数、墙钟、审批等待和真机/提交子限额。
4. 办公/文档转换与办公插件：等待试点用户任务证据再立项，未写半成品合同。

## 3. 门禁与证据

- `docs/evidence/compliance-local.json`：本收口时 **19/19 ok**（P3-A1 起新增 `web-fetch-allowlist-disabled`、P3-B1 起新增 `turn-budget-invocations-exhausted`），合同 digest `06a4f0c9…`；并行门户批次随后追加场景使门禁自适应到 22/22（digest `9d5731b5…`），证据文件始终以全绿为准，删除场景同样会触发重生成。
- 全量验证（P3 收口时）：主仓 pytest（含 24+A2 检索、14 预算、9 数据、8 引用新用例）、`tests/ui` node 独立通过；工具合同时点 52 项（并行门户批次同期推进，工具数以后续记录为准）、能力 11 项。

## 4. 阶段出口判读

按计划 P3 阶段出口条款核对：通用 Agent 文件/代码/网页/文档类受管任务——文件 ✅（工作区工具 + 引用绑定）、网页 ✅（allowlist 抓取）、文档 ✅（latex + 知识）、**代码目标仅到受管只读与预算边界，执行等待环境 Owner**——即出口第三句以「无新模型循环/工具循环、无 shell preset、无绕权」的形态满足；P4 云/HPC/真机适配不受影响。
