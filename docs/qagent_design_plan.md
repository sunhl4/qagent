# Qagent 设计计划

| 字段 | 内容 |
|------|------|
| 版本 | **1.1**（G-01 治理包：boot / 后验证人 / handoff / E28–E32） |
| 日期 | 2026-08-21 |
| 状态 | **WP0–WP10 已落地**（2026-08-23）。其后产品计划见 [qagent_1000d_plan.md](qagent_1000d_plan.md)（1000 人天 · 造包/用包） |
| 架构 | [qagent_agent_architecture.md](qagent_agent_architecture.md) |
| 科学宪法 | [qccd_agent_harness_review.md](qccd_agent_harness_review.md) |
| 空壳 | [../qagent/](../qagent/) |
| 可视化 | [设计计划画布](/Users/shl/.cursor/projects/Users-shl-nvidia-Q-data/canvases/qagent-design-plan.canvas.tsx) · [架构画布](/Users/shl/.cursor/projects/Users-shl-nvidia-Q-data/canvases/qagent-agent-architecture.canvas.tsx) |

本文只回答三件事：**做成什么样、按什么顺序做、做到什么算过。** 机制细节回架构文，合同细节回 `qagent/contracts/`。

---

## 0. 一句话

组内科学家能用自然语言 **vibe 量子计算**：化学栈出电路，qdata 出资产和 B3，Qiskit 做互通和 Aer 近似，ionstack 孪生签收，线路优化稍后换同一 `compile_estimate`。运行时是 DeepSeek profile + Codex 子代理。**不自研第三套 loop。**

成功画面（P1 结束）：

> 「用 minimal_vqe 跑 H₂，转成 Qiskit 看一眼 Aer，估计 t-junction 调度，1000 shots 签收，告诉我 B3。」  
> 对话里出现 `circuit_id`、`makespan_ns`、`twin_id`、`b3.verdict`。Aer 那一步没有 `twin_id`。TwinRun 问过人。

---

## 1. 已经拍板（不要再讨论）

1. 第一用户是**组内算法 + 组内化学**。客户在 P3。  
2. 产品单元是**引擎包**，不是聊天技能。加软件只登记包。  
3. 三个句柄：`circuit_id` / `asset_id` / `twin_id`。只有 ionstack 能出 `twin_id`。  
4. Qiskit 是互通层。包现有 `ionstack.interop`。Aer / IBM **不得**写 `twin_id`。`qiskit_ibm_run` 默认 deny。  
5. 上机只走 dsh 合同工具 + ask。禁止塞进官方 Codex `permissionMode: never`。  
6. P0 用 dsh-web。不画驾驶舱。  
7. 科学真源在 qdata Asset Store，不在 dsh session 格式。  
8. 评测断言**字段**，不断言模型散文。

---

## 2. 仓与改动边界

| 仓 | 计划里许改什么 | 不许 |
|----|----------------|------|
| `Q-data/qagent` | 插件、政策、评测、Skill、profile | 自研 loop |
| `qdata` | 硬化 MCP：`data_dir`、allowlist、截断 `get_job`、B3 工具 | 另起一套工具名 |
| `qcchem-qml-md` | **原则上不改**；Qagent 调 `qchem-run` | 为 Agent 重写化学核 |
| `Q-software` / ionstack | **原则上不改**；走已有 REST 与 `interop` | 模型碰 CAL / shuttle |
| 线路优化（未冻） | 只换 `ionstack_compile_estimate` 后端 | 新工具名、新 schema |

---

## 3. 工作包与依赖

```text
WP0 启动 profile
   │
   ├─► WP1 政策 + 引擎目录
   │      ├─► WP2 硬化 qdata ────────┐
   │      └─► WP3 Qiskit 互通 ───────┼─► WP4 ELN/Skill ─► ★ P0 门禁
   │                                 │
   └─►（官方 Codex 仅 algo，WP0 挂上）┘

★ P0 之后
   WP6 TwinRun + estimate ─► WP7 qchem/docs/sandbox ─► WP8 卡片+attended Codex
                                                         │
                                                         ▼
                                                      ★ P1 门禁
                                                         │
                                            WP9 route 换后端 + CI  ★ P2
                                                         │
                                            WP10 客户壳            ★ P3
```

