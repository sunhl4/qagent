# 1000 人天并行板

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-26 |
| 真源 | [qagent_1000d_plan.md](../qagent_1000d_plan.md) |
| 账本 | [PROGRESS.md](PROGRESS.md) |
| 本对话 | 调度。不独占实现文件。 |

一次对话做不完 1000 人天。本板把**现在就能并行**的包拆成互不抢文件的对话。同事另开对话时，先认领下表空行，再开工。

## 硬轨（所有对话共用）

- 不是重做 Cursor / Codex。第一层继续用它们造包；第二层脑是 `dsh --profile qagent`，脸是 3080。
- 句柄只有 `circuit_id` / `asset_id` / `twin_id`。只有 ionstack TwinRun 能发 `twin_id`。
- `qagent/src` 禁止 `import qdata` / `ionstack` / `qchem` / `qiskit`。
- 禁止扩 `services/agent.py` 当产品循环。`/api/chat` 只走 dsh session。
- 禁止假 `twin_id`、假 `status=done`、训权重。CAL / shuttle 永不进工具。
- 不要改 `qagent/tests/run_tests.py`（调度回收时再挂）。各对话写自己的 `tests/test_<包>.py`。
- 不要改 `docs/execution/PROGRESS.md`（调度写）。
- 不要 commit，除非人明确说 commit。

## 本波已派（2026-08-26 夜）

调度对话已同时拉开 7 路，文件锁互斥。交卷后本对话回收。

| 对话 | 包 | 只许改 | 完成线 |
|------|----|--------|--------|
| [H-01d 批准续跑](0f9b4a1e-4f5b-4491-919b-b1b9c36e38db) | H-01d | **完成** · 已挂 `run_tests.py` | `POST /api/respond` `allowed-once`；活 mux `rpcId` 还要打 3081 |
| [H-03 模型池](8134d8bd-7a14-48f4-8ed9-969e75748c1c) | H-03c/d | **完成** · 已挂 `run_tests.py` | 换默认模型写入 `DEEPSEEK_MODEL`；GET 永不回密钥 |
| [H-04 知识摘录](1c5d10c1-bb99-4474-91ab-96490198009a) | H-04c | **完成** · 已挂 `run_tests.py` | ≤400 字摘录 + 路径；不出网；空库诚实 |
| [A-01 qdata 诚实](fae13fc9-52b9-436d-81a3-38f725ed93f4) | A-01 | **完成** · 已挂 `run_tests.py` | 死 URL 失败；无 CLI 仍走本地卡 |
| [Q 对照入口](09ffd02f-0650-4c97-b86c-1c222bc776e1) | Q-01/Q-02 | **完成** · 已挂 `run_tests.py` | 29/30 可跑；Q-h06 skip `needs live`；Codex 列是 stub |
| [R-03 签收回执](78f1faef-55ea-4fdd-87ac-74858c936890) | R-03 | **完成** · 已挂 `run_tests.py` | `signed` iff `twin_id`+`qccd-twin`；取消/拒绝/重跑已签收均拒绝 |
| [L1-01d 夹具](bb5b9be9-f97d-40de-8a2c-7e9d620b04b5) | L1-01d | **完成** · `tests/fixtures/eval_stub_provider.py` · 已挂 `run_tests.py` | 夹具 `eval_stub`；无 `twin_id` / TwinRun |

第一波 7 路已回收。`tests/run_tests.py` 含 q01 全绿。

## 第二波已派（2026-08-26 夜）

| 对话 | 包 | 只许改 | 完成线 |
|------|----|--------|--------|
| [A-02 qchem](b6ec7df6-26da-4a8a-b3dc-c0d6f5d4c58f) | A-02 | **完成** · 已挂 `run_tests.py` | 无 bin 诚实本地卡；死 bin 不冒充 qchem-cli |
| [L1-02 Codex](aa278a7e-2fde-4aa8-aa0e-e0c22353ceb7) | L1-02 | **完成** · 已挂 `run_tests.py` | 不写 SPI；批准前无 diff。E13 仍吃 `tests_green` 键 |
| [A-04 route](e04d7a36-d1bc-41d2-8b76-832953257658) | A-04 | **完成** · 已挂 `run_tests.py` | 只有 `makespan_ns`，无 `ok` |
| [I-01c 在办](8b23c58c-2d31-4454-9944-d1d090e98539) | I-01c | **完成** · 已挂 `run_tests.py` | 在办列表；批准仍走 `send("批准")` |
| [R-01b Skill](69c8c9b6-1982-40a2-9beb-cb8a4d0523b3) | R-01b | **完成** · 已挂 `run_tests.py` | lab 见量子轨；algo 不见 Twin；preset 仍是 `[]` |
| [A-03c Twin](c8de5d67-23d7-47f3-a31c-8ef9d711ab35) | A-03c | **完成** · 已挂 `run_tests.py` | 换 body 拒绝；死 Twin 无假 id |

第二波 6 路已回收。总跑绿（含 r01b 已挂）。

## 第三波已派（2026-08-26 夜）

| 对话 | 包 | 只许改 | 完成线 |
|------|----|--------|--------|
| [C-01 客户文案](6774e687-d9c0-4926-b6e0-fbd2663c0cea) | C-01 | **完成** · 已挂 `run_tests.py` | 不强迫 recipe 名；模型不挡第一面 |
| [I-02 密钥](c4f4c762-4048-4e86-985c-f6d976f5c4de) | I-02 | **完成** · 已挂 `run_tests.py` | 密钥不进 status / dsh prompt |
| [A-05 目录](e8b287e2-615e-405b-bb52-be8d389924c9) | A-05 | **完成** · 已挂 `run_tests.py` | 最多 20 行；无 Pauli / twin_id |
| [Q-02b CI](ab7a370d-78a9-4581-b822-d1bdf73c251f) | Q-02b | **完成** · 已挂 `run_tests.py` | `.github/workflows/qagent-eval.yml` |
| [R-03c 未签收脸](5ff4c67f-4365-493d-ab4c-435af5364e56) | R-03c | **完成** · 已挂 `run_tests.py` | 只有 `signed` 用绿封条 |
| [L1-03 加包](96d189d9-738e-4700-8688-ac9fe73a8c21) | L1-03 | **完成** · 已挂 `run_tests.py` | Cirq `reserved`，不进五包列表；E22 empty |
| [C-02 租户](1ebccd5c-8d1b-4f3a-a5d9-05e7802789e3) | C-02 | **完成** · 已挂 `run_tests.py` | 空租户见全部；已设租户只见自己；回执无 body |
| [I-03 ELN](17c688cd-359c-4f7d-976c-f241f05a657c) | I-03 | **完成** · 已挂 `run_tests.py` | 五类事件可回放；fork 不带 twin |

第三波已回收。`test_c02` 已挂。

## 第四波已派（2026-08-26 夜）

| 对话 | 包 | 只许改 | 完成线 |
|------|----|--------|--------|
| [C-03 可选云](b3abf8e8-9922-4163-b470-837a216e1d32) | C-03 | **完成** · 已挂 `run_tests.py` | 云关诚实；`qiskit_ibm_run` 有无 URL 都 deny |
| [L1-04 夹具](43287379-8d92-4269-ac6a-284c766a181e) | L1-04 | **完成** · 已挂 `run_tests.py` | 五包字段冻住；无单测 = fail。未改 CI yml |

第四波已回收。

## 第五波已派（2026-08-26 夜）

| 对话 | 包 | 只许改 | 完成线 |
|------|----|--------|--------|
| [L1-02d E13 诚实](dad6a762-eba0-4c9f-82d8-13c5bd75319c) | L1-02d | **完成** · 已挂 `run_tests.py` | 无 app-server 则 `needs_app_server`，不许假 `tests_green` |

第五波已回收。

## 第六波已派（2026-08-27）

| 对话 | 包 | 只许改 | 完成线 |
|------|----|--------|--------|
| [R-02 灵活选工具](34c5c87f-f26e-45e6-8eb9-d04973030a6b) | R-02 | **完成** · 已挂 `run_tests.py` | 未知工具 deny；只估计不上机；persona 仍 `[]` |
| [R-01d Skill 不绕 ask](165a894e-4fc0-4f2f-b0ac-116459495521) | R-01d | **完成** · 已挂 `run_tests.py` | Skill 触发仍 ask |
| [Q-02c 诚实门槛](49f60293-7cf9-4872-8e6c-2eee0abe1859) | Q-02c | **完成** · 已挂 `run_tests.py` | 假 twin / 跳过 ask / CAL = 红。未改 CI yml |
| [O-01a pin](29411b7e-6455-4eca-b6b9-95123f7f0e14) | O-01a | **完成** · 已挂 `run_tests.py` | dsh 0.1.0-rc.8 · Codex 0.147.0 冻住，无书面升 pin |
| [O-01b 安全](936a2e00-7407-43d3-a72f-da493db9ab1d) | O-01b | **完成** · 已挂 `run_tests.py` | 空 host 不再当 loopback；token 门仍在 |
| [O-01c 手册](46c2a109-0ebc-4fd9-9170-9b31d40cc2fe) | O-01c | **完成** · 已挂 `run_tests.py` | 对内/对外各约 2 页 |
| [H-04d 知识命中](adfa7b62-eae2-4e61-99c3-59824a4964e2) | H-04d | **完成** · 已挂 `run_tests.py` | 手册关键词必中；空库诚实 |
| [H-01d 活 mux](d7483005-b746-4256-b18d-a8e2e723dfe1) | H-01d-live | **完成** · 已挂笔记断言；活探要 `QAGENT_LIVE_MUX=1` | 3081 create 通；mux GET 是 426 websocket，未见 rpcId |

第六波已回收。

## 第七波已派（2026-08-27）

| 对话 | 包 | 只许改 | 完成线 |
|------|----|--------|--------|
| [H-01d websocket mux](4bf93c5b-28ec-4bc9-995c-051f20fcd495) | H-01d-ws | **完成** · 已挂 `run_tests.py` | 426 后走 WS 帧拿 `rpcId`；不编造 accepted |
| [I-01d 无障碍](a488f485-3150-4b18-b5be-754943c636ab) | I-01d | **完成** · 已挂 `run_tests.py` | aria-busy；输入中快捷键不抢发送 |
| [G0 演示剧本](ed55f5c3-0d21-4bdb-9660-b012fc3cf91a) | G0-script | **完成** · 已挂 `run_tests.py` | 人填模型后「扫氢分子」清单。不算正式过门 |
| [Q-02 对打报告](47996166-a4f9-4526-a1ec-397dd622240f) | Q-02-report | **完成** · 已挂 `run_tests.py` | 30 条账；Codex 列仍是 stub |
| [C-01c G2 剧本](02de3445-ba38-42e5-a4f8-0baf5551d19b) | C-01c | **完成** · 已挂 `run_tests.py` | 两客户 / 回执 / IBM deny。不算 G2 通过 |

第七波已回收。

## 第八波已派（2026-08-27）

