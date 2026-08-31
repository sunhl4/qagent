# C-01i · 3080 预检只画 checks

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | P |
| 范围 | `qagent/apps/customer-shell/*` · `qagent/tests/test_c01i.py` |
| 状态 | 代码落地，文本测绿。不算接线。不算 G2。不回显 identity。 |

## 产品锁

- 预检行只读 `GET …/preflight` 的布尔 `checks`：`twin_live` / `has_circuit` / `has_asset`。`paintPreflight` / `loadPreflight` 不读 `data.identity`，**不回显 identity**。
- 行用 `textContent`。bits：Twin 通/不通、有/无线路、有/无资产。
- 保持 C-01h：设置 `#reserved-list` 画 `status.reserved_engines`；欢迎 `.packs` **只**扫 `status.engines`。欢迎不出现 pennylane / reserved_engines。
- 批准仍走 `send("批准")` / `send("先不批")`。不 `POST …/approve`。
- 保持 C-01g 行模板 `label · kind · status`。保持 I-03e：`GET /api/eln` 只读。保持 C-02d：`?tenant=` → `X-QAGENT-TENANT`。保持 `#secret-fieldset`。
- 句柄仍只有 `circuit_id` / `asset_id` / `twin_id`。没有三房间、Finder、`btn-twin`、`<select`。
- I-01e 会从 HTTP 去掉 `identity`。本包只画画脸，**不算接线**，**不算 G2**。

## 不做什么

不改 `qagent/src/**`、`assignment.py`、`company.py`。不改 `test_c01h.py` / `test_c01g.py`。不改 `run_tests.py` / `PROGRESS.md` / `PARALLEL.md`。不接线 Pennylane。不加第三套 agent loop。不 commit。本包**不算接线**、**不算 G2** 过门，**不回显 identity**。

## 测

`qagent/tests/test_c01i.py`：`paintPreflight` 画 `has_asset` / `twin_live` / `has_circuit`；JS 无 `data.identity`；C-01h reserved / 欢迎只扫 engines；批准仍走 `send("批准")`；笔记写明不算 G2、不回显 identity。

```text
PYTHONPATH=src python3 tests/test_c01i.py
PYTHONPATH=src python3 tests/test_c01h.py
PYTHONPATH=src python3 tests/test_c01g.py
PYTHONPATH=src python3 tests/test_i01c.py
```
