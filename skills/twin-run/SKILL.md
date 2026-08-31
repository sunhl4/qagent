---
name: twin-run
description: 交 TwinRun。默认建议，不是唯一入口。Skill 触发不能绕过 ask。仅 lab/sign。
---

# 交 TwinRun

默认建议，不是唯一入口。只交 `mode` / `shots` / `circuit.body`。不交 CAL、shuttle、MS。Skill 触发也不能绕过 ask。

## 怎么交

1. 先 `ionstack_compile_estimate`，只看 `makespan_ns`。没有签收 `ok`。
2. `ionstack_twin_run`。lab / sign 默认 **ask**，问过人才执行。
3. 响应里的 `twin_id` 只有 ionstack 能发。记下 shots_actual。
4. 不要把 CAL 或电路全文塞进对话。

## 失败

| 情况 | 预期 |
|------|------|
| algo preset | deny |
| shots ≥ 4096 | 仍是 ask，先问人 |
| Aer / IBM 声称同一 twin | deny；Aer 输出 `provenance=aer`，无 `twin_id` |
| 沙箱 `execute_twin_run` | `ok=false`，不发 REST |

<!-- S-SKILL-03 -->