| 对话 | 包 | 只许改 | 完成线 |
|------|----|--------|--------|
| [H-01d 孤儿 peek](56f904af-2b1b-4502-8c71-be614192c7bc) | H-01d-orphan | **完成** · 已挂 `run_tests.py` | history 无 pending 仍可抽已出现的 mux `rpcId`；空 mux 不编 |
| [G1 演示剧本](c76c89d4-b443-48c0-ac1f-8e93ad3e0c1c) | G1-script | **完成** · 已挂 `run_tests.py` | list_engines / 先估计 / 诚实失败。不算正式过门 |
| [L1-04c CI](7d869c08-23f7-4113-83bf-9c002990dadd) | L1-04c | **完成** · 已挂 `run_tests.py` | 无单测 = CI 红。两句 q02b 命令必须仍在 |
| [C-01d 客户密钥](95495ce1-b012-46aa-8856-86932488e6d6) | C-01d | **完成** · 已挂 `run_tests.py` | `?role=customer` 不见密钥值；id 留给员工设置 |
| [H-01d 活批准证据](c400819b-1845-418f-9cb7-b19b5eedde35) | H-01d-approve-live | **完成** · 已挂笔记断言；活探要 `QAGENT_LIVE_MUX=1` | 无真 `rpcId` 不许写 `accepted:true` |

第八波已回收。

## 第九波已派（2026-08-27）

| 对话 | 包 | 只许改 | 完成线 |
|------|----|--------|--------|
| [G3 评测清单](f87b6b47-8a97-436f-8888-f4972f76e477) | G3-script | **完成** · 已挂 `run_tests.py` | 30 条怎么复跑。不算 G3 过门 |
| [H-04e 手册](7da81c01-69a8-4b8c-82fe-59497fb9639c) | H-04e | **完成** · 已挂 `run_tests.py` | list_engines / makespan 能命中。不删 twinrun_fields |
| [L1-03 接线计划](e3158cfc-5dcb-466a-a0c5-5d58203a81fe) | L1-03-plan | **完成** · 已挂 `run_tests.py` | 列出要先放宽的五包断言。Cirq 仍 reserved |
| [O-01d 客户手册](4b7e5f6a-45ae-45ca-9020-be0d71dd3826) | O-01d | **完成** · 已挂 `run_tests.py` | 写明 `?role=customer`。O-01c 仍绿 |
| [A-01 活探](e5ca5650-4fcc-4377-8f68-7ccd814a3bf6) | A-01-live | **完成** · 已挂笔记断言；活探要 `QAGENT_LIVE_QDATA=1` | 无 CLI 诚实 skip。不许假 `status=done` |

第九波已回收。

## 第十波已派（2026-08-27）

| 对话 | 包 | 只许改 | 完成线 |
|------|----|--------|--------|
| [A-02 活探](0f9d5db2-7ef3-4ac2-93ac-dc752ea31f37) | A-02-live | **完成** · 已挂笔记断言；活探要 `QAGENT_LIVE_QCHEM=1` | 无 `qchem-run` 诚实 skip。不许假 CLI |
| [A-03 活探](2c62b9a9-e8be-470f-b8c5-27797854076d) | A-03-live | **完成** · 已挂笔记断言；活探要 `QAGENT_LIVE_TWIN=1` | Twin `:8765` 不通则 skip。不铸 `twin_id` |
| [H-03d 活切换](72a1e0fb-4bb7-4134-acf6-cf2a30e8a6ce) | H-03d-live | **完成** · 已挂笔记断言；活探要 `QAGENT_LIVE_H03=1` | 未见 host.describe 换模型则未打 |
| [L1-02 app-server](948d9f1b-5317-480e-a5a3-b23932217ef3) | L1-02-live | **完成** · 已挂 `run_tests.py` | 未接线保持 `needs_app_server`。不假 `tests_green` |
| [A-05 活目录](44fd2a3f-32b9-4801-b82d-95e076044179) | A-05-live | **完成** · 已挂笔记断言；活探要 `QAGENT_LIVE_QDATA=1` | 活列表未打。无 Pauli / twin_id |

第十波已回收。不要再派「只笔记诚实 skip」空转。

## 第十一波已派（2026-08-27）

| 对话 | 包 | 只许改 | 完成线 |
|------|----|--------|--------|
| [C-01e G2 脸](a5427b8f-8666-40dc-9186-cb82d6a19ead) | C-01e | **完成** · 已挂 `run_tests.py` | 未就绪打开设置；已签收回执可下载/核验。不算 G2 |
| [chat 打开设置](a4d82fe4-57c0-47e6-9245-3b32d06c6a07) | H-01e-settings | **完成** · 已挂 `run_tests.py` | 未就绪 `open_settings:true`。不造 session |
| [I-03d ELN GET](522812b4-d558-4a79-b5d9-eced7ce3f8d3) | I-03d | **完成** · 已挂 `run_tests.py` | `GET /api/eln` 只读。无密钥 / twin_id |
| [start_ui 客户 URL](6100788c-0259-4471-9c0b-1f56ead87249) | O-01e | **完成** · 已挂 `run_tests.py` | 第二行 `role=customer`。仍 loopback |
| [H-03e 下一句模型](5e3f4662-c7f9-429f-be3e-e66e589258f6) | H-03e | **完成** · 已挂 `run_tests.py` | `next_model` = 公开模型名。无密钥 |

第十一波已回收。`QAGENT_DSH_MUX=0` 总跑绿（含 `c01e` / `h01e_settings` / `i03d`）。不算 G0/G2 过门。

## 第十二波已派（2026-08-27）

| 对话 | 包 | 只许改 | 完成线 |
|------|----|--------|--------|
| [I-03e ELN 脸](43ad8409-21b0-44ae-88ab-ca5c8250b8be) | I-03e | **完成** · 已挂 `run_tests.py` | 3080 只读画 `GET /api/eln`。无 POST / 密钥 / 假 twin_id。不算 G2 |
| [H-04f ELN 手册](5dc14375-c1da-413e-93d5-e85b4cc2f66e) | H-04f | **完成** · 已挂 `run_tests.py` | `eln` / `recipe_pin` 命中知识根。不铸 twin_id |
| [O-01f 组内手册](19b68cac-90c3-4efa-ac44-f1567299b06c) | O-01f | **完成** · 已挂 `run_tests.py` | 写明 ELN 只读 GET。手册里不要出现第四个 `*_id` |
| [C-01f 剧本对齐](95c97c42-9e89-4193-b7e0-15de52f395dd) | C-01f | **完成** · 已挂 `run_tests.py` | 未就绪开设置；已签收可下载/核验。仍不算过门 |

第十二波已回收。`QAGENT_DSH_MUX=0` 总跑绿（含 `i03e` / `h04f` / `o01f` / `c01f`）。不算 G0/G2 过门。

## 第十三波已派（2026-08-27）

| 对话 | 包 | 只许改 | 完成线 |
|------|----|--------|--------|
| [C-02d 租户脸](7a8aee40-9cfb-4a9b-9545-88d3dc7bf765) | C-02d | **完成** · 已挂 `run_tests.py` | `?tenant=` 进 `X-QAGENT-TENANT`。保持 I-03e / C-01e。不算 G2 |
| [I-03f ELN 租户](f8b28c89-7c0c-43c6-b596-a776e5c8d2f3) | I-03f | **完成** · 已挂 `run_tests.py` | 空租户见全部 ELN；已设租户只见本租户交办事件。无 POST |
| [O-01g 租户手册](783ac14e-2b97-4ab0-86c1-cfbb3ff56fb8) | O-01g | **完成** · 已挂 `run_tests.py` | 写明 `?tenant=` / 请求头。不要第四个 `*_id` |
| [C-02e 双客户剧本](312c9c3b-05c2-4128-bf00-6203c9a306bd) | C-02e | **完成** · 已挂 `run_tests.py` | 3080 用 `?tenant=` 走两位客户。仍不算过门 |

第十三波已回收。`QAGENT_DSH_MUX=0` 总跑绿（含 `c02d` / `i03f` / `o01g` / `c02e`）。不算 G0/G2 过门。

## 第十四波已派（2026-08-27）

| 对话 | 包 | 只许改 | 完成线 |
|------|----|--------|--------|
| [C-02f 对话分租户](4f6a4dee-2db9-46d8-aea4-b14746ba69fb) | C-02f | **完成** · 已挂 `run_tests.py` | 空租户仍用现有 session 文件；已设租户各一条 session。不造 twin_id |
| [O-01h start_ui 租户](d35622bd-2039-4ea9-a313-95a2635bdd5c) | O-01h | **完成** · 已挂 `run_tests.py` | 客户脸后再打一行 `?tenant=` 示例。仍 loopback。不算 G2 |
| [H-04g 租户手册](b14a8009-a459-436d-9946-e681c50f657c) | H-04g | **完成** · 已挂 `run_tests.py` | `租户` / `?tenant=` 命中知识根。不铸 twin_id |

第十四波已回收。`QAGENT_DSH_MUX=0` 总跑绿（含 `c02f` / `o01h` / `h04g`）。不算 G0/G2 过门。

## 第十五波已派（2026-08-27）

| 对话 | 包 | 只许改 | 完成线 |
|------|----|--------|--------|
| [L1-03-relax 五包锁](c95caeec-72ef-4743-94c6-a593523ad659) | L1-03-relax | **完成** · 已挂 `run_tests.py`；调度已放宽 `test_engines` / `test_company_shell` | 五包仍在；允许以后变长。Cirq 仍 reserved。不接线、不标 wired |
| [C-02g 对话隔离剧本](841e3079-b0fc-40a9-b856-4238664d4bfd) | C-02g | **完成** · 已挂 `run_tests.py` | 两位客户对话不共用。无第四 `*_id`。仍不算过门 |
| [O-01i 对话分租户手册](738f86b3-3c9e-467e-a581-a147319ef2b5) | O-01i | **完成** · 已挂 `run_tests.py` | 写明已设租户各一条对话。不要 `tenant_id` |

第十五波已回收。`QAGENT_DSH_MUX=0` 总跑绿（含 `l103_relax` / `c02g` / `o01i`）。Cirq 仍 reserved。**不算**已接线。

## 第十六波已派（2026-08-27）

| 对话 | 包 | 只许改 | 完成线 |
|------|----|--------|--------|
| [L1-03-relax2 余锁](eee1ed4c-769a-4a2a-8cf9-d92c57377f2a) | L1-03-relax2 | **完成** · 已挂 `run_tests.py` | 余下恰好五条改为五包打头。Cirq 仍 reserved。不接线 |

第十六波已回收。`QAGENT_DSH_MUX=0` 总跑绿（含 `l103_relax2`）。Cirq 仍 reserved。**不算**已接线。

## 第十七波已派（2026-08-27）

| 对话 | 包 | 只许改 | 完成线 |
|------|----|--------|--------|
| [L1-03-wire Cirq](20666baa-af9d-44e6-a245-b3447bf7e3a1) | L1-03-wire | **完成** · 已挂 `run_tests.py` | `list_engines` 含 cirq 且 wired。无 `import cirq`。provenance=`cirq`。不铸 twin_id。不加 E23 |

第十七波已回收。`QAGENT_DSH_MUX=0` 总跑绿（含 `l103_wire`）。Cirq 已接线。不算 G0/G2。

下一刀要人：按 `G0_demo.md` 填模型走「扫氢分子」；活 HOME 后再打 A-01–A-05；L1-02 要官方 app-server。不要再派 skip 笔记。M-01 仍等 G3。

## 第十八波已派（2026-08-27）

