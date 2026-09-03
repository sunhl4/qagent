---
name: circuit-job
description: 上传线路后的确定性作业。Pin → 估价 → 人批 → TwinRun 或 Aer。Skill 触发不能绕过 ask。
---

# 线路作业

用户上传 OpenQASM 或已有 `circuit_id` 时走这条轨。默认建议，不是唯一入口。Skill 触发也不能绕过 ask。

1. 线路已经钉住：只用短 `circuit_id`。不要把 QASM 全文塞进对话。
2. `qagent_circuit_job` `action=start`。内部会校验并调用 `ionstack_compile_estimate`，只看 `makespan_ns`。
3. 上我们的机器：停在 ask。人批准后同一交办续跑 `ionstack_twin_run`。没有批准不要跑。
4. 只要对照模拟：`backend=aer`。`provenance=aer`，**没有** `twin_id`。
5. 工具回包没有第三句柄。签收看交办状态和绿封条。

## 不要

- CAL / shuttle / 南向符号
- 把 Aer 写成同一 `twin_id`
- 在官方 Codex `permissionMode: never` 里上机
- 把编译器或演示仓当成一个 algorithm_id
