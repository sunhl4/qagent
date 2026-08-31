# I-03p · ELN 脸画实打发数

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | P · I-03p |
| 范围 | `qagent/apps/customer-shell/app.js` · `app.css` · 本笔记 · `qagent/tests/test_i03p.py` |
| 未改 | `eln.py` · `invoke.py` · `chat.py` · `agent.py` · `run_tests.py` · `PROGRESS.md` |
| 状态 | ELN 签收行读 `shots_actual` 画「实打 · N 发」。不读 `twin_id` / `columns`。**不算 G0/G1**。未 commit。 |

## 产品锁

- I-03o 已画估计 / B3。GET `/api/eln` 签收行已有 `shots_actual=8`，脸原先不画。
- 完成线：`elnShots`。`eln-shots`。「实打 · N 发」。不画 `twin_id`。不读 `columns` / 电路 body。不画内部 recipe 名。
- 气泡仍 `send("批准")`。
- **不算 G0 / G1**。没有填模型。skip 当绿 = 没做完。未 commit。

## 不算什么

- **不算 G0**。ready 仍 false。
- 未假 `twin_id`。未 commit。

## 测

```bash
cd /Users/shl/nvidia/qagent
PYTHONPATH=src python3 tests/test_i03p.py
PYTHONPATH=src python3 tests/test_i03o.py
PYTHONPATH=src python3 tests/test_i03g.py
PYTHONPATH=src python3 tests/test_i03e.py
PYTHONPATH=src python3 tests/run_tests.py
```

ELN 画 `twin_id` 或读 `columns` 必须失败。skip 当绿 = 没做完。不 commit。