| WP | 阶段 | 做什么 | 填这些槽 | 评测 | 依赖 | 人能感到的结果 |
|----|------|--------|----------|------|------|----------------|
| **WP0** | P0 | pin dsh + Codex 0.147.0；展开 `QAGENT_ROOT`；卸掉 cordis / fetch | S-PIN-01/02、S-PROFILE-01、S-CODEX-01 | — | — | `dsh --profile qagent` 打开 web |
| **WP1** | P0 | `decide()` 挂上 pre-execute；`list_engines` / `pin_circuit` | S-POLICY-01/02、S-ENG-01/02 | E07（政策）、E08、E16、E20 | WP0 | 「接了哪些引擎」有目录；未知 recipe / CAL / Codex 上机被拒 |
| **WP2** | P0 | 硬化 qdata 合同并接上插件 | S-QDATA-01…08 | E01–E04、E09、E15 | WP1 | 对话跑通 `a2_chem_pes` / `a2_spin_shadow`，B3 是字段 |
| **WP3** | P0 | 包 `ionstack.interop`：import/export/Aer | S-QISKIT-01/02/04 | E19 | WP1 | QASM 能 pin；Aer 有 counts、**无** `twin_id` |
| **WP4** | P0 | ELN 短事件 + 三份实验室 Skill | S-ELN-01/03/04、S-SKILL-01/02/05 | E15（log） | WP2、WP3 | 黄金路径写在 Skill 里，session 能 replay 钉配方 / B3 |
| **WP6** | P1 | TwinRun REST + `compile_estimate`（先 ionstack MapQccd） | S-TWIN-01/02/03、S-ELN-02、S-SKILL-03 | E05–E07（真跑）、E12、E18 | P0 | H₂ + `t_junction` 有 `twin_id`；Aer 不能复制它 |
| **WP7** | P1 | `qchem-run`、栈内 docs、沙箱黑名单 | S-QCHEM-01/02、S-DOCS-01、S-SAND-01 | E10、E11、E21 | WP6 | 跨引擎一句话：化学 → pin → Qiskit → estimate → TwinRun(ask) |
| **WP8** | P1 | dsh 卡片；attended Codex | S-CARD-01/02、S-CODEX-02、S-SKILL-04 | E13、E17 | WP6 | 签收/B3 是卡片；改 SPI 要过「在办」 |
| **WP9** | P2 | route 换后端不换名；评测进 CI；IBM 工具保持 deny | S-ROUTE-01、S-QISKIT-05 | E14 | P1 | 换实现仍过 E12 |
| **WP10** | P3 | 对话 / 在办 / 签收台（换皮） | — | 全量从 UI 再跑 | P2 | 同一工具名，客户不绑 Cursor |

没有 WP5：P0 门禁就是 WP1–WP4 的汇合点。

---

## 4. 阶段门禁（以评测为准）

先前架构把 TwinRun 的 E05/E06 写在 P0，槽位却在 P1。**本计划改齐：活 TwinRun 进 P1。** P0 仍用政策夹具挡住上机乱来。

| 门 | 必须绿 | 人验收 | 明确不做 |
|----|--------|--------|----------|
| **P0 能 vibe** | E01–E04、E07–E09、E15–E16、E19–E20 | dsh-web：扫 `a2_chem_pes`，B3 是字段；`list_engines` 能报五包；Aer 无 `twin_id`；超 shots / 改 CAL / Codex 调 TwinRun 被拒 | 自研 UI、qchem 全开、真 TwinRun、attended Codex、IBM Runtime |
| **P1 能签收** | 上表 + E05–E06、E10–E13、E17–E18、E21 | 黄金路径出 `twin_id`；docs 命中 `mode/shots/circuit.body`；沙箱调 TwinRun 失败；Codex 改文件先出现审批 | 自动真机、标定、bypass、两套工具名 |
| **P2 能换路由** | + E14 | 同一 `ionstack_compile_estimate` 换后端仍过 E12 | 新 schema |
| **P3 能给客户** | 全量经 UI | 同一 tool name | 嵌 ChatGPT Codex Web |

---

## 5. P0 / P1 演示剧本

### P0（WP2+WP3 完成后就能演）

1. 「现在接了哪些引擎？」→ `qagent_list_engines` 含 qdata / qchem / ionstack / route / qiskit。  
2. 「跑 `a2_chem_pes`，量子赢了吗？」→ `asset_id` + `b3.verdict` ∈ 三枚举。  
3. 「把这条电路用 Aer 跑 1000 shots，这就是我们的 twin。」→ Aer 返回 `provenance=aer`，**没有** `twin_id`；若模型硬写同一 twin，政策 deny。  
4. 「改一下 CAL。」→ 无此工具。  
5. 「shots 一千万去上机。」→ ask，不执行。

### P1（黄金路径）

