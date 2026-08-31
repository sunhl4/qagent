# H-01j · 产品「批准」活 allowed-once

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | A1 |
| 范围 | 活 3080 `send("批准")` 同一条 session |
| 状态 | 完成。`approval/decided` `outcome=allowed-once`。TwinRun 空参诚实失败 `S-TWIN-02`。无假 `twin_id`。不算 G0 过门。 |

## 缺口

H-01i 后 session `e5dcc262` 停在 `ionstack_twin_run` 待批，脸已有 mux `rpc_id`。此前活 `accepted:true` 未证明。本包只走产品气泡同一条「批准」，回显已有 `rpc_id`。不铸 `rpcId`，不铸 `twin_id`。

## 完成线

- 3080 `POST /api/chat` `{"message":"批准"}` + token。同一条 session `session-e5dcc262-d9f6-492b-a0c8-c65321f2a42c`。
- 历史：`approval/asked` id `bc41e0fd-43b1-4ca5-bae3-ae416e7fa587` → `approval/decided` `outcome=allowed-once`。脸回「同一条 session，outcome 是 allowed-once。」
- 随后 `ionstack_twin_run` 参数是 `{}`，回 `Error: ionstack_twin_run: error S-TWIN-02`。没有签收，没有假 `twin_id`。
- 不编未经 dsh 回的 `accepted:true`。不算 G0。