| 对话 | 包 | 只许改 | 完成线 |
|------|----|--------|--------|
| [G1e Cirq 剧本](14094410-f501-4447-8e4c-e7b7c5eaa0ca) | G1e | **完成** · 已挂 `run_tests.py` | 「哪些包」五包打头，Cirq 已接线且 interop。不算 G1 过门 |
| [O-01k Cirq 手册](317fc781-5a72-4420-884e-52226e7c5aea) | O-01k | **完成** · 已挂 `run_tests.py` | Cirq 已在目录、不是机器。无第四 `*_id` |
| [C-01g 欢迎包 kind](9904686e-0d91-4c7b-a022-5460fac88e9b) | C-01g | **完成** · 已挂 `run_tests.py` | 欢迎列表也画 `kind`。保持 C-01e / I-03e。不算 G2 |

第十八波已回收。`QAGENT_DSH_MUX=0` 总跑绿（含 `g1e` / `o01k` / `c01g`）。Cirq 产品面已对齐。不算 G0/G1/G2。

## 第十九波已派（2026-08-27）

| 对话 | 包 | 只许改 | 完成线 |
|------|----|--------|--------|
| [G2e Cirq 客户剧本](49bdcd8a-7f29-4637-a231-73c935af0054) | G2e | **完成** · 已挂 `run_tests.py` | 客户清单写明 Cirq 不是我们的机器、不铸 twin_id。保持 C-01c/f。不算 G2 |
| [G3e Cirq 评测](737787be-efa9-497e-8839-2c8f6f2b42cd) | G3e | **完成** · 已挂 `run_tests.py` | 硬轨来源含 Cirq ≠ `qccd-twin`。Codex 仍 stub。不算 G3 |
| [H-04h Cirq 手册](064b3b74-b061-4d6d-80bf-405af7f30a72) | H-04h | **完成** · 已挂 `run_tests.py` | 问 Cirq / interop / `provenance=cirq` 能命中。无 `import cirq`。无 `twin_id=` |
| [I-03g ELN 原因](66cb90f3-2b88-46a0-8453-48ded84a0dd1) | I-03g | **完成** · 已挂 `run_tests.py` | `paintEln` 用 textContent 画短 reason。保持 GET-only。不算 G2 |

第十九波已回收。`QAGENT_DSH_MUX=0` 总跑绿（含 `g2e` / `g3e` / `h04h` / `i03g`）。不算 G0/G2/G3。

## 第二十波已派（2026-08-27）

| 对话 | 包 | 只许改 | 完成线 |
|------|----|--------|--------|
| [H-04i ELN 拒铸](f18c85de-36a2-428f-a7d6-5e88705e4ac9) | H-04i | **完成** · 已挂 `run_tests.py` | 问 claim_blocked / cirq_claim_twin_id 能命中。保持 H-04f 锁句。≤400 字 |
| [I-03h ELN reason HTTP](667d26da-390d-40c4-acf8-d303b9a23858) | I-03h | **完成** · 已挂 `run_tests.py` | `GET /api/eln` 回 `claim_blocked` 且带 `reason`。无 POST。不算 G2 |
| [I-03i ELN 六类](560de39c-77e2-4cb8-8a6a-e7b3a4edf039) | I-03i | **完成** · 已挂 `run_tests.py` | `ELN_EVENT_KINDS` 含 `claim_blocked`。fork 仍丢 twin_id |
| [L1-04c Cirq 门](de396355-2bb6-4cda-ab2e-5a0b9452cb01) | L1-04c-align | **完成** · 已挂 `run_tests.py` | Cirq 已在 `list_engines()`，CI 跟目录走。不算 G3 |

第二十波已回收。`QAGENT_DSH_MUX=0` 总跑绿（含 `h04i` / `i03h` / `i03i` / `l104c_align`）。不算 G0/G2/G3。

## 第二十一波已派（2026-08-27）

| 对话 | 包 | 只许改 | 完成线 |
|------|----|--------|--------|
| [O-01p ELN 拒铸手册](b4e94b8c-f853-4195-8655-c2aeadaa3177) | O-01p | **完成** · 已挂 `run_tests.py` | 值班本写 ELN 拒铸短 reason。无第四 `*_id`。保持 o01c/f |
| [L1-03 Pennylane reserved](e37eedc2-ab37-4139-a911-b7ca7b49ca7a) | L1-03-pl | **完成** · 已挂 `run_tests.py` | pennylane 只在 `reserved_engines`。不进 `engines[]`。无 `import pennylane`。不铸 twin_id。不加 E23 |
| [L1-03 加包说明](319e09ad-254d-4186-be80-b7fddf6c69c1) | L1-03-how | **完成** · 已挂 `run_tests.py` | Cirq 已是 wired 范例；再加包仍先 reserved。不算接线 Pennylane |

第二十一波已回收。`QAGENT_DSH_MUX=0` 总跑绿（含 `o01p` / `l103_how` / `l103_pl`）。Pennylane 只 reserved。不算接线。不算 G0/G2。

## 第二十二波已派（2026-08-27）

| 对话 | 包 | 只许改 | 完成线 |
|------|----|--------|--------|
| [O-01q Pennylane 手册](2b5cf37c-5d7a-4c73-83d4-aa9562eb3452) | O-01q | **完成** · 已挂 `run_tests.py` | 值班本：Pennylane 已 reserved，不在目录。保持 Cirq 已接线。无第四 `*_id` |
| [H-04j Pennylane 知识条](6cb8dc65-f2f8-45d2-ae1d-d8270ce3837a) | H-04j | **完成** · 已挂 `run_tests.py` | 问 Pennylane / reserved 能命中。不在 `engines[]`。无 `import pennylane`。无 `twin_id=` |
| [G1f Pennylane 不在目录](f2b6fae7-1081-4270-a5f3-b3567ea50e9e) | G1f | **完成** · 已挂 `run_tests.py` | 「当场不要看见」：Pennylane 出现在 `engines[]` / 说成已接线。保持 G1e。不算 G1 |
| [I-face 目录行](5a075b77-3929-4638-837a-ef2e31773511) | I-face | **完成** · 已挂 `run_tests.py` | `list_engines` 行写 pennylane reserved、不在 ids。不算接线 |

第二十二波已回收。`QAGENT_DSH_MUX=0` 总跑绿（含 `h04j` / `iface_pl` / `o01q` / `g1f`）。Pennylane 只 reserved。不算接线。不算 G0/G1/G2。

## 第二十三波已派（2026-08-27）

`invoke("qagent_list_engines")` 合同写了 `reserved_engines`，实现没回。Skill 仍说「现在都是 reserved」。本波补透传和脸，**不接线** Pennylane。

| 对话 | 包 | 只许改 | 完成线 |
|------|----|--------|--------|
| [A-05b reserved 透传](d54f7c37-edc1-4744-b762-b08f22d10346) | A-05b | **完成** · 已挂 `run_tests.py` | `invoke` 与 `workplace_status` 带 `reserved_engines`（pennylane reserved）。pennylane 不在 `engines[]` / ids。无 `import pennylane`。不铸 `twin_id` |
| [C-01h 设置画 reserved](46ecd2ea-9cfb-4a11-81b6-dc96b4d8fd8c) | C-01h | **完成** · 已挂 `run_tests.py` | 设置另画 `#reserved-list`。欢迎仍只画 `status.engines`。pennylane 不进 `#engine-list`。保持 C-01g。不算 G2 |
| [R-01e Skill 对齐](45e37ca8-9380-4d91-bcca-98a2e980f55b) | R-01e | **完成** · 已挂 `run_tests.py` | 删「现在都是 reserved」。Cirq wired interop；Pennylane reserved。保持「默认建议」/ 不绕 ask。不算接线 |
| [H-04k 哪些包手册](7d8ab077-dbf6-46e6-b14d-3d13050514f8) | H-04k | **完成** · 已挂 `run_tests.py` | 「哪些包」仍命中。补 Pennylane reserved、不在目录。全文 ≤400 字。无 `twin_id=`。保持 h04e |

第二十三波已回收。`QAGENT_DSH_MUX=0` 总跑绿（含 `a05b` / `c01h` / `r01e` / `h04k`）。Pennylane 只 reserved。不算接线。不算 G0/G1/G2。

## 第二十四波已派（2026-08-27）

I-01c 写预检只回布尔、不回显 identity。实现 `preflight()` 仍带 `identity`。本波修这个，并补 company 面 reserved。**不接线** Pennylane。

| 对话 | 包 | 只许改 | 完成线 |
|------|----|--------|--------|
| [I-01e 预检不回 identity](96503f70-bb57-4214-a604-6d7a0ce7b2b5) | I-01e | **完成** · 已挂 `run_tests.py` | `GET …/preflight` 无 `identity` 键。`checks` 仍有布尔。无密钥 / `twin_id`。保持 I-01c 批准路径 |
| [C-01i 预检只画 checks](61c76cd1-227e-46cc-a0f5-671cc501d79c) | C-01i | **完成** · 已挂 `run_tests.py` | `paintPreflight` 只读 `checks`。可画 `has_asset`。不读 `identity`。保持 C-01h `#reserved-list`。不算 G2 |
| [A-05c company reserved](f39e28bd-67dd-419f-b0cd-81e10cebfe92) | A-05c | **完成** · 已挂 `run_tests.py` | `company_payload` / `GET /api/company` 带 `reserved_engines`。pennylane 不在 `engines` ids。不算接线 |

第二十四波已回收。`QAGENT_DSH_MUX=0` 总跑绿（含 `i01e` / `c01i` / `a05c`）。预检无 identity。不算接线。不算 G0/G2。

## 第二十五波已派（2026-08-27）

`GET /api/assignments` 与 `GET /{id}` 仍回 `to_dict()` 全量 `columns` / `ask.args.circuit`。回执已洗，列表没洗。本波瘦 GET，脸不读 columns。**不接线** Pennylane。

| 对话 | 包 | 只许改 | 完成线 |
|------|----|--------|--------|
| [I-01f 交办 GET 瘦身](f00da390-d657-4431-8b7c-6638a64176d3) | I-01f | **完成** · 已挂 `run_tests.py` | GET list / GET id 无 `columns` / circuit body / `identity` / counts。仍有 `assignment_id` / `status` / `ask_tool` / 三句柄。保持 C-02 租户隔离。preflight 仍无 identity |
| [C-01j 脸不读 columns](d8f36534-de11-42ea-a557-65dd05a55b0f) | C-01j | **完成** · 已挂 `run_tests.py` | inbox / 回执脸不读 `row.columns` / `ask.args`。保持 C-01i 预检与 C-01h reserved。不算 G2 |

第二十五波已回收。`QAGENT_DSH_MUX=0` 总跑绿（含 `i01f` / `c01j`）。GET 交办已瘦。不算接线。不算 G0/G2。

## 第二十六波已派（2026-08-27）

GET 已瘦。POST create/run/approve/cancel/fork 仍回 `to_dict()`。`GET /api/cards` 原样倒最后一条 ELN（可含 `twin_id`），脸不用它。**不接线** Pennylane。

