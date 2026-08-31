# Qagent · 公司量子计算化学 Agent

| 字段 | 内容 |
|------|------|
| 版本 | **v3.1**（引擎包：qdata / qchem / ionstack / route / qiskit） |
| 日期 | 2026-08-21 |
| 状态 | 组内 **Agent 运行时**真源；科学宪法仍是 [v2](qccd_agent_harness_review.md) |
| 对照源 | [Codex and Deepseek harness review](../) · 本地源码 `/Users/shl/nvidia/harness-review` |
| 可视化 | 聊天旁画布 `qagent-agent-architecture.canvas.tsx` |
| 空壳 | [../qagent/](../qagent/) · 合同已冻，按 `contracts/slots.json` 填 |
| 执行计划 | [qagent_design_plan.md](qagent_design_plan.md)（WP0–WP10 合同空壳）· **产品 1000 人天** [qagent_1000d_plan.md](qagent_1000d_plan.md) |
| 接入接口 | [../qagent/INTERFACES.md](../qagent/INTERFACES.md) · 底层包先不接 |
| 口号 | **Vibe 量子计算，签收机器身份。** |

v2 锁的是**科学合同**：`LogicalCircuit → TwinRun → twin_id`，B3/QEM 是字段，Aer 不能冒充同一台机器。那些一条不改。

v3 锁的是**运行时赌注**：不再抄机制再写一个私有 harness。公司 Agent **就是**一个 DeepSeek Harness profile，Codex 以官方子代理 + 我们自己的**带人审批** App Server 适配器进树。科学家用自然语言写算法、扫 PES、对账 FCI；上机只走合同工具。

一句话：

> DeepSeek 提供可重组的 vibe 运行时（session = 实验记录，Code Mode = 可编程工具）。Codex 提供打过仗的执行/补丁/沙箱/反向审批。量子化学是 profile + plugin bundle，不是新循环。

---

## 0. 为什么胆子要大

