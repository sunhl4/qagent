# DeepSeekHarness 企业级自主研发与自动科研平台 · 总技术报告

版本：0.2（计划修订）
日期：2026-10-29，修订 2026-11-01
定位：公司内部平台的技术调研、目标架构与实施基线
读者：算法、平台、HPC、前端、SRE、安全、产品与管理团队

---

## 0. 一页结论

公司要做的不是一个“会自动写代码的聊天窗口”，而是一套**可长期无人值守运行的研发操作系统**。它的核心不是模型本身，而是模型外面的运行框架：任务从哪来、谁能批准、资源怎么申请、执行怎么恢复、结果怎么证明、失败怎么回收。

DeepSeek Harness（下称 DSH）适合作为这套系统的**统一 Agent Harness**，即统一智能体运行框架。公开资料显示它是一个“一切皆插件”的开源 Agent 框架，底层是 Cordis 插件运行时，工具、模型适配器、文件访问乃至 agent loop 本身都以插件形式挂载在共享上下文上。

但 DSH 不能单独承担以下职责，必须与外部系统组合：

| 职责 | 归属 | 原因 |
|---|---|---|
| Agent 会话、工具调用、模型路由、插件扩展 | DSH + Cordis | 这正是 Harness 的强项，公司后续深度开发的主战场 |
| 仓库内编码协作：多信道、并行工单、重启后续跑 | 上游 Super-agent | 计划假设其五模块会完成并开源。本工程不重写 Router、Worker、Watchdog |
| 跨小时到跨月的实验、租约、审批与补偿 | 持久工作流引擎（首选 Temporal） | 实验与资源的事实源在平台。编码工单的续跑由 Super-agent 承担 |
| CPU/GPU/HPC/云/真实硬件的权威调度 | Slurm / Kubernetes + Kueue / SkyPilot / 设备适配器 | Harness 不能成为资源所有权和配额的事实源 |
| 租户、预算、审批、计费、审计 | 平台控制面 + PostgreSQL | 多用户共享必须由服务端强制，不能靠提示词 |
| 代码、数据、模型、实验、结果的证据链 | 对象存储 + MLflow + DVC + 签名清单 | 科学结论必须可复现，不能只留聊天记录 |
| 高风险动作的最终许可 | 策略引擎 + 人工审批 | 不可逆或高成本动作不能完全无人化 |

一句话架构：

```text
DSH 负责“怎么想、怎么调工具”
上游 Super-agent 负责“仓库里这张工单怎么连续做完”
Temporal 负责“实验和租约做到哪一步、失败了怎么办”
Slurm/K8s/SkyPilot 负责“在哪台机器上跑、跑多久、何时收回”
PostgreSQL/对象存储/MLflow/DVC 负责“发生过什么、凭什么相信”
策略引擎 + 审批 + 短期租约负责“谁允许你这么做”
```

与另一台电脑上已开发的 harness-core 采用**契约优先的平行开发**：对方实现 DSH 运行时、云平台、本地 HPC、本地模型、身份、存储与凭据；本工程实现目标、任务、实验、证据、策略、审批与领域工作流。两边只共享版本化端口契约，不共享实现代码，最终按契约合并。

首个可交付目标不是“全自动科学家”，而是：

> 一个研究问题、一个基线、一个指标、一个预算，能够连续运行 24 小时，每轮实验可追踪、可复现、可停止、可回滚、资源可回收。

---

## 1. 研究边界与证据等级

### 1.1 本报告的依据

本报告完全基于本轮公开网络与 GitHub 调研，不引用任何既有本地工程材料。新增核对的重点对象：

- DeepSeek Harness 官方站点与官方文档站
- Cordis 插件框架的公开教程与概念参考
- DeepSeek 官方推理框架 DeepInfer
- DSH 相关公开 npm 包与社区资料
- 78 个公开 GitHub 项目/实现案例

### 1.2 证据等级

| 等级 | 含义 | 本报告中的用法 |
|---|---|---|
| A | 官方文档、官方仓库、可下载代码、官方 API | 可作为架构约束 |
| B | 同行评审论文、可复现实验、生产系统报告 | 可作为设计参考 |
| C | 企业自述、媒体报道、社区文章 | 只能证明“存在这种说法” |
| D | 由 A/B 推导的工程判断 | 必须标注为推断 |
| U | 检索后仍无一手来源 | 不得用猜测填补 |

### 1.3 必须区分的三件事

1. **模型**：DeepSeek 或其他厂商的大模型权重/API。
2. **Harness**：把模型变成可执行 Agent 的运行框架，即 DSH。
3. **平台**：把 Harness 变成多用户、可计费、可审计、可长期运行的企业系统。

三者可以独立演进。公司自部署模型不等于自部署 Harness；使用 DSH 不等于拥有平台；拥有平台不等于拥有科学结论。

### 1.4 公开信息的时效风险

DSH 官方站点明确标注为 **preview**，核心插件与 API 仍在演进。因此：

- 正式开发必须锁定仓库 commit 或发行版本。
- 所有 DSH API 依赖必须经过公司内部适配层。
- 不得把 preview 阶段的插件清单、事件名、配置格式直接写进长期数据契约。
- 每季度做一次 Harness 兼容性回归。

---

## 2. DeepSeekHarness 事实核验

### 2.1 官方公开事实（A 级）

| 项目 | 公开信息 |
|---|---|
| 名称 | DeepSeek Harness，简称 dsh |
| 性质 | 开源 Agent Harness，public preview |
| 架构基础 | Cordis “everything is a plugin” |
| 运行形态 | 桌面应用；也可通过 Web UI 启动 |
| 快速启动 | 安装 Node.js 后执行 `npx @deepseek-ai/dsh web` |
| 源码 | `https://github.com/deepseek-ai/deepseek-harness` |
| 官方站点 | `https://www.deepseek.com/en/harness` |
| 官方文档 | `https://deepseek-harness.github.io/deepseek-harness/` |
| 主要能力 | 日常文档与数据处理、编码、研究检索与引用、后台任务、插件扩展 |
| 开发者能力 | 执行轨迹查看、运行时信息、工具调用排障 |
| 调度能力 | 支持定时或周期性任务 |

官方站点列出的典型场景包括：整理文件、分析表格、起草文档、生成幻灯片；探索仓库、修复缺陷、构建功能、运行测试；查找信息、核验事实、引用来源；运行脚本、批处理文件、跟踪进度；安装或自建插件。

这三点对本项目最关键：

1. **插件是一等公民**，公司能力应以插件形式沉淀，而不是 fork 一个大文件。
2. **有执行轨迹**，这是做审计和可观测的基础。
3. **有定时任务**，但它不等于企业级持久工作流，不能替代 Temporal。

### 2.2 Cordis 插件模型（A 级）

官方 Cordis 文档给出的五个核心概念：

| 概念 | 含义 | 对本项目的意义 |
|---|---|---|
| 插件即服务实现 | 插件可以是带 `apply(ctx)` 的函数，也可以是 Service 子类 | 公司每个能力域做一个插件包 |
| 上下文是服务容器 | 服务占据稳定的 `ctx.<key>`，如 `ctx.tools`、`ctx.llm`、`ctx.sessions` | 不要跨插件直接 import 实现，统一通过服务键解耦 |
| `inject` 声明依赖 | 插件声明依赖后等待服务就绪再启动 | 加载顺序由依赖表达，不靠人工编排 |
| 类型化事件 | 支持 `emit`、`waterfall`、`parallel`、`serial`、`bail` | 策略拦截最适合用 `waterfall` |
| 注册是可逆副作用 | 通过 `ctx.effect()`、`ctx.on()` 安装，卸载时自动撤销 | 必须为每个注册提供 disposer |

`waterfall` 的语义是环绕中间件：监听器收到 `(...args, next)`，调用 `next()` 执行下游；不调用 `next()` 直接返回就是短路。这正好对应“策略网关”：有决策权的监听器可以短路，仅观察的监听器必须委托。

### 2.3 公开包与接口线索（A 级，需按版本复核）

| 包 | 公开描述 | 用途判断 |
|---|---|---|
| `@deepseek-ai/dsh-sdk-client` | 通过 stdio JSON-RPC 驱动 DSH 运行时子进程的 TypeScript 客户端，含高层 turns API 与底层 HarnessClient | 适合平台后端以编程方式驱动会话 |
| `@deepseek-ai/dsh-sandbox` | 进程沙箱抽象 `ctx.sandbox`，定义同世界约束词汇与 `SandboxProvider` 契约 | 正好可作为公司沙箱接入点 |
| `@deepseek-ai/dsh-headless` | 一次性 core Agent/Session runner，基于 dsh-base，不含 Host、HTTP、浏览器层 | 适合批处理和无界面执行 |

这三条线索指向一个清晰的分工：

- **交互式使用**：DSH Web/桌面。
- **平台调度**：headless 或 SDK 驱动。
- **隔离执行**：`SandboxProvider` 接入公司容器/微虚机/K8s。

注意：包名、导出符号和参数必须以锁定的版本重新核对，不能仅凭公开描述写生产代码。

### 2.4 官方推理框架 DeepInfer（A 级）

