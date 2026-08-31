# 1000 人天执行账

| 字段 | 内容 |
|------|------|
| 真源计划 | [qagent_1000d_plan.md](../qagent_1000d_plan.md) |
| 日历日 | 2026-08-27 |
| 计划周 | **周 1 完成，周 2–4 关键路径推进中** |
| 禁止 | 扩 `services/agent.py` 当产品循环；假 `twin_id`；训权重 |

人天是编制账。本账只记已经落地的交付。一次对话做不完 1000 人天。并行认领见 [PARALLEL.md](PARALLEL.md)。

## 已落地

| 任务 | 计划天 | 状态 |
|------|--------|------|
| H-01a 探活 dsh RPC | 8 | 完成 |
| H-01b 适配器 + qagent preset | 10 | 完成 |
| H-01c `/api/chat` 代理 + history 折气泡 | 10 | 完成 |
| H-01d 批准进同一 session | 8 | 完成 · 离线 `allowed-once` 走 `/api/respond`。426 后 WS peek 已挂；活 mux 空帧仍无 `rpcId`，未 invent `accepted:true` |
| H-01e 工具卡 / 短轮询 | 8 | 完成 |
| H-01f / H-02a / H-02b chat 不走 `_loop` | 6+20 | 完成（`agent.turn` 不再被产品测试调用） |
| H-03a/b 模型池字段 + dsh.env | 部分 | `llm_pool` + `DEEPSEEK_MODEL` |
| H-03c/d 换模型下一句生效 | 20 | 完成 · `apply_env` 写 `DEEPSEEK_MODEL`；GET 无密钥。活切换 **未打**（`H-03d_live.md`） |
| H-03e 下一句模型 | — | 完成 · `workplace_status` 带公开 `next_model`。不宣称活切换 |
| H-04a/b 知识库约定 + 空库诚实 | 部分 | `qagent/knowledge/` · `docs.py` 不再盲回手册 |
| H-04c 短摘录合同 | 10 | 完成 · ≤400 字、路径、不出网、最多 8 条 |
| A-01 qdata 死 URL 诚实 | 部分 | 完成 · HTTP 不通失败；无 CLI 仍本地卡。活 CLI/` :8787` **未打**（`A-01_live.md`） |
| A-02 qchem 诚实 | 部分 | 完成 · 无 bin 本地卡；死路径不冒充 CLI。活 skip 笔记仍在 `A-02_live.md` |
| A-04 route 合同 | 30 | 完成 · 换后端仍名 `ionstack_compile_estimate`，无 `ok` |
| A-05 资产目录 | 30 | 完成 · `qdata_list_assets` 短列表，无 Pauli 全文。活目录 **未打**（`A-05_live.md`） |
| A-05b reserved 透传 | — | 完成 · invoke / workplace 带回 `reserved_engines`。pennylane 不在 ids。不算接线 |
| A-05c company reserved | — | 完成 · `GET /api/company` 带回 `reserved_engines`。pennylane 不在 engines。不算接线 |
| A-03a Twin 探活 | 8 | 诚实不通 |
| A-03c Twin 续跑同电路 | 18 | 完成 · 换 `circuit.body` 拒绝；死 URL 无假 `twin_id`。活 skip 笔记仍在 `A-03_live.md` |
| L1-01a/b/c Skill + 规则 | 部分 | write-provider / qchem-scenario / 五份 Skill 文案 / Cursor 规则 |
| L1-01d 夹具 provider | 8 | 完成 · `tests/fixtures/eval_stub_provider.py` |
| L1-02 Codex attended | 40 | 完成 · 不落盘 SPI；无 HTTP app-server 则 `needs_app_server` |
| L1-02d E13 诚实 | 6 | 完成 · E13 认 `needs_app_server`；未接线不再假 `tests_green` |
| L1-02 app-server | — | 笔记落地 · HTTP 未接线。**不算** Codex 真接线已通 |
| L1-03 Cirq 加包 | 40 | 完成 · reserved 不进 `list_engines`；E22 empty。未接线禁止 import cirq |
| L1-03-wire Cirq | — | 完成 · Cirq 进 `engines[]` 且 wired。`provenance=cirq`，无 `twin_id`，无 `import cirq`。E22 allow。不加 E23 |
| L1-03 加包说明 | — | 完成 · Cirq 已是 wired 范例；再加包仍先 reserved。不算接线 Pennylane |
| L1-03-pl Pennylane reserved | — | 完成 · pennylane 只在 `reserved_engines`。不进 `engines[]`。无 `import pennylane`。不加 E23。**不算**已接线 |
| I-face 目录行 | — | 完成 · `qagent_list_engines` 行写 Pennylane reserved、不在 ids。不算接线 |
| L1-03 接线计划 | — | 笔记落地 · 先放宽五包断言才能接线。**不算** Cirq 已接线 |
| L1-03-relax 五包锁 | — | 完成 · `list_engines()` 五包打头、允许变长。`run_tests.py` `test_engines` / `test_company_shell` 已同步。Cirq 仍 reserved。**不算**已接线 |
| L1-03-relax2 余锁 | — | 完成 · `test_invoke` / `test_c03` / `test_l104` 改为五包打头。Cirq 仍 reserved。**不算**已接线 |
| L1-04 算法验收夹具 | 30 | 完成 · `benchmark_v1.json` 冻五包字段；`missing_pack_tests` 无单测则 fail。未改 CI yml |
| Q-01 30 条 JSON + 接线 | 部分 | 30/30 可离线跑。Q-h06 pin→ask→换 body 拒签，无假 `twin_id`。**不算** G3 |
| Q-02a 对打入口 | 14 | 完成 · `tests/run_qagent_vs_codex.py`；Codex 列为 stub，未调官方 |
| Q-02b CI job | 14 | 完成 · `qagent-eval.yml`：E 全量 + Q 对打 |
| R-01 文案 | 部分 | Skill「默认建议，不是唯一入口」 |
| R-01b dsh Skill 注册 | 12 | 完成 · `skill-visibility.json`；algo 无 twin-run |
| R-03a/b 签收 iff twin | 26 | 完成 · `kind=qagent/receipt` · `schema=qagent.receipt/v1` |
| R-03c 未签收脸 | 12 | 完成 · 3080 只有 `signed` 画绿封条 |
| I-01c 在办 | 14 | 完成 · 3080 在办只画 `needs_ask` |
| I-01e 预检不回 identity | — | 完成 · `GET …/preflight` 无 `identity`。checks 三布尔。不算 G2 |
| I-01f 交办 GET 瘦身 | — | 完成 · GET list / id 只回脸字段。无 columns / circuit。不算 G2 |
| I-01g mutation 瘦身 | — | 完成 · POST create/run/approve/reject/cancel/fork 回 `face_payload()`。脸无 `tenant_id` |
| I-01h invoke/vibe HTTP 瘦 | — | 完成 · HTTP 无 payload / steps。内部 `run_vibe_path()` 仍全文 |
| I-01i 脸短 reason | — | 完成 · rejected/failed 带 `reason` ∈ {cancelled, rejected, failed}。无 `error` 原文 |
| I-01j chat HTTP 不回 session | — | 完成 · POST `/api/chat` 与 GET status 无 `session_id`。`turn()` 内部仍可有 |
| I-01k eval HTTP 上门 | — | 完成 · POST `/api/eval` 无 token 403。成功只回 `id` / `ok` / `passed` |
| I-01l reset HTTP 上门 | — | 完成 · POST `/api/agent/reset` 无 token 403。`reset_chat()` 仍可直接调 |
| I-01m workplace PUT 上门 | — | 完成 · PUT `/api/workplace` 无 token 403。GET 仍开门、不回密钥 |
| H-02e HTTP 不再 import agent | — | 完成 · `shell_http.py` 无 `services.agent`。reset 只 `reset_chat()` |
| H-02f agent.turn 拒绝当产品 | — | 完成 · `turn()` 抛错，指去 `chat.turn`。`_loop` 仍在源码 |
| H-03f homes 进 dsh.env | — | 完成 · save 后 `dsh.env` 有 HOME / 知识库路径。云 URL 与超算密钥不进 |
| H-03g start_runtime 读 workplace homes | — | 完成 · 冷启动空 HOME 从 `workplace.json` 补。已有 env 不覆盖 |
| H-03h start_ui 读 homes | — | 完成 · 空 HOME 从 dsh.env / workplace 补。不读 secrets / 云 URL |
| I-03j cards 不泄 twin | — | 完成 · `GET /api/cards` 无 `twin_id` / body / 密钥 |
| I-03k ELN GET 不泄 twin | — | 完成 · GET `/api/eln` 先 `drop_twin`。盘上签收仍可留 `twin_id` |
| C-01k 脸吃 reason | — | 完成 · inbox/回执画待批准/已取消/已拒绝/失败。不算 G2 |
| C-01l ELN 中文种类 | — | 完成 · ELN 行画配方钉住/估计/签收/B3/交办/未认领。不算 G2 |
| C-01m 在办 HTTP 批准 | — | 完成 · 在办「批准上机」走交办 HTTP。气泡仍 `send("批准")`。回执先画 signed。不算 G0/G2 |
| A-05i 活 HTTP 目录 | — | 完成 · 设 `QAGENT_QDATA_URL` 时 `qdata_list_assets` 打 `GET /v1/assets`。死 URL 诚实失败。≤20。无 Pauli / `twin_id`。不算 G0 |
| C-02h 空租户清回组内 | — | 完成 · 空 `?tenant=` 清 `QAGENT_SHELL_TENANT`。回执原文核验，脸上 `ok`。不算 G0/G2 |
| I-01n 脸带估计 | — | 完成 · `face_payload()` 带 `makespan_ns`。HTTP `asg_08372d9b8409` = 3040。无 `columns` / `twin_id`。不算 G0/G1 |
| C-01n 在办画估计 | — | 完成 · 在办读 `row.makespan_ns` 画「估计 · N ns」。`063c7411` 见 3040。气泡仍 `send("批准")`。不算 G0/G1 |
| I-01o 脸带 B3 | — | 完成 · `face_payload()` 带 `b3_verdict`。`asg_b281b611c8f6` = inconclusive。无 `columns` / `b3` 对象。不算 G0/G1 |
| I-03l ELN 取尾 | — | 完成 · `GET /api/eln` 最多 20 条最新。盘上仍全文。不改 `short_payload()`。不算 G0/G2 |
| C-01o 回执画 B3 | — | 完成 · 回执 `b611c8f6` 画「B3 · 尚无定论」。在办/ELN 取尾 8。气泡仍 `send("批准")`。不算 G0/G1 |
| I-01p 脸带 Aer | — | 完成 · `face_payload()` 带 `aer_provenance`。`asg_b281b611c8f6` = aer。不写 `qccd-twin`。不算 G0/G1 |
| C-01p 回执画 Aer | — | 完成 · 回执 `b611c8f6` 画「Aer · 不是孪生签收」。气泡仍 `send("批准")`。不算 G0/G1 |
| I-02d 远程作业头 | — | 完成 · 非 loopback 才带 Bearer。`:8765` / `:8787` 不加。status 无密钥。不算 G0 |
| C-01q 脸画句柄 | — | 完成 · 在办 `7295f98a` 画「线路 · circ_9eb71f044598」「资产 · asset_1264418f2be9」。回执同样画。气泡仍 `send("批准")`。不算 G0/G1 |
| I-03m 交办 fork 复制 ELN | — | 完成 · `assignment.fork` 复制 ELN 且丢 `twin_id`。活 `asg_b281b611c8f6` → `asg_2c75aa13001c` draft。不算 G0 |
| C-01r 回执再走一遍 | — | 完成 · `b611c8f6` 「再走一遍」后对话写「不会带走 twin_id」。气泡仍 `send("批准")`。不算 G0/G1 |
| I-03n invoke 写 ELN 带交办 | — | 完成 · 未批准 `asg_70aea5323481` 有 estimate。批准 `asg_1782987fc2cd` 有 twin_signoff / b3。fork 无 `twin_id`。不算 G0 |
| I-03o ELN 脸画估计/B3 | — | 完成 · ELN 画「估计 · 3040 ns」「B3 · 尚无定论」。不画 `twin_id`。不算 G0/G1 |
| I-03p ELN 脸画实打 | — | 完成 · ELN 签收 `1808d26e` 画「实打 · 8 发」。不画 `twin_id`。不算 G0/G1 |
| I-03q ELN 压交办行 | — | 完成 · 无过滤 GET 每个交办只留最新 assignment。帽仍 20。带 id 不压。不算 G0/G1 |
| I-03r 交办 ELN 句柄 | — | 完成 · assignment 事件带 `circuit_id` / `asset_id`，无 `twin_id`。脸画「线路 ·」「资产 ·」。不算 G0/G1 |
| I-01q 回执实打 | — | 完成 · 已签收 `face_payload()` 带 `shots_actual`。HTTP `asg_8ea0d70e17f9` = 8。回执画「实打 · 8 发」。封条不加。不算 G0/G1 |
| C-01u 设置保存诚实 | — | 完成 · 无 token 保存不再假装已保存。只填模型名会提示还要接口地址。不算 G0 |
| C-01v 展开组内模型栏 | — | 完成 · 未就绪打开设置展开 `staff-pack`。客户不展开。不算 G0 |
| H-01g dsh-tools 去重 | — | 完成 · profile `dsh-tools` 链到宿主。活 `0d634946` `list_engines` 有 `tool/result`。不算 G0 |
| H-01h 产品默认 lab | — | 完成 · `start_runtime` 默认 lab。活 `4122615b` `qdata_run_recipe(a2_chem_pes)` → `asset_fc9f7d82f5d4`。无 `qagent-policy`。不算 G0 |
| H-01i dsh 不注册 sandbox | — | 完成 · 活 `e5dcc262` 无 sandbox 调用。`pin` + `twin_run` ask，脸有 `rpc_id`。E11 仍走 invoke。不算 G0 |
| H-01j 活批准 allowed-once | — | 完成 · 产品「批准」后 `approval/decided` `allowed-once`。TwinRun `{}` → `S-TWIN-02`。无假 `twin_id`。不算 G0 |
| H-01k TwinRun 认 circuit_id | — | 完成 · `_circuit()` 认 pin。dsh 必填 `mode`/`shots`/`circuit_id`。invoke 与产品 `b70510e6` 均真 `twin_id=5c9ce47c…e071a5`。产品 `circuit_id` 写成配方名，走回退线路。不算 G0 |
| H-01l H₂ UCCSD 电路图 | — | 完成 · `uccsd_pauli` pin 4 比特；3080 画 SVG；无 body 不回退 H+CX。无假 `twin_id`。不算 G0 |
| H-01m 专用 Agent 不写死 | — | 完成 · 提示不再默认 UCCSD；新一轮不带回旧电路图。`uccsd_pauli` 仍可走。无假 `twin_id`。不算 G0 |
| C-01w 商业脸 | — | 完成 · Markdown 排版；`GET .../program` 下载 QASM 不进模型；`POST /api/circuits` 收下客户线路；脸上不念 `circ_`/`asset_`/`twin_` 随机码。不算 G0 |
| C-01x 本任务轨 | — | 完成 · 侧栏只画本任务；HTTP 抹句柄/内部名；已画线路不被后到薄导出换掉。不算 G0 |
| C-01y 商业脸 | — | 完成 · 仪器风布局；欢迎入口；新对话。不算 G0 |
| C-01z 公式渲染 | — | 完成 · 本地 KaTeX；聊天气泡画公式。不算 G0 |
| C-01aa 控制台脸 | — | 完成 · 连线硬化；离子阱控制台视觉。不算 G0 |
| C-01ab 科学纸正文 | — | 完成 · 只动 `app.css`：栏宽 72ch、书板表（表头去金）、公式留白、电路图随纸配图注、代码等宽。结构不动。不算 G0 |
| C-01ac 许可单 | — | 完成 · 批准块包 `section.permit`；`button.act` 默认墨色，金只在许可单/在办批准钮；估计字段到了才画，不编。气泡仍 `send("批准")`。不算 G0 |
| C-01ad 轮次与故障条 | — | 完成 · 只动 `app.css`：用户轮次保留对话位置微调；故障条加「故障」标签；reduced-motion 停脉冲锁进测。不算 G0 |
| C-01af 商业工艺 | — | 完成 · 只动 `app.css`：焦点单一边框；`@media print` 白纸藏轨/命令条/顶钮；空状态两条入口锁进测。不算 G0 |
| C-01ae 对话列表 | — | 完成 · 探查：snapshot 只折最后一轮，不假装回看。journal 边车（staff 文件仍 `{sessionId}`）+ `GET /api/chat/sessions` 只读 + 右轨「对话」列（当前/已清）。无 switch 无新写路径。不算 G0 |
| C-01 客户面文案 | 50 | 完成 · 平常话交办；模型收进组内设置 |
| I-02 密钥不进模型 | 30 | 完成 · GET / prompt 无密钥值；远程 job HTTP 才带头 |
| I-03 ELN fork/replay | 30 | 完成 · 五类事件；fork 丢 `twin_id` |
| C-02 租户与回执 | 40 | 完成 · 空租户见全部；A 不见 B；回执可带 `tenant_id`，无电路 body / 密钥 |
| C-03 可选云 | 30 | 完成 · `cloud_url` → `QAGENT_CLOUD_URL`（不进 dsh.env）；IBM 有无 URL 都 deny；死 URL 诚实 |
| O-01a pin 复查 | 6 | 完成 · 四方冻住 dsh `0.1.0-rc.8` / Codex `0.147.0`。偏离必须红，禁止静默升级 |
| O-01b 安全冻住 | 8 | 完成 · 空 host 不再当 loopback；`0.0.0.0` 要 token；GET 无密钥键 |
| R-01d Skill 不绕 ask | 8 | 完成 · 六份 Skill 写明不能绕过 ask；lab TwinRun 仍 ask |
| R-01e Skill 对齐 | — | 完成 · 删「现在都是 reserved」。Cirq wired；Pennylane reserved。不算接线 |
| R-02 灵活选工具 | 40 | 完成 · 未知工具 deny；只估计不上机；`rails.md` 资产优先。persona 仍 `[]` |
| H-04d 知识命中 | 10 | 完成 · `knowledge/manuals` 命中 TwinRun 字段；空库诚实 |
| H-04e 更多手册 | — | 完成 · list_engines / makespan_ns / 回执可命中。未铸 twin_id |
| Q-02c 诚实门槛 | 12 | 完成 · 假 twin / 跳过 ask / CAL 全红。未改 CI yml |
| O-01c 手册 | 6 | 完成 · `docs/handbooks/internal.md` + `customer.md` |
| O-01d 客户角色 | — | 完成 · `customer.md` 写明 `?role=customer`。**不算** G2 |
| O-01e start_ui 客户 URL | — | 完成 · 第二行 `role=customer`。仍 loopback。**不算** G2 |
| O-01f 组内手册 ELN | — | 完成 · 值班本写只读 GET / 未就绪开设置；客户本不看实验流水。无第四 `*_id`。**不算** G2 |
| O-01g 租户手册 | — | 完成 · 空租户见全部且不带头；客户脸 `?tenant=`。无第四 `*_id`。**不算** G2 |
| O-01h start_ui 租户 | — | 完成 · 客户脸后再打 `?tenant=cust-a` 示例。仍 loopback。**不算** G2 |
| O-01i 对话分租户手册 | — | 完成 · 已设租户各一条对话；客户不见对方正在说的话。无第四 `*_id`。**不算** G2 |
| I-03e ELN 脸 | — | 完成 · 3080 回执下只读画 `GET /api/eln`。无 POST / 密钥 / 电路正文 / 假 twin_id。**不算** G2 |
| I-03f ELN 租户 | — | 完成 · 空租户见全部；已设租户只见本租户交办事件。无交办号对客户不可见。无 POST / 假 twin_id |
| H-04f ELN 手册 | — | 完成 · `eln` / `recipe_pin` / `GET /api/eln` 命中 `manuals/eln.md`。不铸 twin_id |
| H-04g 租户手册 | — | 完成 · `租户` / `隔离` / `?tenant=` 命中 `manuals/tenant.md`。不铸 twin_id |
| C-01f 剧本对齐 | — | 完成 · G0 未就绪自动开设置；G2 脸上去下载/核验。**不算**过门 |
| C-02d 租户脸 | — | 完成 · `?tenant=` 写入 `QAGENT_SHELL_TENANT`；有值才带 `X-QAGENT-TENANT`。空租户不带头。**不算** G2 |
| C-02e 双客户剧本 | — | 完成 · G2 两位客户写 `?tenant=`。仍不算过门 |
| C-02f 对话分租户 | — | 完成 · 空租户仍写 `dsh-session.json`；已设租户旁路 `by_tenant`。批准不新开 session。不铸 twin_id |
| C-02g 对话隔离剧本 | — | 完成 · G2 两位客户「对话分开，不共用一条 session / 气泡」。**不算**过门 |
| H-01e-settings 未就绪开设置 | — | 完成 · `turn()` / `_out()` 带 `open_settings`；未就绪才 `true`。`pending_approval` 只抄 snapshot。不造 session / twin_id |
| C-01e G0/G2 脸 | — | 完成 · 未就绪打开设置；已签收回执可下载/核验。**不算** G0/G2 过门 |
| I-03d ELN GET | — | 完成 · `GET /api/eln` 只读 `{events}`；`assignment_id` 过滤；无密钥 / circuit body / twin_id。无 POST 追加 |
| G0 演示剧本 | — | 清单落地 · `G0_demo.md`。**不算**正式过门 |
| G1 演示剧本 | — | 清单落地 · `G1_demo.md`。**不算**正式过门 |
| G1e Cirq 剧本 | — | 完成 · 「哪些包」五包打头；Cirq 已在 `engines[]`，`kind=interop`，`provenance=cirq`。不算 G1 过门 |
| G1f Pennylane 不在目录 | — | 完成 · 不要把 Pennylane 写进 `engines[]` 或说成已接线。不算 G1 |
| G2e Cirq 客户剧本 | — | 完成 · Aer / IBM / 本地卡 / Cirq 都不许冒充。不算 G2 过门 |
| G3e Cirq 评测 | — | 完成 · 硬轨来源含 Cirq ≠ `qccd-twin`。Codex 仍 stub。不算 G3 |
| H-04h Cirq 手册 | — | 完成 · 问 Cirq / interop / `provenance=cirq` 命中 `manuals/cirq.md` |
| I-03g ELN 原因 | — | 完成 · ELN 行 textContent 画约 40 字 reason；映射 `claim_blocked`。不算 G2 |
| I-03h ELN reason HTTP | — | 完成 · `GET /api/eln` 回 `claim_blocked` 且带 `reason`。无 POST。不算 G2 |
| I-03i ELN 六类 | — | 完成 · `ELN_EVENT_KINDS` 五类之后加 `qagent/claim_blocked`。fork 仍丢 twin_id |
| H-04i ELN 拒铸 | — | 完成 · 问 claim_blocked / cirq_claim_twin_id 命中 `eln.md` |
| H-04j Pennylane 知识条 | — | 完成 · 问 Pennylane / reserved 命中 `manuals/pennylane.md`。不算接线 |
| H-04k 哪些包手册 | — | 完成 · 「哪些包」仍命中；Pennylane reserved、不在目录。≤400 字。不算接线 |
| L1-04c Cirq 门 | — | 完成 · CI 笔记跟 `list_engines()`。Cirq 已接线。不算 G3 |
| O-01k Cirq 手册 | — | 完成 · 组内：Cirq 已在目录且互通。客户：别人的模拟器不是我们的机器签收 |
| O-01p ELN 拒铸手册 | — | 完成 · 值班本：claim_blocked 短 reason。客户：实验记录是组内的 |
| O-01q Pennylane 手册 | — | 完成 · Pennylane 已 reserved，不在目录。不算接线 |
| C-01g 欢迎包 kind | — | 完成 · 欢迎 `.packs` 与设置同画 `label · kind · status`。不算 G2 |
| C-01h 设置画 reserved | — | 完成 · 设置 `#reserved-list` 另画未接线。欢迎仍只画 `engines`。不算接线 / G2 |
| C-01i 预检只画 checks | — | 完成 · 预检画 Twin / 线路 / 资产。不读 identity。不算 G2 |
| C-01j 脸不读 columns | — | 完成 · 在办只读 assignment_id / status / ask_tool / handles。不算 G2 |
| G3 评测清单 | — | 清单落地 · `G3_eval.md`。**不算** G3 过门 |
| I-01d 无障碍 | — | 完成 · `#stage`/`#composer`/`#send` 写 `aria-busy`；设置里 Enter 不抢发送 |
| Q-02 对打报告 | — | 完成 · `Q-02_vs_codex.md`：30/30；Q-h06=ok。Codex 列 stub。**不算** G3 |
| Q-h06 离线硬轨 | — | 完成 · pin → ask → 换 body 拒签。无假 `twin_id`。对照表不再 skip。不算 G3 |
| C-01c G2 剧本 | — | 清单落地 · `G2_demo.md`。**不算** G2 过门 |
| H-01d-ws mux | — | 完成 · GET 426 不当成功；短读 WS 帧才抽已出现的 `rpcId`。空 mux 回 `None` |
| H-01d-orphan | — | 完成 · history 无 pending 仍可抽 mux 已有 `rpcId`；空 mux 不编 |
| H-01d 活批准证据 | — | 笔记落地 · create 通；未见 `rpcId`，未 POST respond。**不算**活批准过门 |
| L1-04c CI | 8 | 完成 · `qagent-eval.yml` 第三步 `missing_pack_tests`。两句 q02b 仍在。**不算** G3 |
| C-01d 客户密钥 | 10 | 完成 · `?role=customer` 藏 `#secret-fieldset`；员工设置仍留 id |
| A-01 活探 | — | 笔记落地 · `:8787` 不通。**不算**活 qdata 已通 |
| A-01e start_qdata 读 homes | — | 完成 · 空 HOME 从 dsh.env / workplace 补。不算活 qdata 已通 |
| A-01g 活 qdata 打通 | — | 完成 · `invoke(qdata_run_recipe)` `source=qdata-cli` + `asset_id`。不算 G0 |
| A-01h 活 qdata HTTP | — | 完成 · `:8787` + `invoke(qdata_submit_job)` 有 `job_id`。无 `twin_id`。不算 G0 |
| A-02g 活 qchem 打通 | — | 完成 · 混日志抽出 JSON。`invoke(qchem_run)` `source=qchem-cli` + `asset_id`。不算 G0 |
| A-03g 活 Twin 打通 | — | 完成 · pipeline TwinRun 真 `twin_id` + `qccd-twin`。identity 无 `twin_id`。不算 G0。signoff 仍要 CAL |
| A-03h E05 用 pipeline | — | 完成 · `_twin_args` 默认 `pipeline`。活 `run_eval(E05)` 出 `twin_id`。不算 G0/G3 |
| A-03i vibe_path pipeline | — | 完成 · `run_vibe_path` 默认 `pipeline`。活批准出 `twin_id` + `qccd-twin`。未批准仍 ask。不算 G0/G1 |
| R-03g 活回执 | — | 完成 · 交办 ask / `_run_sign` 默认 `pipeline`。活 create→run→approve 回执 `signed=true` + 真 `twin_id`。不算 G0/G2 |
| R-03h HTTP 回执 | — | 完成 · 3080 create→run→approve 回执 `signed=true` + 真 `twin_id`。无 token 403。不算 G0/G2 |
| H-03j 空 llm 不冲 DEEPSEEK | — | 完成 · `write_dsh_env` 空 llm 留下已有 `DEEPSEEK_*`。云/密钥不进。不算 G0 |
| A-03f start_twin 读 homes | — | 完成 · 空 IONSTACK HOME 从 dsh.env / workplace 补。不算活 Twin 已通 |
| G-01 治理包 | — | 完成 · `boot` / `qagent-minimal` / 后验证人 / doctor / handoff v1 / E28–E32。E23 不加。不算第三套 loop。活 Twin / `:8787` 仍要本机服务 |
| G-02 可诊断性 | — | 完成 · 错误目录 / 四灯 / preset 只读面 / 钉住与导出契约。不改工具名。invoke HTTP 仍瘦。不算 G0 |

