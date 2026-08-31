---
name: h2-uccsd
description: 仅当人明确点名氢分子 UCCSD 时用。默认建议，不是唯一入口。不要先 TwinRun。lab/sign。Skill 触发也不能绕过 ask。
---

# H₂ UCCSD 电路

默认建议，不是唯一入口。只有人明确点名氢分子 / H₂ UCCSD 才走这条。只说「电路图」或其它分子，不要用这个 skill。Skill 触发也不能绕过 ask。

1. `qchem_run`，`scenario=uccsd_pauli`。回 `asset_id` 和 `circuit_id`。
2. 把 `circuit_id` 留给脸画图。不要把 Pauli / QASM 全文塞进对话。不要在对话里画 2 比特 H+CX 示意图。
3. 不要把配方名 `a2_chem_pes` 当成 `circuit_id`。
4. 上机另一步：有了真 `circuit_id` 才 `ionstack_twin_run`，且必须问人。

不要改化学核。不要假 `twin_id`。
