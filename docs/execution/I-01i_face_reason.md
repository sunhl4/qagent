# I-01i · 脸短 reason

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | P |
| 范围 | `qagent/src/qagent/models/assignment.py`（只动 `face_payload()`）· `qagent/tests/test_i01i.py` |
| 状态 | 代码落地，测绿 |

## 产品锁

- `face_payload()` 在 `status` 为 rejected / failed 时带短 `reason`，字面量只许 `cancelled` / `rejected` / `failed`。
- 盘上 cancel 写 `error="cancelled"`，脸映射 `reason="cancelled"`。reject（非 cancelled）→ `reason="rejected"`。failed → `reason="failed"`。
- 其他状态不要 `reason`。脸永不回 `error` 键，不回 error 原文（Twin 失败长句不进 reason）。
- 仍无 `columns` / `brief` / `recipe` / `ask.args` / `identity`。脸无租户号。句柄仍只三个：`circuit_id`、`asset_id`、`twin_id`。
- failed 未用 HTTP 造：服务层 `run(approved=True)` 落 failed 后 GET 验脸。不算接线。

## 不做什么

不改 `entrypoints/shell_http.py` / `services/assignment.py` / `apps/customer-shell/**` / `test_i01f.py` / `test_i01g.py` / `test_c02.py` / `run_tests.py`。不接线 Pennylane。不加第四句柄。不宣称 G0/G2 通过。不 commit。`PROGRESS.md` / `PARALLEL.md` 留给调度挂。
