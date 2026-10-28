# 终端式 agent(Cursor 路线)与 Company Agent:实现difference对照

日期:2026-10-22(UTC+8)。  
用途:对外/对内介绍"为什么公司 Agent 按现在这条路实现"的讲解材料;以公司 HPC/云平台提交这两个团队都已验证过的通路为实例。  
事实依据:本仓 `AGENTS.md` 硬规则、`contracts/`、`packages/`、`src/company_agent/`、`profiles/` 与 [DSH 开发手册](dsh-development-manual.zh-CN.md);文中不含任何账号、密码、密钥或内网地址。

## 0. 一句话结论

**Cursor 式用法是"把你的身份借给模型",Company Agent 是"把封过边的工具交给模型"。** 前者快,因为它一登台就继承了操作者的全部权限与判断;后者的每一分"慢"或"严",都是把过去由"操作者本人现场盯梢"这件事,改写成可校验、可审计、多租户一致的明文合同。

## 1. 场景回放(同一个需求,两条实现)

需求:"帮我把这个作业提交到公司 HPC,然后告诉我队列状态。"

**Cursor(终端式 agent,账号密码已给到它)**

1. 模型在用户本机 shell 里 `ssh <user>@<host>`(密钥/密码来自用户支付给它的上下文或环境);
2. `sbatch /path/to/run.sh`;失败(`Batch script not found`)→ 自己读 man/squeue、改路径、重试;
3. `squeue -u <user>` 看队列,把输出贴回对话;
4. 完成——**全程以操作者的身份、操作者的权限、操作者在屏幕前盯梢为担保**。

**Company Agent(DSH 上的合同工具)**

1. 模型看不到任何凭据;`hpc_submit` 的 schema 说明写明:script 必须是**网关上已存在的绝对 POSIX 路径**;
2. 提交前模型可以 `hpc_script_check`(只读 `test -f`)自查文件是否在网关上;不在→和用户说清楚,而不是烧一次审批后失败;
3. `hpc_submit`(lab/sign 必须 ask)弹出审批卡:provider、job_name、script、partition、nodes、walltime 全在卡上;批准才 `sbatch --parsable`;
4. 返回**短回执**(`slurm_number`),随后 `hpc_queue` / `hpc_job_status` 里用 `slurm_number` 对账(活跃队列+记账历史);
5. 每一步落 `company-agent-diagnostic` 短元数据(工具、操作、request_id、合同摘要、耗时、状态);错误文本经敏感词剥除,不留主机名/路径/密钥。

两条都能到达终点。差别不在"能不能做到",在**每一跳的担保由谁出具**。

## 2. 为什么感觉"难这么多":五处真实差额

| # | 维度 | 终端式 agent | Company Agent |
| --- | --- | --- | --- |
| 1 | 凭据位置 | 账号密码进模型上下文(历史/网关日志/缓存可及) | 密钥只存在适配器环境与凭据文件,经 `apiKeyEnv` 每请求解析;模型只见回执与 `request_id` |
| 2 | 权限面 | 整机 shell + 任意网络 + 任意文件读写 | 封闭工具目录(20 个合同工具);参数 schema 全校验;未知工具/未知 preset/坏信封一律失败闭合 |
| 3 | 失败语义 | 自动重试,可能重复提交真实计费作业 | 重试为零;跨越发送边界后超时/断连一律 `unknown`,凭回执对账,不静默续跑 |
| 4 | 授权表达 | "我有 SSH 权限"这一事实由人肉背书 | 同一事实换成程序可验证:preset 可见性 + ask/deny(lab/sign 逐次审批,boot/algo 拒绝)+ 审批卡快照 |
| 5 | 人群与终端 | 单个开发者、单终端、本人盯梢 | 桌面/网页双端行为一致;不懂 SSH 的同事可安全使用;文本注入(网页/文件里的指令)不能升高为权限 |

差额的实质:**把原来由"人 implicitly 会做"的事(理解报错、自查文件、不重复提交、看好密钥),变成"机器 explicitly 且可审计地做"。** 这类工作是一次性投入,收益按每一次调用复利。

## 3. Company Agent 实现略述(讲解时展开用)

### 3.1 分层与真源

```text
DeepSeek Harness(DSH,锁 0.1.5-rc.2) —— 唯一 agent 运行时(cordis 插件框架,"一切皆插件")
  ├── profiles/company-agent          DSH 组合:preset、模型路由、受管内置工具、Codex 隔离
  ├── packages/company-agent-*        5 个 DSH 插件:只注册工具并转调内核,零业务逻辑
  ├── contracts/(6 个 JSON 合同)      工具 schema/能力/provider/策略/preset/结果预算 = 唯一真源
  └── src/company_agent/              合同内核 + 南向适配器(schema 校验、策略、HTTP 信封、SSH/SDK 桥)
```

- `contracts/` 六个文件在**每次调用开始时读为内容寻址不可变快照**(sha256 摘要),`verify_snapshot_current` 在真正发送前核对磁盘;中途改合同 → 本次调用失败,不复用人工批准。
- `packages/` 层没有模型循环、没有重试:每次调用 = `company-agent invoke` 短命子进程(35s 超时、独立进程组、输出超限清组、stdin ≤256KB、结果 ≤64KB)。

### 3.2 一次工具调用的完整生命周期