`qagent/tests/run_tests.py` 全绿。

## 活探活

- `session.create` + `agentPreset=qagent` 通。
- Twin `:8765` 已通。pipeline TwinRun 出真 `twin_id` + `qccd-twin`。identity 不回 `twin_id`。signoff 仍要 CAL。**不算** G0 / G1。
- 黄金路径 `run_vibe_path(approved=True)` 与交办 `approve()` 已走 pipeline，活回执 `signed=true`（A-03i / R-03g）。3080 HTTP 批准同样签收（R-03h）。**不算** G1 / G2。
- qdata CLI `invoke` 已通（A-01g）。`:8787` + `qdata_submit_job` 已通（A-01h）。`qdata_list_assets` 活 `GET /v1/assets` 已通（A-05i）。**不算** G0。
- 3080/3081 端口通。health 四条 true（H-03i）。`GET /api/workplace` 已 `ready=true`（`https://api.deepseek.com/v1` + `deepseek-v4-flash`）。**不算** G0 过门。
- 空 `?tenant=` 清回组内；脸上原文核验已签收回执写 `ok`（C-02h）。**不算** G2。
- 交办脸 / 在办待批画出 `makespan_ns`（I-01n / C-01n）。HTTP `asg_aa1c063c7411` 短号 `063c7411` 画「估计 · 3040 ns」。**不算** G1。
- 已签收脸 / 回执画出 `b3_verdict`（I-01o / C-01o）。`b611c8f6` 画「B3 · 尚无定论」。ELN HTTP 取尾 20（I-03l）。**不算** G1。
- 已签收脸 / 回执画出 `aer_provenance=aer`（I-01p / C-01p）。`b611c8f6` 画「Aer · 不是孪生签收」。**不算** G1。
- 远程作业 HTTP 才带 Bearer（I-02d）。本机 Twin / qdata 不加。**不算** G0。
- 在办/回执画出 `circuit_id` / `asset_id`（C-01q）。`7295f98a` 画「线路 · circ_9eb71f044598」。**不算** G1。
- G0 剧本已往前：session `session-e5dcc262-d9f6-492b-a0c8-c65321f2a42c` 产品「批准」后 `approval/decided` `allowed-once`。`ionstack_twin_run` `{}` 回 `S-TWIN-02`。H-01k 后 invoke `circuit_id`+`pipeline` 出真 `twin_id=5c9ce47cda91d673598ba1283fed4e5ab4c1c17d2c770245ecab2534e3e071a5`。无假 `twin_id`。**不算** G0 过门。
- 活批准：create + 无害 prompt 通；mux 空，未见 `rpcId`，未 invent `accepted:true`。
- 活换模型：3081 `host.describe` 仍是 `deepseek-v4-flash`。**不算**活切换已通。

