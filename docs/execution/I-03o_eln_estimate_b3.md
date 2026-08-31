# I-03o · ELN 脸画估计与 B3

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | P · I-03o |
| 范围 | `qagent/apps/customer-shell/app.js` · `app.css` · 本笔记 · `qagent/tests/test_i03o.py` |
| 未改 | `eln.py` · `invoke.py` · `chat.py` · `agent.py` · `run_tests.py` · `PROGRESS.md` |
| 状态 | ELN 行读 `makespan_ns` / `verdict` 画「估计 · N ns」「B3 · 尚无定论」。不读 `twin_id` / `columns`。**不算 G0/G1**。未 commit。 |

## 产品锁

- I-03n 已把估计/B3 挂到交办。GET `/api/eln` 尾上已有 `makespan_ns=3040`、`verdict=inconclusive`。脸原先只画种类和短号。
- 完成线：`elnMakespan` / `elnB3Verdict`。`eln-estimate` / `eln-b3`。不画 `twin_id`。不读 `columns` / 电路 body。
- 气泡仍 `send("批准")`。
- **不算 G0 / G1**。没有填模型。skip 当绿 = 没做完。未 commit。

## 不算什么

- **不算 G0**。ready 仍 false。
- 未假 `twin_id`。未 commit。

## 测

```bash
cd /Users/shl/nvidia/qagent
PYTHONPATH=src python3 tests/test_i03o.py
PYTHONPATH=src python3 tests/test_i03g.py
PYTHONPATH=src python3 tests/test_i03e.py
PYTHONPATH=src python3 tests/run_tests.py
```

ELN 画 `twin_id` 或读 `columns` 必须失败。skip 当绿 = 没做完。不 commit。
