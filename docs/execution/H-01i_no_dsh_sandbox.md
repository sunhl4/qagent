# H-01i · 产品 dsh 不注册 sandbox

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | A1 |
| 范围 | `packages/qagent-qdata/src/index.ts` |
| 状态 | 完成。活 session `e5dcc262` 无 `qdata_sandbox_exec` 调用。已 `qagent_pin_circuit` + `ionstack_twin_run` `approval/asked`。E11 仍走 `invoke()`。不算 G0 过门。 |

## 缺口

H-01h 后「扫氢分子」能跑 `qdata_run_recipe(a2_chem_pes)`。模型接着点 `qdata_sandbox_exec` 几十次猜参数，不走 `qagent_pin_circuit` / 估计 / TwinRun ask。不改政策表，不改 E11。

## 完成线

- `qagent-qdata` 的 `apply()` 不再 `registerInvokeTool(..., "qdata_sandbox_exec")`。
- `qdata_get_job` / `qdata_get_run_record` 带合同必填字段，不再让模型猜 `code` / `asset_id`。
- `invoke("qdata_sandbox_exec", "lab", ...)` 仍通。E11 仍是否定南向。
- 活复验：3080 发「扫氢分子」，session `session-e5dcc262-d9f6-492b-a0c8-c65321f2a42c`。`tool/call` 里没有 `qdata_sandbox_exec`。有 `qagent_pin_circuit`（`asset_73dd61eb693e`）和 `ionstack_twin_run`。脸 `awaiting=approve`，`pending_approval.rpc_id=92f6ee98-1558-4792-87af-4ac69bec6de6`。未代批，未编 `accepted:true`。
- 不假 `twin_id`。不算 G0。