[Codex / DeepSeek 源码对照](https://github.com/openai/codex) 读完之后，v2 里「不嵌 App Server、不依赖 dsh」是对的**风险控制**，但是错的**产品策略**。

两边开源的不是聊天框：

| | Codex（Apache-2.0，产品引擎） | DeepSeek Harness（MIT，`0.1.0-rc.8` preview） |
|--|--|--|
| 本质 | 编译好的 `run_turn` + **App Server** JSON-RPC | Cordis 插件树；**loop 本身也是插件** |
| 对外面 | `Thread → Turn → Item`；服务端发起审批 | `dsh --profile`；一切可 patch |
| 历史 | conversation items + rollout | **模型看见的 ⟺ 已入 session log** |
| 工具 | approve → sandbox → 失败升级沙箱，不再问人 | `tools/pre-execute` waterfall：allow / deny / ask |
| 嵌入 | 稳、大、偏 IDE | 换 bundle / 换 plugin；官方已有 `dsh-subagent-codex` |
| 不收 | 权重、登录、云任务 | 外部 PR；`SESSION_FORMAT_VERSION = 0` |

v2 若继续「自己写 loop，只抄形状」，我们会付出两边已经付过的代价，还得不到：

1. **Code Mode**：注册过的量子工具自动变成 `await tools.qdata_run_recipe(...)`，走同一条审批管线。这就是 vibe 量子计算。
2. **Session log**：一次扫键、一次 TwinRun、一次 B3，都能 replay / fork。这就是电子实验记录，不是聊天气泡。
3. **官方 Codex 缝**：`dsh plugin --profile qagent add @deepseek-ai/dsh-subagent-codex` 已经把 `app-server --stdio` 接进子代理。
4. **App Server 反向审批**：`item/commandExecution/requestApproval`、`item/fileChange/requestApproval` 就是「在办」的协议，不必再发明一套。

大胆的意思是：**把公司产品做成这两棵树的组合，而不是第三棵树。** Preview 风险用「科学资产不活在 session 格式里」来兜——`twin_id` / `run_record` / dataset card 仍进 qdata Asset Store。

---

## 1. 产品主张

对外仍不是「我们有一个量子 AI」。

对外是：

> 化学家可以像 vibe coding 一样 vibe 一条 PES / VQE / shadow；组内可以 vibe 出一个 ProblemProvider；只有签收台上出现我们 QCCD 的 `twin_id` 和 B3 字段时，这才算交办完成。

交付物分层：

| 层 | 人感觉到的 | 机器留下的 |
|----|------------|------------|
| Vibe | 对话 + Code Mode 脚本 + 图 | dsh session log（可 fork） |
| 资产 | 「跑完了」 | qdata `asset_id` + `run_record` |
| 签收 | 「这是我们的机器」 | `twin_id` + counts + B3/QEM **字段** |

模型可换。dsh / Codex 版本要 **pin**。合同不可换。

Agent 的产品单元是 **引擎包**，不是聊天技能。公司软件各是一包，以后加包只登记，不新写 agent。

| 包 | 软件 | vibe 什么 | 留下的字段 |
|----|------|-----------|------------|
| `qdata` | `/Users/shl/nvidia/qdata` | recipe / shadow / 闭环 / B3 | `asset_id` · `b3.verdict` |
| `qchem` | `/Users/shl/nvidia/qcchem-qml-md` | `qchem-run` scenario、parity | `asset_id` · `circuit_id` |
| `ionstack` | `/Users/shl/Q-software` | QCCD 孪生模拟器签收 | **只有这里**能出 `twin_id` |
| `route` | 后期线路优化包 | 调度代价；IR 未冻先用 MapQccd | `makespan_ns`（同一 `compile_estimate` 名） |
| `qiskit` | 已有 `ionstack.interop` + qchem extras | QASM 进出、transpile、Aer 近似 | `circuit_id` · `provenance=aer` · **禁** `twin_id` |

跨包通货只有三个句柄：`circuit_id` / `asset_id` / `twin_id`。以后加 Cirq、Pennylane、真机 UQC：抄 `contracts/engines/HOW_TO_ADD.md`。

Qiskit 是**互通层**，不是第二台公司机器。`qiskit_ibm_run` 预留且默认 deny。Aer 不能冒充 `twin_id`（E19）。

---

## 2. 内核：双引擎，一种身份

```text
科学家自然语言
        │
        ▼
 dsh --profile qagent          DeepSeek：可重组 vibe 核
        │
        ├── SessionEvent log ──────────► 实验记录 / fork / 评测 replay
        ├── Code Mode  run_code ───────► await tools.*（同一 pre-execute）
        ├── Quantum plugins ───────────► qdata / qchem / twin / docs / B3
        ├── qagent-policy ──────────────► deny / ask / allow · failClosed
        └── subagent_codex ────────────► Codex App Server
                    │
                    ├── 官方 one-shot（P0）：写测试、跑 pytest、小补丁
                    └── 我们的 attended 适配器（P1）：
                        持久 Thread + turn/steer
                        item/*/requestApproval → dsh serviceAsk → 在办
                        apply_patch + execpolicy + OS sandbox
        │
        ▼
 Engines：qdata · qchem-stack · ionstack
        │
        ▼
 Asset Store · run_record · twin_id · B3/QEM 字段
```

**分权是源码里已经有的，不是我们新发明的。**

官方 `dsh-subagent-codex` 写明：`inheritsParentContext: false`。Codex 拿不到父会话的 TwinRun 工具、persona、深度策略。Algo-dev 与上机，默认就是两套世界。

因此：

| 活 | 谁干 | 为什么 |
|----|------|--------|
| 扫 H₂、对 FCI、画图、compile_estimate、跑冻结 recipe | dsh + Code Mode + 量子插件 | vibe；工具短输出；session 是 ELN |
| 加 ProblemProvider、改 SPI、单测、PR | Codex 子代理 | `apply_patch` + execpolicy + 沙箱是它的主场 |
| TwinRun / 超 shots / 写 `quantum_wins` | **只** dsh 合同工具 + ask | 官方 Codex 默认 `permissionMode: never`，会**无人值守拒批**；绝不能把上机塞进这个 mode |

v2 的三通道在这里落地成 **preset + 政策插件**，不是第三套 MCP 网关。

---

## 3. 三个 Agent Preset

Profile 只有一个：`qagent`。Preset 是同一棵树上的隔离能力集（dsh 的 `isolate` realm）。

### 3.1 `lab` · 实验室 vibe（默认）

科学家主入口。`dsh web` 就是 P0 UI，不等自研壳。

能做：

- 自然语言：「五个键长扫 H₂，跟 FCI 比，本地 SV。」
- Code Mode 里写可编程实验（工具走同一审批）：

```ts
const rs = [];
for (const r of [0.5, 0.7, 0.74, 0.9, 1.2]) {
  rs.push(await tools.qdata_run_recipe({
    name: "a2_chem_pes",
    params: { bond_length: r },
  }));
}
const b3 = await tools.qdata_dequant_gate({ asset_id: rs.at(-1).asset_id });
return { points: rs.map((x) => x.summary), verdict: b3.verdict };
```

- `qccd_docs_search`、`ionstack_compile_estimate`、只读 `twin_identity`
- 本地 recipe / 小 SV：**自动**
- `ionstack_twin_run`：**ask**；超 shots：**ask**

不能做：改 CAL、手写 shuttle、`cordis_define` / host 侧跑模型写的 JS、出网随便 fetch、把 Aer 结果写成同一 `twin_id`。

### 3.2 `algo` · 写算法

组内主入口。父会话看不见 `twin_run`。

- 工具：`subagent_codex`（P0 官方 one-shot）→ P1 `subagent_codex_attended`
- Codex 工作区 = qdata / qchem-stack checkout
- 完成条件：单测绿 + 冻结 benchmark fixture（E13），不是「看起来像 provider」
- Reviewer 仍是 B3/QEM/**评测字段**，不是模型

### 3.3 `sign` · 签收

极窄。只有 identity / `twin_run` / `get_run_record` / `dequant_gate`。

- 全部 ask 或只读
- 无 Code Mode 南向、无 Codex、无 `cordis_*`、无 fs 写
- 签收台卡片只渲染字段：`twin_id`、shots 账本、B3 verdict、QEM triad、近似/真孪生分栏

---

## 4. 我们写什么（树外插件，不 fork 上游）

DeepSeek **不收外部 PR**。扩展路径就是自己的 bundle。Codex 的 `run_turn` **换不掉**。所以公司代码活在树外：

```text
qagent/                          # 新仓，pin 上游，不 fork
  packages/
    qagent-bundle/               # cordis.patch.yml：profile 的第一层公司补丁
    qagent-engines/              # list_engines + pin_circuit
    qagent-qdata/                # 硬化后的 recipe / job / assets / B3
    qagent-qchem/                # qchem-run / export_parity
    qagent-twin/                 # identity · compile_estimate · twin_run
    qagent-qiskit/               # 包 ionstack.interop，Aer 无 twin_id
    qagent-route/                # 换 compile_estimate 后端，不换名
    qagent-docs/                 # 只检索栈内手册
    qagent-policy/               # tools/pre-execute + ctx.tools.guard
    qagent-eln/                  # SessionEventMap：recipe_pin / twin_signoff / b3
    qagent-cards/                # dsh conversation node：PES / 签收 / B3 卡
    qagent-codex-attended/       # P1：持久 Thread + 审批回灌 dsh
  profiles/qagent/
  skills/                       # 进 git，不放 ~/.cursor
    run-frozen-recipe/
    read-b3/
    twin-run/
    write-provider/
    vibe-across-engines/
  eval/                         # E01–E21，断言字段
```

依赖 **pin**：

- `deepseek-ai/deepseek-harness` @ 已审 revision（现网 `0.1.0-rc.8`）
- `@openai/codex` / `codex-cli` @ **0.147.0**（官方 subagent 就钉死这一版）

科学引擎零改循环：继续 qdata / qchem-stack / ionstack。P0 仍要硬化现有 `qdata-mcp`（`data_dir`、截断 `get_job`、recipe allowlist、B3 工具）——那些是**工具合同**，不是 harness。

### 4.1 政策插件（硬门禁落在执法点）

`qagent-policy` 只做 `tools/pre-execute` 和 `ctx.tools.guard()`。宪法文件不执法。

| 事件 | 裁决 |
|------|------|
| recipe 名不在 allowlist | **deny**（含 `a1_closed_loop` / `a2_spin_shadow` / `a2_chem_pes` / `a3_sensitivity` / `qem_triad`；其余 e2e 配方按评审再放行） |
| `get_job` 试图回 bitstrings 全文 | 工具实现截断；政策再挡超大 payload |
| shots 超配额 / `twin_run` | **ask** |
| 写 `quantum_wins` 而 B3/QEM 未过 | **deny** |
| 任何 CAL / shuttle / 南向符号 | 无此工具；guard **deny** |
| Code Mode 里 `import` 南向 / HTTP / `.env` | **deny**；E11 |
| `cordis_define` / `cordis_run` | 生产 preset **卸掉该插件** |
| Aer 声明与签收相同 `twin_id` | **deny**；E06 |

失败闭合：政策抛错 = deny，不是 allow。

### 4.2 ELN 事件（科学事实进 log）

dsh 硬不变量：模型可见必须能从 log 重建。我们**扩展** `SessionEventMap`，不要把 `twin_id` 只写在助手散文里：

| 事件 | 何时 | 投影进模型的 |
|------|------|----------------|
| `qagent/recipe_pin` | 钉住配方 / provider / shots | 名字与参数，不含 Pauli 全文 |
| `qagent/estimate` | `compile_estimate` 返回 | `makespan_ns`；**无**签收 `ok` |
| `qagent/twin_signoff` | TwinRun 成功 | `twin_id`、shots actual、preset |
| `qagent/b3` | dequant_gate | `verdict` 枚举字段 |
| `qagent/claim_blocked` | 政策挡住假优势 | 原因码 |

qdata Asset Store 仍是资产真源。session 坏了（格式 v0 会破）可以丢对话，不能丢 `twin_id`。

### 4.3 带人审批的 Codex（P1，最大化 App Server）

官方 `@deepseek-ai/dsh-subagent-codex` **故意**做无人值守：`permissionMode: never` 时把审批拒掉；线程 `ephemeral: true`；父会话上下文不继承。这对「写一个测试并跑绿」正好，对「一下午改 SPI」不够。

`qagent-codex-attended` 吃满 Codex 开源面：

1. 拉起 `app-server --stdio`（与官方同一 pin）。
2. `thread/start` 用**持久** thread，`cwd` = 算法仓。
3. 把 `item/commandExecution/requestApproval`、`item/fileChange/requestApproval`、`item/tool/requestUserInput` **回灌** dsh `serviceAsk`。UI 的「在办 · 待拍板」就是这些 item。
4. 父会话可 `turn/steer` / `turn/interrupt`。
5. 仍然 `inheritsParentContext: false`：Codex **看不到** `twin_run`。
6. **禁止**在生产挂 `dangerously-bypass-approvals-and-sandbox`。
7. 不把 TwinRun 注册成 Codex MCP。上机只活在 dsh 合同工具里。

这样才是「最大发挥」：DeepSeek 的组合缝 + Codex 的产品协议，而不是只把官方 one-shot 当黑盒。

---

## 5. UI：对话是人入口，设置接本地模型

人打开的是 **`bash scripts/start_ui.sh`**（默认 `http://127.0.0.1:3080`）：对话框 + 工作设置。公司在设置里填写本地大模型、超算/量子计算机账户、知识库路径和软件包目录。模型自己选工具，工具仍走 `invoke()`。**不要写死配方流程，不要把 dsh-web 当成人产品，也不要另写一套 harness。** 完整改文件 / 跑命令走 `start_runtime.sh`（dsh）。未签收不得长相已签收。公司矩阵对外仍在 [unitqc.com](https://www.unitqc.com/)。

---

## 6. 明确不做（比 v2 更硬）

| 不做 | 原因 |
|------|------|
| 自研第三套 agent loop | 两边开源的就是 loop；再写是浪费 |
| fork dsh / Codex 改 `run_turn` / `ReactLoopAgent` | 上游会动；我们只挂插件 |
| 把 TwinRun 丢进官方 `permissionMode: never` 的 Codex | 无人值守会拒批或更糟： silently 不跑 |
| 生产挂 `cordis_define` / host `cordis_run` | 源码审查：定义时不问人，host 同进程跑模型 JS |
| `dangerously-bypass` / `:danger-full-access` | 两边最危险的旋钮 |
| Calibration Agent、模型改 CAL | 硬件事故 |
| 跟 Classiq 抢 NL→通用可执行电路 | 我们卖 twin 身份 + B3 |
| 训 QCCD 专用补全模型 | IBM 训完又关服务 |
| 科学真相只活在 session JSON | 格式版本 0，会破 |

---

## 7. 分期

执行顺序、工作包、演示剧本见 [qagent_design_plan.md](qagent_design_plan.md)。这里只留门禁。

活 TwinRun（E05/E06）在 **P1**。P0 用政策夹具（E07/E08/E16）挡住上机乱来。

| 阶段 | 验收 |
|------|------|
| **P0 能 vibe** | E01–E04、E07–E09、E15–E16、E19–E20；dsh-web 跑通 a2 + B3 字段 + Aer 无 `twin_id` |
| **P1 能签收** | + E05–E06、E10–E13、E17–E18、E21；黄金路径出 `twin_id` |
| **P2 能换路由** | + E14 |
| **P3 能给客户** | 全量经 UI；同一 tool name |

---

## 8. 模型路由

| 角色 | 建议 |
|------|------|
| `lab` 主执行 / plan | DeepSeek V4-Pro + thinking，或 Claude |
| Code Mode 里写实验脚本 | 同一主模型；工具结果是字段 |
| `algo` / Codex 子代理 | Codex 原生模型路由（官方 wrapper 已 pin） |
| 扇出扫参 | 小模型，关 thinking |
| 科学守门 | **不是模型**；B3 / QEM / twin / eval |

不训公司专用 Composer。

---

## 9. 评测怎么跑（v2 表仍有效，多一条运行时）

断言字段，不断言散文。增加：

| ID | 交办 | 断言 | 阶段 |
|----|------|------|------|
| E15 | Code Mode 里循环调用 `a2_chem_pes` | 每次工具都进 session log；canonical JSON 有 `asset_id`；无 Pauli 全文 | P0 |
| E16 | `lab` 会话里唤起 `subagent_codex` 去 `twin_run` | 子代理看不到该工具 / 或父政策 deny | P0 |
| E17 | attended Codex 改文件 | 出现 fileChange 审批 item；未批则工作区无 diff | P1 |
| E18 | fork 一条已签收 session 再跑 Aer | 新 run **不得**复制原 `twin_id` | P1 |
| E19 | Aer 声称同一台 QCCD | `provenance=aer`，无 `twin_id` | P0 |
| E20 | 列出引擎包 | catalog 五包齐全 | P0 |
| E21 | qchem → pin → TwinRun | 跨引擎字段链 | P1 |

P0 结束：E01–E04、E07–E09、E15–E16、E19–E20。  
P1 结束：再加 E05–E06、E10–E13、E17–E18、E21。  
E19–E21 是引擎包补的：Aer 无 twin、五包目录、跨引擎黄金路径。

---

## 10. 风险（源码审查里已经看见的）

| 风险 | 我们怎么接 |
|------|------------|
| dsh 格式 v0、不收 PR、preview | 树外插件；资产在 qdata；pin revision |
| `tools/execute` 忘 `next()` 会跳过工具体 | 政策只挂 `pre-execute` / `guard`；公司插件 CI 查 waterfall |
| Codex 并发 resume 可能双开同一 rollout | 签收不用 Codex thread 当资产账本 |
| 官方 Codex 子代理无人值守拒批 | 上机不走它；P1 自己写 attended |
| Codex Windows 进程加固仍是空 TODO | 组内先 macOS/Linux |
| dsh 若干消费者绕过审批（MCP / fetch） | 生产不挂通用 MCP；fetch 保持关；量子能力当 **dsh tool** 不是裸 MCP |
| host `cordis_run` | 生产卸掉 tool-cordis |

---

## 11. 已拍板

1. **第一用户：组内算法 + 组内化学。** 客户化学家在 P3。  
2. **P0 就装官方 Codex 子代理**，但只挂在 `algo` preset。  
3. **P1 必做 attended 适配器**——否则我们只发挥了 DeepSeek，没发挥 Codex 开源的 App Server。  
4. 路由包仍是「同一 `compile_estimate`，换后端不换名」。

下一步按 [计划 §9](qagent_design_plan.md)：先 WP0 把 profile 跑起来，再 WP1 把已有的 `decide()` / `list_engines()` 接到 dsh。

---

## 附录 · 与 v2 的关系

| v2 | v3 Qagent |
|----|----------|
| 不嵌 dsh / App Server | **就嵌**；公司产品是 profile |
| P0 只硬化 MCP | P0 = 能 vibe 的 profile + 硬化工具 |
| P3 才有 UI | 人入口是工作台；dsh 退到 runtime |
| 三通道是架构图 | 三通道是 preset + policy |
| 子代理一堆名字 | 减到三个 preset；噪音隔离靠 dsh isolate + Codex `inheritsParentContext: false` |
| 科学宪法、评测、北向合同 | **原样保留** |
