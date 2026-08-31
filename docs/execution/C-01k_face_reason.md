# C-01k · 3080 脸吃 reason

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | P |
| 范围 | `qagent/apps/customer-shell/app.js` · `qagent/tests/test_c01k.py` |
| 状态 | 脸字吃 reason，文本测绿。不算接线。不算 G2。 |

## 产品锁

- `faceLabel(status, reason)` 映射：signed → 已签收；`reason=cancelled` → 已取消；`reason=rejected` 或 `status=rejected` → 已拒绝；`reason=failed` 或 `status=failed` → 失败；needs_ask → 待批准；running → 还在跑；其他 → 未签收。
- inbox 状态字走 `faceLabel`，不把 `row.status` 原文上屏。回执 `paintFaceRow` 同样吃 `row.reason`。
- 过滤仍 `row.status === "needs_ask"`；fetch 仍 `status=needs_ask`。批准仍 `send("批准")`。
- 不读 `columns` / `ask.args` / brief / recipe。没有三房间、Finder、`btn-twin`、`<select`。
- 本包只画画脸，**吃 reason**，**不算接线**，**不算 G2**。

## 不做什么

不改 `models/assignment.py` / `shell_http.py` / `index.html`。不改 `test_c01j.py` / `test_c01i.py` / `test_c01h.py`。不改 `run_tests.py` / `PROGRESS.md` / `PARALLEL.md`。不接线 Pennylane。不加第三套 agent loop。不 commit。本包**不算接线**、**不算 G2** 过门。

## 测

`qagent/tests/test_c01k.py`：`faceLabel` 含 已取消 / 已拒绝 / 失败 / 待批准；inbox 不把 `row.status` 赋给 `statusEl.textContent`；仍有 `status=needs_ask`；无 `row.columns` / `ask.args`；笔记写明不算 G2、吃 reason。

```text
PYTHONPATH=src python3 tests/test_c01k.py
PYTHONPATH=src python3 tests/test_c01j.py
PYTHONPATH=src python3 tests/test_c01i.py
```
