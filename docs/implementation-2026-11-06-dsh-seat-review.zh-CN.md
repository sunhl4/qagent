# DSH 座席验收与插件边界（2026-11-06）

本篇记录 2026-11-06 在公司开发桌面上的真实会话验收，以及据此对「DSH 是唯一 Agent Runtime、插件只注册工具」这条策略的复查。不引入第二个模型循环、会话循环或工具循环。汇总后的技术手册和产品开发报告见 [super-dsh-handbook-2026-11-06.zh-CN.md](super-dsh-handbook-2026-11-06.zh-CN.md)。

2026-11-10 起，开发桌面的会话预设改为上游 `standard`，公司工具和批准留在档案插件。下面的云模拟器和超算作业仍是当天的会话记录。授权卡、可见名单和桌面菜单以现行手册第 3 节为准。

## 验收事实

会话在 lab 预设里完成。云平台模拟器 `qiskit-sim` 提交后状态为 `SUCCESS`，结果为 `completed`。超算作业 `67378` 与 `67379` 均为 `COMPLETED`；`67379` 的日志已取回，内容含 `python_ok 3.12.3` 与 `smoke-done`。队列在干跑期间保持为空，干跑使用 `sbatch --test-only`，没有另交作业。

同一次会话里，读队列、列云设备、建目录、传脚本、检查脚本、提交、查状态、取回日志都走公司工具。真机 `quantum_device_run` 没有被调用。量子平台资产列表仍因没有可用平台地址而失败闭合。GitLab 计划中心仍因私有环境没有 `COMPANY_AGENT_GITLAB_URL` 与 `COMPANY_AGENT_GITLAB_TOKEN` 而失败闭合。

## 修过的南向故障

这些故障出在适配器，不改变插件划分。

- 桌面经 `wsl.exe` 发 SSH 时，未转义的 `$HOME` 被展开成 WSL 自己的家目录。集群账号的可写暂存目录是另一处。资源查询改为取集群账号的家目录；写操作把误缓存的 `company_agent` 路径放到该家目录上。
- Windows 文本模式把上传脚本的换行写成 `\r\n`，`sbatch` 拒绝 DOS 换行。SSH 标准输入改为原始字节。
- `c = measure q;` 曾被云程序编译器当成名为 `c` 的门。寄存器测量现在会改写成平台要的逐比特测量。
- `company_office_open` 增加 `.xmind` 与 `.mm`。开发桌面在未另行指定时设置 `COMPANY_AGENT_OPEN_WPS=wps`。关联程序不是 WPS 时仍然拒绝，不改用别的程序。
- 开发桌面的私有环境加载名单增加 GitLab 地址、令牌、项目允许名单和明文开关。名单只在变量已经写入私有环境时生效，不写入凭据。
- `company_research_run` 在 Python 策略里是 lab 询问，但 DSH 策略插件的可审批名单里没有它，询问会被改成拒绝。已补进名单，并给出只含实验标识、任务标识、次数和资源类型的审批理由。

## 自动化、办公与 GitLab 的可用边界

研究迭代的一次批准在 `company_research_run` 内部。批准这一次之后，有界的修改再跑不再逐次弹卡片。该工具不提交超算、不提交云任务、不调用真机。工单只在 `company_work_item` 的 `evaluate` 同时满足 `mode=auto` 与 `strength=explicit` 时打开，并绑定当前 DSH 会话。

计算资源的提交、改脚本、再跑可以留在同一轮对话里连续做。当天的审批卡片是「允许一次」。现行策略改为：`company_grant_open` 在 `lab` / `sign` 询问，一张卡盖住点名工具的后续调用，每个工具最多 20 次或 14400 秒。没有余量时，`hpc_submit`、`hpc_stage_file`、`hpc_dir_create`、`hpc_file_remove`、`hpc_job_cancel`、`quantum_cloud_submit` 和 `quantum_device_run` 仍各自询问。`boot` / `algo` 即使持有授权也拒绝真机、超算提交和云提交。

办公文件和思维导图留在 `company.office`。`.xmind` / `.mm` 由 `company_office_create` 写出，事项导图由 `company_office_matter` 的 `kind=mindmap` 写出，打开用 `company_office_open`。

GitLab 计划工具提交议题、评论和里程碑，写操作要批准。它们不推送普通代码仓库。LaTeX 仓库的一次提交是 `company_latex_push`。普通代码的 `git push` 不是公司工具。

## 对接策略

策略成立，保持不变。

DSH 是唯一 Agent Runtime。公司包只注册合同里的工具，执行转给 `company-agent invoke`。合同决定工具、可见性和询问或拒绝；Python 适配器做南向调用；策略预设决定公司工具能看见什么。命令行全量档案关闭 DSH 内置 preset 和用户可写 preset 根，只留 system-trust 的 `company-agent` 组合。开发桌面的会话预设是上游 `standard`。未知工具、坏信封、缺失 provider 失败闭合。句柄只有 `asset_id`、`circuit_id`、`twin_id`，且 `twin_id` 只从 `quantum_device_run` 配 `ionstack-twinrun` 返回。

