# C-01n · 在办画估计 ns

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | P · C-01n |
| 范围 | `qagent/apps/customer-shell/app.js` · 本笔记 · `qagent/tests/test_c01n.py` |
| 未改 | `chat.py` · `assignment.py` · `shell_http.py` · `agent.py` · `run_tests.py` · `PROGRESS.md` |
| 状态 | 在办读 `row.makespan_ns` 画「估计 · N ns」。不读 `columns`。对话气泡仍 `send("批准")`。**不算 G0**。**不算 G1**。未 commit。 |

## 产品锁

- G1 先估计：右侧在办待批要看见估计，不是再点开内部 columns。
- 完成线：`faceMakespan(row)` 读脸字段 `makespan_ns`。有值才画 `.inbox-estimate`。不读 `row.columns`。
- 在办「批准上机」仍走 HTTP `assignmentAction`。气泡仍 `send("批准")`。源码不出现字面 `/approve`。
- **不算 G0 / G1**。人还没按组内剧本走完。
- skip 当绿 = 没做完。未 commit。不伪造 `twin_id`。不编 `accepted:true`。

## 2026-08-27 真实脸

3080 组内在办：`asg_aa1c063c7411` 短号 `063c7411`，待批准，画「估计 · 3040 ns」。预检仍是 Twin / 线路 / 资产。无 `twin_id`。

## 不算什么

- **不算 G0**。ready 仍 false。
- **不算 G1**。只画已有估计。
- 未改 `chat.py`。未 commit。`send("批准")` 气泡不动。

## 测

```bash
cd /Users/shl/nvidia/qagent
PYTHONPATH=src python3 tests/test_c01n.py
PYTHONPATH=src python3 tests/test_c01j.py
PYTHONPATH=src python3 tests/test_c01m.py
PYTHONPATH=src python3 tests/run_tests.py
```

在办仍不画估计必须失败。skip 当绿 = 没做完。不 commit。