DeepInfer 是 DeepSeek 官方开源的高性能推理框架，公开信息包括：

- Apache-2.0。
- 当前支持模型：DeepSeek-V4.1-Flash。
- 支持 NVIDIA SM100 GPU 与华为昇腾 950 NPU。
- 特性：优化 kernel、Attention DP / balanced CP、MoE EP + EPLB、投机解码、异步调度、batch-invariant 推理、确定性采样、结构化输出。
- 明确说明：完整推理服务所需的 KV cache 系统、PD 分离、数据并行副本间负载均衡“不包含在本次发布中”。

这条对一个准备自部署模型的公司极其重要：**官方推理框架不等于开箱即用的生产推理服务**。公司若自部署，必须补齐：

- KV cache 与上下文管理
- Prefill/Decode 分离
- 多副本负载均衡
- 网关、限流、配额、鉴权
- 可观测、灰度、回滚
- 模型评测与版本治理

### 2.5 模型授权与合规（必须单独核查）

DeepSeek 不同代际模型的权重、许可证和使用条款并不相同，历史版本存在自定义模型许可。正式商用前必须逐模型核查：

- 权重是否可下载、可否商用、是否需署名。
- 是否允许蒸馏、二次训练、对外提供 API。
- 输出内容责任与内容安全要求。
- 数据跨境与行业监管要求。
- 采购 API 时的服务条款、数据处理协议和 SLA。

本报告不替公司法务下结论。工程上必须做到：**模型可替换**，避免任何工作流对象、实验数据或评估基准绑定单一供应商。

---

## 3. 图片中四类范式与 DSH 的映射

图片给出的四个方案，本质上是四个不同层次的东西，不能横向比较优劣。

| 方案 | 它是什么 | 在 DSH 平台中的正确位置 |
|---|---|---|
| Superpowers | 装在现有 coding agent 上的技能与开发流程层 | **方法层**：把需求澄清、设计、计划、TDD、审查、收尾写成 DSH 技能/插件 |
| Karpathy autoresearch | 一个具体自动实验项目，清晰的实验循环范例 | **实验协议层**：固定时间预算、固定指标、单一可修改面、保留或撤销 |
| Ralph | 在 coding agent 外面运行的任务循环 | **实验语义**：每次实验尝试使用新上下文。编码循环改由上游 Super-agent 承担，不落地 shell |
| Pi coding agent | 核心简洁、扩展能力强的 agent harness | **设计参照**：说明 Harness 应保持小而可扩展；本项目用 DSH 替代 Pi 作为落点 |

### 3.1 Superpowers：方法层的正确抽象

Superpowers 的公开工作流是：

1. brainstorming：先澄清真正想做什么。
2. using-git-worktrees：在隔离分支和干净测试基线上工作。
3. writing-plans：拆成 2–5 分钟级别、带精确文件路径和验证步骤的任务。
4. subagent-driven-development 或 executing-plans：逐任务执行并审查。
5. test-driven-development：RED-GREEN-REFACTOR。
6. requesting-code-review：按严重级别报告，关键问题阻断。
7. finishing-a-development-branch：验证、合并/PR/保留/丢弃。

在 DSH 中的落法：

- 不要照抄它的插件格式，只吸收流程。
- 每个阶段做成 DSH 技能或独立插件服务。
- “关键问题阻断”必须由服务端策略执行，不能只靠 agent 自述。
- 计划文件、测试证据、审查结论都要落对象存储，不能只在会话上下文里。

### 3.2 autoresearch：实验协议的四个硬约束

公开项目刻意保持极简，只有三类文件：不可修改的 `prepare.py`、只允许 agent 修改的 `train.py`、人类维护的 `program.md`。核心约束：

1. **固定时间预算**：每次训练固定 5 分钟，忽略启动与编译。
2. **固定指标**：验证集 bits per byte，越低越好，且与词表大小无关。
3. **单一可修改面**：只允许改一个文件，diff 可审查。
4. **可比较性**：因为预算相同，不同结构改动可以横向比较。

这四个约束应升级为公司实验契约：

| 原型约束 | 公司级升级 |
|---|---|
| 固定 5 分钟 | 每类实验声明固定 wall-clock 或固定算力预算 |
| 单一指标 | 主指标 + 护栏指标 + 统计不确定性 |
| 单一文件 | 受限修改面 + 允许清单 + 禁止清单 |
| 保留或撤销 | 自动决策规则 + 人工复核门 + 失败库 |

### 3.3 Ralph：外循环语义，而不是 `while true`

公开实现的机制是：每轮启动一个新的 AI 实例，上下文清零；跨轮记忆只靠三样东西：

- Git 历史
- `progress.txt` 追加式经验
- `prd.json` 任务与通过状态

它的价值在于三个工程直觉：

1. **上下文会腐化**，长会话不如多轮短会话。
2. **状态要外部化**，不能依赖模型记忆。
3. **每轮必须有可机器判断的完成信号**。

但公开实现用 shell 循环驱动，不适合企业级 24/7。公司版本的映射：

| Ralph 原型 | 公司实现 |
|---|---|
| shell `while` 循环 | 编码工单用上游 Super-agent；实验尝试用 Temporal 启动新的 headless 会话 |
| `prd.json` | 平台任务表（Postgres）+ 严格状态机 |
| `progress.txt` | 结构化 ResearchMemory / 失败库 |
| Git 历史 | 分支 + 签名提交 + 运行清单 |
| `<promise>COMPLETE</promise>` | 验收测试 + 证据清单 + 策略校验 |
| 最大迭代次数 | 预算、截止期、连续失败阈值三重停止条件 |

### 3.4 Pi：Harness 应该小而可扩展

Pi 的公开定位是“最小、可扩展的 agent harness”，支持扩展、技能、提示模板、主题、包、RPC、JSON/print 模式和 TypeScript SDK。它明确说明：

- 不内置文件系统、进程、网络、凭据权限系统。
- 默认以启动它的用户权限运行。
- 需要更强边界时用容器、微虚机或策略沙箱。

这给公司两条硬性结论：

1. **Harness 不负责安全边界**，安全必须由外部沙箱和策略层提供。
2. **Harness 必须可嵌入**，需要 SDK/RPC/headless 形态，否则无法被平台调度。

DSH 在这一点上更完整，但同样不能把“插件可扩展”误当成“权限已隔离”。

### 3.5 Super-agent：编码协作层

2026-10-31 的文章与 `dsh-superagent-prototype` 给出了编码协作的目标形态：Router 与 Worker、事件驱动、异步多信道、计算 / 状态 / 环境分离、外部 Watchdog。本报告自 2026-11-01 起按「这五模块会完成并开源」规划阶段 4。

公司侧只保留规格、Superpowers 门禁、独立评审、策略和证据。不在本工程实现路由器、工单库和 Watchdog。实验协议、租约和文献复现不因此替换。约束、降级和回滚见 `docs/15_Super-agent接入与两套时钟.md`。

---

## 4. 78 个公开项目调研矩阵

以下项目按平台职责分类。星标等动态数据仅作参考，不作为选型依据；正式采用前须按 commit/tag 复核许可证、维护状态和安全记录。

标记说明：

- **采用**：建议首版直接使用或作为主参考。
- **候选**：满足条件时使用，需要评估。
- **参考**：借鉴设计，不直接部署。
- **慎用**：能力可用，但许可证、维护状态或安全边界需额外审查。

### 4.1 编程代理与软件工程方法（16）

