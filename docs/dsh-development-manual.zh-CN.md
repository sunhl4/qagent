# DeepSeek Harness 本工程开发规范(手册)

日期:2026-10-22(UTC+8)。  
状态:工程约束文档;依据本仓 `pins.json` 锁定的上游版本与本仓硬规则整理,作为在 DeepSeek Harness(DSH)架构上做开发时的强制规范与检查清单。  
上层引用:[Harness 框架对齐设计 v0.8](company-agent-harness-framework-v0.8.zh-CN.md)、[DSH 集成设计 v0.7](company-agent-dsh-integration-v0.7.zh-CN.md)、[开源调研复核总报告](oss-survey/05-复核总报告.zh-CN.md)。

## 0. 版本与来源

- 本仓锁定(`pins.json`):DSH `0.1.5-rc.2`,DSH 子组件 `0.1.5-rc.3`,node `22.22.0`,provider 协议 `company-agent-provider/1.0`。
- 官方上游:github.com/deepseek-ai/deepseek-harness("Everything is a Plugin");插件框架为 `@deepseek-ai/cordis`(Meta-Framework for Modern JavaScript Applications)。
- 已核对来源(2026-10-22):官方 [Cordis 教程](https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/cordis-tutorial/index.md)、[第 7 章 Into the harness](https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/cordis-tutorial/07-into-the-harness.md)、上游已发布更新版本(需按 §7 流程评估,不得整体升级)。
- 官方安全前提:上游 `SAFETY.md` 自述为 developer preview、未经安全审计,不能作为不可信负载的唯一安全控制。因此本仓合同、审批、审计、隔离与失败闭合不是可选项,是叠加层。

## 1. 定位与硬规则(不可改)

DSH 是唯一 Agent Runtime;公司代码只承载约束与治理。

| # | 硬规则 | 落点 |
| --- | --- | --- |
| 1 | 禁止新增模型循环、会话循环、工具循环;禁止自建排程器与设备循环 | `packages/` 插件只注册与转调 |
| 2 | 不直接 import `company_quantum_platform` 或任何科学算法包 | `src/company_agent/` 仅经 HTTP 信封 |
| 3 | 算法名单只来自平台 `algorithm.catalog`,标识是平台 `component_id`;禁止在 Agent 代码或知识库固化算法列表 | `contracts/` + `knowledge/` |
| 4 | 句柄只有 `asset_id`、`circuit_id`、`twin_id`;`twin_id` 仅 `quantum_device_run` 经 `ionstack-twinrun` 可产出(且 QCCD-Twin 溯源) | `contracts/tools.json` + `invoke.py` 校验 |
| 5 | `quantum_device_run` / `hpc_submit` / `quantum_cloud_submit` 在 `lab`/`sign` 必须 ask,在 `boot`/`algo` 必须 deny | `contracts/presets.json` + `policy.py` |
| 6 | 未知工具、未知 preset、缺失 provider、坏信封全部失败闭合;取消自动重试为零(设备、云、HPC 同) | `gateway.dispatch` + `policy.json` |
| 7 | 工具结果必须短;禁止 CAL、shuttle、bitstrings、Pauli 全文、密钥、完整电路正文;模型可见结果 ≤64,000 B | `contracts/results.json` + `sanitize.py` |
| 8 | 修改工具 schema 时同步合同测试和 DSH 注册;不得为通过旧测试恢复旧工具名 | `tests/` 门禁 |
| 9 | 官方 Codex 使用 `permissionMode: never`、`inheritsParentContext: false`,不挂载模型可见委派工具 | `profiles/company-agent/cordis.patch.yml` |
| 10 | 生产 profile 关闭 DSH 内置 preset 与用户可写 preset 根;不开放 shell/任意执行 preset 绕过审批 | `profiles/` |

## 2. 插件开发规范(cordis)

官方形态:每个能力(工具、适配器、会话、执行环境)都是挂在共享 Context 上的插件;`inject` 声明前置服务;插件卸载时注册项随之注销。

本仓强制落法(在官方形态之上收紧):

