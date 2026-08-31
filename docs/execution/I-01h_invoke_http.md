# I-01h · invoke/vibe HTTP 瘦身

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | P |
| 范围 | `qagent/src/qagent/entrypoints/shell_http.py` · `qagent/tests/test_i01h.py` |
| 状态 | 代码落地，测绿 |

## 产品锁

- `POST /api/invoke` 成功响应只留 `tool` / `decision` / `status`；可选 `slot_id`。不回 payload/steps。`needs_ask` 不带 args。不把 `twin_id` 当作 invoke HTTP 字段打出（内部 TwinRun 成功也不打）。
- `POST /api/vibe` 成功响应只留 `status` / `tool` / `summary`；`handles` 只三句柄（`circuit_id` / `asset_id` / `twin_id`）。不要 `steps`，不要 `aer_leaked_twin_id` / `makespan_ns` / `b3` / `aer_provenance`。无 circuit body。
- `approved=true` 无 token 仍 403，error 形状不变。
- 内部 `invoke()` 与 `run_vibe_path()` 仍全文，给 assignment 黄金路径用。`GET /api/assignments` 仍 face。
- 不算接线。不宣称 G0/G2。

## 不做什么

不改 `services/vibe_path.py` / `services/invoke.py` / `services/assignment.py` / `models/**` / `apps/customer-shell/**` / `run_tests.py`。不接线 Pennylane。不加第四句柄。不铸 `twin_id`。不 commit。`PROGRESS.md` / `PARALLEL.md` 留给调度挂。