| # | 项目 | 可复用能力 | 标记 |
|---|---|---|---|
| 1 | [obra/superpowers](https://github.com/obra/superpowers) | 需求澄清、计划、TDD、子代理执行、代码审查、分支收尾的完整方法层 | 采用（方法） |
| 2 | [karpathy/autoresearch](https://github.com/karpathy/autoresearch) | 固定预算、固定指标、单一修改面、保留或撤销 | 采用（协议） |
| 3 | [snarktank/ralph](https://github.com/snarktank/ralph) | 每轮新上下文，用 PRD、进度文件、Git 历史跨轮记忆 | 参考（实验语义；编码循环改由 Super-agent） |
| 4 | [badlogic/pi-mono](https://github.com/badlogic/pi-mono) | 极简可扩展 harness、RPC、SDK、JSON 模式 | 参考 |
| 5 | [OpenHands/OpenHands](https://github.com/OpenHands/OpenHands) | 自托管 Agent 控制中心，可接本地、容器、VM、云 | 参考 |
| 6 | [OpenHands/software-agent-sdk](https://github.com/OpenHands/software-agent-sdk) | Python/TS/REST SDK，临时 Docker/K8s 工作区 | 参考 |
| 7 | [SWE-agent/SWE-agent](https://github.com/SWE-agent/SWE-agent) | Issue 到代码修复、测试、补丁的自动软件工程基线 | 参考 |
| 8 | [Aider-AI/aider](https://github.com/Aider-AI/aider) | 终端结对编程、编辑、测试、Git 工作流 | 参考 |
| 9 | [Cline/Cline](https://github.com/Cline/Cline) | IDE/CLI/SDK 代理，人工接管入口 | 参考 |
| 10 | [continuedev/continue](https://github.com/continuedev/continue) | 开源编码代理与团队模型接入 | 参考 |
| 11 | [google-gemini/gemini-cli](https://github.com/google-gemini/gemini-cli) | 终端代理与工具调用入口 | 参考 |
| 12 | [openai/codex](https://github.com/openai/codex) | 轻量终端编码代理 | 参考 |
| 13 | [block/goose](https://github.com/block/goose) | 可扩展代理，安装、执行、编辑、测试 | 参考 |
| 14 | [qodo-ai/pr-agent](https://github.com/qodo-ai/pr-agent) | 自动 PR 描述、审查、改进建议 | 采用（评审） |
| 15 | [github/spec-kit](https://github.com/github/spec-kit) | 规范驱动开发，先生成规格再分解实现 | 采用（入口） |
| 16 | [langchain-ai/langgraph](https://github.com/langchain-ai/langgraph) | 有状态、可恢复、可人工介入的代理图 | 参考 |

### 4.2 文献与自动科研（12）

| # | 项目 | 可复用能力 | 标记 |
|---|---|---|---|
| 17 | [SakanaAI/AI-Scientist](https://github.com/SakanaAI/AI-Scientist) | 想法→代码→实验→分析→论文草稿的自动科研原型 | 参考（沙箱） |
| 18 | [stanford-oval/storm](https://github.com/stanford-oval/storm) | 多轮检索、知识整理、带引用长报告 | 采用（检索） |
| 19 | [Future-House/paper-qa](https://github.com/Future-House/paper-qa) | 科学文献高准确率问答与引用 | 采用（问答） |
| 20 | [langchain-ai/open_deep_research](https://github.com/langchain-ai/open_deep_research) | 可配置深度研究代理，多模型、多搜索、MCP | 参考 |
| 21 | [microsoft/markitdown](https://github.com/microsoft/markitdown) | PDF/Office/网页转 Markdown | 采用 |
| 22 | [VikParuchuri/marker](https://github.com/VikParuchuri/marker) | 高质量 PDF 到 Markdown/JSON | 采用 |
| 23 | [opendatalab/MinerU](https://github.com/opendatalab/MinerU) | 复杂文档解析为 LLM-ready 结构 | 候选 |
| 24 | [grobidOrg/grobid](https://github.com/grobidOrg/grobid) | 论文结构、作者、引用元数据抽取 | 采用 |
| 25 | [allenai/s2orc-doc2json](https://github.com/allenai/s2orc-doc2json) | PDF/TeX/JATS 到论文 JSON | 候选 |
| 26 | [zotero/zotero](https://github.com/zotero/zotero) | 长期文献库、附件、标签、人工审阅 | 采用（资产） |
| 27 | [citation-js/citation-js](https://github.com/citation-js/citation-js) | 跨格式引用解析与 CSL 处理 | 采用 |
| 28 | [jgm/pandoc](https://github.com/jgm/pandoc) | Markdown/LaTeX/DOCX/HTML 互转 | 采用（交付） |

### 4.3 实验、评测与追踪（14）

| # | 项目 | 可复用能力 | 标记 |
|---|---|---|---|
| 29 | [openai/evals](https://github.com/openai/evals) | LLM 与工具系统可重复评测框架 | 采用（评测） |
| 30 | [EleutherAI/lm-evaluation-harness](https://github.com/EleutherAI/lm-evaluation-harness) | 统一语言模型基准 | 采用（基准） |
| 31 | [mlflow/mlflow](https://github.com/mlflow/mlflow) | 实验跟踪、模型注册、Agent tracing、评测、成本 | 采用（主） |
| 32 | [wandb/wandb](https://github.com/wandb/wandb) | 训练与实验追踪、可视化 | 候选 |
| 33 | [clearml/clearml](https://github.com/clearml/clearml) | 实验、数据、流水线、调度、服务一体 | 候选 |
| 34 | [aimhubio/aim](https://github.com/aimhubio/aim) | 轻量实验追踪 | 候选 |
| 35 | [treeverse/dvc](https://github.com/treeverse/dvc) | 数据/模型版本、可复现流水线、Git 关联 | 采用（数据版本） |
| 36 | [pachyderm/pachyderm](https://github.com/pachyderm/pachyderm) | 数据中心流水线与数据血缘 | 候选 |
| 37 | [Netflix/metaflow](https://github.com/Netflix/metaflow) | Python 优先的 ML 系统开发与恢复 | 候选 |
| 38 | [determined-ai/determined](https://github.com/determined-ai/determined) | 分布式训练、超参搜索、资源管理 | 参考 |
| 39 | [kubeflow/katib](https://github.com/kubeflow/katib) | Kubernetes 上的 AutoML 与超参搜索 | 候选 |
| 40 | [optuna/optuna](https://github.com/optuna/optuna) | 搜索空间、剪枝、并行试验、可视化 | 采用（搜索） |
| 41 | [facebook/Ax](https://github.com/facebook/Ax) | 贝叶斯优化、多目标、自适应实验设计 | 采用（主动实验） |
| 42 | [google-deepmind/optax](https://github.com/google-deepmind/optax) | JAX 优化器与梯度处理 | 参考 |

### 4.4 编排、超算与资源调度（16）

| # | 项目 | 可复用能力 | 标记 |
|---|---|---|---|
| 43 | [temporalio/temporal](https://github.com/temporalio/temporal) | 持久执行、定时器、重试、信号、异步完成 | 采用（总控） |
| 44 | [PrefectHQ/prefect](https://github.com/PrefectHQ/prefect) | Python 工作流、重试、缓存、事件自动化 | 候选（MVP） |
| 45 | [apache/airflow](https://github.com/apache/airflow) | 定时与依赖型批处理 | 候选（固定 DAG） |
| 46 | [dagster-io/dagster](https://github.com/dagster-io/dagster) | 数据资产、开发、生产、观测一体 | 候选 |
| 47 | [flyteorg/flyte](https://github.com/flyteorg/flyte) | 类型安全 Kubernetes 分布式编排 | 候选 |
| 48 | [argoproj/argo-workflows](https://github.com/argoproj/argo-workflows) | Kubernetes 原生容器工作流 | 候选 |
| 49 | [kubernetes-sigs/kueue](https://github.com/kubernetes-sigs/kueue) | 队列、配额、公平共享、gang、MultiKueue | 采用（K8s 配额） |
| 50 | [volcano-sh/volcano](https://github.com/volcano-sh/volcano) | Kubernetes 批处理与高性能调度 | 候选 |
| 51 | [flux-framework/flux-core](https://github.com/flux-framework/flux-core) | HPC 内部资源管理与作业内调度 | 候选 |
| 52 | [SchedMD/slurm](https://github.com/SchedMD/slurm) | CPU/GPU/HPC 集群队列、配额、生命周期 | 采用（超算） |
| 53 | [skypilot-org/skypilot](https://github.com/skypilot-org/skypilot) | 跨 K8s/Slurm/多云资源抽象、故障切换、自动回收 | 采用（云资源） |
| 54 | [Parsl/Parsl](https://github.com/Parsl/Parsl) | Python 并行脚本与跨 HPC/云执行 | 候选 |
| 55 | [nextflow-io/nextflow](https://github.com/nextflow-io/nextflow) | 可移植可恢复的数据/计算流水线 | 候选 |
| 56 | [snakemake/snakemake](https://github.com/snakemake/snakemake) | 文件依赖式可复现科研流水线 | 候选 |
| 57 | [ray-project/ray](https://github.com/ray-project/ray) | 分布式 Python、Actor、训练、调参 | 采用（并行） |
| 58 | [ray-project/kuberay](https://github.com/ray-project/kuberay) | Kubernetes 上的 Ray 集群与作业 | 候选 |

### 4.5 测试、安全与可观测（12）

| # | 项目 | 可复用能力 | 标记 |
|---|---|---|---|
| 59 | [microsoft/playwright](https://github.com/microsoft/playwright) | 跨浏览器 E2E、trace、截图、AI 浏览器操作 | 采用（前端） |
| 60 | [cypress-io/cypress](https://github.com/cypress-io/cypress) | 前端组件与端到端测试 | 候选 |
| 61 | [SeleniumHQ/selenium](https://github.com/SeleniumHQ/selenium) | 跨浏览器 WebDriver 兼容测试 | 候选 |
| 62 | [pytest-dev/pytest](https://github.com/pytest-dev/pytest) | Python 单元、集成、回归测试 | 采用 |
| 63 | [HypothesisWorks/hypothesis](https://github.com/HypothesisWorks/hypothesis) | 性质测试、自动生成边界输入 | 采用 |
| 64 | [testcontainers/testcontainers-python](https://github.com/testcontainers/testcontainers-python) | 测试中启动依赖服务 | 采用 |
| 65 | [semgrep/semgrep](https://github.com/semgrep/semgrep) | 代码模式与安全静态分析 | 采用 |
| 66 | [github/codeql](https://github.com/github/codeql) | 语义代码安全与数据流漏洞检测 | 采用（门禁） |
| 67 | [aquasecurity/trivy](https://github.com/aquasecurity/trivy) | 镜像、依赖、配置漏洞扫描 | 采用 |
| 68 | [anchore/syft](https://github.com/anchore/syft) | SBOM 生成 | 采用 |
| 69 | [open-telemetry/opentelemetry-collector](https://github.com/open-telemetry/opentelemetry-collector) | 统一采集 traces/metrics/logs | 采用 |
| 70 | [getsentry/sentry](https://github.com/getsentry/sentry) | 异常聚合、发布回归、性能 | 候选 |

### 4.6 量子与算法执行示例（8）

| # | 项目 | 可复用能力 | 标记 |
|---|---|---|---|
| 71 | [Qiskit/qiskit](https://github.com/Qiskit/qiskit) | 量子电路、算子、Sampler/Estimator、transpiler、后端抽象 | 采用（基线） |
| 72 | [PennyLaneAI/pennylane](https://github.com/PennyLaneAI/pennylane) | 可微量子编程、QML、多后端 | 采用（可微） |
| 73 | [NVIDIA/cuda-quantum](https://github.com/NVIDIA/cuda-quantum) | 量子—经典混合、GPU 模拟、多后端 | 候选 |
| 74 | [unitaryfoundation/mitiq](https://github.com/unitaryfoundation/mitiq) | ZNE、PEC、CDR、读出缓解、QSE | 采用（误差缓解） |
| 75 | [quantumlib/Stim](https://github.com/quantumlib/Stim) | 高速稳定子模拟与 QEC 实验 | 采用（QEC） |
| 76 | [quantumlib/PyMatching](https://github.com/quantumlib/PyMatching) | 匹配解码与 syndrome 后处理 | 采用（解码） |
| 77 | [quantumlib/OpenFermion](https://github.com/quantumlib/OpenFermion) | 费米子与量子化学哈密顿量表示 | 采用（化学） |
| 78 | [Pasqal-io/Pulser](https://github.com/Pasqal-io/Pulser) | 中性原子脉冲级序列与设备约束 | 参考 |

### 4.7 矩阵的读法

1. **不要全装**。78 个项目是候选池，不是部署清单。
2. **同类只选一个主实现**。例如工作流主控只选 Temporal，不要同时上 Prefect、Airflow、Dagster、Flyte。
3. **区分“能力可用”与“可生产”**。研究原型即使星标很高，也可能执行模型生成的任意代码。
4. **许可证必须逐版本核查**。GPL/AGPL、自定义模型许可、商业限制都可能影响分发。
5. **维护状态会变化**。本报告中的归档、迁移和重命名只是调研时点快照。

---

## 5. 总体架构

### 5.1 七层模型

| 层 | 职责 | 关键组件 | 不做什么 |
|---|---|---|---|
| L0 目标与组合 | 长期目标、计划表、里程碑、预算、优先级 | 平台前端、Goal/Portfolio 服务 | 不直接调用资源 |
| L1 研究 Agent | 检索、阅读、提出假设、设计复现 | DSH + 文献插件 | 不直接提交昂贵作业 |
| L2 工程 Agent | 实现、重构、测试、修复、生成 PR | DSH + 编码插件 + 沙箱 | 不直接推生产分支 |
| L3 实验编译器 | 把假设变成可执行实验与验收条件 | Experiment 服务、schema 校验 | 拒绝无指标/无预算实验 |
| L4 资源控制面 | 申请、排队、启动、监控、检查点、回收 | Temporal、Slurm 适配、Kueue、SkyPilot | 不是 Agent 的职责 |
| L5 证据与评测 | 保存代码、数据、环境、日志、指标、结论链 | 对象存储、MLflow、DVC、签名清单 | 不把模型解释当结论 |
| L6 治理与运营 | 租户、预算、审批、审计、告警、计费 | 策略引擎、IAM、Postgres、OTel | 不由提示词决定 |

### 5.2 DSH 在架构中的确切位置

```text
                        ┌─────────────────────────────┐
                        │  L0 目标 / 计划 / 预算 / 审批 │
                        └──────────────┬──────────────┘
                                       │ 结构化任务
                        ┌──────────────▼──────────────┐
                        │  平台控制面（API / 租户 / 策略）│
                        └──────────────┬──────────────┘
                                       │ 创建 Run
                        ┌──────────────▼──────────────┐
                        │  持久工作流（Temporal）       │
                        │  状态 / 定时器 / 重试 / 补偿   │
                        └───────┬──────────────┬──────┘
                                │              │
                 ┌──────────────▼───┐   ┌──────▼────────────────┐
                 │ DSH Headless/SDK │   │ 资源适配器             │
                 │ 研究/编码/工具调用 │   │ Slurm/K8s/SkyPilot/QPU │
                 └──────┬───────────┘   └──────┬────────────────┘
                        │                      │
                 ┌──────▼───────────┐   ┌──────▼────────────────┐
                 │ SandboxProvider  │   │ 执行 worker / 作业      │
                 │ 容器/微虚机/K8s   │   │ CPU/GPU/HPC/设备       │
                 └──────┬───────────┘   └──────┬────────────────┘
                        │                      │
                        └──────────┬───────────┘
                                   │ 产物与指标
                        ┌──────────▼─────────────────────────┐
                        │ 证据层：对象存储 / MLflow / DVC      │
                        │ provenance / 签名 / 失败库 / 报告    │
                        └──────────┬─────────────────────────┘
                                   │
                        ┌──────────▼─────────────────────────┐
                        │ 治理层：预算 / 审计 / 告警 / 计费     │
                        └────────────────────────────────────┘
```

关键点：

- DSH 不持有“这个任务已经跑了 3 天”的唯一状态，Temporal 才持有。
- DSH 不持有 GPU 租约，资源适配器才持有。
- DSH 不持有长期模型密钥，凭据代理才持有。
- DSH 产生的是**计划、工具调用、代码补丁、分析文本**，这些都必须被平台结构化和验证。

### 5.3 为什么不让 DSH 定时任务直接承担 24/7

DSH 公开支持定时/周期任务，这对个人用户很方便。但企业级 24/7 需要：

- 跨进程、跨节点、跨版本升级的恢复。
- 外部事件等待（HPC 排队回调、云任务完成、人工审批）。
- 幂等、去重、补偿、对账。
- 精确的预算与配额预留。
- 可查询的历史与审计。

这些是持久工作流引擎的领域。正确做法是：**Temporal 决定“何时启动一个 DSH 会话”，DSH 负责“这一次会话里怎么完成”**。

### 5.4 三种运行形态

| 形态 | 入口 | 适用 | 边界 |
|---|---|---|---|
| 交互形态 | DSH Web/桌面 | 研究人员探索、调试插件、人工接管 | 不作为生产事实源 |
| 无界面形态 | `dsh-headless` 或 SDK | 平台调度的单次任务 | 必须有超时与沙箱 |
| 平台形态 | 控制面 + Temporal + SDK | 多用户、长流程、可计费 | 全链路审计 |

---

## 6. DSH 插件设计

### 6.1 插件清单

| 插件 | 服务键（建议） | 职责 | 依赖 |
|---|---|---|---|
| goal | `ctx.goal` | 读取目标、计划表、里程碑，产出任务草案 | 平台 API |
| literature | `ctx.literature` | 检索、去重、解析、方法卡、引用图 | 对象存储、检索 API |
| evidence | `ctx.evidence` | 证据登记、定位、引用一致性 | 对象存储、Postgres |
| experiment | `ctx.experiment` | 编译 ExperimentSpec、校验预算与停止条件 | schema、策略 |
| resource | `ctx.resource` | 申请/续租/释放 CPU/GPU/HPC/云资源 | 资源适配器 |
| software | `ctx.software` | worktree、补丁、测试、审查、PR | 沙箱、Git |
| model | `ctx.llm` 扩展 | 模型路由、成本、回退、配额 | 模型网关 |
| policy | 事件监听 | 高风险动作拦截、审批触发 | 策略引擎 |
| memory | `ctx.memory` | 研究记忆、失败库、经验检索 | 向量库/对象存储 |
| report | `ctx.report` | 日报、周报、复现报告、发布说明 | 模板引擎 |
| observability | 事件监听 | trace、指标、审计事件 | OTel |
| sandbox | `ctx.sandbox` 实现 | 容器/微虚机/K8s 隔离 | 运行时 |

### 6.2 插件的三条硬规则

1. **每个注册必须有 disposer**：用 `ctx.effect()` 或 `ctx.on()`，保证 reload/teardown 可逆。
2. **跨插件只通过服务键**：不直接 import 另一个插件的实现类。
3. **策略优先用事件，能力优先用服务方法**：拦截用 `waterfall`，正常调用用服务。

### 6.3 策略网关的落法

```text
工具调用前事件（waterfall）
  ├─ 身份与租户检查
  ├─ 资源与预算检查
  ├─ 数据地域与出口检查
  ├─ 高风险动作检查（真实硬件、生产合并、外发数据）
  ├─ 通过 → next()
  └─ 拒绝/需审批 → 直接返回（短路）
```

注意：事件名和参数必须在锁定版本上核对。若 DSH 当前版本没有细粒度工具前置事件，则退化为**平台侧工具代理**：所有高风险工具不直接暴露给模型，而是暴露给平台网关，由网关做检查后再调用真实能力。

### 6.4 插件生命周期

| 阶段 | 动作 | 失败处理 |
|---|---|---|
| 加载 | 校验 manifest、版本、依赖、权限声明 | 拒绝加载并告警 |
| 启动 | `inject` 等待依赖就绪 | 超时回退，不影响核心会话 |
| 运行 | 提供服务、监听事件、写审计 | 异常隔离，熔断 |
| 卸载 | 执行 disposer、释放连接与租约 | 记录残留资源 |
| 升级 | 灰度、双版本并存、回滚 | 保留旧版本产物 |

### 6.5 插件契约

每个插件必须提供：

- 名称、版本、语义化版本号。
- 依赖的 DSH/Cordis 版本范围。
- 声明的服务键与事件。
- 所需权限（文件、网络、进程、模型、资源）。
- 配置 schema。
- 健康检查。
- 迁移脚本（若涉及持久数据）。
- 兼容性测试。
- 安全审查记录。

机器可读样例见 `schemas/plugin-contract.schema.json` 与 `configs/plugin-manifest.example.json`。

---

## 7. 自动科研与算法迭代闭环

### 7.1 七个闭环

| 闭环 | 输入 | 自动动作 | 产出 |
|---|---|---|---|
| 目标闭环 | 目标、计划表、预算、期限 | 拆成可验证任务与优先级 | Goal / Milestone / Task |
| 文献闭环 | 关键词、引用图、PDF、代码链接 | 检索、去重、解析、方法卡、差距 | EvidenceGraph / MethodCard |
| 复现闭环 | 方法卡、数据、基线 | 环境锁定、实现、单测、多种子、差异 | ReproductionReport |
| 假设闭环 | 文献缺口、失败结果 | 提出假设、成本估计、消融设计 | Hypothesis / ExperimentSpec |
| 实验闭环 | ExperimentSpec、分支、预算 | 申请、运行、回收、分析、保留/回退 | Result / Decision |
| 工程闭环 | 需求、代码库、验收标准 | 计划、实现、测试、审查、PR | Patch / TestEvidence |
| 知识闭环 | 结果、审查、负结果 | 更新方法卡、失败库、下一轮计划 | ResearchMemory / 报告 |

### 7.2 文献到复现的详细流程

```text
1. 目标问题
2. 多源检索（arXiv / OpenAlex / Crossref / DBLP / Semantic Scholar）
3. 去重与版本合并（预印本 vs 正式版）
4. 引用图扩展（前向/后向）
5. 全文获取（合法来源、开放获取、机构订阅）
6. 结构化解析（GROBID + Marker/MinerU）
7. 方法卡抽取（问题、输入、流程、超参、基线、指标、硬件）
8. 代码仓库定位（论文链接、作者主页、搜索结果）
9. 复现难度评估（缺失数据、缺失超参、私有依赖、算力）
10. 环境构建（容器、锁文件、随机种子）
11. 基线运行
12. 与原文数值比较
13. 差异归因（数据、实现、评测、硬件、随机性）
14. 可改进点抽取
15. 候选假设生成
16. 最小消融实验设计
17. 进入算法实验闭环
```

### 7.3 方法卡字段

```text
paper_id / title / authors / venue / year / doi / arxiv_id
problem
claims[]
method_summary
inputs / outputs
datasets[]
preprocessing[]
model_or_algorithm
hyperparameters[]
baselines[]
metrics[]
train_test_split
hardware
runtime
original_code_url
reproduction_status
reproduction_difficulty
missing_information[]
suspicious_assumptions[]
improvement_opportunities[]
evidence_locations[]
```

### 7.4 复现的三层验证

| 层 | 问题 | 通过条件 |
|---|---|---|
| 语义复现 | 算法、数据、指标、划分是否与论文一致 | 逐项对照，无未说明差异 |
| 数值复现 | 在相同设置下能否得到接近的数值 | 落在论文报告的误差范围内，或有可解释偏差 |
| 可推广性验证 | 换数据、换规模、换硬件是否仍成立 | 至少一个独立设置下方向一致 |

只有三层都通过，才允许把该方法作为新假设的可靠基线。

### 7.5 实验契约

每个 ExperimentSpec 必须回答：

- 假设是什么，可否被证伪。
- 基线是什么，来自哪里，是否已复现。
- 主指标、护栏指标、统计方法。
- 训练/验证/测试划分，是否有数据泄漏风险。
- 随机种子与重复次数。
- 资源类型、数量、预计时长、最大预算。
- 停止条件（预算、时间、连续失败、早停）。
- 成功判据与失败判据。
- 产物清单与保存位置。
- 需要哪些审批。

### 7.6 决策规则

```text
if 主指标未超过基线 + 最小可观测效应:
    撤销变更，记录负结果
elif 护栏指标退化超过阈值:
    撤销变更，记录原因
elif 结果不稳定（多种子方差过大）:
    追加重复实验，不进入昂贵资源
elif 成本超过预算:
    停止，进入人工复核
else:
    保留变更，生成下一轮消融或扩展实验
```

### 7.7 失败库

失败必须被保存，并且可检索。失败记录至少包含：

- 假设
- 配置
- 结果
- 失败类型（实现错误、数据问题、指标错误、资源不足、假设错误）
- 可复用教训
- 关联代码与运行清单

失败库的价值高于成功库，因为它能防止 24/7 系统反复尝试同一个无效方向。

---

## 8. 软件工程与前端测试闭环

### 8.1 流水线

```text
需求 / Issue
→ 需求澄清（目标、非目标、验收标准）
→ 技术设计（接口、数据、失败模式）
→ 实现计划（小任务、精确文件、验证步骤）
→ 隔离 worktree
→ 先写失败测试
→ 最小实现
→ 单元测试
→ 集成测试（Testcontainers）
→ API 契约测试
→ 浏览器 E2E（Playwright）
→ 静态安全（Semgrep / CodeQL）
→ 依赖与镜像（Trivy / Syft）
→ Agent 代码审查
→ 人工审批
→ 合并
→ 发布
→ 运行监控
→ 自动创建后续 Issue
```

### 8.2 前端测试要求

| 类型 | 工具 | 最低要求 |
|---|---|---|
| 组件测试 | 现有前端测试框架 | 关键组件有渲染与交互测试 |
| E2E | Playwright | 关键用户路径可在 Chromium/Firefox/WebKit 运行 |
| 视觉回归 | 截图 + 基线 | 关键页面有稳定截图基线 |
| 可访问性 | 自动化扫描 + 人工抽查 | 关键流程无严重可访问性问题 |
| 性能 | 浏览器性能指标 | 首屏与关键交互有阈值 |
| 失败证据 | trace、截图、视频、控制台日志 | 失败必须可复现 |

Playwright 的关键优势：跨三大浏览器引擎、测试隔离、自动等待、失败 trace、网络拦截、可被 AI Agent 驱动。这些正好满足“Agent 自己验证前端”的需求。

### 8.3 前端 Agent 的边界

Agent 可以：

- 启动本地开发服务器
- 打开页面、点击、输入、截图
- 读取控制台错误
- 对比截图
- 生成修复补丁

Agent 不可以：

- 直接访问生产环境用户数据
- 绕过登录或权限做测试
- 在没有测试数据隔离的情况下调用真实支付、真实邮件、真实外部服务

### 8.4 合并门禁

合并前必须全部满足：

- 单元测试通过
- 集成测试通过
- E2E 通过
- 静态安全无高危
- 依赖扫描无已知高危
- 变更覆盖关键路径
- 审查意见已处理
- 人工审批通过（按风险等级）
- 回滚方案存在

---

## 9. 资源编排与超算

### 9.1 五类资源队列

| 队列 | 任务 | 时间尺度 | 策略 |
|---|---|---|---|
| CPU 快速验证 | 单测、静态检查、文献解析 | 秒–分钟 | 失败重试，不占 GPU |
| GPU 短实验 | 小数据、超参、评测 | 5–30 分钟 | 固定预算，自动停止 |
| HPC 长任务 | 大规模训练、模拟、扫描 | 小时–天 | 检查点，完成即释放 |
| 真实设备 | QPU、实验设备、高成本服务 | 按供应商 | 人工审批，独立租约 |
| 浏览器/发布 | E2E、截图、报告渲染 | 分钟 | 隔离上下文，保留 trace |

### 9.2 资源请求与租约

```text
ResourceRequest
  → 策略检查（租户、配额、预算、数据地域）
  → 排队（Slurm / Kueue / SkyPilot）
  → 短期 Lease（含范围、时长、fencing token）
  → Worker 持租约执行
  → 心跳与检查点
  → 完成 / 失败 / 超时
  → 释放租约与资源
  → 对账与计量
```

硬规则：

- Agent 永远拿不到长期云密钥。
- 执行前必须写入 attempt 记录。
- 执行状态未知时禁止重复提交。
- 租约过期后旧 fencing token 永久拒绝。
- 资源回收失败必须告警并补偿，不能静默续租。

### 9.3 两队列问题

HPC 和外部资源各自有队列，容易出现“HPC 已占用但 QPU/云还在排队”。缓解手段：

1. 一次只允许一个长等待点。
2. 批处理阶段完成即释放经典资源。
3. 用短 TTL 的 prepare/commit 协调两侧。
4. 设置最大空等时间，超时降级为批处理。
5. 远程无预约能力时，不宣称协同调度。

### 9.4 检查点

长任务必须支持：

- 周期性检查点（按步数或时间）。
- 检查点写入对象存储并校验哈希。
- 失败后从最近检查点恢复，生成新 attempt。
- 旧 attempt 的输出不能覆盖新 manifest。

### 9.5 成本控制

- 每个任务预设最大金额与最大机时。
- 准入时预留悲观成本上界。
- 执行中按 chunk 重估。
- 超预算只在安全边界停止。
- 每日/每周按租户、项目、用户汇总。
- 成本异常触发告警与自动降级。

---

## 10. 模型供应层与 DeepSeek 部署

### 10.1 三种供应方式

| 方式 | 优点 | 风险 | 适用 |
|---|---|---|---|
| 官方 API | 快速、免运维、能力最新 | 依赖外部服务、数据出境、限流 | 早期验证、非敏感任务 |
| 自部署开源权重 | 数据可控、可定制、成本可预测 | 运维复杂、硬件昂贵、能力可能落后 | 敏感数据、稳定高频、合规要求 |
| 采购第三方模型 | 能力互补、合规可选 | 多供应商管理、成本与锁定 | 特定能力、备份路由 |

### 10.2 自部署的现实检查

DeepInfer 公开说明其开源版本提供离线推理与核心特性，但完整服务所需的 KV cache、PD 分离、副本负载均衡“不包含在本次发布中”。这意味着自部署至少需要补齐：

- 推理网关与路由
- KV cache / 上下文管理
- Prefill/Decode 分离
- 多副本负载均衡
- 限流、配额、鉴权
- 指标、日志、trace
- 模型版本与灰度
- 评测与回滚
- 故障转移

可选推理引擎：DeepInfer、vLLM、SGLang、TensorRT-LLM，以及昇腾生态的对应方案。选择依据是硬件、模型、吞吐/延迟目标和团队运维能力，不是“哪个更新”。

### 10.3 模型路由

路由维度：

- 任务类型（规划、编码、长文、检索、结构化输出、评审）
- 上下文长度
- 工具调用能力
- 结构化输出可靠性
- 延迟与吞吐
- 成本
- 数据地域与合规
- 供应商健康度
- 版本固定与可复现性

路由策略：

```text
if 数据敏感 and 本地模型达标: 本地
elif 需要最强推理 and 允许外部: 高端 API
elif 大批量廉价任务: 本地或低价模型
elif 供应商不健康: 回退到备用
else: 默认模型
```

### 10.4 模型评测门

任何模型进入生产路由前必须通过：

- 任务级基准（编码、工具调用、结构化输出、长上下文）
- 公司内部真实任务集
- 幻觉与引用准确性
- 安全与越狱测试
- 成本与延迟
- 稳定性（重复运行一致性）

### 10.5 可替换性设计

- 工作流对象不记录“某模型的原始响应”作为唯一事实。
- 记录模型 ID、版本、参数、提示哈希、工具集版本。
- 所有模型输出都经过 schema 校验。
- 关键决策有确定性规则兜底。
- 换模型后能重放历史任务做对比评测。

---

## 11. 多租户、安全与治理

### 11.1 身份与权限

| 主体 | 身份方式 | 权限边界 |
|---|---|---|
| 人类用户 | 企业 OIDC | 按租户、项目、角色 |
| 服务 | 工作负载身份 + mTLS | 最小权限、短期 |
| Agent | 独立主体 | 不继承操作者全部权限 |
| 运维 | 独立信任域 + 强 MFA | JIT 提权、双人审批 |

### 11.2 沙箱

必须做到：

- 非特权容器或微虚机。
- 只读根文件系统。
- 临时目录配额。
- 默认拒绝网络出口，仅允许白名单。
- 禁止宿主 socket 与设备映射。
- 资源限制（CPU、内存、进程数、磁盘）。
- 执行超时与强制终止。
- 每次任务独立工作区。

### 11.3 凭据

禁止：

- 把长期密钥写进提示词、脚本、环境变量、镜像、共享目录。
- 让 Agent 直接持有云厂商长期密钥。
- 在日志中记录 token。

推荐：

- 凭据代理 + 短期 token。
- token 绑定租户、项目、资源、动作、时长。
- 通过本地 socket 或受限文件注入。
- 任务结束立即撤销。

### 11.4 审批矩阵

| 动作 | 自动 | 需审批 | 禁止 |
|---|---|---|---|
| 读公开文献 | 是 | — | — |
| 解析文档 | 是 | — | — |
| 创建分支 | 是 | — | — |
| 修改实验分支 | 是 | — | — |
| 运行单测 | 是 | — | — |
| 预算内 CPU/GPU 实验 | 是 | — | — |
| 超出预算阈值的 HPC | — | 是 | — |
| 真实量子硬件/实验设备 | — | 是 | — |
| 外发专有数据 | — | 是 | — |
| 修改生产基础设施 | — | 是 | — |
| 合并主分支 | — | 是 | — |
| 正式发布软件 | — | 是 | — |
| 公开发布论文/结论 | — | 是 | — |
| 修改校准/固件/互锁 | — | — | 是 |
| 直接下发硬件控制指令 | — | — | 是 |
| 无限预算/无限重试 | — | — | 是 |
| 未知执行状态盲目重提 | — | — | 是 |

### 11.5 审计

必须记录：

- 谁在何时发起了什么任务。
- 用了哪个模型、哪个版本、哪个提示哈希。
- 调用了哪些工具、参数摘要、结果摘要。
- 申请了什么资源、租约 ID、实际用量。
- 谁批准了什么。
- 产生了哪些产物、哈希、存储位置。
- 失败原因与补偿动作。

审计日志应追加写、不可篡改、可关联 trace。

---

## 12. 数据模型与机器契约

### 12.1 核心对象

| 对象 | 作用 | 关键字段 |
|---|---|---|
| Goal | 长期目标 | 目标、指标、期限、预算、负责人 |
| Milestone | 里程碑 | 关联目标、验收条件、状态 |
| ResearchTask | 研究任务 | 类型、输入、验收、优先级、预算 |
| PaperRecord | 论文记录 | 元数据、来源、版本、许可 |
| MethodCard | 方法卡 | 问题、方法、数据、指标、代码、复现状态 |
| Hypothesis | 假设 | 陈述、依据、可证伪条件、预期效应 |
| ExperimentSpec | 实验规格 | 基线、变量、指标、种子、预算、停止条件 |
| ResourceRequest | 资源请求 | 类型、数量、时长、优先级、预算 |
| ResourceLease | 资源租约 | 范围、时长、fencing token、持有者 |
| Run | 一次执行 | 规格、代码、环境、资源、状态 |
| Attempt | 执行尝试 | 序号、起止、结果、失败原因 |
| Artifact | 产物 | 类型、哈希、URI、来源、签名 |
| Metric | 指标 | 名称、值、单位、不确定度、计算方式 |
| Decision | 决策 | 保留/撤销/扩展/停止、理由、证据 |
| ReproductionReport | 复现报告 | 三层验证结果、差异、结论 |
| ModelRoute | 模型路由 | 任务类型、模型、版本、成本、回退 |
| PolicyDecision | 策略决定 | 允许/拒绝/需审批、理由、主体、资源 |

### 12.2 状态机原则

- 状态只能单调前进或进入明确终态。
- 每次状态变更必须 CAS + revision。
- 状态变更与事件写入同一事务（outbox）。
- 迟到事件不能覆盖新状态。
- 终态不可回退，只能新建对象。

### 12.3 幂等

- 所有写接口带幂等键。
- 相同键 + 相同请求 → 回放原结果。
- 相同键 + 不同请求 → 冲突。
- 外部提交使用确定性 submission token。
- 物理执行不承诺 exactly-once，只承诺“可对账、不盲重试”。

### 12.4 契约文件

见 `schemas/` 目录：

- `research-task.schema.json`
- `experiment-spec.schema.json`
- `plugin-contract.schema.json`
- `policy-decision.schema.json`
- `resource-lease.schema.json`
- `model-route.schema.json`
- `run-manifest.schema.json`

---

## 13. 实施路线图

### 阶段 0：边界与基线（1–2 周）

交付：

- 研究章程（一个问题、一个基线、一个指标、一个预算）
- DSH 版本锁定与插件骨架
- 沙箱基线
- 结果清单 schema
- 人工审批流程

退出标准：手动完成一次可追踪、可复现、可回滚的实验。

### 阶段 1：单任务自动实验（2–4 周）

交付：

- autoresearch 式固定预算循环
- Git 分支与自动回退
- 结构化运行记录
- 本地 CPU/单 GPU 执行

退出标准：

- 连续 24 小时运行
- 无无限循环
- 每轮有唯一 ID 与结果
- 失败可恢复
- 资源可释放

### 阶段 2：资源编排（4–8 周）

交付：

- Temporal 总控
- Slurm 适配
- Kubernetes + Kueue
- SkyPilot 云资源
- 检查点与自动回收
- 执行对账

退出标准：

- 节点故障可恢复
- 控制面重启可继续
- 任务结束资源自动释放
- 未知执行不重复计算

### 阶段 3：文献到复现（6–10 周）

交付：

- 检索与去重
- 全文解析
- 方法卡
- 代码映射
- 基线复现
- 多种子验证
- 差异报告

退出标准：一个研究方向 10–20 篇核心文献结构化 + 一个完整复现。

### 阶段 4：软件工厂（上游 Super-agent 冻结后，8–12 周）

交付：

- 锁定上游 Super-agent，本仓库注册为其 Source
- 规格进入授权范围
- Superpowers 技能与 TDD 门禁
- 独立评审
- Playwright E2E 与安全门禁
- 人工审批

退出标准：合并候选全部门禁通过，Agent 与 Watchdog 均无法越权。上游未冻结时只走单工单 headless 降级，不自研路由器。详见 `docs/15_Super-agent接入与两套时钟.md`。

### 阶段 5：多用户生产化（3–6 个月）

交付：

- 多租户
- 配额与计费
- 模型路由与自部署
- 研究组合管理
- 日报周报
- 故障演练

退出标准：稳定服务多个团队，具备 SLO、审计与恢复演练。

### 首个 30 天

| 时间 | 任务 | 交付 |
|---|---|---|
| 第 1–3 天 | 确定最小研究问题、基线、指标、预算 | Research Charter |
| 第 4–7 天 | DSH 沙箱、Git worktree、Artifact schema | 单轮可恢复实验 |
| 第 2 周 | 固定预算循环 | 24 小时模拟运行 |
| 第 3 周 | 接入一个 HPC/云适配器 | 一次长任务闭环 |
| 第 4 周 | 文献检索与解析，10–20 个方法卡 | 第一份复现报告 |

---

## 14. 验收指标

| 维度 | 初始目标 | 测量方式 |
|---|---|---|
| 流程可靠性 | 控制面月度可用性 ≥ 99.5%，worker 重启后 ≥ 95% 工作流可恢复 | 故障注入 |
| 副作用安全 | 昂贵/物理执行重复检测为 0 | submission token、账单对账 |
| 资源效率 | 长任务完成后 5 分钟内释放；无效等待 < 10–15% | lease 与时间统计 |
| 实验可信度 | 每个正式结论有基线、对照、种子、环境、指标、原始结果 | 清单自动校验 |
| 算法质量 | 候选改进通过独立复核集或多种子稳定性 | 均值、置信区间、方差、成本 |
| 软件质量 | 合并候选通过单测、集成、E2E、静态安全、依赖扫描 | CI 门禁 |
| 文献质量 | 方法卡有可解析来源、定位证据、引用一致 | 抽查 + 自动校验 |
| 成本 | 单任务不超预算；月度偏差 < 15% | 预留/实际/释放三段账本 |
| 安全 | 无长期密钥进入沙箱；越权尝试全部阻断 | 密钥扫描 + 策略日志 |

---

## 15. 风险与反模式

### 15.1 十三个反模式

1. **让一个 Agent 拥有研究、执行、审批、发布全部权限。**
2. **用 `while true` 代替持久工作流。**
3. **把 DSH 定时任务当作企业调度器。**
4. **把 Harness 沙箱当作完整安全边界。**
5. **把模型自评当作科学结论。**
6. **只保存成功实验。**
7. **用平均指标掩盖方差。**
8. **执行状态未知时自动重试。**
9. **让 Agent 持有长期云密钥。**
10. **把 preview API 写进长期数据格式。**
11. **同时部署多套功能重叠的编排系统。**
12. **只做单元测试，不做端到端验证。**
13. **没有预算上限的自动搜索。**

### 15.2 主要风险

| 风险 | 影响 | 缓解 |
|---|---|---|
| DSH preview API 变化 | 插件失效 | 锁版本、适配层、兼容性回归 |
| 模型能力波动 | 结果不稳定 | 版本固定、评测门、回退 |
| 自部署成本超预期 | 预算失控 | 小规模试点、成本模型、混合路由 |
| Agent 生成不安全代码 | 安全事件 | 沙箱、扫描、最小权限、人工门 |
| 资源泄漏 | 费用增加 | 租约、自动回收、对账 |
| 实验不可复现 | 结论无价值 | 环境锁定、种子、清单、证据链 |
| 多租户越权 | 数据泄露 | 硬隔离、策略、审计 |
| 供应商锁定 | 迁移困难 | 可替换模型层、标准对象 |

---

## 16. 双轨开发与集成契约

### 16.1 现实约束

公司已在另一台电脑上开发 DSH 工程，并已接入云平台、本地 HPC 和本地模型。本工程看不到对方代码，但必须能够独立开发，并在后期无损合并。

因此本工程采用**契约优先的平行开发**：共享的不是代码，而是端口契约。

```text
harness-core（对方）
  DSH 运行时、云平台、本地 HPC、本地模型、身份、存储、凭据
        │ 实现端口
        ▼
@company/dsh-contracts（唯一共享真相）
        ▲ 消费端口
        │
research-platform（本工程）
  目标、任务、实验、证据、策略、审批、预算、工作流、报告、前端
```

### 16.2 九个端口

| 端口 | 提供方 | 作用 |
|---|---|---|
| `ModelGatewayPort` | harness-core | 模型调用、路由、用量 |
| `ComputePort` | harness-core | 云、GPU、批任务 |
| `HpcSchedulerPort` | harness-core | HPC 作业、队列、预约 |
| `ArtifactStorePort` | harness-core / 公司存储 | 产物与证据 |
| `IdentityPort` | harness-core / 公司 IdP | 身份与授权 |
| `SecretPort` | harness-core / 公司 Vault | 短期凭据 |
| `EventPort` | harness-core / 公司总线 | 领域事件 |
| `SessionPort` | harness-core | DSH 会话与预算 |
| `TelemetryPort` | harness-core | 指标与审计事件 |

### 16.3 不重复清单

本工程明确不做：

- 不 fork DSH。
- 不写云厂商 SDK 封装。
- 不写 Slurm/HPC 客户端。
- 不部署推理引擎。
- 不建第二套用户、租户、密钥、对象存储、消息系统。
- 不重复实现 DSH 已有插件。

边界判定规则：

```text
把外部资源变成可调用能力 → 对方
认证、密钥、基础存储、基础遥测 → 对方或公司基础设施
研究、实验、软件、证据、审批、预算、报告 → 本工程
DSH 核心或通用工具 → 对方
其余 → 双方评审
```

### 16.4 本工程独立运行的能力

为了让本工程不必等待对方，提供八个内存桩：

| 桩 | 能力 | 声明 |
|---|---|---|
| `StubModelGateway` | 固定响应、延迟、成本、JSON schema、失败注入 | `degraded: true` |
| `StubComputePort` | 内存队列、状态推进、幂等、取消、对账、日志、预约 | `degraded: true` |
| `StubArtifactStorePort` | 内存对象、占位哈希、租户隔离、签名 URL | `degraded: true` |
| `StubIdentityPort` | 默认拒绝、授权、撤销 | `degraded: true` |
| `StubSecretPort` | 短期凭据、scope 校验、TTL 上限 | `degraded: true` |
| `StubEventPort` | 幂等发布、订阅过滤 | `degraded: true` |
| `StubSessionPort` | 会话、预算、取消 | `degraded: true` |
| `StubTelemetryPort` | 脱敏、低基数校验 | `degraded: true` |

桩只用于开发与测试，禁止用于生产、计费对账和科学结论。

### 16.5 合并机制

- 契约走私有 npm registry，包名 `@company/dsh-contracts`。
- 语义化版本；主版本变更需双方评审。
- 双方锁定同一主版本。
- 目录所有权划分：`contracts/` 共享，`platform/` 本工程，`harness-core/` 对方。
- 双方各有反腐蚀层，领域对象不直接使用端口 DTO。
- 一致性用例 28 条，其中 25 条 MUST，双方 CI 都跑。

### 16.6 合并检查

- [ ] 契约主版本一致
- [ ] 一致性测试双方通过
- [ ] 能力声明真实
- [ ] 降级路径可用
- [ ] 错误码映射正确
- [ ] 幂等语义一致
- [ ] 用量与成本口径一致
- [ ] 租户隔离验证
- [ ] 端到端冒烟通过
- [ ] 回滚演练通过

详细内容见 `docs/12_双轨开发与合并策略.md` 与 `docs/13_集成边界与不重复清单.md`。

## 17. 公开来源

### 17.1 DeepSeek Harness 与 Cordis

- DeepSeek Harness 官方站点：https://www.deepseek.com/en/harness
- DeepSeek Harness 仓库：https://github.com/deepseek-ai/deepseek-harness
- DeepSeek Harness 文档：https://deepseek-harness.github.io/deepseek-harness/
- Cordis 教程：https://deepseek-harness.github.io/deepseek-harness/develop/cordis-tutorial
- Cordis 入门：https://deepseek-harness.github.io/deepseek-harness/reference/cordis-primer
- Cordis 仓库：https://github.com/cordiverse/cordis
- DSH SDK 客户端包：https://www.npmjs.com/package/@deepseek-ai/dsh-sdk-client
- DSH 沙箱包：https://www.npmjs.com/package/@deepseek-ai/dsh-sandbox
- DSH headless 包：https://www.npmjs.com/package/@deepseek-ai/dsh-headless
- DeepInfer：https://github.com/deepseek-ai/DeepInfer
- Super-agent 研究原型：https://github.com/deepseek-ai/dsh-superagent-prototype
- 文章转载（2026-10-31）：https://www.chaincatcher.com/article/2300676

### 17.2 四类范式

- Superpowers：https://github.com/obra/superpowers
- autoresearch：https://github.com/karpathy/autoresearch
- Ralph：https://github.com/snarktank/ralph
- Pi：https://github.com/badlogic/pi-mono

### 17.3 其余项目

见第 4 节矩阵，全部附官方仓库链接。

### 17.4 说明

- 星标、归档状态、许可证为调研时点快照。
- 部分仓库发生过迁移或重命名，本报告尽量使用当前官方地址。
- 未核验的功能不得写入生产设计。
- 本报告不构成法律、合规或采购建议。

---

## 18. 双工程分工与合并（2026-10-29 补充）

公司已在另一台电脑开发 `harness-core`，包含 DSH 接入、云平台、本地 HPC、本地模型、身份、存储与凭据。本工程是 `research-layer`，只做研究层。

### 18.1 能力边界

| 能力 | harness-core | research-layer |
|---|---|---|
| DSH 运行时、Cordis、插件加载 | 拥有 | 只消费 `SessionPort` |
| 云平台、GPU 云 | 拥有 | 只调用 `ComputePort` |
| 本地 HPC / Slurm | 拥有 | 只调用 `HpcSchedulerPort` |
| 本地模型与推理 | 拥有 | 只调用 `ModelGatewayPort` |
| 身份、凭据、对象存储、事件、遥测 | 拥有 | 只调用对应端口 |
| 目标、任务、实验规格、决策 | 不涉及 | 拥有 |
| 文献与复现、软件流水线、研究记忆 | 不涉及 | 拥有 |
| 领域策略、审批、预算口径 | 部分 | 拥有 |

### 18.2 契约

- 契约包：`@company/dsh-contracts`，版本 `0.1.0`。
- 9 个端口：Identity、Secret、ArtifactStore、ModelGateway、Compute、HpcScheduler、Event、Session、Telemetry。
- 所有方法返回 `PortResult<T>`，不抛未捕获异常。
- `UNKNOWN_EXECUTION` 不可重试；`reconcile()` 返回 `unknown` 同样禁止重试。
- 双方交换 `IntegrationManifest` 与一致性用例结果。

### 18.3 独立开发

本工程可在只有桩的情况下完整运行：

```bash
make check
```

包括 36 条一致性用例（35 MUST）、157 个契约、流水线、循环、失败库、日报、worktree、租约、账本、恢复、回收、文献、复现、假设门禁与软件门禁测试、契约与桩自检。桩全部声明 `degraded: true`，支持失败注入（未知执行、失败、预算超限、能力缺失）。

阶段 1 的参考实现已经落地：`packages/pipeline/src/loop.ts` 提供有界循环（预算、截止时间、最大尝试次数、连续失败、早停），`packages/domain/src/failure.ts` 提供失败分类；每次尝试写 `manifest.json`，循环写 `loop-summary.json`，失败与负结果同样保留。`packages/domain/src/failure-library.ts` 提供失败去重与检索，`packages/pipeline/src/report.ts` 生成基础日报，`packages/workspace/src/worktree.ts` 提供 Git 分支/worktree 隔离。

阶段 2 的研究层已覆盖单轮与循环级资源控制：`packages/domain/src/lease.ts` 提供租约状态机与续租，`packages/domain/src/cost.ts` 提供三段成本账本，`packages/pipeline/src/lease.ts` 把预留、报价、提交、释放结算与对账接到 `ComputePort`；`packages/domain/src/checkpoint.ts` 提供检查点恢复决策；`packages/domain/src/reclaim.ts` 与 `packages/pipeline/src/reclaim.ts` 提供一轮周期对账、过期回收和泄漏告警。`runExperiment()` 支持租约门控：准入预留、结束释放结算、`costs.json` 快照并入产物；`runExperimentLoop()` 支持循环级门控：共享账本跨轮扣减剩余预算、恢复决策写入尝试记录、达到上限转人工。未知执行只升级，不自动释放或重新提交。持久工作流与真实适配器仍由 harness-core 或后续 Temporal 集成提供。

阶段 3 的研究层部分已落地：`packages/domain/src/literature.ts` 提供文献去重（同 DOI 合并、arXiv 预印本并入正式版、标题冲突转人工确认）、语料组装与方法卡校验（缺证据定位为硬错误）；`packages/pipeline/src/literature.ts` 把组装后的语料与方法卡接到 `ArtifactStorePort`，人工确认候选一并落盘；`packages/domain/src/reproduction.ts` 提供复现难度评分、声明容差比较与报告编译（partial/failed 必须附差异归因，未知执行结论为 `not_attempted`）；`packages/pipeline/src/reproduction.ts` 把每种子的独立提交接到 `ComputePort` 走 `acquireLease`，执行未知立即停止且不释放不重试，预算耗尽后剩余种子跳过；`packages/domain/src/hypothesis.ts` 提供假设质量门与从复现结果草拟候选的证据自动链接。多源检索、全文解析与代码定位仍需文献插件与外部服务。

### 18.4 合并五阶段

| 阶段 | 目标 | 退出条件 |
|---|---|---|
| 0 契约冻结 | 确认端口、错误码、未知执行语义 | 双方签字/tag |
| 1 一致性 | 双方各跑 `cases.yaml` | MUST 全过，差异入 `knownLimitations` |
| 2 影子联调 | 同一实验同时走桩与真实端口 | 状态、产物哈希、决策一致 |
| 3 适配器替换 | 按 ArtifactStore → Identity/Secrets → ModelGateway → Compute 顺序 | 每次替换后全量测试通过 |
| 4 灰度 | 小预算、单租户、非敏感数据 | 错误率、未知执行、成本、释放达标 |
| 5 代码合并 | 统一包名、构建、CI、版本 | 重复实现删除 |

### 18.5 不重复清单

本工程不实现：云 SDK、Slurm 客户端、推理引擎、token 签名与校验、对象存储、DSH 插件加载器、计费账本、Super-agent 的 Router / Worker / Watchdog。

任何需要调用外部系统的代码，必须先有端口；端口没有的能力，先加契约，不在业务层直连。

### 18.6 相关文档

- `docs/12_双轨开发与合并策略.md`
- `docs/13_集成边界与不重复清单.md`
- `docs/14_代码结构与开发指南.md`
- `contracts/README.md`

---

## 附录 A：Canvas

Canvas 源文件位于 `canvas/autonomous-ai-research-workflow.canvas.tsx`，包含：

- 78 项目可筛选矩阵
- 四类范式组合决策
- 分层架构与状态机
- 资源队列
- 分阶段路线
- 验收指标
- 治理门

## 附录 B：文档索引

| 文件 | 内容 |
|---|---|
| `docs/00_交付说明与研究边界.md` | 本工程定位、证据规则、使用方式 |
| `docs/01_DeepSeekHarness统一架构.md` | DSH 在平台中的位置与插件架构 |
| `docs/02_四类范式组合决策.md` | 四个图片项目的取舍与落法 |
| `docs/03_78项目调研矩阵.md` | 完整项目表与选型建议 |
| `docs/04_自动科研与算法迭代工作流.md` | 文献、复现、实验闭环 |
| `docs/05_软件工程与前端测试工作流.md` | 软件交付与 E2E |
| `docs/06_资源编排、超算与模型部署.md` | 资源、租约、模型部署 |
| `docs/07_多租户、安全与治理.md` | 权限、沙箱、审批、审计 |
| `docs/08_实施路线图与验收指标.md` | 阶段计划与指标 |
| `docs/09_DSH插件与服务开发规范.md` | 公司插件开发规则 |
| `docs/10_模型供应层与DeepSeek部署策略.md` | 模型路由与自部署 |
| `docs/11_待确认问题清单.md` | 开工前必须确认的问题 |
| `docs/12_双轨开发与合并策略.md` | 与 harness-core 的边界、契约冻结、合并节奏 |
| `docs/13_集成边界与不重复清单.md` | 本工程不做什么、如何防重复 |
| `docs/14_代码结构与开发指南.md` | 包结构、端口开发、测试与提交规范 |
| `docs/15_Super-agent接入与两套时钟.md` | 编码协作改接上游的假设、边界、降级与回滚 |
| `contracts/` | 九个跨工程端口、DTO、一致性用例 |
| `adapters/stub/` | 本地桩实现 |
