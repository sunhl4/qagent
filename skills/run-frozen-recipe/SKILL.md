---
name: run-frozen-recipe
description: 跑冻结 recipe。默认建议，不是唯一入口。Skill 触发也不能绕过 ask。不要在这里喊 TwinRun。
---

# 跑冻结 recipe

默认建议，不是唯一入口。Skill 触发也不能绕过 ask。允许先 docs、跳过 Aer、只估计不上机。只调用 `qdata_run_recipe`。`name` 必须在 allowlist：

`a1_closed_loop` · `a2_spin_shadow` · `a2_chem_pes` · `a3_sensitivity` · `qem_triad`

## 怎么跑

1. `qagent_list_engines` 确认 `qdata` 在目录里。
2. `qdata_run_recipe`，只传 `name` 和可选 `shots`。
3. 对话里只留 `asset_id` / `summary`。不要把 Pauli、bitstrings、counts 全文读进上下文。
4. 问「量子赢了吗」时改走 `read-b3`。不要在这里喊 TwinRun。

## 失败

| 情况 | 预期 |
|------|------|
| 配方名不在 allowlist | deny |
| shots ≥ 4096 | ask，先问人 |
| 端口错误 | 读 `error`，不要假装跑过 |
