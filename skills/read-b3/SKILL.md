---
name: read-b3
description: 读 B3 verdict。默认建议，不是唯一入口。Skill 触发也不能绕过 ask。可以不上机。
---

# 读 B3

默认建议，不是唯一入口。Skill 触发也不能绕过 ask。可以不上机只要 B3。调用 `qdata_dequant_gate`。只报告 `b3.verdict` 字段，三个值：

`quantum_wins` · `classical_wins` · `inconclusive`

## 规则

- 未过不得写 `quantum_wins`。
- `force_verdict=quantum_wins` 一律 deny，并记 `qagent/claim_blocked`。
- 小网格、经典对照能赢时报告 `classical_wins`，不要改口。
- 工具还没接线时不要编 verdict。