1. **只注册,不实现**。包源码 `src/index.js` 只允许一行级调用 `registerCapabilityTools(ctx, ["<capability>"])`(如 `packages/company-agent-hpc/src/index.js`);工具逻辑、审批、校验、错误清理全部在 Python 合同内核,经子进程转调。
2. **合同是工具可见性的唯一真源**。`registerCapabilityTools` 从 `contracts/tools.json` 读取目录,按当前 preset 的 `visible_tools` 过滤后经 `ctx.tools.register` 注册;本仓禁止在插件里手写 `defineTool`/自订 schema(那是官方教程示例的自由度,本仓让位给合同真源)。
3. **schema 投影规则**。给模型的参数 schema 经 `dshSchema()` 白名单投影(丢弃 `pattern`/`maxLength` 等 DSH 不支持的约束),完整 schema 在 Python 调用前由 `validate_json_schema` 强校验;新增 schema 关键字必须先加入两份白名单并有测试。
4. **`execute` 规范**。每次调用为 `company-agent invoke --tool <t> --preset <p> --args -` 的短命子进程:35 s 超时、`detached` 独立进程组、超时/取消/输出超限清理整组、继承管道有界关闭;stdin 传参 ≤256,000 B;结果经双重校验(内核侧 + 插件侧 `validateInvocationResult`)。
5. **审批接缝**。DSH 的 pre-execute policy 与用户审批先发生;`company-agent-policy` 插件再挂 `tools/pre-execute`,把合同 ask/deny 映射到审批 UI;非 ask 工具的 `authorize` 结果直接放行或拒绝。任何"绕道 ask"实现都被拒绝。
6. **观察事件**。诊断只经 stderr `company-agent-diagnostic:` 短 JSON(固定字段、无凭据/URL/参数/科学正文);`tools/result` 等会话事件只用于呈现,不作为权限或状态源。
7. **生命周期与配置**。YAML/cordis 配置改动遵循整行覆写语义(managed 行先 `disabled:false` 再覆写),坏配置必须 fail loud;禁止依赖 HMR 做生产装载。

## 3. 南向 provider 规范(`company-agent-provider/1.0`)

- 传输:每 provider 一个本地 HTTP `/invoke` 端点,POST 单一路径、单协议版本、封闭字段 `{"protocol","operation","request_id","payload"}`;bearer token 必填,常量时间比较,从不回显。
- 容量:请求 ≤256,000 B;成功/失败信封 ≤64,000 B,超限整次失败,不截断伪装成功;禁止额外字段。
- 幂等语义:`request_id` 只用于关联,不是服务端幂等保证;自动重试为零。任何已跨越发送边界的操作(设备运行、HPC 提交、云提交)超时/断连后只能标 `unknown` 并附 `request_id`,禁止宣称失败或成功。
- 远端命令安全:所有远端命令(SSH 参数、作业名、脚本路径等)先按合同字符类小时长校验再 `shlex.quote`;本地不派生 shell;输出行数/字节封闭。
- 失败闭合:未知操作、未知 provider、缺凭据、缺目标、路径越界一律失败;公众错误文本经敏感词(密钥/URL/路径)剥离,SSH/SDK 原始报错永不透传。
- 提交回执必须当场逐条核对批识别名(状态行、字段数、字符集);不满足即失败。
- 只读回查是对账的事实通道:`hpc_queue`/`hpc_job_status`/`quantum_cloud_devices`/`quantum_cloud_status` 属合同内工具;服务方管理渠道永远是作业事实真源,Agent 侧仅索引与展示。

## 4. preset、触发与编排

| preset | 定位 | HPC 看见 | 云平台看见 | 设备看见 |
| --- | --- | --- | --- | --- |
| `boot` | 只读会话/能力/工作流 | 无 | 无 | 无 |
| `algo` | 算法探索只读 | `hpc_queue`、`hpc_job_status` | `quantum_cloud_devices`、`quantum_cloud_status` | 无 |
| `lab` | 完整提交(agent 交互) | `hpc_queue`、`hpc_job_status`、`hpc_submit(ask)` | devices/status + `quantum_cloud_submit(ask)` | identity + `quantum_device_run(ask)` |
| `sign` | 设备/验收签名 | 无 | devices/status + `quantum_cloud_submit(ask)` | identity + `quantum_device_run(ask)` |