今天的真实提交说明这条缝是通的。云模拟器和 Slurm 都从原生工具审批走到公司网关，再回到短回执。故障在路径展开、换行和编译，修在适配器里，没有加第二套运行时，也没有在客户端上盖一层界面。

不要改成的做法：在插件里写模型循环；把研究时钟接到 `hpc_submit` 或 `quantum_device_run`；为了少点一次批准而把资源提交改成默认允许；安装 Temporal 或第二套图表渲染器；把算法名单写死在 Agent 或知识库里。

## 插件怎么分

插件按凭据、审批爆炸半径和「能不能从某个 profile 里物理拿掉」来分。不按每个工具、每个文件格式或每个界面按钮来分。

| 插件 | 登记的能力 | 判断 |
| --- | --- | --- |
| `company-agent-policy` | 不登记工具，占 `tools/pre-execute` | 必须单独。工具包不能自带审批。 |
| `company-agent-device` | `quantum.device` | 必须单独。minimal 组合不安装它，真机工具才是物理缺席。 |
| `company-agent-hpc` | `compute.hpc` | 必须单独。SSH 凭据和失败域与云、真机都不同。 |
| `company-agent-quantum` | 算法、资产、仿真、编译、`compute.cloud` | 今天可以留在一起。云提交不签发 `twin_id`，boot/algo 由策略拒绝。若以后要「有算法目录、无云 worker」的组合，再把 `compute.cloud` 拆成与 HPC 同级的插件。 |
| `company-agent-office` | `company.office` | 必须留在一个插件里。思维导图、图表、幻灯片是文件种类，不是新插件。 |
| `company-agent-latex` | `company.latex` | 与办公分开。它有 Git 推送和 Overleaf，审批面不同。 |
| `company-agent-plan` | `company.plan` | 与 core 分开。GitLab 令牌不能进常驻核心包。 |
| `company-agent-research` | `company.research` | 与 HPC、云、真机分开。时钟一旦和提交插件打成一个包，边界会被实现带过去。 |
| `company-agent-core` | 工作流、知识、门户 | 留在一起。工单、能力清单和知识是每个公司座席都要的。门户只有一个打开工具，不值得再拆包。 |

不该做成插件的部分：

- `research-layer` 里的 workspace、pipeline、domain。它们是时钟后面的库，由 `company_research_run` 调用。
- 每个办公格式一个插件，或每个 HPC 子命令一个插件。预设和策略已经能隐藏单次提交。
- 普通 Git 推送插件。当前没有允许名单内的代码远程，硬做一个会变成带 shell 的旁路。
- 第二套 DSH 图表或会话循环。文献插件已经登记为 `company.literature`，回执只有计数和编号，不调用研究运行、超算、云或真机。命令行全量档案继续只挂 `company-agent` 组合。开发桌面使用上游标准预设的 shell，不在公司仓库里再写一套。

minimal 组合已经不装 device，这一点是对的。它仍装了 quantum、hpc、research 和 plan。名字上的 minimal 并不等于工具面最小；真正的可见性仍由预设和策略决定。若 minimal 的目标是造包和知识检索，下一步应从这个组合里拿掉 HPC、云和计划写工具，而不是把它们并进 core。

## 自动化从实验卡开始

启动一次研究迭代，先填 `docs/experiment-card.zh-CN.md` 里的表。表上的值交给已有的 `company-agent-research`：`company_research_compile` 校验，通过后在 lab 里批准一次 `company_research_run`。这一次调用按 `max_attempts` 在内部迭代，保留或预算用尽即停止。上限是 5 次。下一轮是一张新卡，或用户明确要求再跑一次。

这张表对应的成熟做法是三件已经在用的东西，而不是再装一个一直循环的插件。