## 下一件（继续不间断时从这里接）

1. 第七十六波已回收。C-01aa：连线硬化 + 离子阱控制台脸。不算 G0。
2. 下一把真刀：人走完签收（真 `circuit_id` 上机或记全的诚实失败）。不要假 `twin_id`。不要再改设置文案。
3. 空 mux 不许编 `accepted:true`。signoff 仍要 CAL；CAL 不进工具。
4. L1-02 真接线要官方 app-server。M-01 仍等 G3。不要用死 `:9` 写活 `dsh.env`。

## 未开始（不要假装做过）

A-01g–A-01k / A-02g–A-02i / A-04g / A-05g–A-05i / A-06g–A-06i 已通。A-03g/h/i pipeline TwinRun 已通（黄金路径 + E05）。R-03g/h 活交办回执已通（服务层 + 3080 HTTP）。C-01m 在办按钮走 HTTP 批准。C-02h 空租户可清回组内，脸上原文核验 `ok`。I-01n / C-01n 待批在办能看见估计 ns。I-01o / C-01o 已签收能看见 B3。I-01p / C-01p 已签收能看见 Aer 不是孪生签收。I-03l ELN 脸取尾。I-02d 远程作业 HTTP 带 Bearer。C-01q 在办/回执能看见 `circuit_id` / `asset_id`。I-03m / C-01r 已签收可 fork 再走、不带走 `twin_id`。I-03n 交办 run 的估计/签收 ELN 带 `assignment_id`。I-03o ELN 脸能看见估计 ns / B3。I-03p ELN 签收能看见实打发数。I-03q 无过滤 ELN 压重复交办行。I-03r 交办 ELN 带 `circuit_id` / `asset_id`。I-01q 已签收回执能看见实打发数。signoff 仍要 CAL。L1-02 Codex 真接线、M-01、G0–G4 正式演示。活 mux 批准 `accepted:true` 仍未证明。
