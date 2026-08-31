# I-01k · eval HTTP 上门

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | P |
| 范围 | `qagent/src/qagent/entrypoints/shell_http.py` · `qagent/tests/test_i01k.py` |
| 状态 | 代码落地，测绿 |

## 产品锁

- `POST /api/eval`：无 `QAGENT_SHELL_TOKEN` 或 token 不匹配 → **eval 无 token 403**，`{"error": "approval requires QAGENT_SHELL_TOKEN"}`（与批准门同句）。有 token 才跑 eval。
- 成功响应只回 `passed` 与 `results` 的 `id` / `ok`。**不回 detail**。无 body / qasm / 密钥。eval HTTP 不回句柄。
- `_chat_http_face` 再剥 `used_tools`。`POST /api/chat` 与 `GET /api/chat/status` 仍无 `session_id`。内部 `turn()` 仍可有 `used_tools`；`run_evals()` 仍全文。
- 不算接线。不宣称 G0/G2。句柄仍只三个：`circuit_id` / `asset_id` / `twin_id`。

## 不做什么

不改 `services/eval_run.py` / `services/chat.py` / `product_eval.py` / `apps/customer-shell/**` / `run_tests.py`。不接线 Pennylane。不加第四句柄。不铸 `twin_id`。不 commit。`PROGRESS.md` / `PARALLEL.md` 留给调度挂。