- [github/spec-kit](https://github.com/github/spec-kit) 是规格入口。实验卡就是交给研究时钟的规格，范围写在这一次运行上。完整实验规格仍是 `research-layer/schemas/experiment-spec.schema.json`；公司工具只接收卡上的短字段。
- GitHub Actions 的 `workflow_dispatch` 把表做成一次运行的 inputs。作业在预算或结论处结束，同一次实验用同一把幂等键，不把 runner 留成常驻进程。`company_research_run` 的 `idempotency_key` 起同一作用。
- 实验协议沿用 autoresearch 已保留的四项：预算、指标、允许修改的路径、保留或撤销。当前时钟读到的指标是 `val_loss`。
- GitHub issue forms 把填好的表变成一张工单。这里对应 `company_work_item` 的 `evaluate`，并且只有 `mode=auto` 且 `strength=explicit` 才打开，绑定当前会话。工单记录这一轮，不自己再开循环。

基线未复现或没有基线指标时，`compileExperiment()` 返回 `E_BASELINE_NOT_REPRODUCED` 或 `E_BASELINE_METRIC`，运行不开始。`resource_type` 里的 `hpc` 和 `qpu` 只表示类别。`qpu` 记下 lab 真机交接，不调用 `quantum_device_run`。超算和云的提交仍是各自插件上的一次一批准。

不采用的做法：按表格起一个新插件并让它一直迭代；把实验卡交给 HPC、云或真机插件；安装 Temporal、Ralph 式 shell 循环，或再部署一套 OpenHands、SWE-agent。研究层文档里的平台时钟仍留在 research-layer，由这一次 `company_research_run` 调用。

## 2026-11-06 公开来源复核

78 项矩阵的检索截止是 2026-10-29。下面只记这次对实验卡有新证据的来源。仓库不新装这些项目，DSH 仍是唯一 Agent Runtime。

| 来源                                                                                                                                                | 时间                                          | 适合我们的部分                                                      | 不引入仓库的部分                                                           |
| ------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------- | ------------------------------------------------------------ | ------------------------------------------------------------------ |
| [GitHub Agentic Workflows safe-outputs 规范 1.29.16](https://github.github.com/gh-aw/specs/safe-outputs-specification/)                             | 2026-11-03                                  | 一次 agent 作业；作业本身只读；写操作交给另一段带权限的步骤；每种写有次数上限；密钥不进 agent 作业     | 不安装 gh-aw，不把 GitHub Actions 当成第二套运行时                               |
| [Spec Kit 1.2.1](https://github.com/github/spec-kit/releases/tag/v1.2.1) 与[交付后维护规格](https://github.github.io/spec-kit/how-to/evolving-specs.html) | 2026-10-16                                  | 章程写一次；每张卡先规格、再计划、再任务；人看过产物再往下走；`converge` 只追加未完成任务，对齐到约定范围就停 | 不安装 `specify-cli`，不把 `/speckit-implement` 循环嵌进公司插件                 |
| [Super-agent 设计探索](https://superagent.ltd/) 与[原型哲学](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/main/docs/000-philosophy.md)     | 2026-10-31                                  | 先有书面规则再行动；主动行为先只记录；一次只问一个具体问题；工单要有终态、预算和截止                   | 原型声明文章里的设计并未全部实现。Router、Watchdog、端侧 daemon 不抄进本仓库                  |
| [autoresearch `program.md](https://github.com/karpathy/autoresearch/blob/master/program.md)`                                                      | 文件页 2026-03-09                              | 人改说明，代理只改一张允许的文件；指标用短提取，不把训练日志灌进上下文；账本只留提交、指标、状态、一句话         | 文件里的 `LOOP FOREVER` 不采用。公司时钟仍以 `max_attempts` 为顶，当前读数仍是 `val_loss` |
| [Robin, Nature](https://www.nature.com/articles/s41586-026-10652-y)                                                                               | 2026-05-19，DOI `10.1038/s41586-026-10652-y` | 实验在实验室闭环里：代理提出假设和方案，人做实验，数据回来后再开下一轮                          | 不部署 Crow、Falcon、Finch。没有真实文献源之前不登记文献插件                             |
| [Copilot coding agent 近况](https://github.blog/ai-and-ml/github-copilot/whats-new-with-github-copilot-coding-agent/)                               | 2026-02-26                                  | 一张写好的 issue 交给一个限制了工具的代理，做完以 PR 结束                           | 代理自审自己的 PR 与作者、评审分离冲突。云端会话交接不接入                                    |
| [The AI Scientist-v2](https://arxiv.org/abs/2504.08066)                                                                                           | 2025-04，arXiv:2504.08066                    | 分阶段，每阶段有停止条件；预算用尽就停；只把当前最好的一个节点带进下一阶段                        | 不采用代理树搜索、自动写论文、去掉人写模板。原文也写明核对成本高，假设缺少领域依据                          |
| [AI co-scientist](https://research.google/blog/accelerating-scientific-breakthroughs-with-an-ai-co-scientist/)                                    | 2025-02-19                                  | 人先给研究目标，系统先产出可检验的假设和方案，再进实验室                                 | 六个专职代理和 Elo 自评不进公司插件                                               |

这批材料支持现在的启动方式：实验卡是规格，`company_research_compile` 是门，一次批准的 `company_research_run` 是那一个作业，超算、云和真机仍在作业外面各自批准。下一轮来自新卡或人交回的结果，不来自常驻循环。

## 仍未闭合

- 私有环境写入 GitLab 地址和令牌之前，计划工具保持未配置。内网 `http` 还要显式打开明文开关。
- 量子平台地址不能使用已失效的本机回环地址。
- 研究时钟的真实一轮尚未在这台桌面会话里跑过。策略插件补上审批名单后，需要重启桌面再在 lab 里批准一次 `company_research_run`。
- 云门户页的嵌入脚本此前返回 404，本次没有改嵌入页，也没有放宽 iframe 沙箱。