| 对话 | 包 | 只许改 | 完成线 |
|------|----|--------|--------|
| [I-01g mutation 瘦身](362cf8f7-9506-403a-97d5-71a23aa6aabe) | I-01g | **完成** · 已挂 `run_tests.py` | POST create/run/approve/reject/cancel/fork 回 `face_payload()`。脸无 `tenant_id`。C-02 用 GET 证隔离。token 门保持 |
| [I-03j cards 不泄 twin](7ae24c74-c539-41a9-8315-13a92a7708cb) | I-03j | **完成** · 已挂 `run_tests.py` | `GET /api/cards` 只留 kind + type + 短 assignment_id + recipe/shots/verdict。无 `twin_id` / body / 密钥。ELN 未改 |

第二十六波已回收。`QAGENT_DSH_MUX=0` 总跑绿（含 `i01g` / `i03j`）。cancel 脸无 `error`；`workbench` 已对齐。不算接线。不算 G0/G2。

## 第二十七波已派（2026-08-27）

GET/POST 交办与 cards 已瘦。`POST /api/invoke` 仍回 `result.__dict__`（整份 payload）。`POST /api/vibe` 仍回黄金路径全 steps（含 circuit body）。脸不用这两条，持 token 的 HTTP 仍漏。**不接线** Pennylane。

| 对话 | 包 | 只许改 | 完成线 |
|------|----|--------|--------|
| [I-01h invoke/vibe HTTP 瘦](aacc2565-c49f-4001-8193-a403701aa8da) | I-01h | **完成** · 已挂 `run_tests.py` | POST invoke 只留 tool/decision/status（可选 slot_id）。POST vibe 只留 status/tool/summary + 三句柄。内部 `run_vibe_path` 仍全文。token 门保持 |
| [I-01i 脸短 reason](f0be2642-7f1e-4f2d-bb15-36915969cbf7) | I-01i | **完成** · 已挂 `run_tests.py` | rejected/failed 带 `reason` ∈ {cancelled, rejected, failed}。脸无 `error`。draft 无 reason。`test_i01f` / `i01g` / `c02` 仍绿 |

第二十七波已回收。`QAGENT_DSH_MUX=0` 总跑绿（含 `i01h` / `i01i`）。不算接线。不算 G0/G2。

## 第二十八波已派（2026-08-27）

I-01i 脸上已有短 `reason`，3080 还在画英文 `needs_ask` / 笼统「已停」。`/api/chat` 仍回 `session_id`，脸不用。**不接线** Pennylane。

| 对话 | 包 | 只许改 | 完成线 |
|------|----|--------|--------|
| [C-01k 脸吃 reason](ffdd8619-615a-4b4c-be18-c5d182ed791c) | C-01k | **完成** · 已挂 `run_tests.py` | inbox/回执用 `faceLabel` 吃 reason。已取消/已拒绝/失败/待批准。不读 columns。保持 `status=needs_ask` |
| [I-01j chat HTTP 不回 session](268cad6c-befb-4814-a452-61a330e5dad9) | I-01j | **完成** · 已挂 `run_tests.py` | POST `/api/chat` 与 GET `/api/chat/status` 无 `session_id`。`turn()` 内部仍可有。C-02 用 store 证隔离 |

第二十八波已回收。`QAGENT_DSH_MUX=0` 总跑绿（含 `c01k` / `i01j`）。`test_r03c` 已对齐「待批准」。不算接线。不算 G0/G2。

## 第二十九波已派（2026-08-27）

`GET /api/eln` 只 `short_payload`，签收事件仍可带盘上的 `twin_id`。脸不画 ELN twin，但 HTTP 仍漏。ELN 种类仍是英文内部名。**不接线** Pennylane。

| 对话 | 包 | 只许改 | 完成线 |
|------|----|--------|--------|
| [I-03k ELN GET 不泄 twin](d41e8f1d-d8bb-4d6e-b806-67394aeefe2e) | I-03k | **完成** · 已挂 `run_tests.py` | GET `/api/eln` 先 `drop_twin` 再 `short_payload`。盘上签收仍可带 `twin_id`。保持 recipe / params / reason |
| [C-01l ELN 中文种类](5bae5fbf-fc33-4bdd-9d5c-485ca2774da2) | C-01l | **完成** · 已挂 `run_tests.py` | ELN 行画配方钉住/估计/签收/B3/交办/未认领。`ELN_KIND_MAP` 键保持。不画 twin_id |

第二十九波已回收。`QAGENT_DSH_MUX=0` 总跑绿（含 `i03k` / `c01l`）。不算接线。不算 G0/G2。

## 第三十波已派（2026-08-27）

`POST /api/eval` 无 token 就会跑 E01–E21，其中 E05 内部 `approved=True` 调 TwinRun。脸不用这条。chat HTTP 仍回 `used_tools`，脸不读。**不接线** Pennylane。不要 skip 笔记。

| 对话 | 包 | 只许改 | 完成线 |
|------|----|--------|--------|
| [I-01k eval HTTP 上门](323be950-3cc8-4d16-80fd-82543f8aee24) | I-01k | **完成** · 已挂 `run_tests.py` | POST `/api/eval` 无 token 403。成功只回 `id` / `ok` / `passed`。chat HTTP 无 `used_tools`。`run_evals()` / `turn()` 内部仍全文 |

第三十波已回收。`QAGENT_DSH_MUX=0` 总跑绿（含 `i01k`）。不算接线。不算 G0/G2。

## 第三十一波已派（2026-08-27）

读面与 eval 已上门。`POST /api/agent/reset` 仍无 token，可清 session + `reset_agent()`。脸不用这条。**不接线** Pennylane。不要 skip 笔记。

| 对话 | 包 | 只许改 | 完成线 |
|------|----|--------|--------|
| [I-01l reset HTTP 上门](91e8287d-1664-4053-900e-29122b7fb61d) | I-01l | **完成** · 已挂 `run_tests.py` | POST `/api/agent/reset` 无 token 403。有 token 才清调用方租户。`reset_chat()` 服务层仍可直接调 |

第三十一波已回收。`QAGENT_DSH_MUX=0` 总跑绿（含 `i01l`）。不算接线。不算 G0/G2。

## 第三十二波已派（2026-08-27）

reset / eval / 批准已上门。`PUT /api/workplace` 仍无 token 就会把 `llm_api_key` / `hpc_secret` / `quantum_secret` 写入盘和 `dsh.env`。脸已带 token。`save_workplace()` 服务层仍可直接调。**不接线** Pennylane。不要 skip 笔记。

| 对话 | 包 | 只许改 | 完成线 |
|------|----|--------|--------|
| [I-01m workplace PUT 上门](fb310a97-7758-4a08-9086-ae2f0afaeff2) | I-01m | **完成** · 已挂 `run_tests.py` | PUT `/api/workplace` 无 token 403。GET 仍开门、不回密钥。`save_workplace()` 仍可直接调 |

第三十二波已回收。`QAGENT_DSH_MUX=0` 总跑绿（含 `i01l` / `i01m`）。不算接线。不算 G0/G2。

## 第三十三波已派（2026-08-27）

写密钥 / reset / eval 已上门。设置里的 home **只进 3080 进程 env**，`dsh.env` 仍只有 `DEEPSEEK_*`。`start_runtime.sh` source 的是 `dsh.env`，dsh 脑看不见 `qdata_home`。`POST /api/agent/reset` 仍 `import reset_agent`（第三 loop）。**不接线** Pennylane。不要 skip 笔记。不要编 `accepted:true`。

| 对话 | 包 | 只许改 | 完成线 |
|------|----|--------|--------|
| [H-03f homes 进 dsh.env](25500802-3802-4364-a173-9e492c84287d) | H-03f | **完成** · 已挂 `run_tests.py` | save 后 `dsh.env` 有 homes（有值才写）。`QAGENT_CLOUD_URL` / hpc/quantum secret 仍不进。`DEEPSEEK_*` 保持 |
| [H-02e HTTP 不再 import agent](0f7e9e63-9c37-4acb-a6da-3c62263bf5c2) | H-02e | **完成** · 已挂 `run_tests.py` | `shell_http.py` 无 `services.agent`。reset 只 `reset_chat()`。token 门保持 |

第三十三波已回收。`QAGENT_DSH_MUX=0` 总跑绿（含 `h02e` / `h03f`）。不算接线。不算 G0/G2。

## 第三十四波已派（2026-08-27）

H-03f 只在 **save** 后写 `dsh.env`。H-03f 之前填进 `workplace.json` 的 HOME，冷启动 `start_runtime.sh` 仍看不见。`invoke()` 禁止偷偷 `apply_env()`（会冲掉 A-01 的 env 隔离）。**不接线** Pennylane。不要 skip 笔记。不要编 `accepted:true`。

| 对话 | 包 | 只许改 | 完成线 |
|------|----|--------|--------|
| [H-03g start_runtime 读 workplace homes](b1f549a4-921e-4f1e-b4d3-25ad93fc03e2) | H-03g | **完成** · 已挂 `run_tests.py` | 空 HOME 从 `workplace.json` 补 export。已有 env 不覆盖。不读 secrets / 云 URL |

第三十四波已回收。`QAGENT_DSH_MUX=0` 总跑绿（含 `h03g`）。不算接线。不算 G0/G2。

## 第三十五波已派（2026-08-27）

homes 已进 `dsh.env`，`start_runtime.sh` 冷启动能补。`start_qdata.sh` / `start_twin.sh` 仍只认当时的环境变量，设置里填了 HOME 也起不来。**不接线**。不要 skip 笔记。不要编 `accepted:true`。不要假 `twin_id`。

| 对话 | 包 | 只许改 | 完成线 |
|------|----|--------|--------|
| [A-01e start_qdata 读 homes](dc27aad2-d694-40fa-a05b-f4c72aae35ae) | A-01e | **完成** · 已挂 `run_tests.py` | 空 `QAGENT_QDATA_HOME` 从 dsh.env / workplace 补。无 home 仍诚实失败。不算活 qdata 已通 |
| [A-03f start_twin 读 homes](b30676b7-5063-4356-a3a2-986b69dea2b5) | A-03f | **完成** · 已挂 `run_tests.py` | 空 `QAGENT_IONSTACK_HOME` 从 dsh.env / workplace 补。无 home 仍诚实失败。不算活 Twin 已通 |

第三十五波已回收。`QAGENT_DSH_MUX=0` 总跑绿（含 `a01e` / `a03f`）。不算接线。不算活 HOME。不算 G0/G2。

## 第三十六波已派（2026-08-27）

`agent.turn()` 仍能进 `_loop` 时产品测试已不调它。H-02f 让 `turn()` 一调就抛。**不接线**。不要 skip 笔记。不要编 `accepted:true`。

| 对话 | 包 | 只许改 | 完成线 |
|------|----|--------|--------|
| [H-02f agent.turn 拒绝当产品](5851f8d2-7e63-4343-913a-cc141b11c01c) | H-02f | **完成** · 已挂 `run_tests.py` | `turn()` 一调就抛。`reset_agent()` 仍可调。`def _loop` 仍在源码 |

第三十六波已回收。`QAGENT_DSH_MUX=0` 总跑绿（含 `h02f`）。不算接线。不算 G0/G2。

## 第三十七波已派（2026-08-27）

本机 HOME 已在场，不再派 skip 笔记。必须打到活 CLI/HTTP 输出。不许把 checkout 在场写成已通。**不接线** Pennylane。不要编 `accepted:true`。不要假 `twin_id`。不要写 workplace 密钥。不要改旧 `*_live.md` skip 合同。

