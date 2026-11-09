# Super-agent 接入与两套时钟

## 1. 计划假设

2026-10-31 晚，DeepSeek 产品部发表《Super-agent 设计探索：迈向更自主的 Agent 系统》，并开源研究原型 [dsh-superagent-prototype](https://github.com/deepseek-ai/dsh-superagent-prototype)（MIT）。原型是 DSH 插件，服务一个 GitHub 仓库，可选接入飞书。文章写明它不是正式产品，发布代码与内部实例不完全相同。

本文件在此之外采用一条**计划假设**，不是已核验证据：

> 文章中的五模块会全部完成，并以可版本锁定的开源形式提供：Router / Worker 双层、事件驱动（过滤、订阅直通、Inline & Spill、链式召回、投机执行）、面向人的异步与多信道交互、计算 / 状态 / 环境分离（含端侧 daemon）、外部 Watchdog。

在该假设成立之前，阶段 0 到阶段 3 不依赖它。阶段 4 以接入上游为准；上游未冻结时走第 8 节的降级路径，禁止在本工程里先写一套临时路由器。

证据等级：原型仓库为 A，文章为企业自述（C），「五模块将全部开源」为计划假设。不得把原型里的工具名、表结构或提示词写进长期数据契约。

## 2. 原计划里的路由器留在原处

原调研里的 router 是**模型路由**，不是 Super-agent 的会话 Router。它已经定了主实现，这次不改、不重写、也不换成 Super-agent。

| 名字 | 原计划 | 开源组件 | 本工程做什么 |
|---|---|---|---|
| 模型路由 | `docs/01` 第 7.2 节、`docs/10` 第 5 节、`schemas/model-route.schema.json` | 推理引擎用 DeepInfer、vLLM、SGLang 或 TensorRT-LLM。网关负责鉴权、配额、限流和回退 | 只保留路由规则和 `ModelGatewayPort`。进程在 harness-core |
| 任务编排 | Temporal | Temporal | 实验、租约、审批的下一步由工作流决定 |
| 编码会话路由 | 2026-10-31 之后才出现 | 上游 Super-agent 的 Router / Worker | 未冻结前不自研。降级路径是一工单一次会话 |

LangGraph 在 78 项矩阵里是参考，用来对照有状态代理图，没有被选成路由器。原计划没有采用 LiteLLM 或另一套独立路由产品。

## 3. 两套时钟

| 时钟 | 时长 | 事实源 | 负责 |
|---|---|---|---|
| Agent 时钟 | 分钟到数小时，并可跨进程重启延续同一工单 | 上游 Super-agent 的 Ticket、Mandate、Trigger | 仓库内编码、评审跟进、IM 与 GitHub 上的连续对话 |
| 平台时钟 | 小时到数月 | Temporal + PostgreSQL + 对象存储 | 实验尝试、资源租约、未知执行、审批等待、证据与失败库 |

编码工单的后续讨论留在同一个 Executor Session。每一次实验尝试仍启动新的上下文。实验完成、队列状态和预算耗尽可以作为上游 Source 的 Trigger，平台状态不写入 DSH Session。

## 4. 原调研工具的去留

原矩阵「每类一个主实现、不让两套 harness 接管同一工作区」继续有效。Super-agent 是 DSH 上的插件，不构成第二套 harness。

| 席位 | 决定 |
|---|---|
| 编码外循环 | 用上游 Super-agent。Ralph 的 shell 循环不落地 |
| Harness | 继续 DSH。Pi、OpenHands、SWE-agent、Aider、Cline、Codex、goose 不部署 |
| 有状态代理图 | LangGraph 不部署。编码事件用上游 Engine，实验状态用 Temporal |
| 开发方法 | Superpowers 保留为 Executor 技能，并由服务端门禁强制 TDD 与审查 |
| 规格入口 | spec-kit 保留。规格成为 Mandate 的范围 |
| PR 评审 | pr-agent 或只读评审工单保留。作者 Agent 不审查自己打开的 PR |
| 实验协议 | autoresearch 的预算、指标、修改面、保留或撤销保留 |
| 持久工作流 | Temporal 保留给实验、租约和审批 |
| 文献、追踪、调度、测试、量子 | GROBID、PaperQA、MLflow、DVC、Slurm、Kueue、SkyPilot、Playwright、Qiskit 等全部保留 |

Ralph 仍贡献三条语义，只用于实验尝试：上下文要短，状态要外置，完成要可验证。

## 5. 本工程不实现的部分

以下能力全部消费上游，本工程不重写：

- Router 与 Worker 的会话组织、批处理和订阅直通
- Trigger、Thread、Ticket、Mandate、Assignment 的存储与恢复
- Inline & Spill、链式召回
- 异步 ReAct 与多信道回复
- 计算、状态、执行环境分离，以及端侧 daemon
- Watchdog 的巡检循环

本工程保留：Goal、Milestone、ExperimentSpec、RunManifest、租约、成本账本、策略、审批、失败库、文献与复现。软件工厂只保留规格、方法门禁、独立评审和合并策略。

## 6. 接入上游时仍然生效的约束

完整开源也不放宽下列规则。

1. 高风险动作仍经过平台策略与审批。投机执行可以在后台准备，交付到主分支、真实硬件、超预算资源或外发数据之前必须停下。
2. 主动行为默认只记录。要交付结果，必须有书面规则，并且规则版本写入 Mandate。
3. Watchdog 可以报告无进展和方向偏离。它不能修改策略、预算、租约，也不能在执行状态未知时自动重试。
4. 端侧 daemon 不保存会话，不持有长期密钥。凭据仍由 `SecretPort` 签发短期令牌，任务结束撤销。
5. 执行环境使用平台沙箱分级。上游原型「以操作系统用户免审批执行」不作为生产配置。
6. 作者工单与评审工单分离。合并门禁仍是测试、安全扫描、证据和人工审批。
7. 跨月研究记忆放在平台的失败库与证据图。不把链式召回当作科学结论的存储。

## 7. 对当前代码的含义

`packages/domain` 与 `packages/pipeline` 里的实验循环、失败库、租约、成本、检查点和回收扫描属于平台时钟，保持不变。它们不是编码路由器的半成品，也不要改成常驻 Agent 循环。

阶段 4 的降级门禁已落地：`packages/domain/src/software-gate.ts` 判断能否合并，`packages/pipeline/src/software.ts` 为一张工单启动一次会话。顺序是先会话后评估：调用方在会话结束后提交外部证据触发 `evaluateSoftwareMerge`。`packages/domain/src/platform-signal.ts` 产生实验完成、租约变化和预算耗尽事件，供以后映射到上游 Source。这些模块不保存 Ticket，也不读取会话正文。

工作区包继续为单次实验尝试提供 Git worktree。编码工单的目录生命周期在阶段 4 交给上游 Executor；在降级路径中仍由本工程按单工单创建。

## 8. 降级与回滚

上游 Super-agent 未发布可锁定版本，或接口与本文假设不符时：

1. 阶段 0 到阶段 3 继续按现有实验与租约实现交付。
2. 阶段 4 改为单工单 headless 会话：一单一次新会话、独立 worktree、相同的规格与合并门禁，装配标记 `degraded`。
3. 不在降级期间把 Router、Watchdog 或 Ticket 库抄进本仓库。
4. 已接入上游后若需退出：停止把本仓库注册为它的 Source，编码任务回到第 2 步。实验数据、租约和证据不依赖它的数据库，无需迁移。

## 9. 影响范围

- 软件工厂的执行底座从「自建 Ralph 式外循环」改为「接入上游 Super-agent」。
- 实验协议、资源编排、文献复现、多租户治理的主实现不变。
- 研究层契约不增加 Super-agent 的内部表。公司侧只用 `contracts/superagent.json` 的对象链和 `flow_foundation` 标明基座；上游 API 冻结后按该划分替换工单存储，仍不复制其内部表结构。
- harness-core 若决定内置该插件，本工程只消费，不平行维护第二份。

## 10. 2026-11-06：流程基座

上游 Super-agent 的整条流程定为公司控制面基座，不再只当作阶段 4 的可选项。Router、订阅和注意力面板是这条基座的必要部分，用来承接大量任务和没有人逐条输入的任务。锁定版本之前，根目录 `company_work_item` 账本是这条流程的薄替身，订阅只记录工单和线程的对应。研究层继续不保存 Ticket，不读取会话正文，不自研 Router。实验、租约和证据留在平台时钟，将来只作为上游 Source 的候选触发，由上游 Router 按订阅进入同一条流程。没有书面规则时只记录。书面规则打开工单后，公司策略仍然管超算、云和真机。

公司时钟在本地指标运行时调用工作区包的 `createExperimentWorktree` 和 `removeExperimentWorktree`。脏工作树仍由工作区包拒绝删除。公司侧的租户次数汇总不调用本层日报，避免把假设和 Markdown 带回工具结果。

## 11. 变更记录

| 日期 | 内容 | 回滚 |
|---|---|---|
| 2026-11-01 | 按「五模块将完成并开源」修订编码协作层与阶段 4。阶段 0–3 的实现不改 | 删除本文件，并恢复 `docs/02`、`docs/05`、`docs/08`、`docs/13` 中指向本文的段落；实验循环代码无需回滚 |
| 2026-11-01 | 写明原模型路由与 Super-agent 会话路由是两套东西 | 模型网关、vLLM / SGLang / DeepInfer 选择保持 | 删去第 2 节即可 |
| 2026-11-06 | 上游流程定为控制面基座；本地账本只是替身 | 删除第 10 节，并去掉 `contracts/superagent.json` 的 `flow_foundation` |
| 2026-11-06 | 公司时钟调用已有 worktree；租户汇总不走本层日报 | 公司时钟不再调用 `worktree-once.mjs`，并去掉 `company_research_digest` |