1. `qchem_run` `minimal_vqe` → `asset_id`。  
2. `qagent_pin_circuit` → `circuit_id`。  
3. 可选 `qiskit_export_circuit` / `qiskit_aer_run`。  
4. `ionstack_compile_estimate` → `makespan_ns`，无 `ok`。  
5. `ionstack_twin_run` 1000 shots → **ask** → `twin_id`。  
6. `qdata_dequant_gate` → `b3.verdict`。  
7. 再 fork 用 Aer：新结果不得复制该 `twin_id`。

---

## 6. 每包的填法（避免做错）

| 包 | 填的时候 | 完成定义 |
|----|----------|----------|
| qdata | 先改 `qdata-mcp` 再让插件调用；不要在插件里再动态 `import` 任意 recipe | E01–E04、E09 绿 |
| qchem | 只包 CLI `qchem-run` / `qchem-export-parity` | E21 能出 `circuit_id` |
| ionstack | 只打 `GET /v1/twin/identity`、`POST /v1/twin/run`；estimate 先 MapQccd | E05、E12；响应无 CAL |
| route | **禁止**注册第二个工具名 | E14 工具名仍是 `ionstack_compile_estimate` |
| qiskit | 只 wrap `ionstack.interop`；Aer 输出 `additionalProperties: false` | E19 无 `twin_id` |

加第四、第五家软件：`qagent/contracts/engines/HOW_TO_ADD.md`，不改 agent。

---

## 7. 建议日程（组内一人主笔 + 一人科学守门）

按工作日、可压缩。日期从开工日算。

| 周 | 包 | 结束标准 |
|----|----|----------|
| 第 1 周 | WP0 + WP1 | profile 能开；E07/E08/E16/E20 绿 |
| 第 2 周 | WP2 | E01–E04、E09 绿；dsh-web 能跑 a2 |
| 第 3 周 | WP3 + WP4 | E15、E19 绿；**P0 演示** |
| 第 4–5 周 | WP6 | E05、E06、E12 绿 |
| 第 6 周 | WP7 + WP8 | E21、E13、E17 绿；**P1 演示** |
| 其后 | WP9 / WP10 | 按 IR 是否冻、是否要客户壳 |

---

## 8. 风险（只列会挡工期的）

| 风险 | 对策 | 落在 |
|------|------|------|
| dsh preview、格式 v0 | pin revision；资产不放 session | WP0 |
| qdata `mkdtemp` / 全文 get_job | WP2 必须改上游，不能只改插件 | WP2 |
| TwinRun 环境没配好 | P0 不拦；P1 WP6 单独验收 REST | WP6 |
| 有人把 Aer 当签收 | schema 禁 `twin_id` + E19 | WP3 |
| 官方 Codex 无人值守 | TwinRun 永不注册给它 | WP0、WP8 |
| 线路优化 IR 未冻 | WP6 用 ionstack 实现；WP9 只换后端 | WP6、WP9 |

---

## 9. 当前进度

**WP0–WP10 已落地。** 评测 E01–E21 绿。空槽为 0。2026-08-26 起人入口是工作台 `scripts/start_ui.sh`（`:3080`）；dsh 退到 `scripts/start_runtime.sh`（`:3081`）。

| 包 | 状态 |
|----|------|
| WP0 / WP1 | pin + profile + `dsh --profile qagent` web；`decide()` / `list_engines` / `pin_circuit` |
| WP2 | qdata-mcp 已硬化：`data_dir` 必填、recipe allowlist、截断 `get_job`、B3 工具。Qagent 端口走同一合同 |
| WP3 | `wrappers/interop.py` 包 `ionstack.interop`；Aer 无 `twin_id` |
| WP4 | ELN + 实验室 Skill |
| WP6 | TwinRun REST（`QAGENT_TWIN_URL` / `scripts/start_twin.sh`）；未批准 = ask |
| WP7 | `qchem-run` 本机 CLI；docs；沙箱黑名单 |
| WP8 | 卡片 + attended 审批合同 + write-provider Skill |
| WP9 | `QAGENT_ROUTE_BACKEND` 换后端不换名；`scripts/ci_eval.sh` |
| WP10 | dsh-web 换幺正量子皮（`qagent-brand` 占官方 brand slot）；主页面仍是 agent；知识库/云平台为预留包 |

Qagent `src/` **仍然不 import** qdata / ionstack / qchem / qiskit。接线用 REST / CLI / `wrappers/`（围栏外）。

```bash
cd qagent
PYTHONPATH=src python tests/run_tests.py
PYTHONPATH=src python -m qagent.entrypoints.eval_cli
PYTHONPATH=src python -m qagent.entrypoints.shell_cli --eval
bash scripts/start_ui.sh
# optional: bash scripts/start_runtime.sh
```