本机路径（只读，不改核）：

- `QAGENT_QDATA_HOME=/Users/shl/nvidia/qdata`（`.venv/bin/qdata` 有 `run`）
- `QAGENT_QCHEM_HOME=/Users/shl/nvidia/qcchem-qml-md`（`.venv/bin/qchem-run`）
- `QAGENT_IONSTACK_HOME=/Users/shl/Q-software`（`.venv/bin/ionstack-serve` 在仓根，不在 `ionstack/` 子目录）

| 对话 | 包 | 只许改 | 完成线 |
|------|----|--------|--------|
| [A-01g 活 qdata 打通](4ed67ca5-b224-4817-8926-9c0a0700e997) | A-01g | **完成** · 已挂 `run_tests.py` | `invoke` `source=qdata-cli` + `asset_182483a482ba`。不算 G0 |
| [A-02g 活 qchem 打通](93a4631e-c384-4c8d-9730-bd109cf48615) | A-02g | **完成** · 已挂 `run_tests.py` | `_last_json_object` + timeout 180。`source=qchem-cli` + `asset_5f9f41afb311`。不算 G0 |
| [A-03g 活 Twin 打通](b5955420-0e18-4ffc-96cc-41a7d6a3bd39) | A-03g | **完成** · 已挂 `run_tests.py` | pipeline TwinRun `twin_id` + `qccd-twin`。identity 无 `twin_id`。不算 G0 |

第三十七波已回收。`QAGENT_DSH_MUX=0` 总跑绿（含 `a01g` / `a02g` / `a03g`）。不算接线。不算 G0/G2。

## 第三十八波已派（2026-08-27）

活 CLI / pipeline Twin 已通。`:8787` 未打。E05 评测仍用 `mode=signoff`（活 Twin 400 要 CAL）。3080 health：`twin_live=true`，`qdata_cli` / `qchem_live` 仍 false（脸进程没 HOME）。**不接线** Pennylane。不要 skip 笔记。不要编 `accepted:true`。CAL 不进工具。不要改旧 `*_live.md`。不要改 `test_q01.py`（Q-h06 skip 合同仍在）。

| 对话 | 包 | 只许改 | 完成线 |
|------|----|--------|--------|
| [A-01h 活 qdata HTTP](9851e5fa-d07a-4bf2-9d2b-92b49801be24) | A-01h | **完成** · 已挂 `run_tests.py` | `:8787` + `job_id=4ba3afa7fc97441ca8139e6a849da378`。无 `twin_id`。不算 G0 |
| [A-03h E05 用 pipeline](2117ad65-25a1-46bb-8888-a396b18fc163) | A-03h | **完成** · 已挂 `run_tests.py` | `_twin_args` 默认 `pipeline`。活 E05 `twin_id` + `qccd-twin`。不算 G0 |
| [H-03h start_ui 读 homes](bd1ad608-4e1b-476e-a59f-90e2d5ddf49b) | H-03h | **完成** · 已挂 `run_tests.py` | 空 HOME 从 dsh.env / workplace 补。不读 secrets / 云 URL |

第三十八波已回收。`QAGENT_DSH_MUX=0` 总跑绿（含 `a01h` / `e05g` / `h03h`）。不算接线。不算 G0/G2。

## 第三十九波已派（2026-08-27）

Q-h06 仍整条 `needs live` skip。换电路拒签 **A-03c 已能离线验**，不必再等活 Twin。`isolate_product_eval` 仍把 Twin URL 隔到 `:1`。**不接线** Pennylane。不要 skip 当绿。不要编 `accepted:true`。不要假 `twin_id`。不算 G3。

| 对话 | 包 | 只许改 | 完成线 |
|------|----|--------|--------|
| [Q-h06 离线硬轨](3fc0940b-ac6f-4921-bf40-4761a1bd6b4d) | Q-h06 | **完成** · 已挂 `run_tests.py` | pin → ask → 换 body 拒签。无假 `twin_id`。对照表 30/30。不算 G3 |

第三十九波已回收。`QAGENT_DSH_MUX=0` 总跑绿（含 `qh06`）。Q-01 30/30 离线可跑。不算接线。不算 G3。

## 第四十波已派（2026-08-27）

submit 已有 `job_id`。`get_job` 活 HTTP 未抄。活 `qdata_run_recipe` 之后 `list_assets` 未证同一 store 出现该卡。**不接线** Pennylane。不要 skip 当绿。不要写 `status=done`。不要假 `twin_id`。

| 对话 | 包 | 只许改 | 完成线 |
|------|----|--------|--------|
| [A-01i 活 get_job](f26e9aca-e193-4365-a4ff-af133c9276b4) | A-01i | **完成** · 已挂 `run_tests.py` | `job_id=8179cf73884f457ab50ac4e27c81536d`，`status=failed`（不是 `done`）。无 `twin_id`。不算 G0 |
| [A-05g 活目录含卡](0e356ea5-9b8c-477e-bf0b-7fadf0e01905) | A-05g | **完成** · 已挂 `run_tests.py` | `asset_id=asset_ffe79d915e4c` 出现在 `list_assets`。≤20。无 Pauli / twin_id。不算 G0 |

第四十波已回收。`QAGENT_DSH_MUX=0` 总跑绿（含 `a01i` / `a05g`）。不算接线。不算 G0/G2。

## 第四十一波已派（2026-08-27）

`get_run_record` 活 CLI 未抄。`compile_estimate` 活 interop 未证与公式 fallback 有别。**不接线** Pennylane。不要 skip 当绿。不要假 `twin_id`。不要写 `ok`。

| 对话 | 包 | 只许改 | 完成线 |
|------|----|--------|--------|
| [A-01j 活 get_run_record](a12cee90-8c6e-4b5b-8fde-c75bf2818ce1) | A-01j | **完成** · 已挂 `run_tests.py` | `asset_id=asset_d89d7c24c9a1` · `run_record_id=run_342966063a97`。无 `twin_id`。不算 G0 |
| [A-04g 活 interop 估计](1b6df162-cc67-4cb1-bac9-8b9136998416) | A-04g | **完成** · 已挂 `run_tests.py` | live `makespan_ns=3040.0` ≠ 公式 `4800.0`。无 `ok` / `twin_id`。不算 G0 |

第四十一波已回收。`QAGENT_DSH_MUX=0` 总跑绿（含 `a01j` / `a04g`）。不算接线。不算 G0/G2。

## 第四十二波已派（2026-08-27）

活 `qchem_run` 出 `asset_id` 但不落 store，`list_assets` 见不到。活 `run_recipe` 之后 `dequant_gate` 未抄。**不接线** Pennylane。不要 skip 当绿。不要假 `twin_id`。不要写 `quantum_wins`。

| 对话 | 包 | 只许改 | 完成线 |
|------|----|--------|--------|
| [A-02h 落 qchem 卡](385861c7-1fa8-4b59-938b-0e1b49ecd3b5) | A-02h | **完成** · 已挂 `run_tests.py` | `asset_id=asset_4a4e6d27bc79` 出现在 `list_assets`。≤20。无 Pauli / twin_id。不算 G0 |
| [A-01k 活 dequant](47515ab5-cbd2-4ccf-a0e2-6a6677b818ab) | A-01k | **完成** · 已挂 `run_tests.py` | `asset_id=asset_f45d6ae07f90`，`b3.verdict=inconclusive`。无 `twin_id`。不算 G0 |

第四十二波已回收。`QAGENT_DSH_MUX=0` 总跑绿（含 `a02h` / `a01k`）。不算接线。不算 G0/G2。

## 第四十三波已派（2026-08-27）

qchem 卡已能落 store，但 dequant 还没打这张卡。`qiskit_aer_run` 活 interop 未证。**不接线** Pennylane。不要 skip 当绿。不要假 `twin_id`。provenance 必须是 `aer`。

| 对话 | 包 | 只许改 | 完成线 |
|------|----|--------|--------|
| [A-02i qchem 后 dequant](16059471-e628-40ba-b0b7-67de3a818d99) | A-02i | **完成** · 已挂 `run_tests.py` | `asset_id=asset_8b00a737b406`，`b3.verdict=inconclusive`。无 `twin_id`。不算 G0 |
| [A-06g 活 Aer](d75503ef-d048-413d-85f4-b0ef803a8773) | A-06g | **完成** · 已挂 `run_tests.py` | `circuit_id=circ_48613db9e404`，`provenance=aer`，counts `{"11": 3, "00": 5}`。无 `twin_id`。不算 G0 |

第四十三波已回收。`QAGENT_DSH_MUX=0` 总跑绿（含 `a02i` / `a06g`）。不算接线。不算 G0/G2。

## 第四十四波已派（2026-08-27）

`qiskit_import` / `qiskit_export` 活 interop 未抄。**不接线** Pennylane。不要 skip 当绿。不要假 `twin_id`。provenance 不许 `qccd-twin`。

| 对话 | 包 | 只许改 | 完成线 |
|------|----|--------|--------|
| [A-06h 活 export](4c6a0240-bb8f-472a-b616-823facf0c8dc) | A-06h | **完成** · 已挂 `run_tests.py` | `circuit_id=circ_48613db9e404`，`qasm3` 对上 `call_interop("export")`。无 `twin_id`。不算 G0 |
| [A-06i 活 import](5075e851-9155-454b-94f0-7a2ca16690c4) | A-06i | **完成** · 已挂 `run_tests.py` | `circuit_id=circ_48613db9e404`，`n_qubits=2` 对上 `call_interop("import")`。无 `twin_id`。不算 G0 |

第四十四波已回收。`QAGENT_DSH_MUX=0` 总跑绿（含 `a06h` / `a06i`）。不算接线。不算 G0/G2。

活 invoke 主路径已抄完。下一把真刀是人走 G0、活 mux `accepted:true`、或 L1-02 官方 app-server。没有第二把就不要凑包。

## 第四十五波已派（2026-08-27）

3080 脸被 SIGTERM 杀掉后已拉起。workplace 只写了三条 HOME，无密钥。活 health：`twin_live` / `qdata_live` / `qchem_live` / `qdata_cli` 全 true。`ready` 仍 false。**不接线** Pennylane。不要 skip 当绿。不要写密钥。不算 G0。

| 对话 | 包 | 只许改 | 完成线 |
|------|----|--------|--------|
| [H-03i 脸 HOME health](346d97ae-a0d1-4584-b55b-f43d4ebe64ae) | H-03i | **完成** · 已挂 `run_tests.py` | health 四条 true。`ready` 仍 false。不算 G0 |

第四十五波已回收。`QAGENT_DSH_MUX=0` 总跑绿（含 `h03i`）。不算接线。不算 G0。

下一把真刀仍是人走 G0（填模型）、活 mux `accepted:true`、或 L1-02 官方 app-server。没有第二把就不要凑包。

## 第四十六波已派（2026-08-27）

目录 cap=20。recipe 5 + knowledge 最多 5，卡片预算 10。旧卡占满预算时，刚跑出的 `asset_id` 可能被挤掉。mux GET 仍是 426，不许编 `accepted:true`。**不接线** Pennylane。不要 skip 当绿。不要假 `twin_id`。

