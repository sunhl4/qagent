# C-01l · ELN 中文种类

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | P |
| 范围 | `qagent/apps/customer-shell/app.js` · `qagent/tests/test_c01l.py` |
| 状态 | ELN 行种类用中文显示名。不算接线。不算 G2。 |

## 产品锁

- `elnType` 仍解析内部名；`ELN_KIND_MAP` 英文键保持（`qagent/recipe_pin` → `recipe_pin` 等）。
- `elnKindLabel` 显示名：recipe_pin → 配方钉住；estimate → 估计；twin_signoff → 签收；b3 → B3；assignment → 交办；claim_blocked → 未认领。
- `paintEln` 种类走 `elnKindLabel`，不把内部名原文上屏。不画 `twin_id`。
- 不读 `columns` / `ask.args`。没有三房间、Finder、`btn-twin`、`<select`。
- 本包只画画脸，**中文种类**，**不算接线**，**不算 G2**。

## 不做什么

不改 `models/eln.py` / `shell_http.py` / `index.html`。不改 `test_i03e.py` / `test_i03g.py` / `test_c01k.py`。不改 `run_tests.py` / `PROGRESS.md` / `PARALLEL.md`。不接线 Pennylane。不加第三套 agent loop。不 commit。本包**不算接线**、**不算 G2** 过门。

## 测

`qagent/tests/test_c01l.py`：`elnKindLabel` 含上述中文；`paintEln` 不写 `typeEl.textContent = kind`；`ELN_KIND_MAP` 仍有 `qagent/recipe_pin` 等键；无 `twin_id` 上屏；笔记写明不算 G2、中文种类。

```text
PYTHONPATH=src python3 tests/test_c01l.py
PYTHONPATH=src python3 tests/test_i03e.py
PYTHONPATH=src python3 tests/test_c01k.py
```
