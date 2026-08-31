# C-01j · 3080 脸不读 columns

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | P |
| 范围 | `qagent/apps/customer-shell/*` · `qagent/tests/test_c01j.py` |
| 状态 | 脸切片已锁，文本测绿。不算接线。不算 G2。不读 columns。 |

## 产品锁

- 在办 / 回执脸只读交办字段：`assignment_id`、`status`、`ask_tool` 或 `ask.tool`、`handles.twin_id`（`signed` 才画 twin）。`paintInbox` / `paintFaceRow` / `askTool` / `signedTwinId` / `refreshInbox` **不读 columns**，不读 `ask.args` / `row.brief` / `row.recipe` / `row.identity`。
- 不开始画 recipe、brief、columns、circuit。I-01f 会把 `GET /api/assignments` 瘦成脸字段；本包只锁 3080 脸。
- 保持 C-01i：`paintPreflight` 三项 checks（`twin_live` / `has_circuit` / `has_asset`），不读 `data.identity`。
- 保持 C-01h：设置 `#reserved-list` 画 `status.reserved_engines`；欢迎只扫 `status.engines`。
- 批准仍走 `send("批准")` / `send("先不批")`。保持 I-03e：`GET /api/eln` 只读。保持 C-02d：`?tenant=` → `X-QAGENT-TENANT`。保持 `#secret-fieldset`。
- 句柄仍只有 `circuit_id` / `asset_id` / `twin_id`。没有三房间、Finder、`btn-twin`、`<select`。
- 本包只画画脸，**不算接线**，**不算 G2**。

## 不做什么

不改 `qagent/src/**`。不改 `test_c01i.py` / `test_c01h.py`。不改 `run_tests.py` / `PROGRESS.md` / `PARALLEL.md`。不接线 Pennylane。不加第三套 agent loop。不 commit。本包**不算接线**、**不算 G2** 过门，**不读 columns**。

## 测

`qagent/tests/test_c01j.py`：inbox / face 切片无 `columns` / `ask.args` / `.brief` / `.recipe`；仍有 `askTool` / `assignment_id` / `status` / `handles`；C-01i 预检 `has_asset`；C-01h `#reserved-list`；`send("批准")` 仍在；笔记写明不算 G2、不读 columns。

```text
PYTHONPATH=src python3 tests/test_c01j.py
PYTHONPATH=src python3 tests/test_c01i.py
PYTHONPATH=src python3 tests/test_c01h.py
PYTHONPATH=src python3 tests/test_i01c.py
```