- 触发编排哲学:模型提议 → `company_workflow_validate` 静态校验(句柄拓扑、参数 schema、审批一致性)→ 审批门控 → 单次派发。规划/Criticizer/Reviewer 不是第二循环,它们在 DSH 会话里以合同工具取得证据。
- 禁用动态编排:官方示例中的动态 workflow、定时自主调用、shell preset、用户可写 preset、模型可见委派工具不进生产;合同层面把 `cordis_define`/`cordis_run` 列入 `forbidden_tools`。
- 任务终止显式化:验收要点以完成、超时/预算(token/墙钟/调用/费用)、等待审批、不可恢复四类结束,禁止依赖模型自觉收尾;断线恢复不重提交,恢复时以平台作业事实对账,冲突必须显式报告。

## 5. 模型接入

- 模型服务沿用既有部署,DSH 经 `llm-pi-ai` provider 适配配置;本仓默认路由 `company-local / deepseek-chat`,公司中转按需显式选用。
- 端点与密钥:地址不进入模型上下文;密钥经 `apiKeyEnv` 每请求引用(继承环境变量优先于原生凭据存储,两者不是等价可编辑来源);诊断与合同仓不得出现密钥。
- 模型能力以实测为准:中文理解、工具调用、流式遮挡/取消、限流都有验收场景;模型不适合工具任务时,不以开放 shell 或绕过审批补偿模型能力。本地服务故障不回退公网。

## 6. 验收与发布纪律

- 验收报告绑定版本四元组:`pins.json` 的 DSH/组件版本、公司合同版本、本地模型标识与版本、验收用例集标识;缺任一不得用于对比或作通过证据。
- 门禁自检(新增/修改工具必跑):`tests/test_contracts.py`(图封闭、唯一、provider 操作绑定)、`tests/test_hpc.py`、`tests/test_cloud.py`、`tests/test_invoke.py`、`tests/test_cli.py`、`tests/test_plugin_runtime.py`、`tests/test_dsh_profiles.py`、`tests/test_no_legacy.py`、`tests/test_managed_builtins.py`。
- 新增能力五步:合同(`tools.json`/`capabilities.json`/`providers.json`/`presets.json`)→ Python adapter(`src/company_agent/`)→ DSH 插件(必要时)→ 门禁同步 → 验收记录。合同文件是内容寻址快照,一次调用内不可变;派发前磁盘变更即失败。

## 7. 上游版本升级流程(不要整体升级)

1. 差异清单:逐条列出目标版本与 `pins.json` 锁定版本间的 API/行为差异(官方 release 说明 + 本仓锁定版本全量回归)。
2. 逐项评估:只采纳本仓确有缺口的扩展点(回答它落在哪个子系统、补哪个缺口);官方新增默认项(委派、shell、动态 workflow 等)即使"上游提供"也默认不进生产。
3. 验收:按 §6 跑全门禁 + 真实任务验收,绑定新版本四元组后并入 `pins.json`。

## 8. 本次实施记录(2026-10-22)

按本规范完成 review 缺口第一项:新增只读对账工具 `hpc_job_status`(capability `compute.hpc`,operation `hpc.job-status`)。

