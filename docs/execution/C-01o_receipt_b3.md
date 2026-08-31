# C-01o · 回执画 B3，在办/ELN 取尾

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | P · C-01o |
| 范围 | `qagent/apps/customer-shell/app.js` · 本笔记 · `qagent/tests/test_c01o.py` |
| 未改 | `chat.py` · `assignment.py` · `shell_http.py` · `agent.py` · `run_tests.py` · `PROGRESS.md` |
| 状态 | 回执读 `row.b3_verdict` 画「B3 · 尚无定论」。在办/ELN 只画最新 8 行。不读 `columns`。对话气泡仍 `send("批准")`。**不算 G0**。**不算 G1**。未 commit。 |

## 产品锁

- G1 批准后要看见 B3。组内在办不应被几十条待批淹没。ELN 应画最新，不是最旧。
- 完成线：`faceB3Verdict(row)` 读脸字段。有值才画 `.receipt-b3`。在办 `asks.slice(-8)`。ELN `shown.slice(-8)`。
- 不读 `row.columns`。气泡仍 `send("批准")`。源码不出现字面 `/approve`。
- **不算 G0 / G1**。
- skip 当绿 = 没做完。未 commit。不伪造 `twin_id`。不编 `accepted:true`。

## 2026-08-27 真实脸

已签收短号 `b611c8f6` 画「B3 · 尚无定论」。ELN 尾 8 行可见配方钉住 / 估计 / 交办。在办只留最新 8 条待批。

## 不算什么

- **不算 G0**。ready 仍 false。
- **不算 G1**。只画已有 B3。
- 未改 `chat.py`。未 commit。`send("批准")` 气泡不动。

## 测

```bash
cd /Users/shl/nvidia/qagent
PYTHONPATH=src python3 tests/test_c01o.py
PYTHONPATH=src python3 tests/test_c01j.py
PYTHONPATH=src python3 tests/test_c01n.py
PYTHONPATH=src python3 tests/run_tests.py
```

回执仍不画 B3 必须失败。skip 当绿 = 没做完。不 commit。
