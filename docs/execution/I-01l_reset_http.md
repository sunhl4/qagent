# I-01l · reset HTTP 上门

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | P |
| 范围 | `qagent/src/qagent/entrypoints/shell_http.py` · `qagent/tests/test_i01l.py` · `qagent/tests/test_c02f.py`（只改 HTTP reset 请求头） |
| 状态 | 代码落地，测绿 |

## 产品锁

- `POST /api/agent/reset`：无 `QAGENT_SHELL_TOKEN` 或 token 不匹配 → **reset 无 token 403**，`{"error": "approval requires QAGENT_SHELL_TOKEN"}`（与批准 / eval 门同句）。不调用清 session。
- 有 token：200 `{"ok": true}`，只清调用方租户。空租户仍只清 staff，保持 C-02f。
- `reset_chat()` 服务层直接调用仍无需 token。3080 脸不用这条。
- 不算接线。不宣称 G0/G2。句柄仍只三个：`circuit_id` / `asset_id` / `twin_id`。

## 不做什么

不改 `services/chat.py` / `services/agent.py` / `apps/customer-shell/**` / `run_tests.py`。不接线 Pennylane。不加第四句柄。不铸 `twin_id`。不 commit。`PROGRESS.md` / `PARALLEL.md` 留给调度挂。
