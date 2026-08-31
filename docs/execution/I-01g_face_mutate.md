# I-01g · 交办 POST 瘦身

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | P |
| 范围 | `qagent/src/qagent/entrypoints/shell_http.py` · `qagent/tests/test_i01g.py` · `qagent/tests/test_i01f.py`（cancel 断言） |
| 状态 | 代码落地，测绿 |

## 产品锁

- `POST /api/assignments`（create）与 `POST /{id}/run` · `approve` · `reject` · `cancel` · `fork` 成功响应回 `face_payload()`，不回 `to_dict()`。
- 不回 `columns`、`brief`、`recipe`、`ask.args`、`identity`、`counts`、circuit body、密钥键。
- `GET /api/assignments` 与 `GET /{id}` 仍 `face_payload()`。
- 回执仍 `receipt()`，预检仍 `preflight()`。403 / 404 error 形状不变。
- `approve` / `run`（`approved=true`）仍走 `approved_allowed` token 门。
- 句柄仍只三个。不铸 `twin_id`。脸无租户号；C-02 用 GET 证隔离。

## 不做什么

不改 `models/assignment.py` / `services/assignment.py` / `apps/customer-shell/**` / `test_c02.py` / `test_i01e.py` / `run_tests.py`。不接线 Pennylane。不加第四句柄。不宣称 G0/G2 通过。不 commit。`PROGRESS.md` / `PARALLEL.md` 留给调度挂。