- 合同:`contracts/tools.json` 增行(pattern 封闭的 `slurm_number`;输出 `provider/slurm_number/state/source` 封闭对象,`source ∈ {queue,history,none}`);`capabilities.json` compute.hpc 清单、`providers.json` `hpc-slurm-ssh` 操作、`presets.json` lab/algo 可见性同步。
- Adapter:`hpc_ssh.py` 新增 `hpc.job-status`:先查活跃队列(`squeue -j`),未命中再查记账历史(`sacct --parsable2`),两视图干净且无行时明确返回 `not_found` 观察;`sacct` 失败仍失败闭合;命令全部过审校验与引用,不派生本地 shell。
- 编排语义:`hpc_submit(ask)` 提交后可用该只读工具核对回执,不再需要到服务方渠道逐条人工核对活跃/近期作业;`quantum_cloud_status` 云侧已具备按回执回查,对账闭环齐平。
- 门禁:`test_hpc.py` roster/操作绑定/policy 表/E2E/引用安全用例同步;`test_contracts.py` 修两处滞后断言(`uqc-cloud` provider 集合、`cloud` kind 操作引用);`test_plugin_runtime.py` 注册顺序同步;`test_no_legacy.py` 按"活性架构 vs 调研存档"边界将 `docs/oss-survey` 排除出承载旧名扫描(调研文档按上游真名记录是事实陈述,不是旧架构遗迹)。
- 提交脚本边界澄清与自助排查(同日):`hpc_submit` 的 `script` 参数始终是"已存在于授权网关上的绝对 POSIX 路径"——相对路径、`~`、Windows 盘符、含空格或直接粘贴脚本正文都会在内核合同层被拒(未到达网关)。为此:(1) `hpc_submit.parameters.script` 增加模型可见说明;(2) 内核对 `hpc_submit` 的 script 格式拒绝输出可行动文案(含"先用 hpc_script_check 核验"指引);(3) 新增第二个只读探测 `hpc_script_check`(`hpc.script-exists`,`test -f`):lab/sign 可见且无需审批,把"烧一次审批后失败"变成"提交前自查";零重试与失败闭合语义不变。注意提交回执失败(网关侧)在内核统一折叠为 `provider compute failed`,做不了逐字透传(远端错误文本按不可信数据处理)。
- 集群资源总览(同日):新增第三个只读探测 `hpc_resources`(`hpc.resources`,`sinfo --parsable2`):每分区一行,返回节点总数/状态聚合(`allocated=2,idle=4` 这类)与核心 alloc/idle/other/total 计数;lab/algo 可见,无需审批;args 必须为空;`sinfo` 失败或超时仍然失败闭合。用户配额(`sshare`/`sacctmgr`)与调度器负载(`sdiag`)未纳入本次合同——为保持最小封闭面,后续如需再按同一模板扩展;云平台侧的 5 qubit/1000 shots 是平台 SDK `get_chips` 返回的全部信息,实时负载需平台侧提供接口后才能进 `quantum_cloud_devices` 合同。
- 网关文件面(同日):新增 `hpc_file_list`(`hpc.file-list`,网关单层目录 ≤32 个常规文件)、`hpc_file_fetch`(`hpc.file-fetch`,网关文件**下载到 DSH 工作区 `gateway/<文件名>`**,仅限 ≤48,000 字节 UTF-8 文本,内容**不经过模型上下文**以避开 OPENQASM/科学正文禁令——结果只有落盘回执 lab/algo 可见)与 `hpc_stage_file`(`hpc.stage-file`,工作区文件**上传/创建到网关路径**,ask 门 lab/sign,合同全新 4 个策略键 `hpc_file_write_*`;文件已存在且未显式 `overwrite=true` 时返回 `written:false, mode:skipped_exists` 诚实回执;工作区读取带 O_NOFOLLOW 与指纹复核,拒绝符号链接/二进制/越界)。运行时侧 `runtime.js` 对该工具与 `quantum_cloud_submit` 同样附带 `X-Company-Workspace` 头;`providers.py` 在两个操作的网关请求上携带该头;`hpc_ssh` 的 `/invoke` 处理器同步读取该头。
- 主动操作补齐(同日晚):`hpc_job_cancel`(`hpc.job-cancel`,`scancel`,lab/sign ask)、`hpc_dir_create`(`hpc.dir-create`,`mkdir -p`,lab/sign ask;已存在目录返回 `created:false, mode:exists` 诚实回执不再重复建)与 `hpc_file_remove`(`hpc.file-remove`,单体文件 `rm`,lab/sign ask;文件缺失返回 `removed:false, mode:skipped_missing`)。策略合同新增 4 个键 `hpc_job_cancel_*`;`hpc_dir_create`/`hpc_file_remove` 复用 `hpc_file_write_*` ask/deny 决策链;四者都在 preset 可见性不变式与 decide 早退硬门中与 `hpc_submit` 同构。至今云平台仍只有平台 SDK 暴露的能力(提交/状态/结果回拿+模拟器限定),没有 SDK 的平台流程(如取消、任意文件、实时负载)列为待平台侧 API 合同项。
- 留档:云/HPC 提交均为零自动重试;`unknown` 状态下对账以平台事实为准,冲突须显式报告(v0.8 四-3 已受理为长期工程位,本次实现只读回查第一步)。
- 云提交方言根因与自动编译(2026-10-23):平台 SDK 的 `ensure_static_qasm` 只接受 `rzz`、`rx`、`ry` 调用；因此工作区里的标准 OpenQASM `h`/`cx`/`rz` 电路必须先在本地适配器内降解到平台方言，再补充 `rzz` 定义和逐位测量。该编译器只处理封闭的静态门语句，不导入科学算法包、不保留自定义门体、不放行动态控制流；编译后再次经过 SDK 校验，校验不通过时不会发生网络提交。工具合同和知识说明已同步。\n- SDK 失联运维诊断(2026-10-22 晚):`quantum_cloud_submit` 在 SDK 层失败时工具恒按合同折算为 `cloud.submit outcome unknown; do not retry automatically`,且 worker 原本把 SDK 异常整体吞掉,运维日志只剩外层类别。为此 `cloud_worker.py` 任意异常落盘"异常类别 + 有界帧名:行号"到与 `gateway._log_failure` 同一文件 `unitqc-company-agent/gateway-errors.log`(首行 `uqc-cloud worker {operation}` 标记),**绝不写值/错误文本**(SDK 报错文本可能携带程序正文或账号资料);日志通道损坏也不影响 stdout 的有界 JSON。配四个门禁:仅类别与帧、不可用通道静默、符号链接目标拒写、main 全链路。现场复盘结论:设备列表/状态查询接口对任务服务密钥不做强校验,"查询成功"不是密钥有效证据;21:04 那次尝试早于回执账本机制落地(回执集成当晚更晚接入),账本目录当晚 21:21 才由测试首次创建,故坐实"更新代码后重启 DSH 栈再提交"才是可对账基线。
- 真·agent 自然语言闭环(2026-10-22 深夜,操作员授权环):用内置 DSH 运行时 + 公司中转模型(gpt-6-luna 流式适配器,harness 记录审批)驱动真实会话完成两弧。云弧:`quantum_cloud_submit(bell.qasm3,qiskit-sim,100)` → ask 放行 → 任务 `c3b36a73…` → `SUCCESS` → `quantum_cloud_result` 回拿 p_1=0.6/p_0=0.4 → 模型自然语言汇报数值。HPC 弧:`hpc_dir_create`(created:false,exists 诚实)→ `hpc_stage_file`(skipped_exists 诚实幂等)→ `hpc_script_check`(exists)→ `hpc_submit` → 真实 Slurm 作业 `17907`(hpc 分区,compute01)→ 轮询 RUNNING→COMPLETED(source:history)→ `hpc_file_fetch` 把 `hpc_probe_out.txt`(hostname/date/nproc/SLURM_JOB_ID 63 字节)下载进工作区 `gateway/`。为此修正:(1) `company-agent-policy` 的 ask 路由白名单补齐 `hpc_stage_file/hpc_job_cancel/hpc_dir_create/hpc_file_remove` 并为每个 ask 工具给出人话审批理由(合同参数名以 tools.json 为准:dir_create/file_remove 用 `path`);(2) workspace 头缺失 —— 服务端 `hpc.file-fetch` 无条件把文件写入工作区 `gateway/` 目录,但 runtime.js 与 providers.py 的头白名单只覆盖 submit/stage-file,fetch 因此从未通过 —— 两级补 `hpc.file-fetch`;(3) 合同四工具描述补充"批准由会话逐次 ask 通道处理,直接调用即可,无需会话外等待"。教训:给 agent 的自然语言指令不得虚构集群路径事实(旧指令写 /data/jobs,集群上不存在——已改为 HOME 下目录);归一化、策略与 explorer 的修复都用真实失败驱动。待跟进:另一会话并行扩 `company_analysis_render` 进合同(presets/capabilities 已含),其测试计数(27→28、boot 列表)由该会话同步,本会话不抢写;并发会话同时写仓库会造成门禁闪红,涉及合同的改动要保持单写者。