```text
模型提议(自然语言)
  ↓ DSH pre-execute 策略管道 + 审批接缝(tools/pre-execute;company-agent-policy 插件)
  ↓ company-agent invoke --tool <t> --preset <p> --args - [--approved]
Python 内核
  1. 合同快照读取 + 内容摘要(contracts/*.json)
  2. 参数包校验:≤256KB、嵌套深度、未知字段、JSON Schema 类型与 pattern
  3. 策略判定 decide():preset 可见性 + ask/deny 合同(_unknown→deny)
  4. ask 且未批准 → needs_ask(审批卡,含参数快照摘要);批准 → 继续
  5. provider HTTP 信封 → http://127.0.0.1:<port>/invoke(Bearer,req_ 开头 32hex 关联号)
适配器(localhost 单一路径单一方法)
  6. hpc_ssh.py:严格目标校验(字符类)→ test -f / squeue / sacct / sbatch --parsable
     全部参数再次按合同字符类校验后 shlex.quote 进远端命令;本地从不派生 shell
  7. cloud.py/cloud_worker.py:SDK 子进程隔离(-I,凭据经环境注入,24s 闹钟限时)
     提交仅允许模拟器;QASM 程序从 DSH 工作区 O_NOFOLLOW 逐级打开、指纹复核
返回链
  8. 结果信封封闭字段(seq: protocol/ok/provider/request_id/result|error)
  9. 输出合同校验 + 64KB 预算 + 禁止内容剥离(cal/shuttle/bitstrings/Pauli 全文/密钥)
 10. 短结果回模型 + stderr 诊断流(固定字段,无凭据/URL/参数/科学正文)
```

### 3.3 preset × 审批矩阵(今天实际状态)

| preset | 定位 | HPC | 云平台 | 量子设备 |
| --- | --- | --- | --- | --- |
| `boot` | 冷启动只读 | 无 | 无 | 无 |
| `algo` | 算法/只读探索 | `hpc_queue`、`hpc_job_status` | `quantum_cloud_devices`、`quantum_cloud_status`、`quantum_cloud_result` | 无 |
| `lab` | 完整交互 | 上述 + `hpc_script_check`、`hpc_submit(ask)` | 上述 + `quantum_cloud_submit(ask)` | `quantum_device_identity` + `quantum_device_run(ask)` |
| `sign` | 签核验收 | `hpc_submit(ask)`、`hpc_script_check` | 同 lab | 同 lab |

`cordis_define`/`cordis_run`(动态 workflow)与任何 shell/编輯类逃生门在 `forbidden_tools` 里;官方 Codex 子代理 `permissionMode: never`、`inheritsParentContext: false`。

### 3.4 结果与证据

- 模型可见结果 ≤64,000 字节,集合/深度/字符串长度封顶;超限整次失败,不截断伪装成功。
- 每次调用的蒸馏物:`request_id`、`contract_digest`、耗时、status/error_category/execution_state——出问题时按 `request_id` 对账,不靠聊天记录考古。
- 验收绑定版本四元组:pins.json(DSH/组件)、合同版本、模型标识、用例集标记;全量门禁当前 716 项通过。

### 3.5 模型接入(公司两条路线都支持)

- 稳态路线:公司本地 DeepSeek(`company-local / deepseek-chat`)直连 `127.0.0.1`,开机即有,默认路由;
- 灵活路线:公司中转(`company-relay`,任意 openai-completions 兼容网关)在 DSH 原生「设置 → 模型」里用 URL + 密钥经 `apiKeyEnv` 显式新增/编辑(类似 Cursor 的模型配置体验);模型发现是显式动作,密钥不进合同仓/模型上下文。
- 本地服务故障不回退公网;超时/重试类高级字段仍在受管 settings 里编辑(组合事实由合同决定,页面只做安全子集)。

## 4. 对 Cursor 路线的吸收与保留

- **吸收**:模型接入的自觉体验(URL+密钥显式配置)、"自然语言闭环提交"的使用预期(为此补了 `hpc_script_check`/`hpc_job_status` 这类把人肉判断工具化的探针,以及错误文案的可行动化)。
- **例外清单**(对标 Cursor 不做):不开放 shell/任意文件写入 preset、不给模型可见委派工具、不用密码进上下文、不让会话文本身核账。
- **设计中的下一步**(未实现,需按"合同→adapter→插件→测试"排期):`hpc_stage_script`(工作区 `.sh` → 网关白名单目录的受控上传,ask + 大小/路径受限),落地后"写脚本→提交→拿回执"全程自然语言闭环,体验贴近 Cursor 而边界保留在审批卡上。

## 5. 什么时候 Cursor 式路线反而是"对的"

诚实边界:如果场景是"一两个人在自己电脑上,用自己密钥,本人全程盯梢、无审计要求",终端式 agent 就够了——它的搭建成本几乎为零,公司合同层在那样的场景里是过度工程。**两种方式可以并存,不冲突**:Cursor/终端跑个人探索,DSH 上跑公司级提交与任何进出租户数据的动作。分界线一句话:

> **密码不进上下文、操作可审计、断点可对账——这三条只要有一条是硬要求,就必须走 Company Agent 这条路。**

## 6. 讲解用一页总结(五点口径)

1. 两者的差距不是"能不能提交作业",而是**每一跳的担保由谁出具**——人肉盯梢 vs 明文合同+审批+诊断。
2. 技术通路与过去完全同源(SSH/squeue/sbatch、SDK),HPC 侧零新增;难度全部在"模型 ↔ 网关"之间把人的隐性判断机器化。
3. 合同(`contracts/`)是唯一真源:工具、可见性、审批、预算、禁止内容都在 6 个内容寻址 JSON 里,改一处即全端一致,并留审计快照。
4. 凭据永不进模型上下文;模型只见封闭 schema 的工具面与短回执——这是与"把账号密码给 Cursor"最本质的一条界线。
5. 已交付证据:HPC/云全链路(队列/提交/状态/结果/脚本自查)在此门禁体系内可用,全量门禁 716 项通过;版本四元组绑定,升级按差异清单而非整体换代。
