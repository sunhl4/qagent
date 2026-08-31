# I-01f · 交办 GET 瘦身

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | P |
| 范围 | `qagent/src/qagent/models/assignment.py` · `qagent/src/qagent/entrypoints/shell_http.py` · `qagent/tests/test_i01f.py` |
| 状态 | 代码落地，测绿 |

## 产品锁

- `GET /api/assignments` 与 `GET /api/assignments/{id}`（无 action）回 `face_payload()`，不回 `to_dict()`。
- 脸键只有：`assignment_id`、`status`、`ask_tool`；可选 `ask: {"tool": ...}`（不要 `args`）；`handles` 只从已有行抄 `circuit_id` / `asset_id` / `twin_id`（有才抄）。
- 不回 `columns`、`brief`、`recipe`、`ask.args`、`identity`、`counts`、circuit body、密钥键。
- 回执仍 `receipt()`，预检仍 `preflight()`（不回显 identity），`POST` run / approve / cancel / fork 仍 `to_dict()`。
- 句柄仍只三个。不铸 `twin_id`。租户 list 隔离仍走 `X-QAGENT-TENANT`。

## 不做什么

不改 `services/assignment.py` / `apps/customer-shell/**` / `test_c02.py` / `test_i01e.py` / `run_tests.py`。不接线 Pennylane。不加第四句柄。不宣称 G0/G2 通过。不 commit。`PROGRESS.md` / `PARALLEL.md` 留给调度挂。