| 对话 | 包 | 只许改 | 完成线 |
|------|----|--------|--------|
| [A-05h 最新卡不被挤](fcdffbe6-9e42-4b7f-9f23-88da7f342a10) | A-05h | **完成** · 已挂 `run_tests.py` | `_card_rows` 取末尾。`asset_id=asset_77f2d9d5757a` 仍在列表。≤20。不算 G0 |

第四十六波已回收。`QAGENT_DSH_MUX=0` 总跑绿（含 `a05h`）。不算接线。不算 G0。

下一把真刀仍是人走 G0（填模型）、活 mux `accepted:true`、或 L1-02 官方 app-server。没有第二把就不要凑包。

## 第四十七波已派（2026-08-27）

E05 / 活 invoke 已走 pipeline。黄金路径 `run_vibe_path` 与交办 ask / `_run_sign` 仍写 `mode=signoff`，活 Twin 400 要 CAL。G1 批准后续跑、G2 交办签收都打在这两处。本波只改 mode，**不把 CAL 塞进工具**。**不接线** Pennylane。不要 skip 当绿。不要编 `accepted:true`。不要假 `twin_id`。不算 G0/G1/G2。

| 对话 | 包 | 只许改 | 完成线 |
|------|----|--------|--------|
| [A-03i vibe_path pipeline](7917b60a-ce25-460d-a226-cf02c813deb8) | A-03i | **完成** · 已挂 `run_tests.py` | `run_vibe_path(approved=True)` 活 `twin_id` + `qccd-twin`。未批准仍 ask。不算 G1 |
| [R-03g 活回执](7917b60a-ce25-460d-a226-cf02c813deb8) | R-03g | **完成** · 已挂 `run_tests.py` | create→run→approve 后回执 `signed=true`，真 `twin_id` + `qccd-twin`。ask.mode=`pipeline`。不算 G2 |

第四十七波已回收。`QAGENT_DSH_MUX=0` 总跑绿（含 `a03i` / `r03g`）。不算接线。不算 G0/G1/G2。

下一把真刀仍是人走 G0（填模型）、活 mux `accepted:true`、或 L1-02 官方 app-server。没有第二把就不要凑包。

## 第四十八波已派（2026-08-27）

活 3080 仍跑着 R-03g 之前的进程时，HTTP `approve` 的 ask 还是 `mode=signoff`，Twin 400 要 CAL。空 llm 的 workplace `save()` 会整文件重写 `dsh.env`，冲掉已有 `DEEPSEEK_*`。本波修保留、重载脸、锁 HTTP 回执。**不接线** Pennylane。不要 skip 当绿。不要编 `accepted:true`。不要假 `twin_id`。不 `pkill dsh`。不算 G0/G2。

| 对话 | 包 | 只许改 | 完成线 |
|------|----|--------|--------|
| [H-03j 空 llm 不冲 DEEPSEEK](7917b60a-ce25-460d-a226-cf02c813deb8) | H-03j | **完成** · 已挂 `run_tests.py` | 空 llm save 留下 `DEEPSEEK_BASE_URL` / `DEEPSEEK_MODEL`。云/密钥不进。不算 G0 |
| [R-03h HTTP 回执](7917b60a-ce25-460d-a226-cf02c813deb8) | R-03h | **完成** · 已挂 `run_tests.py` | 3080 create→run→approve 回执 `signed=true` + 真 `twin_id`。无 token 403。不算 G2 |

第四十八波已回收。`QAGENT_DSH_MUX=0` 总跑绿（含 `h03j` / `r03h`）。不算接线。不算 G0/G2。

下一把真刀仍是人走 G0（填模型）、活 mux `accepted:true`、或 L1-02 官方 app-server。没有第二把就不要凑包。

## 第四十九波已派（2026-08-27）

在办「批准上机」仍 `send("批准")`，空 mux 没有 `rpcId`，点了签不出。HTTP `approve`（R-03h）已经能签。本波只把在办按钮接到交办 HTTP。对话气泡仍 `send("批准")`。**不接线** Pennylane。不要 skip 当绿。不要编 `accepted:true`。不要假 `twin_id`。不算 G0/G2。

| 对话 | 包 | 只许改 | 完成线 |
|------|----|--------|--------|
| [C-01m 在办 HTTP 批准](7917b60a-ce25-460d-a226-cf02c813deb8) | C-01m | **完成** · 已挂 `run_tests.py` | 在办 `assignmentAction(..., "approve")`。气泡仍 `send("批准")`。回执先画 signed。不算 G2 |

第四十九波已回收。`QAGENT_DSH_MUX=0` 总跑绿（含 `c01m`）。不算接线。不算 G0/G2。

下一把真刀仍是人走 G0（填模型）、活 mux `accepted:true`、或 L1-02 官方 app-server。没有第二把就不要凑包。

## 第五十波已派（2026-08-27）

`qdata_list_assets` 有 URL 仍只读本地 store，活 `:8787` `/v1/assets` 看不见。客户演示后 `?tenant=` 清不掉，组内仍带着旧租户头；脸上核验把 `3040.0` stringify 成 `3040`，哈希失败。本波只补这两刀。**不接线** Pennylane。不要 skip 当绿。不要编 `accepted:true`。不要假 `twin_id`。不算 G0/G2。

| 对话 | 包 | 只许改 | 完成线 |
|------|----|--------|--------|
| [A-05i 活 HTTP 目录](7917b60a-ce25-460d-a226-cf02c813deb8) | A-05i | **完成** · 已挂 `run_tests.py` | 设 URL 时 `GET /v1/assets` 进短目录。死 URL 失败。无 Pauli / `twin_id`。不算 G0 |
| [C-02h 空租户清回组内](7917b60a-ce25-460d-a226-cf02c813deb8) | C-02h | **完成** · 已挂 `run_tests.py` | 空 `?tenant=` 清头。回执原文核验 `ok`。气泡仍 `send("批准")`。不算 G2 |

第五十波已回收。`QAGENT_DSH_MUX=0` 总跑绿（含 `a05i` / `c02h`）。不算接线。不算 G0/G2。

下一把真刀仍是人走 G0（填模型）、活 mux `accepted:true`、或 L1-02 官方 app-server。没有第二把就不要凑包。

## 第五十一波已派（2026-08-27）

G1「先估计」闷在 `columns.makespan_ns`，`face_payload()` 不带，在办看不见。本波只把估计露到交办脸和在办行。**不接线** Pennylane。不要改 `canonical_json`。不要放宽 I-01h 给 `/api/vibe` 回 `makespan_ns`。不要 skip 当绿。不要编 `accepted:true`。不要假 `twin_id`。不算 G0/G1。

| 对话 | 包 | 只许改 | 完成线 |
|------|----|--------|--------|
| [I-01n 脸带估计](7917b60a-ce25-460d-a226-cf02c813deb8) | I-01n | **完成** · 已挂 `run_tests.py` | `face_payload()` 带 `makespan_ns`。不回 `columns` / identity。未批无 `twin_id`。不算 G1 |
| [C-01n 在办画估计](7917b60a-ce25-460d-a226-cf02c813deb8) | C-01n | **完成** · 已挂 `run_tests.py` | 在办读 `row.makespan_ns` 画「估计 · N ns」。不读 `columns`。气泡仍 `send("批准")`。不算 G1 |

第五十一波已回收。`QAGENT_DSH_MUX=0` 总跑绿（含 `i01n` / `c01n`）。不算接线。不算 G0/G1。

下一把真刀仍是人走 G0（填模型）、活 mux `accepted:true`、或 L1-02 官方 app-server。没有第二把就不要凑包。

## 第五十二波已派（2026-08-27）

G1 批准后 B3 闷在 `columns.b3`。ELN 盘上 8000+ 行，脸一次 GET 空窗。本波只把 B3 露到交办脸/回执，并把 ELN HTTP 与在办取尾。**不接线** Pennylane。不要改 `short_payload()`。不要 skip 当绿。不要编 `accepted:true`。不要假 `twin_id`。不算 G0/G1。

| 对话 | 包 | 只许改 | 完成线 |
|------|----|--------|--------|
| [I-01o 脸带 B3](7917b60a-ce25-460d-a226-cf02c813deb8) | I-01o | **完成** · 已挂 `run_tests.py` | `face_payload()` 带 `b3_verdict`。不回 `columns` / `b3` 对象。不算 G1 |
| [I-03l ELN 取尾](7917b60a-ce25-460d-a226-cf02c813deb8) | I-03l | **完成** · 已挂 `run_tests.py` | `GET /api/eln` 最多 20 条最新。不改 `short_payload()`。不算 G2 |
| [C-01o 回执画 B3](7917b60a-ce25-460d-a226-cf02c813deb8) | C-01o | **完成** · 已挂 `run_tests.py` | 回执读 `row.b3_verdict` 画「B3 · 尚无定论」。在办/ELN 取尾 8。气泡仍 `send("批准")`。不算 G1 |

第五十二波已回收。`QAGENT_DSH_MUX=0` 总跑绿（含 `i01o` / `i03l` / `c01o`）。不算接线。不算 G0/G1。

下一把真刀仍是人走 G0（填模型）、活 mux `accepted:true`、或 L1-02 官方 app-server。没有第二把就不要凑包。

## 第五十三波已派（2026-08-27）

G1「这是不是 Aer 签收的」闷在 `columns.aer_provenance`。本波只把外国模拟器来源露到交办脸和回执，并写明不是孪生签收。**不接线** Pennylane。不要把 `qccd-twin` 写成 aer。不要 skip 当绿。不要编 `accepted:true`。不要假 `twin_id`。不算 G0/G1。

| 对话 | 包 | 只许改 | 完成线 |
|------|----|--------|--------|
| [I-01p 脸带 Aer](7917b60a-ce25-460d-a226-cf02c813deb8) | I-01p | **完成** · 已挂 `run_tests.py` | `face_payload()` 带 `aer_provenance`。永不写 `qccd-twin`。不算 G1 |
| [C-01p 回执画 Aer](7917b60a-ce25-460d-a226-cf02c813deb8) | C-01p | **完成** · 已挂 `run_tests.py` | 回执读 `row.aer_provenance` 画「Aer · 不是孪生签收」。气泡仍 `send("批准")`。不算 G1 |

第五十三波已回收。`QAGENT_DSH_MUX=0` 总跑绿（含 `i01p` / `c01p`）。不算接线。不算 G0/G1。

下一把真刀仍是人走 G0（填模型）、活 mux `accepted:true`、或 L1-02 官方 app-server。没有第二把就不要凑包。

## 第五十四波已派（2026-08-27）

I-02b 的 `job_auth_headers()` 原先在，南向 HTTP 没用。本波只给非 loopback 作业 URL 带 Bearer。本机 Twin / qdata 不加。**不接线** Pennylane。不要把密钥写进 status / chat。不要 skip 当绿。不要编 `accepted:true`。不要假 `twin_id`。不算 G0。

| 对话 | 包 | 只许改 | 完成线 |
|------|----|--------|--------|
| [I-02d 远程作业头](7917b60a-ce25-460d-a226-cf02c813deb8) | I-02d | **完成** · 已挂 `run_tests.py` | `json_headers`：远程 Bearer，loopback 无 Authorization。活 Twin / qdata 仍通。不算 G0 |

第五十四波已回收。`QAGENT_DSH_MUX=0` 总跑绿（含 `i02d`）。不算接线。不算 G0。

