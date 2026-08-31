# G1 演示清单（组内人走，30 分钟，不宣称通过）

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | P · G1-script |
| 范围 | 人对着 3080 脸、3081 上 `dsh --profile qagent` 走「哪些包 → 估计 H₂ → 批准 → Aer 来源」 |
| 状态 | 清单已写。人走。自动测试只核对本页措辞。本页不是过门账。 |

这是组内人走检查清单，不是过门账。Qagent 不是重做 Cursor / Codex。脑是 3081 的 `dsh --profile qagent`，脸是 3080。句柄只有 `circuit_id` / `asset_id` / `twin_id`。只有 ionstack TwinRun 能发 `twin_id`。Aer / IBM / Cirq 的 `provenance` 不许写成 `qccd-twin`。不铸 `twin_id`，不另开第三套 loop，不发明第四个句柄。人还没对着活脸走完之前，G1 仍未过。

上机要问人。未签收不是绿封条。估计出的数、排队、你先不批、诚实失败，都不是绿印。

## 人走步骤（约 30 分钟）

先确认 3081 上 `dsh --profile qagent` 已起，本机打开 3080。没有活 dsh，停在这里，不要编一条 session。密钥只填设置，不贴进对话。

### 1. 「现在有哪些包？」

对人说：现在有哪些包？

期望：走到 `list_engines`（工具名也可是 `qagent_list_engines`）。五包 `qdata` / `qchem` / `ionstack` / `route` / `qiskit` 仍打头且 wired。Cirq 已在 `engines[]`，`kind=interop`，`provenance=cirq`，不是 `qccd-twin`，不许发 `twin_id`。不要把 Cirq 说成我们的机器。不要把 Pennylane 写进 `engines[]`，不要把 Pennylane 说成已接线。

### 2. 「扫 H₂，先估计。」

对人说：扫 H₂，先估计。

期望：先 pin（对话里出现 `circuit_id`），再给出 `makespan_ns`。这一步 Twin 未批，没有活 `twin_id`。`makespan_ns` 不是签收，更不是绿封条。没有资产时：`asset_id` 或诚实本地卡，不要编一个。

### 3. 批准

上机必须先问人（在办里待批）。人还没批，不要走 TwinRun。

- Twin home 活着：批准之后，**只有** ionstack TwinRun 可以出现 `twin_id`。Aer / IBM / 本地卡 / Cirq 都不许手写一个。
- Twin home 不在：必须诚实失败。失败文案要写清**不会伪造**，不要补假 `twin_id`。G1 允许这种诚实失败；不许把失败改口成签收。

本清单不代铸 `twin_id`。没有活 TwinRun，就停在失败，不要本地造一个。

### 4. 「这是不是 Aer 签收的？」

对人说：这是不是 Aer 签收的？

若刚才跑过 Aer：`provenance=aer`，没有同一条 `twin_id`。Aer 不是 ionstack 签收。`provenance=aer` 不是 `qccd-twin`，也不能拿来冒充绿封条。没跑过 Aer：老实说没跑，不要补一条 Aer 回执。

## 当场要看见

- 3080 脸、3081 脑（`dsh --profile qagent`）。
- 「哪些包」→ `list_engines`，五包打头且 wired；Cirq 已在 `engines[]`，`kind=interop`，`provenance=cirq`，不是 `qccd-twin`，不许发 `twin_id`。
- 「扫 H₂，先估计」→ `makespan_ns`，Twin 未批。
- 上机先问人。未签收不是绿封条。
- 有 Twin home：`twin_id` 只来自 TwinRun。无：失败且**不会伪造**。
- 若跑过 Aer：`provenance=aer`，无同一 `twin_id`。

## 当场不要看见

- 假 `twin_id`，或把 Aer / IBM / 本地卡 / Cirq 标成 `qccd-twin`。
- 未批就上机，或把 `makespan_ns` 当成签收。
- 未签收却盖绿封条。
- 把 Cirq 说成我们的机器，或给 Cirq 铸 `twin_id`。
- Pennylane 出现在 `engines[]`，或把 Pennylane 说成已接线。
- 第四个句柄。

## 失败怎么记

当场抄：状态码或连接错误、工具名、当时看见的句柄（`circuit_id` / `asset_id` / `twin_id` 里实际出现的）、有没有 `makespan_ns`、失败里有没有「不会伪造」、Aer 的 `provenance` 是不是 `aer`。缺哪项就写缺。不要补假 `twin_id`，不要把失败改口。

## 不做

- 不铸假 `twin_id`，不假装活 Twin。不把 Cirq 说成我们的机器，不给 Cirq 铸 `twin_id`。不把 Pennylane 说成已接线。
- 不把 `services/agent.py` 当产品循环，不加第三套 loop。
- 不发明第四个句柄。
- 不改 `qagent/src`、customer-shell、`run_tests.py`、`PROGRESS.md`、`chat.py`。
- 不把本清单当成过门。人还没对着 3080 / 3081 走完四步之前，G1 仍未过。不要对外说门禁演完了。
