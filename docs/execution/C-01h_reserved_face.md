# C-01h · 3080 设置另画 reserved

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | P |
| 范围 | `qagent/apps/customer-shell/*` · `qagent/tests/test_c01h.py` |
| 状态 | 代码落地，文本测绿。不算接线。不算 G2。 |

## 产品锁

- 设置「已接软件」`#engine-list` **只**画 `status.engines`。旁边另列 `#reserved-list`（未接线 / reserved），读 `status.reserved_engines || []`。没有该键就空列表。
- 两列都用 C-01g 行模板 `label · kind · status`，`textContent` 写行，不要 `innerHTML` 拼包名。
- 欢迎 `.packs` **继续只**扫 `status.engines`。欢迎不读 reserved，不出现 pennylane。
- reserved 不是已接、不是 wired。本包只画画脸，**不算接线**，**不算 G2**。
- 句柄仍只有 `circuit_id` / `asset_id` / `twin_id`。不编造第四句柄。HTML 正文不写 `assignment_id`。
- 不做模型墙。没有三房间、Finder、`btn-twin`、`<select`。
- 保持 C-01g / C-01e：未就绪 `showModal`；`?role=customer` 仍藏 `#secret-fieldset`。
- 保持 I-03e：`GET /api/eln` 只读、无 POST。
- 保持 C-02d：`?tenant=` → `X-QAGENT-TENANT`；空租户不带头。

## 不做什么

不改 `qagent/src/**`、`workplace.py`、`catalog.py`、`INTERFACES.md`、`catalog.json`。不改 `run_tests.py` / `PROGRESS.md` / `PARALLEL.md`。不接线 Pennylane。不加第三套 agent loop。不编造 `twin_id`。不 commit。欢迎和 `#engine-list` 不画 reserved。本包**不算接线**、**不算 G2** 过门。

## 测

`qagent/tests/test_c01h.py`：设置有 `#reserved-list`；`fillSettings` 用 `textContent` 画 `reserved_engines`；`paintWelcome` 仍只吃 `status.engines`；C-01g 行模板仍在；eln / tenant / secret-fieldset 句子仍在；不宣称过门。

```text
PYTHONPATH=src python3 tests/test_c01h.py
PYTHONPATH=src python3 tests/test_c01g.py
PYTHONPATH=src python3 tests/test_c01e.py
```