下一把真刀仍是人走 G0（填模型）、活 mux `accepted:true`、或 L1-02 官方 app-server。没有第二把就不要凑包。

## 第五十五波已派（2026-08-27）

G1「先 pin」的 `circuit_id` 已在交办 `handles`，在办/回执没画。本波只把线路和资产句柄画到脸上。**不接线** Pennylane。不要读 `columns` / `ask.args`。不要 skip 当绿。不要编 `accepted:true`。不要假 `twin_id`。不算 G0/G1。

| 对话 | 包 | 只许改 | 完成线 |
|------|----|--------|--------|
| [C-01q 脸画句柄](7917b60a-ce25-460d-a226-cf02c813deb8) | C-01q | **完成** · 已挂 `run_tests.py` | 在办/回执读 `handles.circuit_id` / `asset_id` 画「线路 ·」「资产 ·」。气泡仍 `send("批准")`。不算 G1 |

第五十五波已回收。`QAGENT_DSH_MUX=0` 总跑绿（含 `c01q`）。不算接线。不算 G0/G1。

下一把真刀仍是人走 G0（填模型）、活 mux `accepted:true`、或 L1-02 官方 app-server。没有第二把就不要凑包。

## 第五十六波已派（2026-08-27）

交办 HTTP `fork` 原先只 `create()`，ELN replay 是空的。本波把 `copy_events_for_fork` 接到交办 fork，并在已签收回执加「再走一遍」。**不接线** Pennylane。不要把 `twin_id` 拷到新交办。不要 skip 当绿。不要编 `accepted:true`。不要假 `twin_id`。不算 G0/G1。

| 对话 | 包 | 只许改 | 完成线 |
|------|----|--------|--------|
| [I-03m 交办 fork 复制 ELN](7917b60a-ce25-460d-a226-cf02c813deb8) | I-03m | **完成** · 已挂 `run_tests.py` | `assignment.fork` 复制 ELN 且 `drop_twin`。记下 parent。新交办 draft。不算 G1 |
| [C-01r 回执再走一遍](7917b60a-ce25-460d-a226-cf02c813deb8) | C-01r | **完成** · 已挂 `run_tests.py` | 已签收「再走一遍」走 `assignmentAction(..., "fork")`。气泡仍 `send("批准")`。不算 G1 |

第五十六波已回收。`QAGENT_DSH_MUX=0` 总跑绿（含 `i03m` / `c01r`）。不算接线。不算 G0/G1。

下一把真刀仍是人走 G0（填模型）、活 mux `accepted:true`、或 L1-02 官方 app-server。没有第二把就不要凑包。

## 第五十七波已派（2026-08-27）

交办 run 写下的估计/签收 ELN 原先不带 `assignment_id`，`replay` 看不见，fork 拷不到。本波只让 invoke 带上交办 id。**不接线** Pennylane。不要 skip 当绿。不要编 `accepted:true`。不要假 `twin_id`。不算 G0/G1。

| 对话 | 包 | 只许改 | 完成线 |
|------|----|--------|--------|
| [I-03n invoke 写 ELN 带交办](7917b60a-ce25-460d-a226-cf02c813deb8) | I-03n | **完成** · 已挂 `run_tests.py` | 未批准有 estimate；批准有 twin_signoff / b3。fork 后无 `twin_id`。不算 G1 |

第五十七波已回收。`QAGENT_DSH_MUX=0` 总跑绿（含 `i03n`）。不算接线。不算 G0/G1。

下一把真刀仍是人走 G0（填模型）、活 mux `accepted:true`、或 L1-02 官方 app-server。没有第二把就不要凑包。

## 第五十八波已派（2026-08-27）

I-03n 已把估计/B3 写进 GET `/api/eln` 尾，脸原先只画种类和短号。本波只让 ELN 行读 `makespan_ns` / `verdict` 画出数字。**不接线** Pennylane。不要 skip 当绿。不要编 `accepted:true`。不要假 `twin_id`。不算 G0/G1。

| 对话 | 包 | 只许改 | 完成线 |
|------|----|--------|--------|
| [I-03o ELN 脸画估计/B3](7917b60a-ce25-460d-a226-cf02c813deb8) | I-03o | **完成** · 已挂 `run_tests.py` | ELN 画「估计 · 3040 ns」「B3 · 尚无定论」。不画 `twin_id`。不算 G1 |

第五十八波已回收。`QAGENT_DSH_MUX=0` 总跑绿（含 `i03o`）。不算接线。不算 G0/G1。

下一把真刀仍是人走 G0（填模型）、活 mux `accepted:true`、或 L1-02 官方 app-server。没有第二把就不要凑包。

## 第五十九波已派（2026-08-27）

I-03o 已画估计 / B3。GET `/api/eln` 签收行已有 `shots_actual`，脸原先不画。本波只让 ELN 行读出发数。**不接线** Pennylane。不要 skip 当绿。不要编 `accepted:true`。不要假 `twin_id`。不算 G0/G1。

| 对话 | 包 | 只许改 | 完成线 |
|------|----|--------|--------|
| [I-03p ELN 脸画实打](7917b60a-ce25-460d-a226-cf02c813deb8) | I-03p | **完成** · 已挂 `run_tests.py` | ELN 画「实打 · 8 发」。不画 `twin_id`。不算 G1 |

第五十九波已回收。`QAGENT_DSH_MUX=0` 总跑绿（含 `i03p`）。不算接线。不算 G0/G1。

下一把真刀仍是人走 G0（填模型）、活 mux `accepted:true`、或 L1-02 官方 app-server。没有第二把就不要凑包。

## 第六十波已派（2026-08-27）

总跑把交办状态写满 ELN 最近 20 条，签收/实打从无过滤 GET 里消失，`i03p` 活测红。本波只压重复 assignment 行。**不接线** Pennylane。不要 skip 当绿。不要编 `accepted:true`。不要假 `twin_id`。不算 G0/G1。

| 对话 | 包 | 只许改 | 完成线 |
|------|----|--------|--------|
| [I-03q ELN 压交办行](7917b60a-ce25-460d-a226-cf02c813deb8) | I-03q | **完成** · 已挂 `run_tests.py` | 无过滤 GET 每个交办只留最新 assignment。帽仍 20。带 id 的 GET 不压。不算 G1 |

第六十波已回收。`QAGENT_DSH_MUX=0` 总跑绿（含 `i03q`）。不算接线。不算 G0/G1。

下一把真刀仍是人走 G0（填模型）、活 mux `accepted:true`、或 L1-02 官方 app-server。没有第二把就不要凑包。

## 第六十一波已派（2026-08-27）

交办 ELN 原先只有 status / room，在办已能看见线路/资产。本波只把句柄写进 assignment 事件并让脸画出来。**不接线** Pennylane。不要 skip 当绿。不要编 `accepted:true`。不要假 `twin_id`。不算 G0/G1。

| 对话 | 包 | 只许改 | 完成线 |
|------|----|--------|--------|
| [I-03r 交办 ELN 句柄](7917b60a-ce25-460d-a226-cf02c813deb8) | I-03r | **完成** · 已挂 `run_tests.py` | assignment 事件带 `circuit_id` / `asset_id`，无 `twin_id`。脸画「线路 ·」「资产 ·」。不算 G1 |

第六十一波已回收。`QAGENT_DSH_MUX=0` 总跑绿（含 `i03r`）。不算接线。不算 G0/G1。

下一把真刀仍是人走 G0（填模型）、活 mux `accepted:true`、或 L1-02 官方 app-server。没有第二把就不要凑包。

## 第六十二波已派（2026-08-27）

ELN 已画实打，回执/在办 `face_payload()` 原先没有 `shots_actual`。本波只把 Twin 实打发数露到已签收脸上。**不接线** Pennylane。不要 skip 当绿。不要编 `accepted:true`。不要假 `twin_id`。不算 G0/G1。

| 对话 | 包 | 只许改 | 完成线 |
|------|----|--------|--------|
| [I-01q 回执实打](7917b60a-ce25-460d-a226-cf02c813deb8) | I-01q | **完成** · 已挂 `run_tests.py` | 已签收 GET 有 `shots_actual`。回执画「实打 · 8 发」。封条不加该字段。不算 G1 |

第六十二波已回收。`QAGENT_DSH_MUX=0` 总跑绿（含 `i01q`）。不算接线。不算 G0/G1。

下一把真刀仍是人走 G0（填模型）、活 mux `accepted:true`、或 L1-02 官方 app-server。没有第二把就不要凑包。

## 第六十三波已派（2026-08-27）

人只填模型名或没带 token 打开 3080 时，保存写不进盘，脸上却说已保存。本波只让保存诚实。**不接线** Pennylane。不要 skip 当绿。不要代填密钥。不算 G0。

| 对话 | 包 | 只许改 | 完成线 |
|------|----|--------|--------|
| [C-01u 设置保存诚实](7917b60a-ce25-460d-a226-cf02c813deb8) | C-01u | **完成** · 已挂 `run_tests.py` | 403 说要 `?token=`。只填模型名提示还要接口地址。不算 G0 |

第六十三波已回收。`QAGENT_DSH_MUX=0` 总跑绿（含 `c01u`）。不算接线。不算 G0。

下一把真刀仍是人走 G0（带 token 填地址 + 模型名 + API Key）、活 mux `accepted:true`、或 L1-02 官方 app-server。没有第二把就不要凑包。

## 第六十四波已派（2026-08-27）

组内模型栏原先折叠，人只看见密钥或只填模型名。本波只在未就绪时展开组内栏。**不接线** Pennylane。不要 skip 当绿。不要代填密钥。不算 G0。

| 对话 | 包 | 只许改 | 完成线 |
|------|----|--------|--------|
| [C-01v 展开组内模型栏](7917b60a-ce25-460d-a226-cf02c813deb8) | C-01v | **完成** · 已挂 `run_tests.py` | 未就绪展开 `staff-pack`。客户不展开。不算 G0 |

第六十四波已回收。`QAGENT_DSH_MUX=0` 总跑绿（含 `c01v`）。不算接线。不算 G0。

下一把真刀仍是人走 G0（带 token 填地址 + 模型名 + API Key）、活 mux `accepted:true`、或 L1-02 官方 app-server。没有第二把就不要凑包。

## 第六十五波已派（2026-08-27）

活 dsh 点 `qagent_list_engines` 时 `ctx.tools[TOOL_RUNTIME_SCHEDULER]` 对不上（profile 另有一份 `dsh-tools`）。本波只把 profile 那份链到宿主。**不接线** Pennylane。不要 skip 当绿。不要编 `accepted:true`。不要假 `twin_id`。不算 G0。

| 对话 | 包 | 只许改 | 完成线 |
|------|----|--------|--------|
| [H-01g dsh-tools 去重](7917b60a-ce25-460d-a226-cf02c813deb8) | H-01g | **完成** · 已挂 `run_tests.py` | profile `dsh-tools` realpath = 宿主。活 session `0d634946` `list_engines` 有 `tool/result`，无 `prepare` undefined。不算 G0 |

第六十五波已回收。`test_h01g` 已挂。`QAGENT_DSH_MUX=0` 总跑绿（含 `h01g`）。不算接线。不算 G0。

