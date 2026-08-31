# I-01m · workplace PUT 上门

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | P |
| 范围 | `qagent/src/qagent/entrypoints/shell_http.py` · `qagent/tests/test_i01m.py` · `qagent/tests/run_tests.py`（只补 `PUT /api/workplace` 请求头） |
| 状态 | 代码落地，测绿 |

## 产品锁

- `PUT /api/workplace`：无 `QAGENT_SHELL_TOKEN` 或 token 不匹配 → **workplace PUT 无 token 403**，`{"error": "approval requires QAGENT_SHELL_TOKEN"}`（与批准 / eval / reset 门同句）。不写盘、不写 `dsh.env`。
- 有 token：200，形状仍是 `{workplace, ready}`。`GET /api/workplace` 仍开门、不回密钥值。
- `save_workplace()` 服务层直接调用仍无需 token。3080 脸 `saveWorkplace` 已走 `headers()`。
- 不算接线。不宣称 G0/G2。句柄仍只三个：`circuit_id` / `asset_id` / `twin_id`。

## 不做什么

不改 `services/workplace.py` / `apps/customer-shell/**` / `start_ui.sh`。不接线 Pennylane。不加第四句柄。不铸 `twin_id`。不 commit。`PROGRESS.md` / `PARALLEL.md` 留给调度挂。