下一把真刀：3081 `start_runtime` 默认 `QAGENT_PRESET=algo`，lab 工具被政策挡。或活 mux `accepted:true`、L1-02 官方 app-server。没有第二把就不要凑包。

## 第六十六波已派（2026-08-27）

活 `active_preset` 被写成 `sign`，3081 启动默认仍是 `algo`，`qchem_run` / `qdata_run_recipe` 回 `qagent-policy`。本波只把产品脑默认改成 lab。**不接线** Pennylane。不要 skip 当绿。不要编 `accepted:true`。不要假 `twin_id`。不算 G0。

| 对话 | 包 | 只许改 | 完成线 |
|------|----|--------|--------|
| [H-01h 产品默认 lab](7917b60a-ce25-460d-a226-cf02c813deb8) | H-01h | **完成** · 已挂 `run_tests.py` | `start_runtime` `:-lab`。活 `4122615b` `qdata_run_recipe(a2_chem_pes)` 出 `asset_fc9f7d82f5d4`，无 `qagent-policy`。不算 G0 |

第六十六波已回收。`test_h01h` 已挂。`QAGENT_DSH_MUX=0` 总跑绿（含 `h01h`）。不算接线。不算 G0。

下一把真刀：人走完 G0（交办/待批/诚实失败）、活 mux `accepted:true`、或 L1-02 官方 app-server。模型在 `qdata_sandbox_exec` 空转不是本包。没有第二把就不要凑包。

## 第六十七波已派（2026-08-27）

H-01h 后模型在 `qdata_sandbox_exec` 里猜参数空转，不走 pin / 估计 / TwinRun ask。本波只让产品 dsh 不注册该工具。**不接线** Pennylane。不要 skip 当绿。不要编 `accepted:true`。不要假 `twin_id`。不算 G0。

| 对话 | 包 | 只许改 | 完成线 |
|------|----|--------|--------|
| [H-01i dsh 不注册 sandbox](7917b60a-ce25-460d-a226-cf02c813deb8) | H-01i | **完成** · 已挂 `run_tests.py` | 活 `e5dcc262` 无 sandbox 调用。`pin` + `twin_run` ask，`rpc_id` 已在脸。未代批。E11 仍走 invoke。不算 G0 |

第六十七波已回收。`test_h01i` 已挂。`h01i` 笔记 `rpc_id` 断言已放行。不算接线。不算 G0。

下一把真刀：人走完 G0（交办/待批/诚实失败）、活 mux `accepted:true`、或 L1-02 官方 app-server。没有第二把就不要凑包。

## 第六十八波已派（2026-08-27）

H-01i 后脸已有 mux `rpc_id`。本波只走产品「批准」回显该 id。**不接线** Pennylane。不要 skip 当绿。不要编未经 dsh 回的 `accepted:true`。不要假 `twin_id`。不算 G0。

| 对话 | 包 | 只许改 | 完成线 |
|------|----|--------|--------|
| [H-01j 活批准 allowed-once](7917b60a-ce25-460d-a226-cf02c813deb8) | H-01j | **完成** · 已挂 `run_tests.py` | session `e5dcc262` `approval/decided` `allowed-once`。TwinRun `{}` → `S-TWIN-02`。无假 `twin_id`。不算 G0 |

第六十八波已回收。`test_h01j` 已挂。不算接线。不算 G0。

下一把真刀：人走完签收（TwinRun 要带 circuit / pipeline）、或 L1-02 官方 app-server。没有第二把就不要凑包。

## 第六十九波已派（2026-08-27）

H-01j 后产品「批准」已 `allowed-once`，但 TwinRun 空参 `S-TWIN-02`。本波只让 `_circuit()` / dsh schema 认 pin 的 `circuit_id`。**不接线** Pennylane。不要 skip 当绿。不要假 `twin_id`。不算 G0。

| 对话 | 包 | 只许改 | 完成线 |
|------|----|--------|--------|
| [H-01k TwinRun 认 circuit_id](7917b60a-ce25-460d-a226-cf02c813deb8) | H-01k | **完成** · 已挂 `run_tests.py` | invoke 真 `twin_id=5c9ce47c…e071a5`。产品 `b70510e6` TwinRun 带 `circuit_id`+`pipeline`（值是配方名，走回退线路）同样真 id。`{}` 仍失败。不算 G0 |

第六十九波已回收。`test_h01k` 已挂。不算接线。不算 G0。

下一把真刀：人要 H₂ UCCSD 和电路图时不要只剩「批准上机」。无 body 的 `circuit_id` 不许回退 H+CX。

## 第七十波已派（2026-08-27）

人要 H₂ UCCSD 和电路图，产品却写死 2 比特 H+CX 并只给「批准上机」。本波只让 `uccsd_pauli` pin 真线路、3080 画图、去掉回退。**不接线** Pennylane。不要 skip 当绿。不要假 `twin_id`。不算 G0。

| 对话 | 包 | 只许改 | 完成线 |
|------|----|--------|--------|
| [H-01l H₂ UCCSD 电路图](7917b60a-ce25-460d-a226-cf02c813deb8) | H-01l | **完成** · 已挂 `run_tests.py` | `qchem_run uccsd_pauli` pin 4 比特；`GET /api/circuits` 有门列表；无 body 不回退 H+CX。不算 G0 |

第七十波已回收。`test_h01l` 已挂。不算接线。不算 G0。

下一把真刀：拆掉「任何话 → H₂ UCCSD 图」。UCCSD 仍是能力，不是唯一入口。

## 第七十一波已派（2026-08-27）

H-01l 后对话框把 H₂ UCCSD 写成了默认反应。本波只让模型按这句话选公司工具，并让新一轮不再带回上一轮电路图。**不接线** Pennylane。不要 skip 当绿。不要假 `twin_id`。不算 G0。

| 对话 | 包 | 只许改 | 完成线 |
|------|----|--------|--------|
| [H-01m 专用 Agent 不写死](7917b60a-ce25-460d-a226-cf02c813deb8) | H-01m | **完成** · 已挂 `run_tests.py` | `qchem_run` / 欢迎 / lab 技能不再默认 UCCSD；新一轮不带回旧 `circuit_id`。`uccsd_pauli` 能力仍在。不算 G0 |

第七十一波已回收。`test_h01m` 已挂。不算接线。不算 G0。

## 第七十二波已派（2026-08-28）

3080 还是工作台：Markdown 当纯文本、随机句柄堆在脸上、线路不能按产品方式拿走。本波做商业脸：排版、按 `circuit_id` 下载/上传逻辑线路、脸上不念随机码。**不接线** Pennylane。不要 skip 当绿。不要假 `twin_id`。不算 G0。

| 对话 | 包 | 只许改 | 完成线 |
|------|----|--------|--------|
| [C-01w 商业脸](7917b60a-ce25-460d-a226-cf02c813deb8) | C-01w | **完成** · 已挂 `run_tests.py` | 对话 Markdown；`GET .../program` 下载 QASM 不进模型；`POST /api/circuits` 收下客户线路；脸上无人话以外的 `circ_`/`asset_`/`twin_` 随机码。不算 G0 |

第七十二波已回收。`test_c01w` 已挂。不算接线。不算 G0。

下一把真刀：人走完签收（真 `circuit_id` 的 TwinRun 或记全的诚实失败）、或 L1-02 官方 app-server。没有第二把就不要凑包。

## 第七十三波已派（2026-08-28）

C-01w 之后脸上仍像工作台：侧栏堆旧回执、模型报内部名、后到的薄导出换掉已画线路。本波收成「本任务」产品轨。**不接线** Pennylane。不要 skip 当绿。不要假 `twin_id`。不算 G0。

| 对话 | 包 | 只许改 | 完成线 |
|------|----|--------|--------|
| [C-01x 本任务轨](7917b60a-ce25-460d-a226-cf02c813deb8) | C-01x | **完成** · 已挂 `run_tests.py` | 右侧只画本任务一条；HTTP 回复抹句柄/内部名；已画线路不被后到薄 `circuit` 换掉。不算 G0 |

第七十三波已回收。`test_c01x` 已挂。不算接线。不算 G0。

## 第七十四波已派（2026-08-28）

脸还像内部工作台：注入条压在侧栏下面，欢迎页没有入口，没有新对话。本波收成商业仪器风。**不接线** Pennylane。不要 skip 当绿。不要假 `twin_id`。不算 G0。

| 对话 | 包 | 只许改 | 完成线 |
|------|----|--------|--------|
| [C-01y 商业脸](7917b60a-ce25-460d-a226-cf02c813deb8) | C-01y | **完成** · 已挂 `run_tests.py` | 主栏与侧栏分开；欢迎入口不写死 UCCSD；新对话走 reset。不算 G0 |

第七十四波已回收。`test_c01y` 已挂。不算接线。不算 G0。

## 第七十五波已派（2026-08-28）

3080 聊天气泡不渲染公式。本波给 `customer-shell` 加本地 KaTeX。**不接线** Pennylane。不要 skip 当绿。不要假 `twin_id`。不算 G0。

| 对话 | 包 | 只许改 | 完成线 |
|------|----|--------|--------|
| [C-01z KaTeX](7917b60a-ce25-460d-a226-cf02c813deb8) | C-01z | **完成** · 已挂 `run_tests.py` | 本地 vendor KaTeX；`fillRichText` 画 `\(...\)` / `$$...$$`；钉住失败用人话。不算 G0 |

第七十五波已回收。`test_c01z` 已挂。不算接线。不算 G0。

## 第七十六波已派（2026-08-29）

「没连上」吞掉还在办的一轮；脸仍像通用聊天框。本波硬化轮询，并把脸改成离子阱控制台。**不接线** Pennylane。不要 skip 当绿。不要假 `twin_id`。不算 G0。

| 对话 | 包 | 只许改 | 完成线 |
|------|----|--------|--------|
| [C-01aa 控制台](7917b60a-ce25-460d-a226-cf02c813deb8) | C-01aa | **完成** · 已挂 `run_tests.py` | 轮询失败不立刻放弃；在办不提 dsh；控制台式样。不算 G0 |

第七十六波已回收。`test_c01aa` 已挂。不算接线。不算 G0。

复制下面「开工词」到新对话，把 `认领` 换成你的包。

| 包 | 建议谁 | 只许改 | 依赖 |
|----|--------|--------|------|
| M-01 | A1 | 禁止本波 | G3 之后 |

## 开工词（另开对话用）

```text
仓：/Users/shl/nvidia/qagent
先读 docs/qagent_1000d_plan.md、docs/execution/PARALLEL.md、docs/execution/PROGRESS.md。
我认领：<包名>。只改 PARALLEL.md 里这一行的「只许改」。
硬轨：不是重做 Cursor/Codex；脑是 dsh；三句柄；只有 TwinRun 发 twin_id；
qagent/src 不 import 科学核；不扩 agent.py；不训权重；不 commit。
写自己的 tests/test_<包>.py，不要改 tests/run_tests.py 和 PROGRESS.md。
做完写 docs/execution/<包>.md，并跑：
cd /Users/shl/nvidia/qagent && PYTHONPATH=src python3 tests/test_<包>.py
以及 PYTHONPATH=src python3 tests/run_tests.py（必须仍绿）。
```

## 调度回收

各对话交卷后，本对话把新测挂进 `tests/run_tests.py`，更新 `PROGRESS.md`，再派下一波。
